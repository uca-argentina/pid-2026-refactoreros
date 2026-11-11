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

## Construcción completa, respaldo y recuperación sin internet

Los siguientes procedimientos se ejecutan en PowerShell y requieren Docker
Desktop iniciado con contenedores Linux. Se utiliza el nombre de carpeta
`pid-2026-refactoreros` y un respaldo externo en `../butaca-respaldo`.
Si el repositorio tiene otro nombre, las rutas deben ajustarse manteniendo ese
mismo nombre durante la recuperación: Compose lo utiliza para nombrar la imagen.
No se debe utilizar un nombre de proyecto Compose distinto entre estos pasos.

### 1. Construir desde cero con internet

Desde la raíz del repositorio, crear `.env` solamente si todavía no existe:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

Antes de continuar, configurar los valores `change-me...` de `.env`.
**El siguiente `down --volumes` elimina la base local existente.** Si contiene
datos necesarios, se debe generar un respaldo antes de ejecutar ese comando.
La reconstrucción no elimina `django/media` del disco.

```powershell
# Eliminar los contenedores y la base local anterior.
docker compose down --volumes

# Reconstruir sin reutilizar capas de instalación y actualizar las imágenes base.
docker compose build --no-cache --pull web
docker compose pull db

# Levantar los servicios y generar datos de práctica.
docker compose up -d --wait --no-build
.\scripts\local.ps1 Seed
```

La aplicación queda disponible en http://localhost:8000, salvo que `DJANGO_PORT`
indique otro puerto. Las migraciones se aplican automáticamente al iniciar.

### Guardar un punto de recuperación

Una vez comprobado el funcionamiento, guardar las imágenes construidas y una
copia del proyecto fuera de su carpeta. La carpeta `../butaca-respaldo` debe ser
nueva para evitar mezclar respaldos de distintos estados.

```powershell
New-Item -ItemType Directory -Path ..\butaca-respaldo -ErrorAction Stop

# Guardar las imágenes de Django y PostgreSQL con sus nombres actuales.
$imagenesButaca = docker compose config --images
docker image save -o ..\butaca-respaldo\imagenes.tar @imagenesButaca

# Detener la aplicación para evitar escrituras durante la copia de datos y media.
docker compose stop web
.\scripts\local.ps1 Backup -BackupFile backups/checkpoint.dump

# Copiar código, historial Git, .env, archivos subidos y respaldos de la base.
robocopy . ..\butaca-respaldo\repo /E /XJ /XD artifacts .venv venv env env_pid __pycache__ staticfiles
if ($LASTEXITCODE -ge 8) { throw 'No se pudo completar la copia del proyecto.' }

# Volver a iniciar la aplicación después de completar el respaldo.
docker compose up -d --wait --no-build --pull never
```

Se debe comprobar que `imagenes.tar`, `repo/.env` y
`repo/backups/checkpoint.dump` existan en el respaldo. Si hay archivos subidos,
también debe existir `repo/django/media`. El respaldo debe conservarse intacto:
contiene secretos y datos privados, por lo que no debe publicarse en GitHub.
Los códigos de salida de Robocopy entre 0 y 7 no indican un fallo de copia.
Si falla cualquier paso, se debe resolver el error antes de continuar con el
borrado o considerar el respaldo completo.

### 2. Eliminar el entorno y recuperar el código respaldado

Desde la raíz del proyecto, el siguiente comando elimina sus contenedores,
volúmenes e imágenes locales sin etiqueta personalizada. **Se pierde la base
local actual.** No se eliminan los archivos del repositorio ni el respaldo externo.

```powershell
docker compose down --volumes --rmi local
```

Si el código también quedó dañado, se puede apartar la carpeta actual y recuperar
la copia guardada. `pid-2026-refactoreros-roto` no debe existir previamente.
Estos comandos conservan la carpeta dañada para permitir rescatar archivos.

```powershell
cd ..

Rename-Item -LiteralPath pid-2026-refactoreros `
    -NewName pid-2026-refactoreros-roto -ErrorAction Stop

Copy-Item -LiteralPath .\butaca-respaldo\repo `
    -Destination .\pid-2026-refactoreros -Recurse -ErrorAction Stop

cd .\pid-2026-refactoreros
```

Si `docker-compose.yml` o `.env` quedaron dañados, se deben recuperar esos archivos
desde el respaldo antes de ejecutar `down`, conservando el nombre del proyecto
Compose original para que se elimine el entorno correcto.

### 3. Recuperar el entorno sin internet

Esta recuperación **carga imágenes ya construidas; no reconstruye el Dockerfile**.
Una reconstrucción sin caché necesita descargar dependencias de Python y no puede
completarse sin internet con el Dockerfile actual.

Con Docker Desktop iniciado, desde la raíz del repositorio recuperado:

```powershell
docker image load -i ..\butaca-respaldo\imagenes.tar
docker compose up -d --wait --no-build --pull never
```

Para utilizar una base recién creada con datos de práctica:

```powershell
.\scripts\local.ps1 Seed
```

La base será nueva si previamente se ejecutó `down --volumes`; los archivos
subidos recuperados en `django/media` se conservan. Para restaurar los datos
originales **en lugar de ejecutar `Seed`**:

```powershell
.\scripts\local.ps1 Restore -BackupFile backups/checkpoint.dump -DatabaseName butacacero_recuperada
```

Después, cambiar `POSTGRES_DB` en `.env` a `butacacero_recuperada` y ejecutar:

```powershell
docker compose up -d --wait --no-build --pull never
```

`Restore` requiere un nombre de base nuevo y no sobrescribe bases existentes.
No se debe ejecutar `build` ni `Prepare` durante la recuperación sin conexión.
Para trasladar el respaldo a otra notebook, se debe copiar toda la carpeta
`butaca-respaldo`, utilizar el mismo nombre de carpeta del repositorio y contar
con Docker Desktop previamente instalado y operativo. Ambos equipos deben usar
una arquitectura compatible, por ejemplo x64.
La configuración offline debe utilizar archivos locales y correo en consola;
servicios externos configurados por separado, como Cloudinary o SMTP, requieren
conexión. La imagen Docker no incluye los datos de PostgreSQL del volumen ni los
archivos montados desde el repositorio: por eso se respaldan por separado.

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

## Pruebas

Desde PowerShell, el script inicia la base de datos e incluye la configuración de pruebas:

```powershell
# Todas las pruebas
.\scripts\local.ps1 Test

# Una prueba puntual: módulo.Clase.método
.\scripts\local.ps1 Test -TestLabels web.manager.tests.ManagerFuncionesTests.test_gerente_crea_funcion_sin_publicarla
```

Si ya estás dentro del contenedor, podés ejecutar:

```bash
# Todas las pruebas de una clase
python manage.py test web.manager.tests.ManagerFuncionesTests --settings=butacaCero.test_settings

# Una prueba puntual
python manage.py test web.manager.tests.ManagerFuncionesTests.test_gerente_crea_funcion_sin_publicarla --settings=butacaCero.test_settings
```

Agregá `-v 2` para ver el nombre y resultado de cada prueba.

Usá `--settings=butacaCero.test_settings` al ejecutar las pruebas directamente:
activa correo en memoria, almacenamiento local sin servicios externos, una carpeta
temporal para imágenes y un hash de contraseñas más rápido. Sin esa opción, Django
usa la configuración habitual del proyecto. Django crea una base de pruebas
separada en ambos casos; esa separación no depende de `--settings`.

## Desarrollo con Django

Los ejemplos usan campos del proyecto. Los nombres genéricos `nombre`,
`descripcion`, `inicio` y `fin` se reemplazan por los del formulario o modelo
correspondiente. Los métodos `clean_*` pertenecen al formulario; los campos del
modelo y los widgets se definen en lugares distintos.

### Etiquetas de opciones

Para campos con `choices`, Django genera `get_FOO_display()`: se reemplaza `FOO`
por el nombre del campo.

```python
screening.status                # Valor guardado: "borrador"
screening.get_status_display()  # Etiqueta: "Borrador"
```

```django
{{ screening.get_status_display }}
```

En templates se omiten los paréntesis. `verbose_name` es el nombre del campo;
la etiqueta de cada opción viene de `choices`. Con `TextChoices`, una opción
tiene `.value` y `.label`, y la clase ofrece `.choices`.

### Opciones de los campos

| Opción | Para qué sirve |
|---|---|
| `verbose_name` | Nombre legible del campo en formularios y admin. |
| `choices` | Opciones que valida Django y que el formulario muestra como selector. No crea por sí sola una restricción SQL. |
| `default` | Valor al crear una instancia sin indicar ese campo. No rellena un campo omitido en un formulario enviado. |
| `blank=True` | Permite dejarlo vacío en la validación de Django y en formularios generados. |
| `null=True` | Permite almacenar `NULL` en la base. En campos de texto normalmente se usa la cadena vacía. |
| `db_column` | Nombre de la columna SQL; en Python se sigue usando el nombre del atributo. |
| `max_length` | Longitud máxima de un campo de texto. |
| `related_name` | Nombre para acceder a la relación desde el otro modelo. |
| `on_delete` | Comportamiento de Django al borrar el objeto referenciado; por ejemplo, `PROTECT` impide borrarlo si tiene referencias. |

Un campo obligatorio nuevo necesita resolver qué valor tendrán las filas
existentes. Si `makemigrations` pide un valor por única vez, ese valor completa
los registros anteriores; no equivale a dejar un `default` permanente en el modelo.

### Campos y propiedades

Un campo del modelo guarda información en la base. Un método calcula o ejecuta
algo. `@property` permite acceder a un método como atributo, sin paréntesis:

```python
screening.ends_at  # Se calcula con el inicio y la duración de la película.
```

Una propiedad no crea una columna, no requiere migración y no guarda ni cachea
automáticamente el resultado. En templates, tanto propiedades como métodos sin
argumentos se consultan con la notación de punto.

### Formularios de modelos

- `Meta.fields` del `ModelForm` determina qué campos incluye.
- Si el template recorre `{% for field in form %}`, los campos se renderizan automáticamente. Si están escritos uno por uno, se debe actualizar ese HTML.
- Para editar un registro, el formulario necesita `instance=objeto`; sin ella, guardar puede crear otro registro.
- Se usa `form.is_valid()` antes de leer `form.cleaned_data` o guardar datos enviados.
- `form.errors`, `form.non_field_errors()` y los errores de cada campo permiten identificar por qué no guarda.
- `form.save(commit=False)` devuelve la instancia sin guardarla todavía; luego se necesita `instance.save()` y, si corresponde, `form.save_m2m()`.

`ModelForm` valida los campos incluidos. En cambio, llamar a `objeto.save()`
directamente no ejecuta automáticamente `full_clean()`; `choices` no reemplaza
esa validación.

### Valores en templates

| Necesidad | Ejemplo |
|---|---|
| Leer un atributo o relación | `{{ screening.movie.title }}` |
| Mostrar una etiqueta de `choices` | `{{ screening.get_status_display }}` |
| Dar formato a una fecha | `{{ screening.starts_at\|date:"d/m/Y H:i" }}` |
| Usar un reemplazo para valores falsos, incluidos `0` y `False` | `{{ valor\|default:"Sin datos" }}` |
| Reemplazar únicamente `None` | `{{ valor\|default_if_none:"Sin datos" }}` |
| Armar un enlace desde el nombre de una ruta | `{% url 'manager:funciones_update' screening.pk %}` |

Si una variable no existe, el template suele mostrar vacío: conviene verificar
el nombre que llega en el contexto. Dentro de un bucle se usa el objeto de esa
iteración. Si una página muestra varias funciones, los datos de una sola no
describen necesariamente a todas.

### Inspección de objetos

Dentro del contenedor, `python manage.py shell` permite consultar los modelos:

```python
from domain.screenings.models import Screening

Screening.objects.filter(status=Screening.Status.DRAFT)  # Colección filtrada.
screening = Screening.objects.first()  # Una instancia o None si no hay filas.
if screening is not None:
    print(screening.pk, screening.get_status_display())
```

- `get(pk=...)` devuelve un único objeto y lanza una excepción si no existe.
- `filter(...)` devuelve un queryset, aunque no encuentre filas.
- `exists()` responde si hay resultados; `count()` cuenta registros.
- `order_by("starts_at")` ordena ascendente; `order_by("-starts_at")`, descendente.
- `objeto.refresh_from_db()` vuelve a cargar sus valores desde la base.
- Para fechas compatibles con la configuración de Django se usa `django.utils.timezone.now()`.

### Migraciones

Estos comandos se ejecutan dentro del contenedor. Desde PowerShell se antepone
`docker compose exec web`.

```bash
# Ayuda completa del comando; -n y --name son equivalentes.
python manage.py help makemigrations

# Ver qué archivo generaría, sin escribirlo.
python manage.py makemigrations screenings --dry-run

# Generar el archivo con un nombre descriptivo.
python manage.py makemigrations screenings --name nombre_descriptivo

# Ver aplicadas [X] y pendientes [ ].
python manage.py showmigrations screenings

# Ver qué se aplicaría y luego aplicarlo.
python manage.py migrate screenings --plan
python manage.py migrate screenings

# Detectar cambios del modelo que todavía no tienen migración.
python manage.py makemigrations --check --dry-run
```

`makemigrations` compara los modelos con el historial de migraciones; no compara
directamente el esquema real de la base. `migrate` aplica las operaciones pendientes.
En el archivo generado, `dependencies` indica qué migraciones deben existir antes
y `operations` contiene cambios como `AddField`, `AlterField` o `RenameField`.

Para deshacer una migración local, se indica la anterior como destino.
Por ejemplo, para volver de una `0008` a la `0007`:

```bash
python manage.py migrate screenings 0007 --plan
python manage.py migrate screenings 0007
```

El plan también puede incluir migraciones dependientes de otras apps.
Deshacer un campo agregado elimina sus valores. Primero se revierte y después
se borran el archivo local y sus cambios de código. Si nunca se aplicó, se puede
borrar directamente ese archivo. Para migraciones ya compartidas se conserva el
historial y se crea una nueva que revierta el cambio.

El contenedor aplica migraciones al iniciarse: si se conserva el archivo, un reinicio
puede volver a aplicarlo. `--fake` modifica el registro de migraciones sin ejecutar
el cambio de esquema, por lo que no sirve para deshacer el cambio en la base.

### Respuestas de formularios en tests

Al enviar un formulario, `302` suele ser la redirección después de guardar;
`200` puede ser el formulario renderizado de nuevo con errores. Esos errores
permiten identificar el problema antes de cambiar la expectativa del test.

Si se agrega un campo obligatorio al formulario, los tests que envían datos
válidos también deben enviarlo. El `default` del modelo no completa ese dato
faltante en el POST. Se conserva la expectativa de éxito y se comprueba el valor
guardado.

Dentro de un test con el cliente de Django:

```python
print(response.status_code)
print(response.context["form"].errors)  # Si la respuesta incluye ese formulario.
objeto.refresh_from_db()  # Antes de comprobar cambios guardados por una vista.
```

`assertRedirects` comprueba una redirección, `assertContains` busca contenido en la
respuesta y `assertEqual` compara valores. Para aislar el fallo se ejecuta el método
puntual con `-v 2`, como se muestra en la sección de pruebas.

### Tipos de datos y controles

| Dato | Campo del modelo | Control del formulario |
|---|---|---|
| Nombre, código o texto corto | `CharField(max_length=...)` | `TextInput` |
| Descripción o comentario | `TextField` | `Textarea` |
| Opciones fijas | `CharField` con `choices` | `Select` automático |
| Sí/no | `BooleanField(default=False)` | `CheckboxInput` |
| Cantidad | `IntegerField` o `PositiveIntegerField` | `NumberInput` |
| Precio o porcentaje decimal | `DecimalField(max_digits=..., decimal_places=...)` | `NumberInput` |
| Fecha, hora o ambas | `DateField`, `TimeField`, `DateTimeField` | Widget con `type="date"`, `"time"` o `"datetime-local"` |
| Correo o enlace | `EmailField` o `URLField` | `EmailInput` o `URLInput` |
| Color hexadecimal | `CharField(max_length=7)` con validador | `TextInput(attrs={"type": "color"})` |
| Imagen o archivo | `ImageField` o `FileField` | `ClearableFileInput` |
| Elegir otro registro | `ForeignKey` | `Select` generado por `ModelForm` |
| Elegir varios registros | `ManyToManyField` | `SelectMultiple` o `CheckboxSelectMultiple` |

El widget decide cómo se ve el control; no cambia el tipo de columna ni garantiza
la validación en el servidor. No hace falta migrar por cambiar solamente un widget.
Un `forms.CharField` tampoco crea una columna: eso corresponde a `models.CharField`.

### Texto, normalización y sanitización

- **Normalizar:** quitar espacios sobrantes o unificar un formato.
- **Validar:** rechazar datos que no cumplen una regla.
- **Sanitizar HTML:** permitir ciertas etiquetas y eliminar contenido peligroso con una herramienta especializada.
- **Escapar al mostrar:** representar caracteres HTML como texto para que no se interpreten como etiquetas.

Ejemplo de normalización y validación de un campo de formulario:

```python
from django import forms

# Dentro de la clase del formulario:
def clean_nombre(self):
    nombre = self.cleaned_data["nombre"].strip()
    nombre = " ".join(nombre.split())
    if len(nombre) < 3:
        raise forms.ValidationError("Ingresá al menos 3 caracteres.")
    return nombre  # El valor retornado queda en cleaned_data.
```

Los `forms.CharField` ya quitan espacios de los extremos por defecto (`strip=True`).
Unificar todos los espacios es una decisión adicional y puede eliminar saltos
de línea o formato. `.lower()` y `.upper()` también son decisiones de formato,
no medidas de seguridad.

Para texto común, `{{ objeto.descripcion }}` usa escape HTML automático. `|safe`
y `mark_safe` omiten esa protección. Ese escape no convierte texto arbitrario
en CSS, JavaScript o una URL segura. Para enviar datos a JavaScript se usa
`json_script`; para insertar texto con JavaScript se prefiere `textContent` a
`innerHTML`.

Si se permite HTML enriquecido, hace falta definir etiquetas/atributos permitidos
y elegir un sanitizador mantenido. Una expresión regular o `strip_tags` no son
un sanitizador de seguridad para luego marcar el resultado como seguro.

### Selector de color

`django/web/manager/forms/seat_types.py` ya usa un control de color. Para limitar
el dato a `#RRGGBB`, un campo de modelo puede incluir:

```python
from django.core.validators import RegexValidator
from django.db import models

color = models.CharField(
    max_length=7,
    default="#000000",
    validators=[RegexValidator(
        regex=r"\A#[0-9a-fA-F]{6}\Z",
        message="Usá un color hexadecimal como #12ABEF.",
    )],
)
```

Y dentro de `Meta` del `ModelForm`:

```python
widgets = {"color": forms.TextInput(attrs={"type": "color"})}
```

El selector ayuda a elegir el color; el validador rechaza valores manipulados.
Si se usa en un estilo, se acepta únicamente el formato de color previsto, no CSS
libre. El formato anterior no admite nombres como `red`, transparencia ni `#FFF`.

### Números y límites

- Para dinero se usa `DecimalField` y `Decimal("0.10")`, evitando cálculos con `float`.
- `max_digits` cuenta todos los dígitos; `decimal_places`, los decimales. Con `8` y `2`, quedan hasta seis dígitos enteros.
- `PositiveIntegerField` admite cero. Si el mínimo es uno, se agrega `MinValueValidator(1)`.
- Para un porcentaje entre 0 y 100 se combinan `MinValueValidator` y `MaxValueValidator`.
- Los atributos HTML `min`, `max` y `step` ayudan en el navegador; la regla también se valida en el servidor.
- Si el dato cambia fuera de formularios, una `CheckConstraint` permite proteger la regla en la base.

Un checkbox sin marcar normalmente no envía su clave.
`bool(request.POST.get("activo"))` no convierte correctamente todos los valores:
incluso `bool("false")` da `True`. Se usa el valor convertido por el formulario
en `cleaned_data`.

### Validación entre campos

`clean_<campo>()` permite validar una regla individual y `clean()` comparar varios.
Ejemplo dentro de un formulario que tenga `inicio` y `fin`:

```python
def clean(self):
    datos = super().clean()
    inicio = datos.get("inicio")
    fin = datos.get("fin")
    if inicio is not None and fin is not None and fin <= inicio:
        self.add_error("fin", "El fin debe ser posterior al inicio.")
    return datos
```

Se usa `.get()` porque un campo inválido puede faltar en `cleaned_data`. Para errores
generales se puede lanzar `forms.ValidationError`. Al sobrescribir `ModelForm.clean()`
se conserva `super().clean()` para mantener la validación que realiza Django.

### Fechas y horarios

El formato que envía el navegador debe coincidir con el que acepta el formulario.
`datetime-local` usa un valor como `2026-11-10T20:30` y no envía zona horaria.
El campo `starts_at` en `django/web/manager/forms/screenings.py` combina
`input_formats`, el tipo de widget y su `format`.

`timezone.now()` permite comparar fechas con zona horaria. Un filtro `date`
del template solo cambia la presentación; no modifica el dato guardado.

### Imágenes y archivos

La carga de archivos requiere estas dos piezas:

```html
<form method="post" enctype="multipart/form-data">
```

```python
form = MiFormulario(request.POST, request.FILES, instance=objeto)
```

Los archivos llegan en `request.FILES`. `accept="image/*"` ayuda al selector del
navegador, pero no valida el contenido recibido. Se usa un campo de formulario
adecuado y validaciones de tamaño y formato. Hay una función reutilizable
`validate_image_size` en `django/web/manager/forms/uploads.py`.

Antes de acceder a la URL de un archivo opcional se verifica si existe:

```django
{% if objeto.imagen %}
  <img src="{{ objeto.imagen.url }}" alt="Descripción de la imagen">
{% endif %}
```

### Relaciones y unicidad

- Para una lista fija que cambia con el código se puede usar `choices`.
- Para categorías administrables que tienen sus propios datos se usa otro modelo y una relación.
- Una categoría por objeto se representa con `ForeignKey`; varias etiquetas, con `ManyToManyField`.
- Para acceder a una FK, `objeto.movie` obtiene el objeto y `objeto.movie_id` su identificador.
- Las relaciones múltiples usan su administrador: `.all()`, `.add(...)`, `.remove(...)` o `.set(...)`. La instancia debe estar guardada primero.
- Después de `form.save(commit=False)` se guarda la instancia y se llama a `form.save_m2m()`.
- Para favoritos, una restricción única sobre usuario y objeto evita duplicados. `get_or_create` se apoya en esa unicidad para resolver concurrencia.

Una comprobación `exists()` no garantiza unicidad: dos peticiones pueden comprobar
al mismo tiempo. `unique=True` o `UniqueConstraint` mantienen la regla en la base.

### Búsqueda, filtros y ordenación

```python
from django.db.models import Q

texto = request.GET.get("q", "").strip()
queryset = Screening.objects.all()
if texto:
    queryset = queryset.filter(
        Q(movie__title__icontains=texto) | Q(room__name__icontains=texto)
    )
```

`__` recorre relaciones o agrega búsquedas: `__icontains`, `__gte`, `__lte`,
`__in`, `__isnull`. Las condiciones de un mismo `filter` se combinan con AND;
`Q(...) | Q(...)` expresa OR.

Para ordenar desde un parámetro del usuario se usa un diccionario de opciones
permitidas en vez de pasar cualquier texto a `order_by`. La paginación se resuelve
con `Paginator` o `paginate_by` en una `ListView`. Si recorrer relaciones genera
muchas consultas, `select_related` carga FK y `prefetch_related` carga colecciones.
Los filtros por relaciones múltiples pueden necesitar `distinct()`.

### Acciones y permisos

- Un enlace GET sirve para consultar. Las acciones que guardan o borran usan POST con `{% csrf_token %}`.
- Ocultar un botón no impide llamar a la URL. Se verifica el permiso en la vista y, cuando corresponde, sobre el objeto.
- El dueño se obtiene de `request.user`, no de un identificador de usuario enviado en el formulario.
- Si varias escrituras deben completarse juntas se usa `transaction.atomic()`.
- `F()` permite evitar incrementos perdidos; `select_for_update()` coordina cambios de filas dentro de una transacción.
- Cuando hay estados con transiciones permitidas se reutilizan los métodos del modelo para conservar sus reglas.

### Cobertura de pruebas

| Caso | Qué comprobar |
|---|---|
| Valor válido | Se guarda el dato esperado; se recarga el objeto con `refresh_from_db()`. |
| Vacío u omitido | Se rechaza si es obligatorio o se admite si es opcional. |
| Límites | Mínimo, máximo y un valor fuera de cada extremo. |
| Dato manipulado | Opción inexistente, color inválido, ID ajeno o formato incorrecto. |
| Normalización | El valor guardado refleja la regla, por ejemplo quitar espacios. |
| Edición | Cambia el registro existente y conserva el resto de sus datos. |
| Permisos | Usuario autorizado, sin sesión y usuario sin permiso. |
| Presentación | Se muestra el dato de cada objeto y el texto ingresado no se interpreta como HTML. |
| Registros anteriores | La migración deja valores compatibles con las reglas nuevas. |

Para validar formularios aislados se inspeccionan `form.is_valid()` y `form.errors`.
Para comprobar un rechazo se verifica el error esperado; no alcanza con un `200`,
que también puede ser una página exitosa. El cliente de tests de Django omite
por defecto los controles CSRF; `Client(enforce_csrf_checks=True)` los activa.

Referencias: [validación de formularios](https://docs.djangoproject.com/en/6.0/ref/forms/validation/),
[escape y seguridad](https://docs.djangoproject.com/en/6.0/topics/security/) y
[carga de archivos](https://docs.djangoproject.com/en/6.0/topics/http/file-uploads/).
