from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import DATASET_ACTIVE, DATASET_ARCHIVED, ROUND_ONE, ROUND_TWO, ROUND_TWO_DEFINITION
from app.models import AnnotationRound, Dataset, Note
from app.services.import_service import NotePayload


def replace_active_dataset(db: Session, name: str, notes: Sequence[NotePayload]) -> Dataset:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("El nombre del conjunto es obligatorio")
    if not notes:
        raise ValueError("El conjunto debe contener al menos una nota")
    active = db.scalar(select(Dataset).where(Dataset.status == DATASET_ACTIVE).order_by(Dataset.id.desc()).limit(1))
    if active is not None:
        active.status = DATASET_ARCHIVED
        active.archived_at = datetime.now(timezone.utc)
        db.flush()
    dataset = Dataset(name=clean_name, status=DATASET_ACTIVE)
    db.add(dataset)
    db.flush()
    db.add_all([
        AnnotationRound(dataset_id=dataset.id, round_number=ROUND_ONE, name="Ronda 1", definition_text=None, definition_visible=False),
        AnnotationRound(dataset_id=dataset.id, round_number=ROUND_TWO, name="Ronda 2", definition_text=ROUND_TWO_DEFINITION, definition_visible=True),
    ])
    db.add_all([Note(dataset_id=dataset.id, external_id=item.external_id, position=item.position, title=item.title, text=item.text, published_at=item.published_at, outlet=item.outlet, url=item.url, section=item.section, metadata_json=item.metadata_json) for item in notes])
    db.flush()
    return dataset
