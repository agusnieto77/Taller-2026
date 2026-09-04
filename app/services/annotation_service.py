from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants import ROUND_ONE, ROUND_TWO
from app.models import Annotation, AnnotationRound, Dataset, Note, Progress


class AnnotationError(Exception):
    pass


class RoundLockedError(AnnotationError):
    pass


class RoundNotAvailableError(AnnotationError):
    pass


class NoteUnavailableError(AnnotationError):
    pass


@dataclass(frozen=True)
class RoundStatus:
    round_number: int
    name: str
    total_count: int
    answered_count: int
    completed: bool
    locked: bool
    can_start: bool
    definition_text: str | None = None

    @property
    def remaining_count(self) -> int:
        return max(0, self.total_count - self.answered_count)


@dataclass(frozen=True)
class SaveResult:
    annotation: Annotation
    answered_count: int
    total_count: int
    completed: bool
    next_note: Note | None


def get_active_dataset(db: Session) -> Dataset | None:
    return db.scalar(select(Dataset).where(Dataset.status == "active").order_by(Dataset.id.desc()).limit(1))


def get_active_notes(db: Session, dataset_id: int) -> list[Note]:
    return list(db.scalars(select(Note).where(Note.dataset_id == dataset_id, Note.deleted_at.is_(None)).order_by(Note.position, Note.id)).all())


def get_round(db: Session, dataset_id: int, round_number: int) -> AnnotationRound | None:
    return db.scalar(select(AnnotationRound).where(AnnotationRound.dataset_id == dataset_id, AnnotationRound.round_number == round_number))


def _progress(db: Session, user_id: int, round_id: int) -> Progress | None:
    return db.scalar(select(Progress).where(Progress.user_id == user_id, Progress.round_id == round_id))


def get_round_status(db: Session, user_id: int, round_number: int) -> RoundStatus:
    dataset = get_active_dataset(db)
    if dataset is None:
        raise RoundNotAvailableError("No hay un conjunto activo")
    round_ = get_round(db, dataset.id, round_number)
    if round_ is None:
        raise RoundNotAvailableError("Ronda inexistente")
    total = db.scalar(select(func.count(Note.id)).where(Note.dataset_id == dataset.id, Note.deleted_at.is_(None))) or 0
    answered = db.scalar(select(func.count(Annotation.id)).join(Note, Annotation.note_id == Note.id).where(Annotation.user_id == user_id, Annotation.round_id == round_.id, Note.dataset_id == dataset.id, Note.deleted_at.is_(None))) or 0
    progress = _progress(db, user_id, round_.id)
    completed = bool(progress and progress.completed_at is not None and answered == total)
    round_one_complete = True
    if round_number == ROUND_TWO:
        first = get_round(db, dataset.id, ROUND_ONE)
        first_progress = _progress(db, user_id, first.id) if first else None
        first_answered = db.scalar(select(func.count(Annotation.id)).join(Note, Annotation.note_id == Note.id).where(Annotation.user_id == user_id, Annotation.round_id == (first.id if first else -1), Note.dataset_id == dataset.id, Note.deleted_at.is_(None))) or 0
        round_one_complete = bool(first and first_progress and first_progress.completed_at is not None and first_answered == total)
    return RoundStatus(round_number, round_.name, total, answered, completed, round_number == ROUND_ONE and completed, round_one_complete, round_.definition_text if round_.definition_visible else None)


def get_first_pending_note(db: Session, user_id: int, round_number: int) -> Note | None:
    dataset = get_active_dataset(db)
    if dataset is None:
        return None
    round_ = get_round(db, dataset.id, round_number)
    if round_ is None:
        return None
    return db.scalar(select(Note).where(Note.dataset_id == dataset.id, Note.deleted_at.is_(None), ~select(Annotation.note_id).where(Annotation.user_id == user_id, Annotation.round_id == round_.id, Annotation.note_id == Note.id).exists()).order_by(Note.position, Note.id).limit(1))


def get_note_for_round(db: Session, user_id: int, round_number: int, note_id: int) -> tuple[Note, Annotation | None, RoundStatus]:
    dataset = get_active_dataset(db)
    if dataset is None:
        raise NoteUnavailableError("No hay un conjunto activo")
    round_ = get_round(db, dataset.id, round_number)
    if round_ is None:
        raise NoteUnavailableError("Ronda inexistente")
    note = db.scalar(select(Note).where(Note.id == note_id, Note.dataset_id == dataset.id, Note.deleted_at.is_(None)))
    if note is None:
        raise NoteUnavailableError("Nota no disponible")
    status = get_round_status(db, user_id, round_number)
    if not status.can_start:
        raise RoundNotAvailableError("La ronda todavía no está habilitada")
    annotation = db.scalar(select(Annotation).where(Annotation.user_id == user_id, Annotation.round_id == round_.id, Annotation.note_id == note_id))
    first_pending = get_first_pending_note(db, user_id, round_number)
    if annotation is None and first_pending is not None and first_pending.id != note_id:
        raise NoteUnavailableError("Debe continuar por la primera nota pendiente")
    if annotation is None and first_pending is None:
        raise NoteUnavailableError("La ronda ya está completa")
    return note, annotation, status


def save_annotation(db: Session, user_id: int, round_number: int, note_id: int, value: bool) -> SaveResult:
    if type(value) is not bool:
        raise ValueError("La clasificación debe ser booleana")
    try:
        dataset = get_active_dataset(db)
        if dataset is None:
            raise NoteUnavailableError("No hay un conjunto activo")
        round_ = get_round(db, dataset.id, round_number)
        note = db.scalar(select(Note).where(Note.id == note_id, Note.dataset_id == dataset.id, Note.deleted_at.is_(None)))
        if round_ is None or note is None:
            raise NoteUnavailableError("Nota o ronda no disponible")
        status = get_round_status(db, user_id, round_number)
        if not status.can_start:
            raise RoundNotAvailableError("La ronda todavía no está habilitada")
        if round_number == ROUND_ONE and status.locked:
            raise RoundLockedError("La ronda 1 ya está cerrada")
        annotation = db.scalar(select(Annotation).where(Annotation.user_id == user_id, Annotation.round_id == round_.id, Annotation.note_id == note_id))
        if annotation is None:
            annotation = Annotation(user_id=user_id, round_id=round_.id, note_id=note_id, value=value)
            db.add(annotation)
        else:
            annotation.value = value
            annotation.updated_at = datetime.now(timezone.utc)
        progress = _progress(db, user_id, round_.id)
        if progress is None:
            progress = Progress(user_id=user_id, dataset_id=dataset.id, round_id=round_.id, last_position=note.position)
            db.add(progress)
        else:
            progress.last_position = max(progress.last_position, note.position)
            progress.updated_at = datetime.now(timezone.utc)
        db.flush()
        answered = db.scalar(select(func.count(Annotation.id)).join(Note, Annotation.note_id == Note.id).where(Annotation.user_id == user_id, Annotation.round_id == round_.id, Note.dataset_id == dataset.id, Note.deleted_at.is_(None))) or 0
        total = status.total_count
        completed = answered == total and total > 0
        if completed and progress.completed_at is None:
            progress.completed_at = datetime.now(timezone.utc)
        db.commit()
        next_note = get_first_pending_note(db, user_id, round_number)
        return SaveResult(annotation, answered, total, completed, next_note)
    except Exception:
        db.rollback()
        raise
