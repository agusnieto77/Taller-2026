from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.labeling import router as labeling_router
from app.routes.results import router as results_router


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name)
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie=settings.session_cookie_name,
        https_only=settings.session_cookie_secure,
        same_site="lax",
    )
    application.mount("/static", StaticFiles(directory="static"), name="static")

    @application.get("/health", name="health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/")
    def root(request: Request):
        if not request.session.get("user_id"):
            return RedirectResponse("/login", status_code=303)
        if request.session.get("role") == "admin":
            return RedirectResponse("/admin", status_code=303)
        return RedirectResponse("/labeling", status_code=303)

    application.include_router(auth_router)
    application.include_router(labeling_router)
    application.include_router(results_router)
    application.include_router(admin_router)
    return application


app = create_app()
