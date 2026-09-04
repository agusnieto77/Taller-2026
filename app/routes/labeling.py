from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db

from app.constants import ROUND_ONE, ROUND_TWO
from app.services.annotation_service import NoteUnavailableError, RoundNotAvailableError, get_first_pending_note, get_note_for_round, get_round_status, save_annotation
from app.security import issue_csrf_token, validate_csrf
from app.dependencies import require_user

router = APIRouter(prefix="/labeling")
templates = Jinja2Templates(directory="app/templates")


def _user(request: Request, db: Session):
    return require_user(request, db)


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = _user(request, db)
    statuses = [get_round_status(db, user.id, number) for number in (ROUND_ONE, ROUND_TWO)]
    return templates.TemplateResponse(request=request, name="labeling/dashboard.html", context={"user": user, "statuses": statuses, "csrf_token": issue_csrf_token(request)})


@router.get("/round/{round_number}")
def round_start(request: Request, round_number: int, db: Session = Depends(get_db)):
    user = _user(request, db)
    if round_number not in (ROUND_ONE, ROUND_TWO):
        raise HTTPException(404, "Ronda inexistente")
    status = get_round_status(db, user.id, round_number)
    if not status.can_start:
        if round_number == ROUND_TWO:
            return RedirectResponse("/labeling/round/2/transition", status_code=303)
        return RedirectResponse("/labeling", status_code=303)
    pending = get_first_pending_note(db, user.id, round_number)
    if pending is None:
        return RedirectResponse("/labeling/round/2/transition" if round_number == ROUND_ONE else "/results", status_code=303)
    return RedirectResponse(f"/labeling/round/{round_number}/note/{pending.id}", status_code=303)


@router.get("/round/{round_number}/transition", response_class=HTMLResponse)
def transition(request: Request, round_number: int, db: Session = Depends(get_db)):
    user = _user(request, db)
    if round_number != ROUND_TWO:
        raise HTTPException(404)
    first = get_round_status(db, user.id, ROUND_ONE)
    if not first.completed:
        return RedirectResponse("/labeling", status_code=303)
    second = get_round_status(db, user.id, ROUND_TWO)
    return templates.TemplateResponse(request=request, name="labeling/transition.html", context={"user": user, "status": second, "csrf_token": issue_csrf_token(request)})


@router.get("/round/{round_number}/note/{note_id}", response_class=HTMLResponse)
def note_page(request: Request, round_number: int, note_id: int, db: Session = Depends(get_db)):
    user = _user(request, db)
    try:
        note, annotation, status = get_note_for_round(db, user.id, round_number, note_id)
    except (NoteUnavailableError, RoundNotAvailableError) as exc:
        pending = get_first_pending_note(db, user.id, round_number)
        if pending and isinstance(exc, NoteUnavailableError):
            return RedirectResponse(f"/labeling/round/{round_number}/note/{pending.id}", status_code=303)
        raise HTTPException(403, str(exc))
    context = {"user": user, "note": note, "annotation": annotation, "status": status, "csrf_token": issue_csrf_token(request), "round_number": round_number}
    if round_number == ROUND_TWO:
        context["definition_text"] = status.definition_text
    return templates.TemplateResponse(request=request, name="labeling/note.html", context=context)


@router.post("/round/{round_number}/note/{note_id}/label")
def label_note(request: Request, round_number: int, note_id: int, db: Session = Depends(get_db), value: str = Form(""), csrf_token: str = Form("")):
    user = _user(request, db)
    validate_csrf(request, csrf_token)
    normalized_value = value.strip().lower()
    if normalized_value not in ("true", "false"):
        raise HTTPException(422, "Clasificación inválida")
    try:
        result = save_annotation(db, user.id, round_number, note_id, normalized_value == "true")
    except (NoteUnavailableError, RoundNotAvailableError) as exc:
        raise HTTPException(403, str(exc))
    except Exception as exc:
        from app.services.annotation_service import RoundLockedError
        if isinstance(exc, RoundLockedError):
            raise HTTPException(409, str(exc))
        raise
    if result.next_note is not None:
        return RedirectResponse(f"/labeling/round/{round_number}/note/{result.next_note.id}", status_code=303)
    if round_number == ROUND_ONE:
        return RedirectResponse("/labeling/round/2/transition", status_code=303)
    return RedirectResponse("/results", status_code=303)
