from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db

from app.dependencies import require_user
from app.models import Dataset, User
from app.security import issue_csrf_token
from app.services.annotation_service import get_round_status
from app.services.results_service import build_study_results

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/results", response_class=HTMLResponse)
def results(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    dataset = db.scalar(select(Dataset).where(Dataset.status == "active"))
    if dataset is None:
        return RedirectResponse("/labeling", status_code=303)
    first = get_round_status(db, user.id, 1)
    second = get_round_status(db, user.id, 2)
    if not first.completed or not second.completed:
        return RedirectResponse("/labeling", status_code=303)
    annotator_ids = list(
        db.scalars(
            select(User.id).where(
                User.active.is_(True),
                User.role == "annotator",
            )
        ).all()
    )
    study = build_study_results(db, dataset.id, annotator_ids)
    return templates.TemplateResponse(
        request=request,
        name="results/index.html",
        context={"user": user, "study": study, "csrf_token": issue_csrf_token(request)},
    )
