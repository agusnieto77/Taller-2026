from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.constants import DATASET_ACTIVE, ROUND_ONE, ROUND_TWO, ROUND_TWO_DEFINITION
from app.models import AnnotationRound, Dataset, Note, User

_SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"
_NOTES_PATH = _SEED_DIR / "notes.json"
_USERS_PATH = _SEED_DIR / "users.json"
_DEMO_DATASET_NAME = "Notas demo"
_PASSWORD_HASHER = PasswordHash.recommended()


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
    if len(users) != 4:
        raise ValueError("Seed users fixture must contain exactly 4 users")
    return users


def _seeded_usernames(users: list[dict[str, Any]]) -> set[str]:
    usernames: set[str] = set()
    for user in users:
        usernames.add(str(user["username"]))
    return usernames


def _seed_write_scope(db: Session):
    return db.begin_nested() if db.in_transaction() else db.begin()


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


def _ensure_demo_notes(db: Session, dataset_id: int, notes: list[dict[str, Any]]) -> None:
    existing_notes = {
        note.external_id: note
        for note in db.scalars(select(Note).where(Note.dataset_id == dataset_id)).all()
    }

    for position, note in enumerate(notes, start=1):
        external_id = str(note["id"])
        title = str(note["titulo"])
        text = str(note["texto"])
        published_at = _parse_optional_date(note.get("fecha"))
        outlet = note.get("medio")
        url = note.get("url")
        section = note.get("seccion")
        metadata_json = note.get("metadata")
        existing_note = existing_notes.get(external_id)

        if existing_note is None:
            db.add(
                Note(
                    dataset_id=dataset_id,
                    external_id=external_id,
                    position=position,
                    title=title,
                    text=text,
                    published_at=published_at,
                    outlet=str(outlet) if outlet is not None else None,
                    url=str(url) if url is not None else None,
                    section=str(section) if section is not None else None,
                    metadata_json=metadata_json,
                )
            )
            continue

        if existing_note.title != title:
            existing_note.title = title
        if existing_note.text != text:
            existing_note.text = text
        if existing_note.published_at != published_at:
            existing_note.published_at = published_at
        if existing_note.outlet != (str(outlet) if outlet is not None else None):
            existing_note.outlet = str(outlet) if outlet is not None else None
        if existing_note.url != (str(url) if url is not None else None):
            existing_note.url = str(url) if url is not None else None
        if existing_note.section != (str(section) if section is not None else None):
            existing_note.section = str(section) if section is not None else None
        if existing_note.metadata_json != metadata_json:
            existing_note.metadata_json = metadata_json


def _ensure_demo_users(db: Session, users: list[dict[str, Any]], seeded_usernames: set[str]) -> None:
    existing_users = {
        user.username: user
        for user in db.scalars(
            select(User).where(User.username.in_(sorted(seeded_usernames)))
        ).all()
    }

    for user in users:
        username = str(user["username"])
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


def seed_demo_data(db: Session, settings: Settings) -> None:
    if not settings.seed_demo_data:
        return

    with _seed_write_scope(db):
        active_demo_dataset = db.scalar(
            select(Dataset)
            .where(Dataset.status == DATASET_ACTIVE, Dataset.name == _DEMO_DATASET_NAME)
            .order_by(Dataset.id)
            .limit(1)
        )
        if active_demo_dataset is None:
            if db.scalar(select(Dataset.id).where(Dataset.status == DATASET_ACTIVE).limit(1)) is not None:
                return
            dataset = Dataset(name=_DEMO_DATASET_NAME, status=DATASET_ACTIVE)
            db.add(dataset)
            db.flush()
        else:
            dataset = active_demo_dataset

        notes = _load_seed_notes()
        users = _load_seed_users()
        seeded_usernames = _seeded_usernames(users)

        _ensure_demo_rounds(db, dataset.id)
        _ensure_demo_notes(db, dataset.id, notes)
        _ensure_demo_users(db, users, seeded_usernames)
