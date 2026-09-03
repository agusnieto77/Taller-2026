from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name)
    application.mount("/static", StaticFiles(directory="static"), name="static")

    @application.get("/health", name="health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
