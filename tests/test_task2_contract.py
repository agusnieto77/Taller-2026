from pathlib import Path


def test_task2_seed_and_model_files_exist() -> None:
    assert Path("app/constants.py").exists()
    assert Path("app/models.py").exists()
    assert Path("alembic.ini").exists()
    assert Path("alembic/env.py").exists()
    assert Path("alembic/versions/0001_initial.py").exists()
    assert Path("data/seed/notes.json").exists()
    assert Path("data/seed/users.json").exists()
    assert Path("app/services/seed_service.py").exists()
    assert Path("scripts/init_db.py").exists()
    assert Path("tests/conftest.py").exists()
