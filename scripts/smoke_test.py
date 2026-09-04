from __future__ import annotations

import re
import sys
from urllib.parse import urljoin

import httpx

BASE_URL = "http://127.0.0.1:8000"
DEFINITION = "Una protesta es una reunión de al menos 50 personas que expresa públicamente una demanda, reclamo u oposición dirigida al gobierno."


def csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "No se encontró token CSRF"
    return match.group(1)


def login(client: httpx.Client, username: str, password: str) -> httpx.Response:
    page = client.get("/login")
    assert page.status_code == 200
    response = client.post("/login", data={"username": username, "password": password, "csrf_token": csrf(page.text)}, follow_redirects=True)
    assert response.status_code == 200
    return response


def label_round(client: httpx.Client, round_number: int, values: list[str]) -> None:
    for value in values:
        page = client.get(f"/labeling/round/{round_number}", follow_redirects=True)
        assert page.status_code == 200
        match = re.search(r'action="/labeling/round/\d+/note/(\d+)/label', page.text)
        assert match, f"No hay nota pendiente en ronda {round_number}"
        response = client.post(f"/labeling/round/{round_number}/note/{match.group(1)}/label", data={"value": value, "csrf_token": csrf(page.text)}, follow_redirects=True)
        assert response.status_code == 200


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=10, follow_redirects=False) as first:
        dashboard = login(first, "user01", "user@01")
        assert "Ronda 1" in dashboard.text
        label_round(first, 1, ["true", "false"] * 5)
        transition = first.get("/labeling/round/2/transition")
        assert transition.status_code == 200 and DEFINITION in transition.text
        label_round(first, 2, ["true"] * 10)
        dashboard = first.get("/labeling")
        assert "10/10" in dashboard.text
        assert first.get("/results").status_code == 200

    with httpx.Client(base_url=BASE_URL, timeout=10, follow_redirects=False) as second:
        dashboard = login(second, "user02", "user@02")
        assert "0/10" in dashboard.text
        assert second.get("/results").status_code == 303
        label_round(second, 1, ["true"] * 10)
        label_round(second, 2, ["false"] * 10)
        results = second.get("/results")
        assert results.status_code == 200
        for text in ("Ronda 1", "Ronda 2", "Desacuerdos", "Cambios"):
            assert text in results.text, text

    with httpx.Client(base_url=BASE_URL, timeout=10, follow_redirects=False) as admin:
        dashboard = login(admin, "admin", "local-only-admin-2026")
        assert dashboard.status_code == 200 and admin.get("/admin").status_code == 200

    print("smoke ok: two users, two rounds, isolation and results")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, httpx.HTTPError) as exc:
        print(f"smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
