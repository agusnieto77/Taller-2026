"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-09-03 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("trim(username) <> ''", name="ck_users_username_nonempty"),
        sa.CheckConstraint(
            "role IN ('annotator', 'admin')",
            name="ck_users_role_valid",
        ),
    )

    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_datasets_status_valid",
        ),
    )
    op.create_index(
        "uq_datasets_single_active",
        "datasets",
        ["status"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.Integer(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("outlet", sa.String(length=255), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("section", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("dataset_id", "external_id", name="uq_notes_dataset_external_id"),
        sa.UniqueConstraint("dataset_id", "position", name="uq_notes_dataset_position"),
    )
    op.create_index(
        "ix_notes_active_lookup",
        "notes",
        ["dataset_id", "deleted_at", "position"],
    )

    op.create_table(
        "annotation_rounds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.Integer(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("definition_text", sa.Text(), nullable=True),
        sa.Column(
            "definition_visible",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.CheckConstraint("round_number IN (1, 2)", name="ck_annotation_rounds_round_number_valid"),
        sa.UniqueConstraint(
            "dataset_id",
            "round_number",
            name="uq_annotation_rounds_dataset_round_number",
        ),
    )

    op.create_table(
        "annotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "round_id",
            sa.Integer(),
            sa.ForeignKey("annotation_rounds.id"),
            nullable=False,
        ),
        sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id"), nullable=False),
        sa.Column("value", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "round_id", "note_id", name="uq_annotations_user_round_note"),
    )

    op.create_table(
        "progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column(
            "round_id",
            sa.Integer(),
            sa.ForeignKey("annotation_rounds.id"),
            nullable=False,
        ),
        sa.Column("last_position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "round_id", name="uq_progress_user_round"),
    )


def downgrade() -> None:
    op.drop_table("annotations")
    op.drop_table("progress")
    op.drop_index("ix_notes_active_lookup", table_name="notes")
    op.drop_table("notes")
    op.drop_table("annotation_rounds")
    op.drop_index("uq_datasets_single_active", table_name="datasets")
    op.drop_table("datasets")
    op.drop_table("users")
