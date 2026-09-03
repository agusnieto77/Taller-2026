# Diseño: etiquetado colaborativo de notas periodísticas

**Fecha:** 2026-09-03  
**Estado:** diseño validado en conversación; pendiente de revisión del documento  
**Alcance:** primera versión funcional local, preparada para VPS Linux

## 1. Objetivo y alcance

La aplicación permitirá que varios anotadores identificados clasifiquen el mismo conjunto de notas periodísticas con una variable binaria:

- `TRUE` / `CONFLICTO`
- `FALSE` / `NO CONFLICTO`

Cada anotador completará dos rondas independientes sobre las mismas notas, siempre de la nota 1 a la última:

1. ronda ciega, sin mostrar la definición de conflicto;
2. ronda con una definición explícita visible.

Las respuestas se persistirán inmediatamente, el progreso podrá reanudarse y los resultados mostrarán coincidencias, desacuerdos y cambios entre rondas. La primera versión no implementará todavía Cohen’s Kappa, Fleiss’ Kappa u otras métricas, pero aislará el cálculo de resultados para incorporarlas después.

No se incluirán funcionalidades ajenas al etiquetado, como mensajería, perfiles sociales, notificaciones o un sistema de asignaciones por subconjuntos. Todos los anotadores activos trabajarán sobre el conjunto global activo.

## 2. Arquitectura elegida

Se implementará un monolito server-rendered:

- **Backend:** FastAPI.
- **Templates:** Jinja2.
- **Persistencia:** SQLAlchemy 2.0 con SQLite por defecto.
- **Migraciones:** Alembic.
- **Frontend:** HTML/CSS y JavaScript mínimo, sin SPA ni build frontend.
- **Sesiones:** cookie firmada mediante middleware de Starlette.
- **Contraseñas:** hash Argon2.
- **Pruebas:** pytest y TestClient de FastAPI.

La aplicación utilizará rutas síncronas y sesiones de SQLAlchemy síncronas para mantener el código pequeño y directo. `DATABASE_URL` permitirá cambiar SQLite por PostgreSQL posteriormente sin trasladar la lógica de negocio a las rutas.

Estructura prevista:

```text
app/
  main.py
  config.py
  database.py
  models/
  repositories/
  services/
  routes/
  templates/
static/
data/
  seed/
scripts/
alembic/
tests/
Dockerfile
.env.example
README.md
pyproject.toml
```

La lógica de dominio quedará fuera de los templates y de los handlers HTTP. En particular, el guardado de etiquetas, las reglas de transición de rondas, la agregación de resultados y la importación masiva serán servicios independientes y testeables.

## 3. Modelo de datos

### 3.1 `users`

- `id`
- `username`, único
- `display_name`
- `password_hash`
- `role`: `annotator` o `admin`
- `active`
- `created_at`
- `updated_at`

No habrá registro público. El administrador podrá crear, activar, desactivar y actualizar credenciales de usuarios.

### 3.2 `datasets`

- `id`
- `name`
- `status`: `active` o `archived`
- `created_at`
- `archived_at` opcional

Solo existirá un conjunto activo. El reemplazo no borrará la versión anterior: creará un conjunto nuevo y archivará el anterior, manteniendo separadas las etiquetas históricas.

### 3.3 `notes`

- `id`, clave interna
- `dataset_id`
- `external_id`, identificador estable provisto en JSON/CSV, único dentro del conjunto
- `position`
- `title`
- `text`
- `published_at` opcional
- `outlet` opcional
- `url` opcional
- `section` opcional
- `metadata_json` opcional
- `deleted_at` opcional
- `created_at`
- `updated_at`

En los archivos de carga, el campo obligatorio `id` se conservará como `external_id`. Las consultas del trabajo utilizarán solo notas del conjunto activo cuyo `deleted_at` sea nulo, ordenadas por `position`.

La eliminación administrativa será lógica: la nota sale del trabajo vigente, pero sus etiquetas permanecen disponibles para auditoría histórica.

### 3.4 `annotation_rounds`

- `id`
- `dataset_id`
- `round_number`: `1` o `2`
- `name`
- `definition_text` opcional
- `definition_visible`
- restricción única `(dataset_id, round_number)`

Cada conjunto se crea con exactamente dos rondas. La ronda 1 no tendrá definición visible. La ronda 2 almacenará la definición entregada para el estudio y la mostrará literalmente.

### 3.5 `annotations`

- `id`
- `user_id`
- `round_id`
- `note_id`
- `value`, booleano
- `created_at`
- `updated_at`
- restricción única `(user_id, round_id, note_id)`

La clasificación inicial inserta la fila. Una corrección actualiza la misma fila y `updated_at`; nunca se crea una etiqueta duplicada.

### 3.6 `progress`

- `id`
- `user_id`
- `dataset_id`
- `round_id`
- `last_position`
- `completed_at` opcional
- `updated_at`
- restricción única `(user_id, round_id)`

La cantidad respondida se calcula desde `annotations` para evitar un contador desincronizado. La posición, el estado de finalización y sus marcas de tiempo quedan persistidos para reanudar el trabajo.

## 4. Rondas y flujo de etiquetado

1. El usuario inicia sesión.
2. El dashboard muestra el progreso de ambas rondas.
3. La primera acción disponible es comenzar o continuar la ronda 1.
4. Cada nota se muestra en orden con `Nota X de N`.
5. En ronda 1 no aparece la definición de conflicto.
6. El usuario pulsa `CONFLICTO` o `NO CONFLICTO`.
7. El servidor valida el estado y guarda etiqueta y progreso en una transacción.
8. La respuesta HTTP usa el patrón Post/Redirect/Get y dirige a la siguiente nota pendiente. La ruta de continuar no permitirá saltar notas no respondidas: siempre abrirá la primera pendiente. Se podrán revisar y corregir notas anteriores de la ronda actual, pero la ronda solo se completará cuando todas estén respondidas.
9. Al responder la última nota, la ronda 1 queda completada y bloqueada.
10. El usuario ve una pantalla de transición con la definición de la ronda 2.
11. La ronda 2 se habilita para ese usuario inmediatamente, sin esperar a otros anotadores.
12. La definición permanece visible en cada pantalla de la ronda 2.
13. La ronda 2 puede corregirse incluso después de completada, porque la corrección fue aprobada para el flujo general.

Mientras la ronda 1 esté en curso, el usuario puede volver a notas ya respondidas y corregirlas. Después de `completed_at`, el servidor rechazará cualquier modificación de ronda 1 aunque se intente llamar directamente a la ruta.

Todas las escrituras se ejecutarán dentro de una transacción. Un fallo de persistencia hará rollback tanto de la etiqueta como del progreso.

### Definición de la ronda 2

Se mostrará exactamente este texto, sin resumirlo ni reescribirlo:

> Una protesta es una reunión de al menos 50 personas que expresa públicamente una demanda, reclamo u oposición dirigida al gobierno. La acción debe tener como blanco principal a una autoridad estatal, una política pública, una decisión gubernamental o alguna otra forma de intervención del Estado. Quedan fuera de esta definición las acciones protagonizadas por grupos más pequeños, así como aquellas dirigidas exclusivamente contra empresas, organizaciones privadas u otros actores no estatales. La protesta se concibe, por lo tanto, como una forma de movilización colectiva de cierta magnitud orientada explícitamente hacia el poder público.

## 5. Rutas e interfaz de anotadores

Rutas principales:

- `GET /login`: formulario de ingreso.
- `POST /login`: autentica y crea sesión.
- `POST /logout`: cierra sesión.
- `GET /`: redirige según autenticación y rol.
- `GET /labeling`: dashboard personal.
- `GET /labeling/round/{round_number}`: abre la primera nota pendiente.
- `GET /labeling/round/{round_number}/note/{note_id}`: muestra una nota.
- `POST /labeling/round/{round_number}/note/{note_id}/label`: guarda clasificación y redirige.
- `GET /labeling/round/{round_number}/transition`: pantalla de transición cuando corresponda.
- `GET /results`: resultados disponibles.

El dashboard mostrará nombre, estado por ronda, `respondidas/total`, botones de continuar o revisar y el acceso a resultados.

La pantalla de nota priorizará lectura y velocidad:

- título destacado;
- cuerpo con ancho de lectura limitado y tipografía legible;
- metadatos solo cuando existan;
- definición de ronda 2 en un bloque claramente separado;
- botones grandes con textos completos y colores consistentes;
- estado seleccionado cuando la nota ya tenga respuesta;
- controles deshabilitados durante el envío para evitar doble clic;
- confirmación adicional al modificar una respuesta existente, cuando corresponda.

El diseño será responsive y accesible mediante teclado. No se ocultará la definición en ronda 1 solo con CSS: el servidor no la enviará al template de esa ronda.

## 6. Panel administrativo

El panel vivirá bajo `/admin` y utilizará layout, navegación y estilos separados de la tarea de etiquetado.

Rutas y capacidades:

- `/admin`: resumen general del conjunto activo.
- `/admin/notes`: listar y buscar notas.
- `/admin/notes/new`: agregar notas.
- `/admin/notes/{id}/edit`: editar notas.
- `POST /admin/notes/{id}/delete`: retirar notas lógicamente.
- `/admin/import`: reemplazar el conjunto con JSON o CSV.
- `/admin/users`: consultar, crear, activar/desactivar usuarios y cambiar credenciales.
- `/admin/progress`: progreso de cada usuario por ronda.
- `/admin/annotations`: consultar etiquetas con filtros de usuario, ronda, nota y fecha.
- `/admin/results`: resultados de ambas rondas y cambios entre ellas.

La importación exigirá `id`, `titulo` y `texto`. Admitirá `fecha`, `medio`, `url`, `seccion` y metadatos adicionales. El archivo completo se validará antes de abrir una transacción de reemplazo. IDs duplicados, campos obligatorios vacíos, posiciones inválidas o formatos no soportados dejarán intacto el conjunto activo y mostrarán errores por fila.

## 7. Resultados y métricas

El servicio de resultados recibirá `dataset_id`, `round_id` y la lista de anotadores activos; no dependerá de una vista concreta.

### Estado

- Una ronda es `DEFINITIVA` cuando todos los anotadores activos tienen `completed_at` para esa ronda.
- En caso contrario es `PARCIAL`.
- El estudio completo solo será definitivo cuando todos hayan completado ambas rondas.
- Los usuarios inactivos no se incluyen en el denominador del conjunto vigente.

### Unanimidad por nota

Para cada nota con al menos dos respuestas:

- coincidencia si todas las etiquetas disponibles son iguales;
- desacuerdo si hay valores diferentes;
- porcentaje sobre las notas comparables.

Las notas con cero o una respuesta se informarán aparte y no se presentarán como coincidencias.

### Comparación por pares

Para cada nota se comparan todos los pares de anotadores que respondieron:

- total de pares: `k × (k - 1) / 2`;
- pares coincidentes: mismos valores;
- pares discordantes: valores diferentes;
- porcentajes sobre el total de pares comparables.

La tabla de desacuerdos mostrará nota, título y clasificación de cada anotador; una persona sin respuesta figurará como pendiente.

### Cambios entre rondas

Se comparará cada combinación usuario-nota con respuestas presentes en ambas rondas:

- sin cambio: `TRUE → TRUE` o `FALSE → FALSE`;
- cambio: `TRUE → FALSE` o `FALSE → TRUE`;
- respuestas faltantes excluidas y contabilizadas como cobertura incompleta.

Los resultados se mostrarán separados por ronda y con un resumen de cambios. La interfaz dejará una extensión clara para registrar métricas futuras con una abstracción de métrica, sin agregar Kappa a esta versión.

## 8. Autenticación, autorización y seguridad

- Usuarios identificados por `username` único.
- Contraseñas con Argon2; nunca se guardan en texto plano.
- La sesión contiene únicamente el identificador necesario y se firma con `SECRET_KEY`.
- Cookie `HttpOnly`, `SameSite=Lax` y `Secure` configurable; en VPS se habilitará `Secure`.
- Token CSRF en formularios que modifican datos.
- Toda ruta administrativa verifica el rol en el servidor.
- No habrá registro público ni acceso anónimo a notas o resultados.
- Se validarán pertenencia al conjunto, ronda habilitada, nota vigente y estado de bloqueo antes de cada escritura.
- Los logs no incluirán contraseñas ni contenido innecesario de etiquetas.

## 9. Datos iniciales y archivos externos

El repositorio incluirá:

- 10 notas ficticias en JSON, fuera de templates y código de interfaz;
- varios anotadores demo con credenciales documentadas para local;
- al menos un administrador demo;
- un script idempotente de inicialización que crea el esquema, conjunto, rondas, usuarios y notas si no existen.

El administrador podrá reemplazar los datos reales desde el panel sin editar código. También podrá usar el mismo formato JSON/CSV desde la línea de comandos si se incluye una utilidad de carga.

## 10. Configuración y despliegue

`.env.example` documentará como mínimo:

- `APP_ENV`;
- `SECRET_KEY`;
- `DATABASE_URL`;
- credenciales del administrador inicial para la semilla;
- `SESSION_COOKIE_SECURE`;
- URL/host y puerto de ejecución.

Localmente se ejecutará con:

```bash
uvicorn app.main:app --reload
```

El proyecto incluirá Dockerfile con volumen para `data/`, migraciones explícitas y una orden de inicialización separada. En VPS Linux se recomienda ejecutar detrás de Nginx o Caddy con HTTPS y un servidor ASGI de producción. No habrá rutas ni scripts dependientes de Windows.

## 11. Verificación

Pruebas automatizadas:

- autenticación, hash y roles;
- restricción única de etiquetas;
- guardado inmediato y reanudación;
- corrección durante ronda 1 y bloqueo posterior;
- desbloqueo individual de ronda 2;
- ocultamiento de definición en ronda 1 y visualización exacta en ronda 2;
- progreso independiente por usuario y ronda;
- resultados parciales y definitivos;
- unanimidad, comparación por pares y cambios entre rondas;
- importación JSON/CSV atómica y validación por fila;
- permisos y operaciones administrativas;
- retiro lógico de notas.

También se ejecutará un smoke test sobre la aplicación iniciada realmente con los datos demo: login de anotador, etiquetado de ambas rondas, persistencia tras recarga, consulta de resultados y acceso administrativo.

## 12. Criterios de aceptación

La primera versión se considerará funcional cuando:

1. usuarios distintos puedan iniciar sesión con identidades diferenciadas;
2. cada uno pueda completar las mismas notas dos veces;
3. la ronda 1 no exponga la definición;
4. la ronda 2 exponga exactamente la definición aprobada;
5. las respuestas se guarden inmediatamente sin duplicados;
6. el progreso sobreviva al cierre y reapertura;
7. la ronda 1 se bloquee tras completarse;
8. los resultados distingan estado parcial y definitivo;
9. se muestren coincidencias, desacuerdos, porcentajes, notas conflictivas y etiquetas por usuario;
10. se muestren cambios entre rondas;
11. el administrador pueda administrar notas, usuarios, progreso, etiquetas, resultados e importaciones;
12. el conjunto de notas pueda reemplazarse sin modificar el código de interfaz;
13. la aplicación pueda ejecutarse localmente y esté documentada para VPS.
