# Butaca Cero

Proyecto Django dockerizado con PostgreSQL.

## Estructura

```text
.
├── docker-compose.yml
├── .env.example
├── docker/
│   └── django/
│       ├── Dockerfile
│       └── entrypoint.sh
└── django/
    ├── manage.py
    ├── requirements.txt
    └── butacaCero/
```

## Levantar el proyecto

```powershell
Copy-Item .env.example .env
docker compose up --build
```

La aplicacion queda disponible en:

```text
http://localhost:8000
```

El admin de Django queda en:

```text
http://localhost:8000/admin/
```

## Comandos utiles

Ejecutar migraciones manualmente:

```powershell
docker compose exec web python manage.py migrate
```

Crear superusuario:

```powershell
docker compose exec web python manage.py createsuperuser
```

Ver logs:

```powershell
docker compose logs -f web
```

Apagar contenedores:

```powershell
docker compose down
```

Apagar y borrar la base de datos local:

```powershell
docker compose down -v
```
