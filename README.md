# Butaca Cero

Aplicación de cine desarrollada con Django y PostgreSQL.

## Inicio local

Requiere Docker Desktop iniciado. Desde la raíz del proyecto, en PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

Copiar `.env` solo la primera vez y cambiar los valores `change-me...`.
La aplicación queda en http://localhost:8000. No subir `.env` a Git.
La primera construcción requiere internet; las imágenes ya descargadas permiten trabajar localmente.

Para crear datos y cuentas de prueba:

```powershell
docker compose exec web python manage.py seed_practice
```

Usuarios: `gerente@local.test`, `operador@local.test` y `cliente@local.test`.
Contraseña inicial: `PracticaLocal2026!`. No reemplaza contraseñas existentes.

## Comandos básicos

```powershell
# Ver logs
docker compose logs -f web

# Ejecutar pruebas
docker compose run --rm --no-deps --entrypoint python web manage.py test --settings=butacaCero.test_settings

# Después de modificar modelos
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate

# Crear un administrador para /admin/
docker compose exec web python manage.py createsuperuser

# Apagar sin borrar la base de datos
docker compose down
```

El código está en `django/`: `domain/` contiene modelos y lógica de negocio;
`web/` contiene vistas, rutas, formularios, templates y archivos estáticos.
