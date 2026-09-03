from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.constants import ADMIN_ROLE, ANNOTATOR_ROLE, DATASET_ACTIVE, ROUND_ONE, ROUND_TWO, ROUND_TWO_DEFINITION
from app.database import Base
from app.models import AnnotationRound, Dataset, Note, User
from app.services.seed_service import hash_password, seed_demo_data


@pytest.fixture
def memory_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_seed_demo_data_creates_expected_rows(memory_session: Session) -> None:
    seed_demo_data(memory_session, get_settings())

    dataset = memory_session.scalar(select(Dataset))
    assert dataset is not None
    assert dataset.name == "Notas demo"
    assert dataset.status == DATASET_ACTIVE

    rounds = memory_session.scalars(select(AnnotationRound).order_by(AnnotationRound.round_number)).all()
    assert [round_.round_number for round_ in rounds] == [ROUND_ONE, ROUND_TWO]
    assert rounds[0].definition_text is None
    assert rounds[0].definition_visible is False
    assert rounds[1].definition_text == ROUND_TWO_DEFINITION
    assert rounds[1].definition_visible is True

    notes = memory_session.scalars(select(Note).order_by(Note.position)).all()
    assert len(notes) == 10
    assert [note.position for note in notes] == list(range(1, 11))
    assert [note.external_id for note in notes] == [f"nota-{index:02d}" for index in range(1, 11)]

    users = memory_session.scalars(select(User).order_by(User.id)).all()
    assert [user.username for user in users] == ["ana", "bruno", "carla", "admin"]
    assert {user.role for user in users} == {ANNOTATOR_ROLE, ADMIN_ROLE}
    assert all(user.password_hash != "" for user in users)
    assert all(not user.password_hash.startswith("local-only-") for user in users)


def test_seed_demo_data_is_idempotent(memory_session: Session) -> None:
    seed_demo_data(memory_session, get_settings())
    counts_before = {
        "datasets": memory_session.query(Dataset).count(),
        "rounds": memory_session.query(AnnotationRound).count(),
        "notes": memory_session.query(Note).count(),
        "users": memory_session.query(User).count(),
    }

    seed_demo_data(memory_session, get_settings())
    counts_after = {
        "datasets": memory_session.query(Dataset).count(),
        "rounds": memory_session.query(AnnotationRound).count(),
        "notes": memory_session.query(Note).count(),
        "users": memory_session.query(User).count(),
    }

    assert counts_before == {"datasets": 1, "rounds": 2, "notes": 10, "users": 4}
    assert counts_after == counts_before


def test_seeded_fixture_uses_stable_ids(seeded_db: Session) -> None:
    assert seeded_db.query(Dataset).count() == 1
    assert seeded_db.query(AnnotationRound).count() == 2
    assert seeded_db.query(Note).count() == 3
    assert seeded_db.query(User).count() == 4

    assert [note.id for note in seeded_db.scalars(select(Note).order_by(Note.id)).all()] == [1, 2, 3]
    assert [user.id for user in seeded_db.scalars(select(User).where(User.username != "admin").order_by(User.id)).all()] == [1, 2, 3]


def test_hash_password_returns_argon2_hash() -> None:
    hashed = hash_password("local-only-test-2026")
    assert hashed.startswith("$argon2")
    assert "local-only-test-2026" not in hashed
