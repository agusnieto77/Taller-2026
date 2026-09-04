from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.database import SessionLocal
from app.services.dataset_service import replace_active_dataset
from app.services.import_service import ImportValidationError, parse_notes_upload


def main() -> int:
    parser = argparse.ArgumentParser(description="Reemplaza el conjunto activo de notas")
    parser.add_argument("--file", required=True, help="Archivo JSON o CSV")
    parser.add_argument("--name", default="Notas importadas", help="Nombre del nuevo conjunto")
    args = parser.parse_args()
    path = Path(args.file)
    try:
        payloads = parse_notes_upload(path.name, path.read_bytes())
    except (OSError, ImportValidationError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    db = SessionLocal()
    try:
        dataset = replace_active_dataset(db, args.name, payloads)
        db.commit()
        print(f"dataset_id={dataset.id} notes={len(payloads)}")
    except Exception as exc:
        db.rollback()
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
