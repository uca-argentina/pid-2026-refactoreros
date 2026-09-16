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

## Consideraciones

- No subir `.env` a Git.
- `.env.example` es solo una plantilla.
- PostgreSQL no expone puerto al host; Django se conecta internamente a `db:5432`.
- El servicio Docker `web` es Django.
- La app Django `frontend` contiene templates, CSS y JS simples.
- Las apps `users`, `movies`, `rooms`, `screenings` y `cinema` contienen dominio/backend.
