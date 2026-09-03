# Etiquetado colaborativo de notas periodísticas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir una aplicación web local y preparada para VPS donde varios usuarios clasifiquen las mismas notas en dos rondas, con persistencia inmediata, progreso, comparación y administración.

**Architecture:** Monolito server-rendered con FastAPI, Jinja2, SQLAlchemy síncrono y SQLite por defecto. La lógica de etiquetado, transición de rondas, importación y resultados vivirá en servicios independientes de las rutas y templates. El conjunto de notas se versionará mediante datasets para que el reemplazo sea atómico y no mezcle historiales.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, SQLAlchemy 2.0, Alembic, SQLite, Pydantic Settings, Starlette SessionMiddleware, pwdlib/Argon2, pytest, httpx, HTML/CSS y JavaScript mínimo.

## Global Constraints

- La aplicación manejará un conjunto global de notas compartido por todos los anotadores activos.
- Cada anotador completará dos rondas sobre las mismas notas, en orden, de la nota 1 a la última.
- La ronda 1 no enviará ni mostrará la definición de conflicto al template.
- La ronda 1 permitirá correcciones mientras esté en curso y quedará bloqueada al completarse.
- La ronda 2 se habilitará para cada anotador inmediatamente después de completar su ronda 1.
- La ronda 2 mostrará literalmente la definición aprobada y permitirá correcciones posteriores.
- No existirá una etiqueta duplicada para `(usuario, ronda, nota)`.
- Cada clasificación se guardará inmediatamente junto con el progreso dentro de una transacción.
- Las notas iniciales estarán en JSON separado de la interfaz y serán exactamente 10.
- La importación aceptará JSON y CSV, validará el archivo completo y reemplazará el dataset activo de forma atómica.
- Los resultados mostrarán unanimidad por nota, comparación por pares, desacuerdos detallados y cambios entre rondas.
- Los resultados deben distinguir `PARCIAL` de `DEFINITIVO` con denominadores explícitos.
- Las métricas de Kappa no se implementarán ahora; el servicio de resultados debe admitir extensiones posteriores.
- Las rutas administrativas estarán bajo `/admin` y verificarán el rol en el servidor.
- Las contraseñas se almacenarán únicamente como hash Argon2.
- `SECRET_KEY`, `DATABASE_URL` y la configuración de cookies vendrán de variables de entorno.
- No se crearán funcionalidades de mensajería, perfiles sociales, notificaciones ni asignaciones por subconjuntos.
- Toda escritura web usará `POST`, token CSRF y el patrón Post/Redirect/Get.
- Se ejecutarán pruebas enfocadas y un smoke test real; no se afirmará que el flujo está completo sin evidencia de ejecución.

---

## Mapa de archivos y límites

### Archivos de configuración y ejecución

- `pyproject.toml`: metadatos, dependencias y comandos de desarrollo.
- `.env.example`: configuración local y de VPS sin secretos reales.
- `alembic.ini`: conexión y ubicación de migraciones.
- `alembic/env.py`: integración de Alembic con `Base.metadata` y settings.
- `alembic/versions/0001_initial.py`: esquema inicial.
- `Dockerfile`: imagen de producción.
- `docker-compose.yml`: ejecución local con volumen persistente.
- `scripts/init_db.py`: migración y seed idempotentes.
- `scripts/load_notes.py`: carga masiva CLI usando el mismo servicio que el panel.

### Código de aplicación

- `app/config.py`: `Settings` y validación de entorno.
- `app/database.py`: engine, `SessionLocal`, `Base` y dependencia `get_db`.
- `app/models.py`: seis entidades SQLAlchemy y constraints.
- `app/constants.py`: roles, estados y definición aprobada de ronda 2.
- `app/security.py`: hash, verificación, sesión y CSRF.
- `app/dependencies.py`: `get_current_user`, `require_user`, `require_admin`.
- `app/services/seed_service.py`: dataset y usuarios demo.
- `app/services/annotation_service.py`: progreso, acceso a rondas y guardado de etiquetas.
- `app/services/results_service.py`: unanimidad, pares, cambios y estado parcial/final.
- `app/services/import_service.py`: parseo y validación de JSON/CSV.
- `app/services/dataset_service.py`: reemplazo versionado del dataset.
- `app/routes/auth.py`: login/logout.
- `app/routes/labeling.py`: dashboard y flujo de ambas rondas.
- `app/routes/results.py`: resultados de anotadores.
- `app/routes/admin.py`: notas, importación, usuarios, progreso, etiquetas y resultados.
- `app/main.py`: creación de FastAPI, middleware, templates, static y routers.

### Datos y templates

- `data/seed/notes.json`: 10 notas ficticias con campos requeridos y opcionales.
- `data/seed/users.json`: tres anotadores y un administrador demo para local.
- `app/templates/base.html`: layout común de anotadores.
- `app/templates/auth/login.html`: login.
- `app/templates/labeling/dashboard.html`: progreso personal.
- `app/templates/labeling/note.html`: lectura y clasificación.
- `app/templates/labeling/transition.html`: paso entre rondas.
- `app/templates/results/index.html`: resultados por ronda y cambios.
- `app/templates/admin/base.html`: layout administrativo separado.
- `app/templates/admin/dashboard.html`: resumen administrativo.
- `app/templates/admin/notes.html`, `note_form.html`, `import.html`: gestión de notas.
- `app/templates/admin/users.html`, `user_form.html`: gestión de usuarios.
- `app/templates/admin/progress.html`, `annotations.html`, `results.html`: consultas administrativas.
- `static/styles.css`: diseño responsive, lectura y botones.
- `static/app.js`: deshabilitar botones y confirmar correcciones.

### Pruebas

- `tests/conftest.py`: base SQLite aislada, cliente y fixtures.
- `tests/test_security.py`: hash, sesión, CSRF y roles.
- `tests/test_annotation_service.py`: invariantes de rondas, etiquetas y progreso.
- `tests/test_results_service.py`: algoritmos y estados.
- `tests/test_import_service.py`: formatos, errores y duplicados.
- `tests/test_routes.py`: flujo HTTP de anotador.
- `tests/test_admin_routes.py`: permisos y administración.

---

## Task 1: Scaffold de aplicación y configuración

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/database.py`
- Create: `app/main.py`
- Create: `tests/__init__.py`
- Create: `tests/test_health.py`
- Create: `static/styles.css`

**Interfaces:**
- Produce `Settings` loaded by `get_settings()`.
- Produce `Base`, `engine`, `SessionLocal` and `get_db()`.
- Produce `create_app() -> FastAPI` and expose module variable `app`.

- [ ] **Step 1: Write the package metadata and dependency contract**

Add this exact dependency set to `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "collaborative-news-labeling"
version = "0.1.0"
description = "Aplicación web de etiquetado colaborativo de notas periodísticas"
requires-python = ">=3.12"
dependencies = [
  "alembic>=1.13,<2",
  "fastapi>=0.115,<1",
  "httpx>=0.27,<1",
  "jinja2>=3.1,<4",
  "pydantic-settings>=2.6,<3",
  "pwdlib[argon2]>=0.2,<1",
  "python-multipart>=0.0.9,<1",
  "sqlalchemy>=2.0,<3",
  "uvicorn[standard]>=0.30,<1",
]

[project.optional-dependencies]
test = [
  "pytest>=8,<9",
  "pytest-cov>=5,<6",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.setuptools.packages.find]
include = ["app*"]
```

- [ ] **Step 2: Define environment settings and SQLite defaults**

Implement `Settings` in `app/config.py` with these fields and defaults:

```python
class Settings(BaseSettings):
    app_name: str = "Etiquetado colaborativo"
    app_env: str = "development"
    secret_key: str = "local-only-change-me"
    database_url: str = "sqlite:///./data/app.db"
    session_cookie_name: str = "labeling_session"
    session_cookie_secure: bool = False
    admin_username: str = "admin"
    admin_password: str = "admin123"
    seed_demo_data: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
```

Expose a cached `get_settings() -> Settings`. Reject the development secret when `app_env == "production"` by raising `ValueError` during settings construction.

- [ ] **Step 3: Create database primitives**

Implement `app/database.py`:

```python
class Base(DeclarativeBase):
    pass

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

For SQLite, register a `connect` listener that executes `PRAGMA foreign_keys=ON` and `PRAGMA busy_timeout=5000`. Create the `data/` directory in the init script rather than at import time.

- [ ] **Step 4: Wire a health endpoint and application factory**

Implement `create_app()` in `app/main.py` with:
```python
settings = get_settings()
app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/health", name="health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

Create `tests/test_health.py` with:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

Do not import feature routers yet: `auth_router`, `labeling_router`, `results_router` and `admin_router` are created in later tasks. Create `static/styles.css` with the valid baseline rule `body { margin: 0; }` so the static mount works from the first commit. Configure `Jinja2Templates(directory="app/templates")` when the first HTML router is added in Task 3, register it on `app.state.templates`, and keep the database dependency injectable in tests.

- [ ] **Step 5: Verify the scaffold and commit**

Run:

```bash
python -m pip install -e ".[test]"
python -m pytest tests/test_health.py -q
```

Expected: one health test passes, and `python -c "from app.main import app; print(app.title)"` prints `Etiquetado colaborativo`.

Commit:

```bash
git add pyproject.toml .env.example app tests static
git commit -m "chore: scaffold FastAPI labeling app"
```

---

## Task 2: Modelado, migraciones y datos demo

**Files:**
- Create: `app/models.py`
- Create: `app/constants.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_initial.py`
- Create: `data/seed/notes.json`
- Create: `data/seed/users.json`
- Create: `app/services/seed_service.py`
- Create: `app/services/__init__.py`
- Create: `scripts/init_db.py`
- Test: `tests/conftest.py`

**Interfaces:**
- `seed_demo_data(db: Session, settings: Settings) -> None` is idempotent.
- `ROUND_TWO_DEFINITION` is the exact approved Spanish text.
- ORM classes are `User`, `Dataset`, `Note`, `AnnotationRound`, `Annotation`, `Progress`.

- [ ] **Step 1: Define constants and ORM constraints**

Define in `app/constants.py`:

```python
ANNOTATOR_ROLE = "annotator"
ADMIN_ROLE = "admin"
DATASET_ACTIVE = "active"
DATASET_ARCHIVED = "archived"
ROUND_ONE = 1
ROUND_TWO = 2
ROUND_TWO_DEFINITION = "Una protesta es una reunión de al menos 50 personas que expresa públicamente una demanda, reclamo u oposición dirigida al gobierno. La acción debe tener como blanco principal a una autoridad estatal, una política pública, una decisión gubernamental o alguna otra forma de intervención del Estado. Quedan fuera de esta definición las acciones protagonizadas por grupos más pequeños, así como aquellas dirigidas exclusivamente contra empresas, organizaciones privadas u otros actores no estatales. La protesta se concibe, por lo tanto, como una forma de movilización colectiva de cierta magnitud orientada explícitamente hacia el poder público."
```

In `app/models.py`, use typed SQLAlchemy 2.0 mappings. Add these constraints:

- `users.username` unique and non-empty at service level;
- `notes(dataset_id, external_id)` unique;
- `notes(dataset_id, position)` unique;
- `annotation_rounds(dataset_id, round_number)` unique;
- `annotations(user_id, round_id, note_id)` unique;
- `progress(user_id, round_id)` unique;
- foreign keys with cascade only from a dataset to its rounds/notes, never from an annotation update to duplicate rows.

Use `Boolean` for `Annotation.value`, nullable timestamps for `completed_at`/`deleted_at`, and `JSON` for `Note.metadata_json`.

- [ ] **Step 2: Add the initial Alembic migration**

Configure `alembic/env.py` to import `Base.metadata` and read the database URL from `get_settings()`. Write revision `0001_initial` that creates all six tables, indexes active note queries, and applies the unique constraints from Step 1. The downgrade must drop tables in dependency order: `annotations`, `progress`, `notes`, `annotation_rounds`, `datasets`, `users`.

- [ ] **Step 3: Create ten independent demo notes and demo users**

Create `data/seed/notes.json` as a JSON array of exactly ten records with fields:

```json
{
  "id": "nota-01",
  "titulo": "...",
  "texto": "...",
  "fecha": "2026-01-15",
  "medio": "Diario Ejemplo",
  "url": "https://example.invalid/notas/01",
  "seccion": "Política",
  "metadata": {"source": "demo"}
}
```

Use unique IDs `nota-01` through `nota-10`, realistic but fictitious Spanish titles and bodies, and a mix of likely `TRUE`/`FALSE` cases under both definitions. Do not include labels in the fixture.

Create `data/seed/users.json` with three annotators (`ana`, `bruno`, `carla`) and one admin (`admin`), each with a clearly documented local-only password. Store only these seed input passwords in this demo fixture; `seed_demo_data()` must hash them before insertion.

- [ ] **Step 4: Implement idempotent initialization**

Implement `seed_demo_data()` to:

1. return without changes when an active dataset and the seeded users already exist;
2. create dataset `Notas demo` with status `active`;
3. create round 1 with `definition_text=None`, `definition_visible=False`;
4. create round 2 with `definition_text=ROUND_TWO_DEFINITION`, `definition_visible=True`;
5. insert the ten notes ordered by position 1–10;
6. insert users with Argon2 hashes and their roles;
7. commit once.

Implement `scripts/init_db.py` to create `data/`, run `alembic upgrade head`, and call `seed_demo_data()`.

- [ ] **Step 5: Add isolated test database fixture**

In `tests/conftest.py`, create an in-memory SQLite engine using `StaticPool`, enable foreign keys, call `Base.metadata.create_all`, override `app.dependency_overrides[get_db]`, and expose fixtures:

```python
@pytest.fixture
def db() -> Iterator[Session]: ...

@pytest.fixture
def client(db: Session) -> TestClient: ...

@pytest.fixture
def seeded_db(db: Session) -> Session: ...
```

The seeded fixture must contain three annotators, one admin, one dataset, two rounds and three notes with explicit IDs `1`, `2` and `3` for notes and explicit IDs `1`, `2` and `3` for users, so service tests can use stable fixture values without relying on database allocation order.

- [ ] **Step 6: Run migration and seed checks, then commit**

Run:

```bash
python scripts/init_db.py
python -c "from app.database import SessionLocal; from app.models import Dataset, Note; db=SessionLocal(); print(db.query(Dataset).count(), db.query(Note).count()); db.close()"
```

Expected output: one dataset and ten notes. Run `python scripts/init_db.py` a second time; counts remain one dataset and ten notes.

Commit:

```bash
git add app/models.py app/constants.py alembic alembic.ini data/seed scripts/init_db.py tests/conftest.py
git commit -m "feat: add annotation data model and demo seed"
```

---

## Task 3: Seguridad, autenticación y autorización

**Files:**
- Create: `app/security.py`
- Create: `app/routes/__init__.py`
- Create: `app/dependencies.py`
- Create: `app/routes/auth.py`
- Create: `app/templates/base.html`
- Create: `app/templates/auth/login.html`
- Modify: `app/main.py`
- Test: `tests/test_security.py`

**Interfaces:**
- `hash_password(password: str) -> str`.
- `verify_password(password: str, password_hash: str) -> bool`.
- `issue_csrf_token(request: Request) -> str`.
- `validate_csrf(request: Request, token: str) -> None`.
- `require_user(request: Request, db: Session) -> User`.
- `require_admin(request: Request, db: Session) -> User`.

- [ ] **Step 1: Write failing security tests**

Add tests that assert:

```python
def test_password_round_trip():
    encoded = hash_password("correcta")
    assert encoded != "correcta"
    assert verify_password("correcta", encoded)
    assert not verify_password("incorrecta", encoded)


def test_csrf_token_is_stable_in_session(client):
    first = client.get("/login")
    second = client.get("/login")
    assert first.status_code == 200
    assert first.text.count('name="csrf_token"') == 1
    assert second.text.count('name="csrf_token"') == 1


def test_login_rejects_invalid_csrf(client):
    response = client.post(
        "/login",
        data={"username": "ana", "password": "demo", "csrf_token": "invalid"},
    )
    assert response.status_code == 400

Run `python -m pytest tests/test_security.py -q`; expected: FAIL because the security module and routes do not exist.

- [ ] **Step 2: Implement Argon2 and CSRF**

Use `pwdlib.PasswordHash.recommended()` for password hashing. Store a random CSRF token in `request.session["csrf_token"]`, compare it with `secrets.compare_digest`, and raise `HTTPException(status_code=400, detail="CSRF token inválido")` on mismatch. Every POST template must receive the token.

- [ ] **Step 3: Implement session dependencies**

`require_user` reads `request.session["user_id"]`, loads an active `User`, and raises `HTTPException(status_code=303, headers={"Location": "/login"})` when the session is missing or inactive. `require_admin` calls the same lookup and raises `HTTPException(status_code=303, headers={"Location": "/labeling"})` for non-admin users. Session login stores only `user_id` and `role`; logout clears the session.

- [ ] **Step 4: Implement login/logout routes and templates**

Add:

- `GET /login`: render username, password and CSRF fields;
- `POST /login`: validate CSRF, verify active user credentials, set session and redirect to `/admin` for admins or `/labeling` for annotators;
- `POST /logout`: validate CSRF, clear session and redirect to `/login`.

Invalid credentials re-render the form with `"Usuario o contraseña incorrectos"` and HTTP 401 without revealing whether the username exists. `base.html` must expose navigation conditionally by role and a logout form.

- [ ] **Step 5: Run focused tests and commit**

Run `python -m pytest tests/test_security.py -q`; expected: all tests pass. Add tests for successful annotator/admin login, invalid credentials, CSRF rejection and inactive user rejection.

Commit:

```bash
git add app/security.py app/dependencies.py app/routes/auth.py app/templates/base.html app/templates/auth/login.html app/main.py tests/test_security.py
git commit -m "feat: add session authentication and role checks"
```

---

## Task 4: Servicio de etiquetado y flujo de rondas

**Files:**
- Create: `app/services/annotation_service.py`
- Create: `app/routes/labeling.py`
- Create: `app/templates/labeling/dashboard.html`
- Create: `app/templates/labeling/note.html`
- Create: `app/templates/labeling/transition.html`
- Modify: `static/styles.css`
- Create: `static/app.js`
- Modify: `app/main.py`
- Test: `tests/test_annotation_service.py`
- Test: `tests/test_routes.py`

**Interfaces:**
- `get_active_dataset(db: Session) -> Dataset | None`.
- `get_round_status(db: Session, user_id: int, round_number: int) -> RoundStatus`.
- `RoundStatus`, `SaveResult`, `RoundLockedError` and `NoteUnavailableError` are defined in `app.services.annotation_service`.

- [ ] **Step 1: Write failing service tests for the core invariants**

Add tests with seeded data:

```python
def test_save_annotation_is_immediate_and_unique(seeded_db):
    result = save_annotation(seeded_db, user_id=1, round_number=1, note_id=1, value=True)
    assert result.answered_count == 1
    save_annotation(seeded_db, user_id=1, round_number=1, note_id=1, value=False)
    rows = seeded_db.query(Annotation).filter_by(user_id=1, round_id=1, note_id=1).all()
    assert len(rows) == 1
    assert rows[0].value is False


def test_round_two_requires_round_one_completion(seeded_db):
    status = get_round_status(seeded_db, user_id=1, round_number=2)
    assert status.can_start is False


def test_round_one_locks_after_last_note(seeded_db):
    for note_id in (1, 2, 3):
        save_annotation(seeded_db, 1, 1, note_id, True)
    status = get_round_status(seeded_db, 1, 1)
    assert status.completed is True
    assert status.locked is True
    with pytest.raises(RoundLockedError):
        save_annotation(seeded_db, 1, 1, 1, False)
```

Run `python -m pytest tests/test_annotation_service.py -q`; expected: FAIL because services are missing.

- [ ] **Step 2: Implement dataset and round status queries**

Query only the active dataset and notes where `deleted_at IS NULL`, ordered by `position`. Compute `answered_count` with a count query for the user/round. `completed` is true only when the count equals the active note count and `Progress.completed_at` is set. A missing progress row is treated as zero progress during reads and created by `save_annotation` on its first write, so read-only requests never create uncommitted state. Round 2 `can_start` is true only when the same user’s round 1 is complete. Round 1 `locked` is true when its progress is complete.

- [ ] **Step 3: Implement first-pending and note access rules**

`get_first_pending_note` returns the first active note without an annotation for the user and round. A route may render an already answered note for correction in the current round, but an unanswered note that is not the first pending note redirects to the first pending note. A completed round redirects to its summary/transition instead of exposing a new note. A deleted note or note from another dataset raises `NoteUnavailableError`.

- [ ] **Step 4: Implement transactional upsert and progress updates**

`save_annotation` must:

1. load the active dataset, requested round and active note;
2. reject round 2 if round 1 is incomplete;
3. reject round 1 if it is locked;
4. insert or update the unique annotation row;
5. update `Progress.last_position` and `updated_at`;
6. set `completed_at` exactly when all active notes have answers;
7. commit once and return `SaveResult`.

On any exception, rollback and re-raise a domain error. Boolean input must be parsed strictly from form values `true` and `false`.

- [ ] **Step 5: Add labeling routes and screens**

Implement:

- `GET /labeling`: render both `RoundStatus` values;
- `GET /labeling/round/{round_number}`: redirect to first pending or transition/results;
- `GET /labeling/round/{round_number}/note/{note_id}`: render title, body, progress and only the round-2 definition when `round_number == 2`;
- `POST /labeling/round/{round_number}/note/{note_id}/label`: validate CSRF, parse label, call `save_annotation`, redirect to next pending or transition/results.

The round-1 template must not receive a `definition_text` key. The transition page must display the round-2 definition after round 1 completes.

- [ ] **Step 6: Add responsive task styling and duplicate-submit prevention**

Use CSS variables for colors, a readable `max-width`, large full-width mobile buttons and visible focus states. `static/app.js` listens to the label form submit event, disables both buttons, and adds `aria-busy="true"`. If an existing annotation is being changed, show `window.confirm("¿Cambiar esta clasificación?")`; cancel prevents submission. Do not use JavaScript to enforce authorization or hide the round-1 definition.

- [ ] **Step 7: Run focused route/service tests and commit**

Run:

```bash
python -m pytest tests/test_annotation_service.py tests/test_routes.py -q
```

Expected: all tests pass, including resume after a new client request, round-2 rejection before round-1 completion, exact definition visibility and round-1 lock enforcement.

Commit:

```bash
git add app/services/annotation_service.py app/routes/labeling.py app/templates/labeling static tests/test_annotation_service.py tests/test_routes.py
 git commit -m "feat: implement two-round annotation workflow"
```

---

## Task 5: Resultados por ronda y cambios entre rondas

**Files:**
- Create: `app/services/results_service.py`
- Create: `app/routes/results.py`
- Create: `app/templates/results/index.html`
- Test: `tests/test_results_service.py`
- Modify: `app/templates/labeling/dashboard.html`
- Modify: `app/main.py`

**Interfaces:**
- `build_round_results(db: Session, dataset_id: int, round_id: int, annotator_ids: Sequence[int]) -> RoundResults`.
- `build_study_results(db: Session, dataset_id: int, annotator_ids: Sequence[int]) -> StudyResults`.
- `RoundResults` includes `status`, `answered_notes`, `unanswered_notes`, `unanimity`, `pairwise`, `disagreements`, `per_user`.
- `StudyResults` includes `round_one`, `round_two`, `changes`, `overall_status`.

- [ ] **Step 1: Write failing metric tests with controlled labels**

Create a fixture with three annotators and three notes. Add tests asserting:


```python
def test_unanimity_excludes_single_response(seeded_db):
    # note 1: TRUE/TRUE, note 2: TRUE/FALSE/TRUE, note 3: one answer
    result = build_round_results(seeded_db, dataset_id=1, round_id=1, annotator_ids=[1, 2, 3])
    assert result.unanimity.comparable_notes == 2
    assert result.unanimity.agreements == 1
    assert result.unanimity.disagreements == 1
    assert result.unanimity.agreement_percent == 50.0


def test_pairwise_counts_each_available_pair(seeded_db):
    result = build_round_results(seeded_db, 1, 1, [1, 2, 3])
    assert result.pairwise.total_pairs == 4
    assert result.pairwise.agreements == 2
    assert result.pairwise.disagreements == 2


def test_changes_compare_same_user_and_note(seeded_db):
    result = build_study_results(seeded_db, 1, [1, 2, 3])
    assert result.changes.true_to_false == 1
    assert result.changes.false_to_true == 1
    assert result.changes.missing_excluded >= 0
```

Run `python -m pytest tests/test_results_service.py -q`; expected: FAIL because result types and functions are missing.

- [ ] **Step 2: Implement typed result structures and round status**

Use frozen dataclasses for `MetricSummary`, `PairwiseSummary`, `DisagreementRow`, `ChangeSummary`, `RoundResults` and `StudyResults`. Percentage helpers return `None` when the denominator is zero and round non-null percentages to two decimals. Determine a round’s `DEFINITIVO` status only when every active annotator has a completed progress row.

- [ ] **Step 3: Implement unanimity and pairwise algorithms**

Load active notes, active annotator names and annotations into dictionaries keyed by note ID. For each note with at least two responses, classify unanimity from the set of values. For pairs, iterate combinations of the response list and increment equal/different counts. Preserve response absence as `None` for the disagreement table; never count missing data as agreement.

- [ ] **Step 4: Implement disagreement rows and per-user totals**

Return only notes whose available values contain both `True` and `False`. Include `external_id`, title, position and a map of every active annotator’s display name to `True`, `False` or `None`. Compute per-user answered counts for the dashboard and admin view.

- [ ] **Step 5: Implement cross-round changes**

Join round-1 and round-2 annotations on `(user_id, note_id)`. Count `true_to_false`, `false_to_true`, `unchanged`, `comparable_labels` and `missing_excluded`. Return rows for every changed label with note and user identity.

- [ ] **Step 6: Add results route and templates**

`GET /results` calls `build_study_results` for the current dataset and active annotators. Render two clearly separated sections/tabs for rounds 1 and 2, each with `PARCIAL`/`DEFINITIVO`, answered coverage, unanimity, pairwise metrics and disagreement table. Render the changes summary below them. Use explicit denominator text such as `1 de 2 notas comparables` and `2 de 4 pares`.

- [ ] **Step 7: Verify result behavior and commit**

Run:

```bash
python -m pytest tests/test_results_service.py tests/test_routes.py -q
```

Expected: all result tests pass and `/results` is accessible to an authenticated annotator while reflecting partial completion.

Commit:

```bash
git add app/services/results_service.py app/routes/results.py app/templates/results app/templates/labeling/dashboard.html tests/test_results_service.py tests/test_routes.py
git commit -m "feat: add partial and final agreement results"
```

---

## Task 6: Administración de notas, importación y usuarios

**Files:**
- Create: `app/services/import_service.py`
- Create: `app/services/dataset_service.py`
- Create: `app/routes/admin.py`
- Create: `app/templates/admin/base.html`
- Create: `app/templates/admin/dashboard.html`
- Modify: `app/main.py`
- Create: `app/templates/admin/notes.html`
- Create: `app/templates/admin/note_form.html`
- Create: `app/templates/admin/import.html`
- Create: `app/templates/admin/users.html`
- Create: `app/templates/admin/user_form.html`
- Create: `app/templates/admin/progress.html`
- Create: `app/templates/admin/annotations.html`
- Create: `app/templates/admin/results.html`
- Test: `tests/test_import_service.py`
- Test: `tests/test_admin_routes.py`

**Interfaces:**
- `parse_notes_upload(filename: str, content: bytes) -> list[NotePayload]`.
- `replace_active_dataset(db: Session, name: str, notes: Sequence[NotePayload]) -> Dataset`.
- `NotePayload` contains `external_id`, `position`, `title`, `text`, optional metadata and dates.
- Admin routes use `require_admin` and never reuse annotator-only templates.

- [ ] **Step 1: Write failing parser tests**

Test valid JSON array, JSON object with `notes`, valid CSV, missing required fields, duplicate IDs, invalid dates, invalid metadata JSON and unsupported extensions. Assert errors include row number and field name, for example:

```python
def test_duplicate_ids_are_rejected():
    with pytest.raises(ImportValidationError, match=r"fila 2.*id duplicado"):
        parse_notes_upload("notas.json", b'[{"id":"a","titulo":"A","texto":"x"},{"id":"a","titulo":"B","texto":"y"}]')
```

Run `python -m pytest tests/test_import_service.py -q`; expected: FAIL because parser code is missing.

- [ ] **Step 2: Implement JSON and CSV validation**

Accept required keys `id`, `titulo`, `texto`. Accept aliases `fecha`, `medio`, `url`, `seccion`, `metadata`; accept `position` when present and otherwise assign one-based input order. Reject empty required strings, duplicate IDs, positions below 1, duplicate positions, malformed UTF-8, invalid ISO dates and metadata values that are not JSON objects. Return normalized `NotePayload` objects without touching the database.

- [ ] **Step 3: Implement atomic dataset replacement**

`replace_active_dataset` must run in the caller’s transaction:

1. archive the current active dataset and set `archived_at`;
2. create the new active dataset;
3. create round 1 with no definition and round 2 with `ROUND_TWO_DEFINITION`;
4. insert normalized notes with their positions and metadata;
5. commit only after every insert succeeds.

If any insert fails, rollback leaves the old active dataset unchanged. Existing annotations remain linked to archived rounds.

- [ ] **Step 4: Implement administrative note CRUD**

Add forms and routes for listing/searching, adding, editing and logical deletion of active notes. Require CSRF for all writes. Validate title/text/id exactly as the parser does. Deleting a note sets `deleted_at` and displays a confirmation containing the title; current progress and result queries exclude it while its annotations remain queryable in admin history.

- [ ] **Step 5: Implement import route and user management**

`GET /admin/import` renders file and dataset-name fields. `POST /admin/import` reads `UploadFile`, parses fully before calling `replace_active_dataset`, displays row-level errors without changing data, and redirects to `/admin` on success. `/admin/users` lists users and supports create, activate/deactivate and password reset with Argon2 hashing. Prevent deactivating the last active admin and prevent creating duplicate usernames.

- [ ] **Step 6: Implement administrative queries**

Add `/admin/progress` with a table of username, round, answered/total, completed timestamp and status. Add `/admin/annotations` with filters for username, round number, external note ID and date range. Add `/admin/results` using the same `build_study_results` service plus archived-dataset selection when requested. Every page uses `app/templates/admin/base.html` and has no annotator task buttons.

- [ ] **Step 7: Run admin/import tests and commit**

Run:

```bash
python -m pytest tests/test_import_service.py tests/test_admin_routes.py -q
```

Expected: all parser, atomic replacement, authorization, CRUD, user and query tests pass. Confirm a failed import leaves the original active dataset ID unchanged.

Commit:

```bash
git add app/services/import_service.py app/services/dataset_service.py app/routes/admin.py app/templates/admin tests/test_import_service.py tests/test_admin_routes.py
git commit -m "feat: add administrative note and user management"
```

---

## Task 7: Integración visual, documentación y contenedorización

**Files:**
- Modify: `static/styles.css`
- Modify: `app/templates/base.html`
- Modify: all templates under `app/templates/`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Modify: `.env.example`
- Create: `README.md`
- Modify: `scripts/load_notes.py`

**Interfaces:**
- README commands must work from a clean checkout on Windows and Linux.
- Docker container stores SQLite at `/app/data/app.db` and exposes port 8000.
- CLI loader calls `parse_notes_upload` and `replace_active_dataset` rather than duplicating parsing.

- [ ] **Step 1: Finish responsive and accessible UI**

Define CSS for a 700px reading column, 44px minimum button height, high-contrast `CONFLICTO`/`NO CONFLICTO` states, visible keyboard focus, responsive tables and a distinct admin color accent. Ensure each form has labels, errors, `aria-live` feedback and no color-only meaning. Add a `noscript` message explaining that classification still works through normal form submission but duplicate-submit prevention is unavailable.

- [ ] **Step 2: Add production container and compose volume**

Use this container contract:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic
COPY data ./data
COPY scripts ./scripts
COPY static ./static
RUN pip install --no-cache-dir .
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["sh", "-c", "python scripts/init_db.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

`docker-compose.yml` must define service `web`, read `.env`, publish `8000:8000`, and mount `./data:/app/data`. Do not mount source code in the production-style compose file.

- [ ] **Step 3: Add CLI note replacement**

Implement `scripts/load_notes.py` with arguments `--file` and `--name`, read bytes, call `parse_notes_upload`, call `replace_active_dataset`, and print the created dataset ID and note count. Exit with code 2 and print each validation error to stderr without changing the database.

- [ ] **Step 4: Write complete README and environment example**

Document:

- Python virtual environment creation on Windows PowerShell and Linux;
- `pip install -e ".[test]"`;
- `copy .env.example .env` on PowerShell and `cp .env.example .env` on Linux;
- `python scripts/init_db.py`;
- `uvicorn app.main:app --reload`;
- demo credentials and local-only warning;
- URLs for annotator, results and admin;
- JSON/CSV schemas with required and optional fields;
- admin import behavior and logical deletion;
- `docker compose up --build`;
- VPS outline: persistent data volume, production secret, `SESSION_COOKIE_SECURE=true`, reverse proxy, HTTPS and backups of SQLite;
- how to run tests and the smoke command.

Do not put real production passwords in the README or `.env.example`; demo credentials must be explicitly marked local-only.

- [ ] **Step 5: Run package, container and documentation checks, then commit**

Run:

```bash
python -m pytest -q
python scripts/load_notes.py --help
python -m compileall app scripts
```

Expected: all tests pass, help shows `--file` and `--name`, and compilation exits successfully. Build the image with `docker compose build`; expected: successful image build.

Commit:

```bash
git add static app/templates Dockerfile docker-compose.yml .env.example README.md scripts/load_notes.py
 git commit -m "docs: package app for local and VPS deployment"
```

---

## Task 8: Smoke test end-to-end y revisión final

**Files:**
- Create: `scripts/smoke_test.py`
- Modify: `README.md` if command details need correction

**Interfaces:**
- `scripts/smoke_test.py` uses `httpx.Client` against `http://127.0.0.1:8000` and exits non-zero on any failed assertion.

- [ ] **Step 1: Implement the real-flow smoke script**

The script must:

1. log in as `ana`;
2. assert dashboard shows `Ronda 1` and `0/10`;
3. submit notes 1–10 in round 1 with alternating values;
4. assert round 1 becomes locked and round 2 transition includes the exact approved definition;
5. submit notes 1–10 in round 2;
6. reload dashboard and assert both rounds show `10/10`;
7. request `/results` and assert `Ronda 1`, `Ronda 2`, `PARCIAL` or `DEFINITIVO`, `coincidencias`, `desacuerdos` and `cambios` appear;
8. log in as `admin`, assert `/admin` succeeds and `/labeling` is not the admin landing page;
9. assert an annotator session receives a redirect from `/admin`.

Use the actual form CSRF token from each response and follow redirects explicitly so the script tests the production route contract rather than calling services directly.

- [ ] **Step 2: Run the full verification suite**

Run:

```bash
python -m pytest -q
python scripts/init_db.py
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal run:

```bash
python scripts/smoke_test.py
```

Expected: pytest passes, the server starts, and the smoke script exits 0 after exercising both rounds, partial/final results and admin separation. Stop the server after the script completes.

- [ ] **Step 3: Verify import replacement and resume behavior manually**

Start from a copy of the demo database, label at least two notes as `bruno`, stop/restart the server, and assert the dashboard opens the first unanswered note rather than resetting progress. Run a valid five-note replacement file through the admin import or CLI, assert a new active dataset is created, and assert the old dataset is archived with its annotations preserved.

- [ ] **Step 4: Perform final quality checks**

Run:

```bash
python -m pytest --cov=app --cov-report=term-missing
python -m compileall app scripts
```

Inspect the final files for accidental secrets, debug prints, unresolved implementation markers, templates that expose the round-2 definition in round 1, and routes that write with `GET`. Correct any finding, rerun the affected focused test, then commit:

```bash
git add scripts/smoke_test.py README.md app tests
 git commit -m "test: verify complete collaborative labeling flow"
```

The final response must cite the exact verification commands and observed results; do not claim completion before the smoke script succeeds.
