from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_honor_app_name_environment(monkeypatch):
    monkeypatch.delenv("APP_TITLE", raising=False)
    monkeypatch.setenv("APP_NAME", "Configured application")
    assert Settings().app_name == "Configured application"
