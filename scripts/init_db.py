from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.config import get_settings
from app.database import SessionLocal
from app.services.seed_service import seed_demo_data


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    (repo_root / "data").mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=repo_root, check=True)

    settings = get_settings()
    db = SessionLocal()
    try:
        seed_demo_data(db, settings)
    finally:
        db.close()


if __name__ == "__main__":
    main()
