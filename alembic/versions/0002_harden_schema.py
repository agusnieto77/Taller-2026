"""harden schema for existing stamped databases

Revision ID: 0002_harden_schema
Revises: 0001_initial
Create Date: 2026-09-03 00:00:01.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_harden_schema"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


_USERS_USERNAME_INDEX = "uq_users_username"
_DATASETS_ACTIVE_INDEX = "uq_datasets_single_active"
_TIMEZONE_COLUMNS = (
    ("users", "created_at"),
    ("users", "updated_at"),
    ("datasets", "created_at"),
    ("datasets", "archived_at"),
    ("notes", "deleted_at"),
    ("notes", "created_at"),
    ("notes", "updated_at"),
    ("annotations", "created_at"),
    ("annotations", "updated_at"),
    ("progress", "completed_at"),
    ("progress", "updated_at"),
)


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _has_unique_constraint(inspector: sa.Inspector, table_name: str, column_names: tuple[str, ...]) -> bool:
    return any(tuple(constraint["column_names"]) == column_names for constraint in inspector.get_unique_constraints(table_name))


def _ensure_username_uniqueness(bind: sa.engine.Connection, inspector: sa.Inspector) -> None:
    if _has_index(inspector, "users", _USERS_USERNAME_INDEX):
        return
    if _has_unique_constraint(inspector, "users", ("username",)):
        return

    op.create_index(_USERS_USERNAME_INDEX, "users", ["username"], unique=True)



def _ensure_active_dataset_uniqueness(bind: sa.engine.Connection, inspector: sa.Inspector) -> None:
    if _has_index(inspector, "datasets", _DATASETS_ACTIVE_INDEX):
        return

    op.create_index(
        _DATASETS_ACTIVE_INDEX,
        "datasets",
        ["status"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )



def _ensure_postgresql_timezones(bind: sa.engine.Connection, inspector: sa.Inspector) -> None:
    if bind.dialect.name != "postgresql":
        return

    for table_name, column_name in _TIMEZONE_COLUMNS:
        column = next(column for column in inspector.get_columns(table_name) if column["name"] == column_name)
        column_type = column["type"]
        if getattr(column_type, "timezone", False):
            continue

        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=False),
            type_=sa.DateTime(timezone=True),
            existing_nullable=column["nullable"],
            postgresql_using=f"{column_name} AT TIME ZONE 'UTC'",
        )



def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    _ensure_username_uniqueness(bind, inspector)
    _ensure_active_dataset_uniqueness(bind, inspector)
    _ensure_postgresql_timezones(bind, inspector)



def downgrade() -> None:
    return
