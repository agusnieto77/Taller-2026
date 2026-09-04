# Guía de despliegue en VPS

Esta guía permite desplegar la aplicación desde cero en un VPS Ubuntu 24.04, clonando la rama `main` del repositorio. La configuración recomendada usa SQLite, Uvicorn, systemd, Nginx y HTTPS.

## 1. Arquitectura del despliegue

```text
Internet → Nginx :80/:443 → Uvicorn 127.0.0.1:8000 → SQLite
```

Decisiones importantes:

- Python 3.12 o superior es obligatorio.
- Uvicorn escucha únicamente en `127.0.0.1`; el puerto 8000 no se expone a Internet.
- Se usa un solo worker porque la base predeterminada es SQLite.
- Nginx sirve como proxy inverso y termina HTTPS.
- systemd mantiene la aplicación activa y la reinicia ante fallos.
- La base `data/app.db` y el archivo `.env` son locales al servidor y no se guardan en Git.

## 2. Datos necesarios antes de comenzar

El agente debe disponer de:

- Acceso `sudo` o `root` al VPS.
- Ubuntu 24.04 o una distribución equivalente con Python 3.12.
- Un dominio o subdominio apuntando a la IP pública del VPS, si se usará HTTPS.
- Puertos TCP 22, 80 y 443 habilitados.

En los ejemplos se usan estos valores:

```text
Repositorio: https://github.com/agusnieto77/Taller-2026.git
Rama: main
Directorio: /opt/taller/app
Usuario del servicio: taller
Dominio de ejemplo: etiquetado.example.com
```

Reemplazar `etiquetado.example.com` por el dominio real en todos los comandos.

## 3. Instalar dependencias del sistema

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nginx curl ufw openssl
python3 --version
```

La versión informada debe ser 3.12 o superior. Si `python3` apunta a una versión anterior, instalar Python 3.12 y usar `python3.12` en los comandos posteriores.

Para HTTPS también se necesita Certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
```

## 4. Crear el usuario del servicio y clonar el repositorio

```bash
sudo useradd --system --create-home --home-dir /opt/taller --shell /usr/sbin/nologin taller
sudo -u taller git clone --branch main --single-branch \
  https://github.com/agusnieto77/Taller-2026.git /opt/taller/app
cd /opt/taller/app
```

Si el usuario `taller` ya existe, `useradd` puede responder que está creado; continuar después de verificar:

```bash
id taller
sudo chown -R taller:taller /opt/taller
```

## 5. Crear el entorno virtual e instalar la aplicación

```bash
sudo -u taller python3 -m venv /opt/taller/app/.venv
sudo -u taller /opt/taller/app/.venv/bin/python -m pip install --upgrade pip
sudo -u taller /opt/taller/app/.venv/bin/python -m pip install /opt/taller/app
```

Comprobar la instalación:

```bash
sudo -u taller /opt/taller/app/.venv/bin/python -c "import fastapi, sqlalchemy, uvicorn; print('dependencias ok')"
```

## 6. Crear la configuración de producción

Generar un secreto aleatorio:

```bash
SECRET_KEY="$(openssl rand -hex 32)"
echo "$SECRET_KEY"
```

Crear `/opt/taller/app/.env`:

```bash
sudo tee /opt/taller/app/.env > /dev/null <<EOF
APP_ENV=production
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=sqlite:///./data/app.db
SESSION_COOKIE_NAME=labeling_session
SESSION_COOKIE_SECURE=true
SEED_DEMO_DATA=true
HOST=127.0.0.1
PORT=8000
EOF
sudo chown taller:taller /opt/taller/app/.env
sudo chmod 600 /opt/taller/app/.env
```

Reglas:

- Nunca usar `local-only-change-me` como `SECRET_KEY` en producción.
- Con HTTPS, `SESSION_COOKIE_SECURE` debe ser `true`.
- Si se desplegará temporalmente solo por HTTP y por IP, usar `SESSION_COOKIE_SECURE=false`; volver a `true` inmediatamente después de habilitar HTTPS.
- No copiar el `.env` a Git ni compartir su secreto.

## 7. Inicializar la base de datos

El comando siguiente aplica las migraciones y carga las notas y usuarios iniciales:

```bash
cd /opt/taller/app
sudo -u taller /opt/taller/app/.venv/bin/python scripts/init_db.py
sudo chown -R taller:taller /opt/taller/app/data
```

La carga inicial crea:

- Un administrador: `admin` / `local-only-admin-2026`.
- Veinte anotadores: `user01` / `user@01` hasta `user20` / `user@20`.

Estas credenciales son conocidas porque forman parte de los datos iniciales. Después del primer ingreso, cambiar la contraseña del administrador desde **Administración → Usuarios → Contraseña**.

Verificar que la base exista:

```bash
sudo -u taller test -s /opt/taller/app/data/app.db
echo "base de datos creada"
```

## 8. Configurar el servicio systemd

Crear `/etc/systemd/system/taller.service`:

```bash
sudo tee /etc/systemd/system/taller.service > /dev/null <<'EOF'
[Unit]
Description=Aplicación de etiquetado colaborativo
After=network.target

[Service]
Type=simple
User=taller
Group=taller
WorkingDirectory=/opt/taller/app
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/taller/app/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/taller/app/data

[Install]
WantedBy=multi-user.target
EOF
```

Activar y arrancar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now taller
sudo systemctl status taller --no-pager
```

Comprobar el backend directamente desde el VPS:

```bash
curl -fsS http://127.0.0.1:8000/health
echo
```

La respuesta correcta es:

```json
{"status":"ok"}
```

Si falla:

```bash
sudo journalctl -u taller -n 100 --no-pager
```

No continuar con Nginx hasta que `/health` responda correctamente.

## 9. Configurar Nginx

Crear `/etc/nginx/sites-available/taller` y sustituir el dominio:

```bash
sudo tee /etc/nginx/sites-available/taller > /dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name etiquetado.example.com;

    client_max_body_size 20M;

    location /static/ {
        alias /opt/taller/app/static/;
        expires 7d;
        add_header Cache-Control "public, max-age=604800";
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
EOF
```

Habilitar el sitio:

```bash
sudo ln -sfn /etc/nginx/sites-available/taller /etc/nginx/sites-enabled/taller
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

Comprobar por HTTP:

```bash
curl -fsS http://etiquetado.example.com/health
```

Debe devolver estado `200`.

## 10. Habilitar HTTPS

El DNS debe resolver al VPS antes de ejecutar Certbot:

```bash
getent hosts etiquetado.example.com
sudo certbot --nginx -d etiquetado.example.com
```

Elegir la redirección automática de HTTP a HTTPS. Después verificar:

```bash
curl -fsS https://etiquetado.example.com/health
echo
sudo certbot renew --dry-run
```

Abrir en un navegador:

```text
https://etiquetado.example.com/login
```

Confirmar que el certificado sea válido, que el login funcione y que la cookie de sesión tenga el atributo `Secure`.

## 11. Configurar el firewall

Antes de activar UFW, habilitar SSH para evitar perder acceso:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

No abrir el puerto 8000. Uvicorn debe continuar escuchando solo en `127.0.0.1`.

## 12. Lista de verificación final

Ejecutar y validar todos los puntos:

```bash
sudo systemctl is-active --quiet taller && echo "taller: activo"
sudo systemctl is-active --quiet nginx && echo "nginx: activo"
curl -fsS http://127.0.0.1:8000/health
curl -fsS https://etiquetado.example.com/health
sudo ss -ltnp | grep -E ':80|:443|127.0.0.1:8000'
```

Verificación funcional en navegador:

1. Ingresar como `admin` y abrir todas las secciones de administración.
2. Confirmar que aparecen exactamente 20 anotadores activos.
3. Cambiar la contraseña inicial del administrador.
4. Ingresar con `user01` / `user@01`.
5. Clasificar una nota y comprobar que el progreso cambie.
6. Cerrar sesión y volver a ingresar para confirmar persistencia.
7. Revisar la interfaz desde un teléfono o una ventana angosta.

## 13. Actualizar una instalación existente

Crear primero un respaldo y luego actualizar con avance lineal de Git:

```bash
sudo systemctl stop taller
sudo cp /opt/taller/app/data/app.db \
  "/opt/taller/app/data/app.db.backup-$(date +%Y%m%d-%H%M%S)"
cd /opt/taller/app
sudo -u taller git pull --ff-only origin main
sudo -u taller /opt/taller/app/.venv/bin/python -m pip install /opt/taller/app
sudo -u taller /opt/taller/app/.venv/bin/alembic upgrade head
sudo systemctl start taller
curl -fsS http://127.0.0.1:8000/health
```

No volver a ejecutar `scripts/init_db.py` durante una actualización normal: además de migrar, ese script sincroniza los datos iniciales. Para una actualización se usa únicamente `alembic upgrade head`.

Si `git pull --ff-only` falla, detener el despliegue y revisar los cambios locales. No usar `git reset --hard` ni borrar archivos sin identificar primero qué se perdería.

## 14. Respaldo y restauración de SQLite

Para obtener un respaldo consistente, detener brevemente las escrituras:

```bash
sudo systemctl stop taller
sudo cp /opt/taller/app/data/app.db /var/backups/taller-app-$(date +%Y%m%d-%H%M%S).db
sudo systemctl start taller
```

Restaurar un respaldo:

```bash
sudo systemctl stop taller
sudo cp /var/backups/ARCHIVO.db /opt/taller/app/data/app.db
sudo chown taller:taller /opt/taller/app/data/app.db
sudo systemctl start taller
curl -fsS http://127.0.0.1:8000/health
```

Conservar respaldos fuera del VPS o sincronizarlos periódicamente con almacenamiento externo.

## 15. Diagnóstico rápido

### El servicio no inicia

```bash
sudo systemctl status taller --no-pager
sudo journalctl -u taller -n 200 --no-pager
```

Comprobar que `.env` tenga un `SECRET_KEY` distinto del valor local y que `data/` pertenezca a `taller`.

### Error 502 de Nginx

```bash
curl -v http://127.0.0.1:8000/health
sudo nginx -t
sudo journalctl -u nginx -n 100 --no-pager
```

Un 502 indica normalmente que Uvicorn no está activo o que Nginx apunta a un puerto incorrecto.

### El login vuelve a la misma página

- Confirmar que se accede por HTTPS si `SESSION_COOKIE_SECURE=true`.
- Revisar fecha y hora del VPS con `timedatectl`.
- Comprobar que el navegador acepta cookies.
- Revisar `journalctl -u taller`.

### Base de datos de solo lectura

```bash
sudo chown -R taller:taller /opt/taller/app/data
sudo chmod 750 /opt/taller/app/data
sudo chmod 640 /opt/taller/app/data/app.db
sudo systemctl restart taller
```

### Los estilos no cargan

```bash
curl -I https://etiquetado.example.com/static/styles.css
namei -l /opt/taller/app/static/styles.css
```

Nginx debe poder atravesar `/opt/taller/app` y leer el contenido de `static/`.

## 16. Despliegue sin dominio, solo para evaluación temporal

Si todavía no existe un dominio:

1. Configurar `SESSION_COOKIE_SECURE=false` en `.env`.
2. Usar Nginx con `server_name _;` y solo el puerto 80.
3. Acceder a `http://IP_DEL_VPS/login`.
4. No exponer directamente el puerto 8000.
5. Migrar a HTTPS y volver a `SESSION_COOKIE_SECURE=true` antes de usar datos reales.

Este modo no es adecuado para producción porque las credenciales y cookies viajan sin cifrado.
