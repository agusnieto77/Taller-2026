from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text as sa_text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import ADMIN_ROLE, ANNOTATOR_ROLE, DATASET_ACTIVE, DATASET_ARCHIVED, ROUND_ONE, ROUND_TWO
from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("trim(username) <> ''", name="ck_users_username_nonempty"),
        CheckConstraint(f"role IN ('{ANNOTATOR_ROLE}', '{ADMIN_ROLE}')", name="ck_users_role_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=sa_text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))

    annotations: Mapped[list[Annotation]] = relationship(back_populates="user")
    progress_entries: Mapped[list[Progress]] = relationship(back_populates="user")


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(f"status IN ('{DATASET_ACTIVE}', '{DATASET_ARCHIVED}')", name="ck_datasets_status_valid"),
        Index(
            "uq_datasets_single_active",
            "status",
            unique=True,
            sqlite_where=sa_text("status = 'active'"),
            postgresql_where=sa_text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[list[Note]] = relationship(back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True)
    annotation_rounds: Mapped[list[AnnotationRound]] = relationship(back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True)
    progress_entries: Mapped[list[Progress]] = relationship(back_populates="dataset")


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        UniqueConstraint("dataset_id", "external_id", name="uq_notes_dataset_external_id"),
        UniqueConstraint("dataset_id", "position", name="uq_notes_dataset_position"),
        Index("ix_notes_active_lookup", "dataset_id", "deleted_at", "position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    outlet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))

    dataset: Mapped[Dataset] = relationship(back_populates="notes")
    annotations: Mapped[list[Annotation]] = relationship(back_populates="note")


class AnnotationRound(Base):
    __tablename__ = "annotation_rounds"
    __table_args__ = (
        CheckConstraint(f"round_number IN ({ROUND_ONE}, {ROUND_TWO})", name="ck_annotation_rounds_round_number_valid"),
        UniqueConstraint("dataset_id", "round_number", name="uq_annotation_rounds_dataset_round_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    definition_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_text("0"))

    dataset: Mapped[Dataset] = relationship(back_populates="annotation_rounds")
    annotations: Mapped[list[Annotation]] = relationship(back_populates="round")
    progress_entries: Mapped[list[Progress]] = relationship(back_populates="round")


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (UniqueConstraint("user_id", "round_id", "note_id", name="uq_annotations_user_round_note"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    round_id: Mapped[int] = mapped_column(ForeignKey("annotation_rounds.id"), nullable=False)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id"), nullable=False)
    value: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))

    user: Mapped[User] = relationship(back_populates="annotations")
    round: Mapped[AnnotationRound] = relationship(back_populates="annotations")
    note: Mapped[Note] = relationship(back_populates="annotations")


class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (UniqueConstraint("user_id", "round_id", name="uq_progress_user_round"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    round_id: Mapped[int] = mapped_column(ForeignKey("annotation_rounds.id"), nullable=False)
    last_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=sa_text("0"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))

    user: Mapped[User] = relationship(back_populates="progress_entries")
    dataset: Mapped[Dataset] = relationship(back_populates="progress_entries")
    round: Mapped[AnnotationRound] = relationship(back_populates="progress_entries")
