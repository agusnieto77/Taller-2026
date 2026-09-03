from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants import ADMIN_ROLE, ANNOTATOR_ROLE, DATASET_ACTIVE, ROUND_ONE, ROUND_TWO
from app.database import Base, get_db
from app.main import app
from app.models import AnnotationRound, Dataset, Note, User
from app.services.seed_service import hash_password


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db() -> Iterator[Session]:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_db(db: Session) -> Session:
    dataset = Dataset(id=1, name="Fixture demo", status=DATASET_ACTIVE)
    round_one = AnnotationRound(
        id=1,
        dataset_id=1,
        round_number=ROUND_ONE,
        name="Ronda 1",
        definition_text=None,
        definition_visible=False,
    )
    round_two = AnnotationRound(
        id=2,
        dataset_id=1,
        round_number=ROUND_TWO,
        name="Ronda 2",
        definition_text="Definición visible",
        definition_visible=True,
    )
    users = [
        User(
            id=1,
            username="ana",
            display_name="Ana López",
            password_hash=hash_password("local-only-ana-2026"),
            role=ANNOTATOR_ROLE,
            active=True,
        ),
        User(
            id=2,
            username="bruno",
            display_name="Bruno Pérez",
            password_hash=hash_password("local-only-bruno-2026"),
            role=ANNOTATOR_ROLE,
            active=True,
        ),
        User(
            id=3,
            username="carla",
            display_name="Carla Gómez",
            password_hash=hash_password("local-only-carla-2026"),
            role=ANNOTATOR_ROLE,
            active=True,
        ),
        User(
            id=4,
            username="admin",
            display_name="Admin Demo",
            password_hash=hash_password("local-only-admin-2026"),
            role=ADMIN_ROLE,
            active=True,
        ),
    ]
    notes = [
        Note(
            id=1,
            dataset_id=1,
            external_id="nota-01",
            position=1,
            title="Titular 1",
            text="Texto 1",
            published_at=None,
            outlet="Fixture",
            url="https://example.invalid/fixture/01",
            section="Política",
            metadata_json={"source": "fixture"},
        ),
        Note(
            id=2,
            dataset_id=1,
            external_id="nota-02",
            position=2,
            title="Titular 2",
            text="Texto 2",
            published_at=None,
            outlet="Fixture",
            url="https://example.invalid/fixture/02",
            section="Sociedad",
            metadata_json={"source": "fixture"},
        ),
        Note(
            id=3,
            dataset_id=1,
            external_id="nota-03",
            position=3,
            title="Titular 3",
            text="Texto 3",
            published_at=None,
            outlet="Fixture",
            url="https://example.invalid/fixture/03",
            section="Ciudad",
            metadata_json={"source": "fixture"},
        ),
    ]

    db.add(dataset)
    db.add_all([round_one, round_two])
    db.add_all(users)
    db.add_all(notes)
    db.commit()
    return db
