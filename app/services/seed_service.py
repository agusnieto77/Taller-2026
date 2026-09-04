from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.config import Settings
from app.constants import ADMIN_ROLE, ANNOTATOR_ROLE, DATASET_ACTIVE, ROUND_ONE, ROUND_TWO, ROUND_TWO_DEFINITION
from app.models import AnnotationRound, Dataset, Note, User

_SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"
_NOTES_PATH = _SEED_DIR / "notes.json"
_USERS_PATH = _SEED_DIR / "users.json"
_DEMO_DATASET_NAME = "Notas demo"
_PASSWORD_HASHER = PasswordHash.recommended()
_SQLITE_SEED_RETRIES = 3
_SQLITE_RETRYABLE_ERROR_MARKERS = (
    "database is locked",
    "database table is locked",
    "database schema is locked",
    "unique constraint failed",
)


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def _load_json_array(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def _load_seed_notes() -> list[dict[str, Any]]:
    notes = _load_json_array(_NOTES_PATH)
    if len(notes) != 10:
        raise ValueError("Seed notes fixture must contain exactly 10 notes")
    return notes


def _load_seed_users() -> list[dict[str, Any]]:
    users = _load_json_array(_USERS_PATH)
    roles = [str(user.get("role", "")) for user in users]
    if roles.count(ANNOTATOR_ROLE) != 20 or roles.count(ADMIN_ROLE) != 1:
        raise ValueError("Seed users fixture must contain 20 annotators and 1 admin")
    return users


def _seeded_usernames(users: list[dict[str, Any]]) -> set[str]:
    usernames: set[str] = set()
    for user in users:
        raw_username = user.get("username")
        if raw_username is None:
            raise ValueError("Seed user username is required")
        username = str(raw_username).strip()
        if not username:
            raise ValueError("Seed user username cannot be blank")
        if username in usernames:
            raise ValueError(f"Duplicate seed username: {username}")
        usernames.add(username)
    return usernames


def _parse_optional_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    return date.fromisoformat(str(value))


def _ensure_demo_rounds(db: Session, dataset_id: int) -> None:
    desired_rounds = [
        {
            "round_number": ROUND_ONE,
            "name": "Ronda 1",
            "definition_text": None,
            "definition_visible": False,
        },
        {
            "round_number": ROUND_TWO,
            "name": "Ronda 2",
            "definition_text": ROUND_TWO_DEFINITION,
            "definition_visible": True,
        },
    ]
    existing_rounds = {
        round_.round_number: round_
        for round_ in db.scalars(select(AnnotationRound).where(AnnotationRound.dataset_id == dataset_id)).all()
    }

    for round_data in desired_rounds:
        round_ = existing_rounds.get(round_data["round_number"])
        if round_ is None:
            db.add(
                AnnotationRound(
                    dataset_id=dataset_id,
                    round_number=round_data["round_number"],
                    name=round_data["name"],
                    definition_text=round_data["definition_text"],
                    definition_visible=round_data["definition_visible"],
                )
            )
            continue

        if round_.name != round_data["name"]:
            round_.name = round_data["name"]
        if round_.definition_text != round_data["definition_text"]:
            round_.definition_text = round_data["definition_text"]
        if round_.definition_visible != round_data["definition_visible"]:
            round_.definition_visible = round_data["definition_visible"]


def _note_matches_seed(note: Note, note_data: tuple[int, str, str, str, date | None, str | None, str | None, str | None, Any]) -> bool:
    position, _external_id, title, text, published_at, outlet, url, section, metadata_json = note_data
    return (
        note.position == position
        and note.title == title
        and note.text == text
        and note.published_at == published_at
        and note.outlet == outlet
        and note.url == url
        and note.section == section
        and note.metadata_json == metadata_json
    )


def _ensure_demo_notes(db: Session, dataset_id: int, notes: list[dict[str, Any]]) -> None:
    existing_notes = list(db.scalars(select(Note).where(Note.dataset_id == dataset_id)).all())
    seed_external_ids = {str(note["id"]) for note in notes}
    desired_notes: list[tuple[int, str, str, str, date | None, str | None, str | None, str | None, Any]] = []

    for position, note in enumerate(notes, start=1):
        external_id = str(note["id"])
        title = str(note["titulo"])
        text = str(note["texto"])
        published_at = _parse_optional_date(note.get("fecha"))
        outlet = note.get("medio")
        url = note.get("url")
        section = note.get("seccion")
        metadata_json = note.get("metadata")
        desired_notes.append(
            (
                position,
                external_id,
                title,
                text,
                published_at,
                str(outlet) if outlet is not None else None,
                str(url) if url is not None else None,
                str(section) if section is not None else None,
                metadata_json,
            )
        )

    existing_seed_notes = {note.external_id: note for note in existing_notes if note.external_id in seed_external_ids}
    preserved_extras = [note for note in existing_notes if note.external_id not in seed_external_ids]

    canonical = True
    for note_data in desired_notes:
        existing_note = existing_seed_notes.get(note_data[1])
        if existing_note is None or not _note_matches_seed(existing_note, note_data):
            canonical = False
            break

    if canonical:
        expected_position = len(desired_notes) + 1
        for extra in sorted(preserved_extras, key=lambda note: (note.position, note.id)):
            if extra.position != expected_position:
                canonical = False
                break
            expected_position += 1

    if canonical:
        return

    if existing_notes:
        temporary_position_base = max(abs(note.position) for note in existing_notes) + len(existing_notes) + 1
        for temporary_position, note in enumerate(
            sorted(existing_notes, key=lambda current: (current.position, current.id))
        ):
            note.position = temporary_position_base + temporary_position
        db.flush()

    extras = sorted(preserved_extras, key=lambda note: (note.position, note.id))

    for position, external_id, title, text, published_at, outlet, url, section, metadata_json in desired_notes:
        existing_note = existing_seed_notes.get(external_id)
        if existing_note is None:
            db.add(
                Note(
                    dataset_id=dataset_id,
                    external_id=external_id,
                    position=position,
                    title=title,
                    text=text,
                    published_at=published_at,
                    outlet=outlet,
                    url=url,
                    section=section,
                    metadata_json=metadata_json,
                )
            )
            continue

        existing_note.position = position
        if existing_note.title != title:
            existing_note.title = title
        if existing_note.text != text:
            existing_note.text = text
        if existing_note.published_at != published_at:
            existing_note.published_at = published_at
        if existing_note.outlet != outlet:
            existing_note.outlet = outlet
        if existing_note.url != url:
            existing_note.url = url
        if existing_note.section != section:
            existing_note.section = section
        if existing_note.metadata_json != metadata_json:
            existing_note.metadata_json = metadata_json

    for position, note in enumerate(extras, start=len(desired_notes) + 1):
        note.position = position


def _ensure_demo_users(db: Session, users: list[dict[str, Any]], seeded_usernames: set[str]) -> None:
    existing_users = {
        user.username: user
        for user in db.scalars(select(User).where(User.username.in_(sorted(seeded_usernames)))).all()
    }

    for user in users:
        raw_username = user.get("username")
        if raw_username is None:
            raise ValueError("Seed user username is required")
        username = str(raw_username).strip()
        if not username:
            raise ValueError("Seed user username cannot be blank")

        display_name = str(user.get("display_name", username))
        role = str(user["role"])
        active = bool(user.get("active", True))
        existing_user = existing_users.get(username)

        if existing_user is None:
            db.add(
                User(
                    username=username,
                    display_name=display_name,
                    password_hash=hash_password(str(user["password"])),
                    role=role,
                    active=active,
                )
            )
            continue

        if existing_user.display_name != display_name:
            existing_user.display_name = display_name
        if existing_user.role != role:
            existing_user.role = role
        if existing_user.active != active:
            existing_user.active = active


def _get_active_demo_dataset(db: Session) -> Dataset | None:
    return db.scalar(
        select(Dataset)
        .where(Dataset.status == DATASET_ACTIVE, Dataset.name == _DEMO_DATASET_NAME)
        .order_by(Dataset.id)
        .limit(1)
    )


def _get_any_active_dataset(db: Session) -> Dataset | None:
    return db.scalar(select(Dataset).where(Dataset.status == DATASET_ACTIVE).order_by(Dataset.id).limit(1))


def _ensure_demo_dataset(db: Session) -> Dataset | None:
    active_demo_dataset = _get_active_demo_dataset(db)
    if active_demo_dataset is not None:
        return active_demo_dataset
    if _get_any_active_dataset(db) is not None:
        return None

    try:
        with db.begin_nested():
            dataset = Dataset(name=_DEMO_DATASET_NAME, status=DATASET_ACTIVE)
            db.add(dataset)
            db.flush()
            return dataset
    except IntegrityError:
        active_demo_dataset = _get_active_demo_dataset(db)
        if active_demo_dataset is not None:
            return active_demo_dataset
        if _get_any_active_dataset(db) is not None:
            return None
        raise


def _is_retryable_sqlite_error(exc: Exception) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return any(marker in message for marker in _SQLITE_RETRYABLE_ERROR_MARKERS)


def _seed_demo_data_body(db: Session) -> None:
    dataset = _ensure_demo_dataset(db)
    if dataset is None:
        return

    notes = _load_seed_notes()
    users = _load_seed_users()
    seeded_usernames = _seeded_usernames(users)

    _ensure_demo_rounds(db, dataset.id)
    _ensure_demo_notes(db, dataset.id, notes)
    _ensure_demo_users(db, users, seeded_usernames)


def _seed_demo_data_with_retries(db: Session) -> None:
    for attempt in range(_SQLITE_SEED_RETRIES):
        try:
            with db.begin():
                _seed_demo_data_body(db)
            return
        except (IntegrityError, OperationalError) as exc:
            if db.get_bind().dialect.name != "sqlite" or not _is_retryable_sqlite_error(exc):
                raise
            if attempt + 1 >= _SQLITE_SEED_RETRIES:
                raise
            db.expire_all()


def seed_demo_data(db: Session, settings: Settings) -> None:
    if not settings.seed_demo_data:
        return

    if db.in_transaction():
        with db.begin_nested():
            _seed_demo_data_body(db)
        return

    _seed_demo_data_with_retries(db)
