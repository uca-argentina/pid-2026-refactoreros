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
- conexion a PostgreSQL externa mediante `DATABASE_URL` (Neon);
- media persistente externa mediante credenciales separadas de Cloudinary;
- `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY` generado por Render y `DJANGO_ALLOWED_HOSTS` conectado al hostname del servicio;
- health check en `/health/`.

Pasos:

1. Crear una base PostgreSQL en Neon y copiar la connection string.
2. Crear una cuenta/proyecto en Cloudinary y copiar `cloud name`, `API key` y `API secret`.
3. Subir la rama con los cambios a GitHub.
4. En Render, crear un Blueprint desde este repositorio y elegir la rama que contiene `render.yaml`.
5. Cuando Render pida secretos, cargar:

```text
DATABASE_URL=postgresql://...
CLOUDINARY_CLOUD_NAME=cloud-name
CLOUDINARY_API_KEY=api-key
CLOUDINARY_API_SECRET=api-secret
```

No usar `CLOUDINARY_URL` en este deploy. El proyecto estandariza Cloudinary en las tres variables separadas para evitar credenciales duplicadas o mezcladas.

El Blueprint define `DJANGO_REQUIRE_CLOUDINARY=True` para evitar que Render arranque usando filesystem efimero si faltan esas credenciales.

6. Esperar el primer deploy. El contenedor ejecuta `collectstatic` y `migrate` antes de iniciar Gunicorn.
7. Si el plan permite Shell, crear el superusuario desde la Shell de Render:

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

Las imagenes subidas desde el admin (peliculas, logos del cine, fondo de login e iconos de butaca) se guardan en Cloudinary cuando `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` y `CLOUDINARY_API_SECRET` estan configuradas. Si esas variables no existen, Django usa el filesystem local en `MEDIA_ROOT`; eso sirve para desarrollo, pero no para Render free porque el filesystem del servicio es efimero.

## Consideraciones

- No subir `.env` a Git.
- `.env.example` es solo una plantilla.
- PostgreSQL no expone puerto al host; Django se conecta internamente a `db:5432`.
- El servicio Docker `web` es Django.
- Las apps bajo `django/domain/` contienen dominio/backend: modelos, admin y validaciones reutilizables.
- Las apps bajo `django/web/` contienen pantallas server-rendered: views, urls, templates, CSS y JS.
- Las apps `users`, `movies`, `rooms`, `screenings` y `cinema` contienen dominio/backend.
