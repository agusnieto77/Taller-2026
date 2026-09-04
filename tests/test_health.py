import re
from datetime import datetime, timezone

from sqlalchemy import select

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.models import AnnotationRound, Progress



def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_honor_app_name_environment(monkeypatch):
    monkeypatch.delenv("APP_TITLE", raising=False)
    monkeypatch.setenv("APP_NAME", "Configured application")
    assert Settings().app_name == "Configured application"


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _login(client, username: str = "ana", password: str = "local-only-ana-2026") -> None:
    page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "username": username,
            "password": password,
            "csrf_token": _csrf(page.text),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_labeling_page_explains_the_decision(client, seeded_db):
    _login(client)
    response = client.get("/labeling/round/1", follow_redirects=True)

    assert response.status_code == 200
    assert "¿La nota informa sobre una protesta?" in response.text
    assert 'data-shortcut="1"' in response.text
    assert 'data-shortcut="2"' in response.text


def test_results_page_supplies_csrf_for_logout(client, seeded_db):
    _login(client)
    rounds = seeded_db.scalars(
        select(AnnotationRound).order_by(AnnotationRound.round_number)
    ).all()
    completed_at = datetime.now(timezone.utc)
    seeded_db.add_all(
        [
            Progress(
                user_id=1,
                dataset_id=1,
                round_id=round_.id,
                last_position=3,
                completed_at=completed_at,
            )
            for round_ in rounds
        ]
    )
    seeded_db.commit()

    results = client.get("/results")
    assert results.status_code == 200
    token = _csrf(results.text)
    logout = client.post(
        "/logout",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"
