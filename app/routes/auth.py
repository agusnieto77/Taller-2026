from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db

from app.models import User
from app.security import issue_csrf_token, validate_csrf, verify_password

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request=request, name="auth/login.html", context={"csrf_token": issue_csrf_token(request), "error": None})


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, db: Session = Depends(get_db), username: str = Form(""), password: str = Form(""), csrf_token: str = Form("")):
    validate_csrf(request, csrf_token)
    user = db.scalar(select(User).where(User.username == username.strip()))
    if user is None or not user.active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request=request, name="auth/login.html", context={"csrf_token": issue_csrf_token(request), "error": "Usuario o contraseña incorrectos"}, status_code=401)
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["role"] = user.role
    return RedirectResponse("/admin" if user.role == "admin" else "/labeling", status_code=303)


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form("")):
    validate_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
