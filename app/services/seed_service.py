from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.constants import (
    ADMIN_ROLE,
    ANNOTATOR_ROLE,
    DATASET_ACTIVE,
    ROUND_ONE,
    ROUND_TWO,
    ROUND_TWO_DEFINITION,
)
from app.models import AnnotationRound, Dataset, Note, User

_SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"
_NOTES_PATH = _SEED_DIR / "notes.json"
_USERS_PATH = _SEED_DIR / "users.json"
_PASSWORD_HASHER = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def _load_json_array(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data


def _load_seed_notes() -> list[dict[str, Any]]:
    notes = _load_json_array(_NOTES_PATH)
    if len(notes) != 10:
        raise ValueError("seed notes fixture must contain exactly ten records")
    return notes


def _load_seed_users() -> list[dict[str, Any]]:
    users = _load_json_array(_USERS_PATH)
    if len(users) != 4:
        raise ValueError("seed users fixture must contain exactly four records")
    return users


def _seeded_usernames(users: list[dict[str, Any]]) -> set[str]:
    usernames: set[str] = set()
    for user in users:
        username = str(user.get("username", "")).strip()
        if not username:
            raise ValueError("seed user usernames must be non-empty")
        usernames.add(username)
    return usernames


def seed_demo_data(db: Session, settings: Settings) -> None:
    if not settings.seed_demo_data:
        return

    notes = _load_seed_notes()
    users = _load_seed_users()
    seeded_usernames = _seeded_usernames(users)

    active_dataset = db.scalar(select(Dataset).where(Dataset.status == DATASET_ACTIVE).limit(1))
    existing_usernames = set(
        db.scalars(
            select(User.username).where(User.username.in_(sorted(seeded_usernames)))
        ).all()
    )
    if active_dataset is not None and existing_usernames == seeded_usernames:
        return

    db.rollback()

    dataset = Dataset(name="Notas demo", status=DATASET_ACTIVE)
    db.add(dataset)
    db.flush()

    round_one = AnnotationRound(
        dataset_id=dataset.id,
        round_number=ROUND_ONE,
        name="Ronda 1",
        definition_text=None,
        definition_visible=False,
    )
    round_two = AnnotationRound(
        dataset_id=dataset.id,
        round_number=ROUND_TWO,
        name="Ronda 2",
        definition_text=ROUND_TWO_DEFINITION,
        definition_visible=True,
    )
    db.add_all([round_one, round_two])
    db.flush()

    db.add_all(
        [
            Note(
                dataset_id=dataset.id,
                external_id=str(note["id"]),
                position=index,
                title=str(note["titulo"]),
                text=str(note["texto"]),
                published_at=date.fromisoformat(str(note["fecha"])),
                outlet=str(note["medio"]),
                url=str(note["url"]),
                section=str(note["seccion"]),
                metadata_json=note.get("metadata"),
            )
            for index, note in enumerate(notes, start=1)
        ]
    )

    db.add_all(
        [
            User(
                username=str(user["username"]),
                display_name=str(user.get("display_name", user["username"])),
                password_hash=hash_password(str(user["password"])),
                role=str(user["role"]),
                active=bool(user.get("active", True)),
            )
            for user in users
        ]
    )

    db.commit()
