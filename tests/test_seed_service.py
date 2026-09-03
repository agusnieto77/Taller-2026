from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import MetaData, Table, create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.constants import ADMIN_ROLE, ANNOTATOR_ROLE, DATASET_ACTIVE, DATASET_ARCHIVED, ROUND_ONE, ROUND_TWO, ROUND_TWO_DEFINITION
from app.database import Base
from app.models import AnnotationRound, Dataset, Note, User
from app.services import seed_service
from app.services.seed_service import hash_password, seed_demo_data


@pytest.fixture
def memory_session() -> Iterator[Session]:
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


def test_initial_migration_and_model_metadata_enforce_unique_usernames_and_single_active_dataset(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "alembic.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo_root,
        env=env,
        check=True,
    )

    assert User.__table__.columns["username"].unique is True
    active_dataset_index = next(index for index in Dataset.__table__.indexes if index.name == "uq_datasets_single_active")
    assert active_dataset_index.unique is True
    assert active_dataset_index.dialect_options["sqlite"]["where"] is not None
    assert active_dataset_index.dialect_options["postgresql"]["where"] is not None

    engine = create_engine(db_url)
    users = Table("users", MetaData(), autoload_with=engine)
    datasets = Table("datasets", MetaData(), autoload_with=engine)

    with engine.begin() as conn:
        conn.execute(
            users.insert(),
            {
                "username": "duplicate",
                "display_name": "Duplicate One",
                "password_hash": "hash-1",
                "role": ANNOTATOR_ROLE,
            },
        )
        with pytest.raises(IntegrityError):
            conn.execute(
                users.insert(),
                {
                    "username": "duplicate",
                    "display_name": "Duplicate Two",
                    "password_hash": "hash-2",
                    "role": ANNOTATOR_ROLE,
                },
            )

        index_sql = conn.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='uq_datasets_single_active'"
        ).scalar_one()
        assert "WHERE status = 'active'" in index_sql

        conn.execute(
            datasets.insert(),
            {
                "name": "Active one",
                "status": DATASET_ACTIVE,
            },
        )
        conn.execute(
            datasets.insert(),
            {
                "name": "Archived one",
                "status": DATASET_ARCHIVED,
            },
        )
        with pytest.raises(IntegrityError):
            conn.execute(
                datasets.insert(),
                {
                    "name": "Active two",
                    "status": DATASET_ACTIVE,
                },
            )


def test_alembic_env_imports_models_before_assigning_metadata() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = textwrap.dedent(
        f"""
        import importlib.util
        import sys
        import types
        from contextlib import nullcontext
        from pathlib import Path

        repo_root = Path(r"{repo_root.as_posix()}")
        sys.path.insert(0, str(repo_root))
        fake_context = types.ModuleType("alembic.context")
        fake_context.config = types.SimpleNamespace(
            get_main_option=lambda name: "sqlite://",
            set_main_option=lambda name, value: None,
            config_ini_section="alembic",
        )
        fake_context.is_offline_mode = lambda: True
        fake_context.configure = lambda **kwargs: None
        fake_context.begin_transaction = lambda: nullcontext()
        fake_context.run_migrations = lambda: None

        fake_alembic = types.ModuleType("alembic")
        fake_alembic.context = fake_context
        fake_alembic.__path__ = []

        sys.modules["alembic"] = fake_alembic
        sys.modules["alembic.context"] = fake_context

        spec = importlib.util.spec_from_file_location("alembic.env", repo_root / "alembic" / "env.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        from app.database import Base

        print(",".join(sorted(Base.metadata.tables)))
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip().split(",") == ["annotation_rounds", "annotations", "datasets", "notes", "progress", "users"]


def test_seeded_usernames_trim_and_validate() -> None:
    assert seed_service._seeded_usernames(
        [
            {"username": " ana "},
            {"username": "bruno"},
        ]
    ) == {"ana", "bruno"}

    with pytest.raises(ValueError, match="username is required"):
        seed_service._seeded_usernames([{"display_name": "Ana"}])

    with pytest.raises(ValueError, match="cannot be blank"):
        seed_service._seeded_usernames([{"username": "   "}])

    with pytest.raises(ValueError, match="Duplicate seed username"):
        seed_service._seeded_usernames(
            [
                {"username": " ana "},
                {"username": "ana"},
            ]
        )


def test_seed_demo_data_repairs_existing_demo_dataset(memory_session: Session) -> None:
    dataset = Dataset(id=1, name="Notas demo", status=DATASET_ACTIVE)
    round_one = AnnotationRound(
        id=1,
        dataset_id=1,
        round_number=ROUND_ONE,
        name="Ronda 1",
        definition_text=None,
        definition_visible=False,
    )
    existing_user = User(
        id=1,
        username="ana",
        display_name="Ana López",
        password_hash=hash_password("local-only-ana-2026"),
        role=ANNOTATOR_ROLE,
        active=True,
    )
    deleted_at = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    stale_note = Note(
        id=1,
        dataset_id=1,
        external_id="nota-01",
        position=7,
        title="Titular 1",
        text="Texto 1",
        published_at=None,
        outlet="Fixture",
        url="https://example.invalid/fixture/01",
        section="Política",
        metadata_json={"source": "fixture"},
    )
    deleted_note = Note(
        id=2,
        dataset_id=1,
        external_id="nota-02",
        position=1,
        title="Titular 2",
        text="Texto 2",
        published_at=None,
        outlet="Fixture",
        url="https://example.invalid/fixture/02",
        section="Sociedad",
        metadata_json={"source": "fixture"},
        deleted_at=deleted_at,
    )

    memory_session.add_all([dataset, round_one, existing_user, stale_note, deleted_note])
    memory_session.commit()

    seed_demo_data(memory_session, get_settings())

    demo_dataset = memory_session.scalar(select(Dataset).where(Dataset.name == "Notas demo"))
    assert demo_dataset is not None
    assert demo_dataset.id == 1
    assert memory_session.query(Dataset).count() == 1
    assert memory_session.query(AnnotationRound).count() == 2
    assert memory_session.query(Note).count() == 10
    assert memory_session.query(User).count() == 4

    rounds = memory_session.scalars(select(AnnotationRound).order_by(AnnotationRound.round_number)).all()
    assert [round_.round_number for round_ in rounds] == [ROUND_ONE, ROUND_TWO]
    assert rounds[1].definition_text == ROUND_TWO_DEFINITION
    assert rounds[1].definition_visible is True

    notes = memory_session.scalars(select(Note).order_by(Note.position)).all()
    assert [note.position for note in notes] == list(range(1, 11))
    assert [note.external_id for note in notes] == [f"nota-{index:02d}" for index in range(1, 11)]
    assert memory_session.scalar(select(Note).where(Note.external_id == "nota-02")).deleted_at == deleted_at
    assert {user.role for user in memory_session.scalars(select(User)).all()} == {ANNOTATOR_ROLE, ADMIN_ROLE}


def test_seed_demo_data_commits_after_read_only_autobegin_transaction(memory_session: Session) -> None:
    memory_session.execute(select(Dataset.id)).all()
    assert memory_session.in_transaction()

    seed_demo_data(memory_session, get_settings())

    assert not memory_session.in_transaction()
    assert memory_session.query(Dataset).count() == 1
    assert memory_session.query(AnnotationRound).count() == 2
    assert memory_session.query(Note).count() == 10
    assert memory_session.query(User).count() == 4


def test_seed_demo_data_leaves_unrelated_active_dataset_untouched(memory_session: Session) -> None:
    dataset = Dataset(id=1, name="Otra investigación", status=DATASET_ACTIVE)
    memory_session.add(dataset)
    memory_session.commit()

    seed_demo_data(memory_session, get_settings())

    untouched_dataset = memory_session.scalar(select(Dataset))
    assert untouched_dataset is not None
    assert untouched_dataset.name == "Otra investigación"
    assert memory_session.query(Dataset).count() == 1
    assert memory_session.query(AnnotationRound).count() == 0
    assert memory_session.query(Note).count() == 0
    assert memory_session.query(User).count() == 0


def test_seed_demo_data_preserves_caller_pending_changes_and_rolls_back_seed_writes(memory_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    caller_dataset = Dataset(id=1, name="Caller dataset", status=DATASET_ARCHIVED)
    memory_session.add(caller_dataset)

    def failing_ensure_demo_users(db: Session, users, seeded_usernames) -> None:
        raise RuntimeError("seed write failed")

    monkeypatch.setattr(seed_service, "_ensure_demo_users", failing_ensure_demo_users)

    with pytest.raises(RuntimeError, match="seed write failed"):
        seed_demo_data(memory_session, get_settings())
    memory_session.flush()
    assert memory_session.scalar(select(Dataset).where(Dataset.name == "Caller dataset")) is not None
    assert memory_session.scalar(select(Dataset).where(Dataset.name == "Notas demo")) is None
    assert memory_session.query(AnnotationRound).count() == 0
    assert memory_session.query(Note).count() == 0
    assert memory_session.query(User).count() == 0


def test_seed_demo_data_uses_normalized_usernames(memory_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    users = [dict(user) for user in seed_service._load_seed_users()]
    users[0]["username"] = " ana "
    users[1]["username"] = "\nbruno\t"
    monkeypatch.setattr(seed_service, "_load_seed_users", lambda: users)

    seed_demo_data(memory_session, get_settings())

    assert sorted(user.username for user in memory_session.scalars(select(User).order_by(User.username)).all()) == [
        "admin",
        "ana",
        "bruno",
        "carla",
    ]


def test_seed_demo_data_allows_missing_fecha(memory_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    notes = [dict(note) for note in seed_service._load_seed_notes()]
    notes[0]["fecha"] = None
    monkeypatch.setattr(seed_service, "_load_seed_notes", lambda: notes)

    seed_demo_data(memory_session, get_settings())

    first_note = memory_session.scalar(select(Note).where(Note.external_id == "nota-01"))
    assert first_note is not None
    assert first_note.published_at is None
    assert memory_session.query(Note).count() == 10


def test_seeded_fixture_uses_stable_ids(seeded_db: Session) -> None:
    assert seeded_db.query(Dataset).count() == 1
    assert seeded_db.query(AnnotationRound).count() == 2
    assert seeded_db.query(Note).count() == 3
    assert seeded_db.query(User).count() == 4

    assert [note.id for note in seeded_db.scalars(select(Note).order_by(Note.id)).all()] == [1, 2, 3]
    users = seeded_db.scalars(select(User).where(User.username != "admin").order_by(User.id)).all()
    assert [user.id for user in users] == [1, 2, 3]

    round_two = seeded_db.scalar(select(AnnotationRound).where(AnnotationRound.round_number == ROUND_TWO))
    assert round_two is not None
    assert round_two.definition_text == ROUND_TWO_DEFINITION


def test_hash_password_returns_argon2_hash() -> None:
    hashed = hash_password("local-only-test-2026")
    assert hashed.startswith("$argon2")
    assert "local-only-test-2026" not in hashed
