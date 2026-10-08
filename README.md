# Butaca Cero

Backend Django dockerizado con PostgreSQL.

## Levantar

Crear el `.env` local:

```powershell
Copy-Item .env.example .env
```

Editar `.env` y cambiar los valores `change-me...`.

Levantar contenedores:

```powershell
docker compose up --build
```

La app queda en:

```text
http://localhost:8000
```

Si se cambia el `.env` con Docker ya levantado, recrear el contenedor web:

```powershell
docker compose up -d --force-recreate web
```

## URLs utiles

```text
Login:  http://localhost:8000/login/
Signup: http://localhost:8000/signup/
Admin:  http://localhost:8000/admin/
Health: http://localhost:8000/health/
```

## Primer acceso admin

Crear el primer superusuario de Django:

```powershell
docker compose exec web python manage.py createsuperuser
```

Entrar a:

```text
http://localhost:8000/admin/
```

Con ese superusuario, crear el primer usuario gerente:

1. Crear un usuario normal desde `Users`.
2. Asignarle email y password.
3. Crear/asociar un perfil `Gerente`.

El admin queda solo para uso excepcional/sysadmin. El uso normal va a ir por pantallas propias.

## Comandos utiles

Ver estado:

```powershell
docker compose ps
```

Ver logs:

```powershell
docker compose logs -f web
```

Correr tests:

```powershell
docker compose run --rm web python manage.py test
```

Crear migraciones:

```powershell
docker compose exec web python manage.py makemigrations
```

Aplicar migraciones:

```powershell
docker compose exec web python manage.py migrate
```

Apagar:

```powershell
docker compose down
```

Borrar contenedores y base local:

```powershell
docker compose down -v
```

## Deploy en Render

El repo incluye `render.yaml` para crear un Blueprint con:

- un Web Service Docker para Django;
- una base PostgreSQL administrada;
- `DATABASE_URL`, `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY` generado por Render y `DJANGO_ALLOWED_HOSTS` conectado al hostname del servicio;
- health check en `/health/`.

Pasos:

1. Subir la rama con los cambios a GitHub.
2. En Render, crear un Blueprint desde este repositorio y elegir la rama que contiene `render.yaml`.
3. Esperar el primer deploy. El contenedor ejecuta `collectstatic` y `migrate` antes de iniciar Gunicorn.
4. Si el plan permite Shell, crear el superusuario desde la Shell de Render:

```bash
python manage.py createsuperuser
```

En el plan free de Render no hay Shell. Para crear el primer admin, configurar temporalmente estas variables en el Web Service y hacer un redeploy:

```text
DJANGO_CREATE_SUPERUSER=True
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=una-password-segura
```

El deploy crea el usuario si no existe. Despues de entrar al admin, cambiar la password si hace falta y borrar `DJANGO_CREATE_SUPERUSER` o cambiarla a `False`.

Si se agrega un dominio propio, sumar el hostname a `DJANGO_ALLOWED_HOSTS` y el origen HTTPS a `DJANGO_CSRF_TRUSTED_ORIGINS`, por ejemplo:

```text
DJANGO_ALLOWED_HOSTS=butaca-cero.onrender.com,mi-dominio.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://mi-dominio.com
```

En producción, Django usa SMTP por defecto para no depender del backend de consola. Si la app va a enviar emails, configurar `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD`, `DJANGO_EMAIL_USE_TLS` y `DJANGO_DEFAULT_FROM_EMAIL` en Render.

Render inyecta `PORT`; el Dockerfile lo usa para iniciar Gunicorn en `0.0.0.0:$PORT`.

Para que las imagenes subidas desde el admin se vean en Render, el Blueprint define `DJANGO_SERVE_MEDIA=True` y Django sirve `/media/`. En el plan free esos archivos viven en el filesystem efimero del servicio: pueden perderse al reiniciar o redeployar. Para uso real conviene migrar media a un storage persistente externo o a un plan con disco persistente.

## Consideraciones

- No subir `.env` a Git.
- `.env.example` es solo una plantilla.
- PostgreSQL no expone puerto al host; Django se conecta internamente a `db:5432`.
- El servicio Docker `web` es Django.
- Las apps bajo `django/domain/` contienen dominio/backend: modelos, admin y validaciones reutilizables.
- Las apps bajo `django/web/` contienen pantallas server-rendered: views, urls, templates, CSS y JS.
- Las apps `users`, `movies`, `rooms`, `screenings` y `cinema` contienen dominio/backend.
