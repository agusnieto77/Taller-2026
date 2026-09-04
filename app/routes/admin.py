from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.constants import ADMIN_ROLE, ANNOTATOR_ROLE

from app.models import Annotation, Dataset, Note, Progress, User
from app.dependencies import require_admin
from app.security import hash_password, issue_csrf_token, validate_csrf
from app.services.dataset_service import replace_active_dataset
from app.services.import_service import ImportValidationError, parse_notes_upload
from app.services.results_service import build_study_results

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


def _ctx(request, user, **extra):
    return {"request": request, "user": user, "csrf_token": issue_csrf_token(request), **extra}


@router.get("", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    dataset = db.scalar(select(Dataset).where(Dataset.status == "active"))
    note_count = (
        db.scalar(
            select(func.count(Note.id)).where(
                Note.dataset_id == dataset.id,
                Note.deleted_at.is_(None),
            )
        )
        if dataset
        else 0
    )
    annotator_count = (
        db.scalar(
            select(func.count(User.id)).where(
                User.active.is_(True),
                User.role == ANNOTATOR_ROLE,
            )
        )
        or 0
    )
    annotation_count = (
        db.scalar(
            select(func.count(Annotation.id))
            .join(Note, Annotation.note_id == Note.id)
            .where(
                Note.dataset_id == dataset.id,
                Note.deleted_at.is_(None),
            )
        )
        if dataset
        else 0
    )
    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context=_ctx(
            request,
            user,
            dataset=dataset,
            note_count=note_count,
            annotator_count=annotator_count,
            annotation_count=annotation_count,
        ),
    )

@router.get("/notes", response_class=HTMLResponse)
def notes_list(request: Request, db: Session = Depends(get_db), q: str = ""):
    user = require_admin(request, db)
    dataset = db.scalar(select(Dataset).where(Dataset.status == "active"))
    filters = [Note.dataset_id == (dataset.id if dataset else -1), Note.deleted_at.is_(None)]
    term = q.strip()
    if term:
        pattern = f"%{term.lower()}%"
        filters.append(or_(func.lower(Note.title).like(pattern), func.lower(Note.external_id).like(pattern)))
    notes = list(db.scalars(select(Note).where(*filters).order_by(Note.position)).all())
    return templates.TemplateResponse(request=request, name="admin/notes.html", context=_ctx(request, user, notes=notes, q=q))



@router.post("/notes/{note_id}/edit")
def note_update(request: Request, note_id: int, db: Session = Depends(get_db), external_id: str = Form(""), title: str = Form(""), text: str = Form(""), csrf_token: str = Form("")):
    user = require_admin(request, db); validate_csrf(request, csrf_token)
    note = db.get(Note, note_id)
    if note is None:
        return RedirectResponse("/admin/notes", status_code=303)
    if not external_id.strip() or not title.strip() or not text.strip():
        return templates.TemplateResponse(request=request, name="admin/note_form.html", context=_ctx(request, user, note=note, error="ID, título y texto son obligatorios"), status_code=400)
    note.external_id, note.title, note.text = external_id.strip(), title.strip(), text.strip()
    db.commit()
    return RedirectResponse("/admin/notes", status_code=303)


@router.get("/notes/new", response_class=HTMLResponse)
def note_new(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request=request, name="admin/note_form.html", context=_ctx(request, require_admin(request, db), note=None, error=None))
@router.get("/notes/{note_id}/edit", response_class=HTMLResponse)
def note_edit(request: Request, note_id: int, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    note = db.get(Note, note_id)
    if note is None:
        return RedirectResponse("/admin/notes", status_code=303)
    return templates.TemplateResponse(request=request, name="admin/note_form.html", context=_ctx(request, user, note=note, error=None))


@router.post("/notes/new")
def note_create(request: Request, db: Session = Depends(get_db), external_id: str = Form(""), title: str = Form(""), text: str = Form(""), csrf_token: str = Form("")):
    user = require_admin(request, db); validate_csrf(request, csrf_token)
    dataset = db.scalar(select(Dataset).where(Dataset.status == "active"))
    if dataset is None or not external_id.strip() or not title.strip() or not text.strip():
        return templates.TemplateResponse(request=request, name="admin/note_form.html", context=_ctx(request, user, note=None, error="ID, título y texto son obligatorios"), status_code=400)
    position = (db.scalar(select(func.max(Note.position)).where(Note.dataset_id == dataset.id)) or 0) + 1
    db.add(Note(dataset_id=dataset.id, external_id=external_id.strip(), position=position, title=title.strip(), text=text.strip()))
    db.commit()
    return RedirectResponse("/admin/notes", status_code=303)


@router.post("/notes/{note_id}/delete")
def note_delete(request: Request, note_id: int, db: Session = Depends(get_db), csrf_token: str = Form("")):
    require_admin(request, db); validate_csrf(request, csrf_token)
    note = db.get(Note, note_id)
    if note:
        note.deleted_at = datetime.now(timezone.utc); db.commit()
    return RedirectResponse("/admin/notes", status_code=303)


@router.get("/import", response_class=HTMLResponse)
def import_form(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request=request, name="admin/import.html", context=_ctx(request, require_admin(request, db), error=None))


@router.post("/import")
def import_notes(request: Request, db: Session = Depends(get_db), file: UploadFile = File(...), name: str = Form("Notas importadas"), csrf_token: str = Form("")):
    user = require_admin(request, db); validate_csrf(request, csrf_token)
    try:
        payloads = parse_notes_upload(file.filename or "", file.file.read())
        dataset = replace_active_dataset(db, name, payloads)
        db.commit()
    except (ImportValidationError, ValueError) as exc:
        db.rollback()
        return templates.TemplateResponse(request=request, name="admin/import.html", context=_ctx(request, user, error=str(exc)), status_code=400)
    return RedirectResponse("/admin", status_code=303)


@router.get("/users", response_class=HTMLResponse)
def users(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    return templates.TemplateResponse(request=request, name="admin/users.html", context=_ctx(request, user, users=list(db.scalars(select(User).order_by(User.username)).all()), error=None))


@router.post("/users")
def user_create(request: Request, db: Session = Depends(get_db), username: str = Form(""), display_name: str = Form(""), password: str = Form(""), role: str = Form(ANNOTATOR_ROLE), csrf_token: str = Form("")):
    admin = require_admin(request, db); validate_csrf(request, csrf_token)
    if not username.strip() or not password or role not in (ANNOTATOR_ROLE, ADMIN_ROLE) or db.scalar(select(User).where(User.username == username.strip())):
        return templates.TemplateResponse(request=request, name="admin/users.html", context=_ctx(request, admin, users=list(db.scalars(select(User)).all()), error="Datos inválidos o usuario duplicado"), status_code=400)
    db.add(User(username=username.strip(), display_name=display_name.strip() or username.strip(), password_hash=hash_password(password), role=role, active=True)); db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/toggle")
def user_toggle(request: Request, user_id: int, db: Session = Depends(get_db), csrf_token: str = Form("")):
    admin = require_admin(request, db); validate_csrf(request, csrf_token)
    target = db.get(User, user_id)
    if target is not None:
        active_admin_count = db.scalar(
            select(func.count(User.id)).where(
                User.role == ADMIN_ROLE,
                User.active.is_(True),
            )
        )
        if target.active and target.role == ADMIN_ROLE and active_admin_count <= 1:
            return RedirectResponse("/admin/users", status_code=303)
        target.active = not target.active
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/password")
def user_password(request: Request, user_id: int, db: Session = Depends(get_db), password: str = Form(""), csrf_token: str = Form("")):
    require_admin(request, db); validate_csrf(request, csrf_token)
    target = db.get(User, user_id)
    if target is not None and password:
        target.password_hash = hash_password(password)
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/progress", response_class=HTMLResponse)
def progress(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    rows = list(
        db.scalars(
            select(Progress)
            .options(selectinload(Progress.user), selectinload(Progress.round))
            .order_by(Progress.user_id, Progress.round_id)
        ).all()
    )
    return templates.TemplateResponse(request=request, name="admin/progress.html", context=_ctx(request, user, rows=rows))


@router.get("/annotations", response_class=HTMLResponse)
def annotations(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    rows = list(
        db.scalars(
            select(Annotation)
            .options(selectinload(Annotation.user), selectinload(Annotation.note), selectinload(Annotation.round))
            .order_by(Annotation.created_at.desc())
        ).all()
    )
    return templates.TemplateResponse(request=request, name="admin/annotations.html", context=_ctx(request, user, rows=rows))


@router.get("/results", response_class=HTMLResponse)
def admin_results(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    dataset = db.scalar(select(Dataset).where(Dataset.status == "active"))
    annotator_ids = list(db.scalars(select(User.id).where(User.active.is_(True), User.role == ANNOTATOR_ROLE)).all())
    study = build_study_results(db, dataset.id, annotator_ids) if dataset else None
    return templates.TemplateResponse(request=request, name="admin/results.html", context=_ctx(request, user, study=study))
