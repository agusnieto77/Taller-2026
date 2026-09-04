from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import ADMIN_ROLE
from app.models import User


def get_current_user(request: Request, db: Session) -> User:
    user_id = request.session.get("user_id")
    user = db.scalar(select(User).where(User.id == user_id, User.active.is_(True))) if user_id else None
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_user(request: Request, db: Session) -> User:
    return get_current_user(request, db)


def require_admin(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if user.role != ADMIN_ROLE:
        raise HTTPException(status_code=303, headers={"Location": "/labeling"})
    return user
