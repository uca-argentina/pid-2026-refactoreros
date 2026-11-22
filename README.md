# Butaca Cero

Aplicación de cine desarrollada con Django y PostgreSQL.

## Contenido

- [Inicio local](#inicio-local)
- [Respaldo y recuperación sin internet](#construcción-completa-respaldo-y-recuperación-sin-internet)
- [Comandos básicos](#comandos-básicos)
- [Pruebas](#pruebas)
- [Mapa del código y de los datos](#mapa-del-código-y-de-los-datos)
- [ORM para consultar y modificar](#orm-para-consultar-y-modificar)
- [Listas, diccionarios y JSON](#listas-diccionarios-y-json)
- [Compras, butacas y reprogramación](#compras-butacas-y-reprogramación)
- [Rutas, controladores y formularios](#rutas-controladores-y-formularios)
- [Desarrollo con Django](#desarrollo-con-django)
- [Utilidades de consulta y edición](#utilidades-de-consulta-y-edición)

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

## Utilidades de consulta y edición

`django/toolbox/` contiene funciones opcionales para usar desde una vista o desde
`manage.py shell`. No agrega rutas ni modifica los flujos existentes.

### Buscar y editar

```python
from toolbox.orm import (
    buscar_usuario_por_email, compras_de, filtrar, ordenar, buscar_texto,
    buscar_uno, editar_campos, describir_campos,
)
from domain.movies.models import Movie

usuario = buscar_usuario_por_email("cliente@local.test")
compras = ordenar(compras_de(usuario), "created_at", descendente=True)
peliculas = buscar_texto(Movie, "aventura", "title", "synopsis")
peliculas = filtrar(peliculas, "rating", "ATP")
pelicula = buscar_uno(peliculas, pk=1)
if pelicula is not None:
    pelicula = editar_campos(pelicula, title="Nuevo título")
campos = describir_campos(Movie)
```

- `filtrar`: `igual`, `igual_sin_mayusculas`, `contiene`, `empieza_con`, `mayor`,
  `mayor_o_igual`, `menor`, `menor_o_igual`, `en` y `es_nulo`. Admite relaciones
  como `screening__movie__title`. Conserva los filtros del queryset recibido.
- `buscar_uno` devuelve objeto o `None`; `exigir_uno` rechaza también la ausencia.
  Ambos rechazan resultados ambiguos. `buscar_usuario_por_email` exige un usuario activo.
- `a_diccionarios(origen, *campos)` y `valores(origen, campo)` devuelven listas.
  `describir_campos` muestra nombres, tipos y opciones sin consultar filas.
- `entrada_de(usuario, compra_id, entrada_id)` busca una entrada propia;
  `entradas_sin_usar(compra)` filtra uso, no estado de función ni devoluciones.
- `editar_campos` valida y devuelve una instancia nueva. Los campos admitidos están
  en `toolbox.orm.CAMPOS_EDITABLES`; los permisos los comprueba el controlador.
  Para compras, estados, stock, credenciales y permisos se utilizan los servicios.
- `separar_butaca(lista, etiqueta)` y `total_butacas(lista)` trabajan sobre datos
  Python: no guardan ni sincronizan entradas u ocupación.

### Candy y juegos

```python
from toolbox.candy import seleccion_candy, pedidos_de, pedido_de, editar_componentes_combo
from toolbox.juegos import cupones_de, partida_publica_de, historial_juegos_de, editar_pregunta

seleccion = seleccion_candy(productos={producto_id: 2}, combos={combo_id: 1})
pedidos = pedidos_de(usuario)
pedido = pedido_de(usuario, pedido_id)
combo = editar_componentes_combo(gerente, combo_id, {producto_id: 2})
cupones = cupones_de(usuario, estado="available")
partida = partida_publica_de(usuario, partida_id)
eventos = historial_juegos_de(usuario)
pregunta = editar_pregunta(gerente, pregunta_id, options=["A", "B", "C"], correct=1)
```

Los identificadores del ejemplo se obtienen de registros existentes o formularios
validados. Las consultas respetan al dueño. Las dos ediciones exigen gerente y
reutilizan formularios existentes. Un combo requiere al menos dos unidades totales;
una pregunta, tres respuestas distintas. Las ediciones conservan los snapshots anteriores.

Reglas a tener en cuenta:

- Candy tiene pedidos ligados a entradas, independientes y de premios. Usar
  `pedidos_de`, que incluye los tres; `order.user_id` es una propiedad, no un filtro SQL.
- Los combos consumen stock de sus productos. Editar su composición no cambia
  pedidos anteriores ni stock. Desactivar un producto no desactiva sus combos.
- Comprar Candy: `domain.candy.services.buy_candy_only(usuario, seleccion, clave)`.
  Precios y stock se validan en servidor. `clave` es un UUID: conservarlo al reintentar
  la misma operación; usar uno nuevo para una compra distinta.
- Entregar o deshacer Candy: `deliver_candy_order(codigo, operador)` y
  `undo_candy_pickup(entrega_id, operador)`, en el mismo módulo. El QR Candy es `BCC:`;
  el de entradas es `BC2:`. La reversión exige el mismo operador y tiene un plazo.
- Juegos: usar `domain.games.services.start`, `answer`, `spin`, `grant` y
  `request_pickup`. Cada operación recibe un UUID para reintentos. `grant` exige
  gerente y motivo; no modificar tiradas o intentos directamente.
- `state(usuario)` puede crear cuenta, vencer partidas y registrar eventos.
  `partida_publica_de` solo consulta y oculta respuestas correctas; no actualiza plazos.
- El premio reserva stock al ganar: solicitar su retiro no lo descuenta otra vez.
  Los cupones pasan de `available` a `requested` y después a `redeemed` al entregar.
- Publicar/cancelar funciones: `Screening.change_status`, que conserva transiciones,
  snapshots y devoluciones. Promociones: se aplica el menor precio, no se acumulan.
  Editar email: la gestión también sincroniza `username`; usar su formulario y vista.

Para verificar las utilidades o generar la referencia del modelo:

```powershell
.\scripts\local.ps1 Test -TestLabels toolbox
python -m pip install -r scripts/requirements-docs.txt
python scripts/export_model_reference.py
```

El PDF queda en `artifacts/modelo-butaca-cero.pdf`; describe el modelo declarado,
sin consultar datos ni aplicar migraciones. La dependencia de exportación es opcional.

## Mapa del código y de los datos

| Componente | Archivo o carpeta |
|---|---|
| Modelos de compra, entrada y ocupación | `django/domain/tickets/models.py` |
| Consultas de disponibilidad existentes | `django/domain/tickets/selectors.py` |
| Compra y reprogramación existentes | `django/domain/tickets/services/checkout.py`, `reprogramming.py` |
| Validación del operador y credenciales | `django/domain/tickets/services/admission.py`, `credentials.py` |
| Perfiles de usuario | `django/domain/users/models.py` |
| Controladores del cliente | `django/web/tickets/views/` |
| Exportaciones usadas por las rutas | `django/web/tickets/views/__init__.py` |
| Rutas y formularios | `django/web/tickets/urls.py`, `forms.py` |
| Pantalla de una compra | `django/web/tickets/templates/ticket_detail.html` |
| Rutas principales | `django/butacaCero/urls.py` |

El modelo distingue compras, entradas individuales, butacas vendidas y reservas temporales:

```text
User ── ticket_purchases ──> TicketPurchase (user, screening, quantity, total)
                              ├── tickets ──> AdmissionTicket
                              │                (number, seat_label, code, used_at)
                              ├── sold_seats ──> SeatPurchase
                              │                   (screening, label, used_at)
                              └── selected_seats: lista JSON de diccionarios
User ── customer_profile ──> Customer (perfil; no contiene email)
SeatReservation: bloqueo temporal de una butaca, no una entrada comprada
```

`AdmissionTicket` obtiene su dueño a través de `ticket.purchase.user`.
`SeatPurchase` impide vender dos veces la misma combinación función/butaca.
`selected_seats` conserva datos de precio de la compra. Cambiar solo una de estas
representaciones deja inconsistencias.

**Efecto especial de `TicketPurchase.save()`:** al crear una compra genera
automáticamente `quantity` objetos `AdmissionTicket`. No genera los `SeatPurchase`;
eso lo hace el servicio de compra. Al editar una compra existente, `save()` no
sincroniza automáticamente sus entradas ni sus butacas vendidas.

**Códigos actuales:** el operador busca `TicketPurchase.validation_token` o
`validation_code_digest`; el QR de compra lleva `BC2:`. Aunque `AdmissionTicket`
tiene `code` y un payload `BC1:`, el servicio actual del operador no busca ese
código individual. La credencial utilizada para el ingreso corresponde a la compra.

## ORM para consultar y modificar

Abrir una consola con los modelos y la configuración cargados:

```powershell
docker compose exec web python manage.py shell
```

```python
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from domain.tickets.models import AdmissionTicket, SeatPurchase, TicketPurchase

User = get_user_model()
user = User.objects.filter(email__iexact="cliente@local.test").first()
if user is None:
    raise ValidationError("No existe el usuario de práctica.")
purchases = TicketPurchase.objects.filter(user=user)  # QuerySet, puede estar vacío.
purchase = purchases.first()                         # Objeto o None.
```

Los siguientes ejemplos requieren una `purchase` existente. En una vista,
reemplazar el usuario del ejemplo por `request.user` y los IDs por parámetros de
ruta validados. En el shell no existe `request`.

| Necesidad | Ejemplo | Resultado |
|---|---|---|
| Un objeto obligatorio en una vista | `get_object_or_404(TicketPurchase, pk=pk, user=request.user)` | Objeto o respuesta 404; verifica propiedad. |
| Un objeto obligatorio en un servicio | `TicketPurchase.objects.get(pk=purchase_pk, user=user)` | Objeto; capturar `TicketPurchase.DoesNotExist` si falta. |
| Muchos o ninguno | `purchase.tickets.filter(used_at__isnull=True)` | QuerySet; no es una entrada individual. |
| Comprobar existencia | `purchase.tickets.filter(used_at__isnull=False).exists()` | `True` o `False`. |
| Contar | `purchase.tickets.count()` | Entero. |
| Recorrer relaciones | `AdmissionTicket.objects.filter(purchase__user=user)` | Entradas del usuario. |
| Lista de valores simples | `list(purchase.tickets.values_list("seat_label", flat=True))` | Por ejemplo `['A1', 'A2']`. |
| Lista de diccionarios | `list(purchase.tickets.values("id", "seat_label"))` | Por ejemplo `[{'id': 1, 'seat_label': 'A1'}]`. |
| Ordenar | `purchase.tickets.order_by("number")` | QuerySet ordenado. |
| Excluir | `purchase.tickets.exclude(used_at=None)` | Entradas utilizadas. |

`get()` también puede lanzar `MultipleObjectsReturned` si el filtro no identifica
una sola fila. Un queryset se ejecuta al consumirlo; `list(...)` materializa los
resultados, pero no transforma sus modelos en diccionarios. Para eso usar `values`.
En un modelo se lee `ticket.seat_label`; en un diccionario, `seat["label"]`.

### Filtros habituales

| Filtro | Significado |
|---|---|
| `email=texto` | Igualdad exacta según la comparación de la base. |
| `email__iexact=texto.strip()` | Igualdad sin distinguir mayúsculas. |
| `purchase__user=user` | Seguir una relación y comparar el usuario. |
| `pk__in=[1, 2]` | Uno de esos IDs. |
| `used_at__isnull=True` | Todavía no utilizada. |
| `starts_at__gt=timezone.now()` | Fecha posterior a ahora. |
| `starts_at__lte=timezone.now()` | Fecha anterior o igual a ahora. |
| `email__icontains=texto` | Contiene texto; sirve para buscar, no para identificar destinatario. |

Dentro de un mismo `filter`, las condiciones se unen con AND. `__` puede recorrer
relaciones o indicar un lookup. `customer.user.email` es acceso en Python;
`Customer.objects.filter(user__email__iexact=correo)` es consulta ORM.

### Crear, editar, relacionar y borrar

```python
# Crear una cuenta de prueba: create_user cifra la contraseña.
recipient = User.objects.create_user(
    username="destino-practica", email="destino@local.test",
    password="PracticaLocal2026!",
)
from domain.users.models import Customer
Customer.objects.create(user=recipient)  # Si el recorrido necesita perfil cliente.

# Editar una instancia: asignar en Python no alcanza, hay que guardar.
recipient.first_name = "Destinatario"
recipient.save(update_fields=["first_name"])
recipient.refresh_from_db()

# Una ForeignKey recibe el objeto o su ID, no una lista de usuarios.
# purchase.user = recipient       # En memoria; guardar cambia TODA la compra.
# purchase.user_id = recipient.pk # Alternativa equivalente.

# Una relación inversa se consulta con su manager.
tickets = list(purchase.tickets.all())
labels = list(purchase.sold_seats.values_list("label", flat=True))
```

Usar otro username si ya existe la cuenta. Cambiar `purchase.user` modifica el
usuario asociado a toda la compra, incluidas sus entradas y el acceso a los datos
relacionados; no modifica únicamente una entrada individual.

`QuerySet.update(campo=valor)` escribe directamente en SQL y devuelve cuántas filas
afectó: no llama a `save()`, `full_clean()` ni señales de guardado. `bulk_create` y
`bulk_update` también omiten el `save()` de cada instancia. Por eso no usar
`TicketPurchase.objects.bulk_create(...)` esperando entradas/códigos automáticos.
`delete()` borra y puede arrastrar relaciones con `CASCADE`: no usarlo para mover
una compra. En cualquier edición, comprobar las reglas del dominio antes de guardar.

## Listas, diccionarios y JSON

Los siguientes ejemplos de manipulación de datos no requieren Django.

```python
from decimal import Decimal

seats = [
    {"label": "A1", "price": "1000.00", "promotion": ""},
    {"label": "A2", "price": "800.00", "promotion": "Promo"},
]
label = "A1"

# Leer y encontrar.
first = seats[0]  # Solo si la lista no está vacía.
price = first["price"]  # Clave obligatoria; KeyError si falta.
promotion = first.get("promotion", "")  # Valor por defecto si la clave no existe.
labels = [seat["label"] for seat in seats]
chosen = next((seat for seat in seats if seat["label"] == label), None)
remaining = [dict(seat) for seat in seats if seat["label"] != label]
if chosen is None:
    raise ValueError("La butaca no pertenece a la compra.")
chosen_copy = dict(chosen)

# Agregar, cambiar y quitar en una copia.
copy = [dict(seat) for seat in seats]
copy.append({"label": "A3", "price": "1000.00", "promotion": ""})
copy[0]["price"] = "900.00"
removed = copy.pop()  # Quita y devuelve el último elemento.
copy[0].pop("promotion", None)  # Quita una clave sin fallar si no existe.

# Índice por etiqueta: útil si voy a buscar muchas veces.
by_label = {seat["label"]: seat for seat in seats}
seat = by_label.get("A2")
for seat_label, seat_data in by_label.items():
    print(seat_label, seat_data["price"])

# Cantidad, total y pertenencia.
quantity = len(remaining)
total = sum((Decimal(seat["price"]) for seat in remaining), Decimal("0"))
occupied = {"A1", "B1"}
requested = {"A1", "A2"}
conflicts = requested & occupied  # Intersección: {'A1'}.
has_duplicates = len(labels) != len(set(labels))
```

`copy = seats` comparte la misma lista. `seats.copy()` copia la lista, pero comparte
sus diccionarios. `[dict(seat) for seat in seats]` copia también cada diccionario;
si hay estructuras anidadas que se van a modificar, usar `copy.deepcopy`.
No quitar elementos de una lista mientras se la recorre: construir `remaining`.
El índice `by_label` pisa duplicados; validar antes que no se repitan etiquetas.
`.get("price", "0")` no reemplaza un `None` explícito; no ocultar precios faltantes
tratándolos como cero en una operación real.

### Del formulario al JSONField y viceversa

```python
import json

text = '[{"label": "A1", "price": "1000.00"}]'
payload = json.loads(text)  # Texto JSON -> lista/diccionario de Python.
if not isinstance(payload, list):
    raise ValueError("Se esperaba una lista.")
encoded = json.dumps(payload)  # Python -> texto JSON, por ejemplo para un POST.

# selected_seats es JSONField: Django ya entrega una lista de Python.
# purchase.selected_seats = payload
# purchase.save(update_fields=["selected_seats"])
```

No hacer `json.loads(purchase.selected_seats)` ni guardar `json.dumps(payload)`
en ese JSONField: se espera una estructura Python. Los precios del snapshot se
guardan como texto y se calculan con `Decimal`, no con `float`.

`request.POST` es un `QueryDict`: `.get("email", "")` devuelve un valor y
`.getlist("ticket_ids")` devuelve los valores de varios inputs con el mismo nombre.
Los IDs recibidos son texto; un `forms.IntegerField` los convierte y valida.
`TicketPurchaseForm.clean_selected_seats()` ya convierte el texto JSON del POST.
No confiar en precios ni pertenencia recibidos del navegador.

## Compras, butacas y reprogramación

### Creación y relaciones

`TicketPurchase.buy(...)` delega en el servicio `buy_tickets` de
`domain/tickets/services/checkout.py`. Este servicio valida disponibilidad,
calcula precios y guarda compra, entradas y ocupación en una transacción.

Al crear una compra directamente con `TicketPurchase.objects.create(...)` o
`save()`, se generan sus entradas individuales, pero no las filas `SeatPurchase`.
Para el flujo de venta se utiliza el servicio, que mantiene las relaciones y
comprueba las reglas del dominio.

Copiar una instancia asignándole `pk = None` no copia sus relaciones y puede
conservar campos únicos, como las credenciales. Para crear un registro independiente
se especifican sus campos y se revisan las relaciones que deban conservarse.

### Actualización de butacas

Una modificación de butacas involucra estos datos:

| Dato | Ubicación |
|---|---|
| Función, cantidad, total y detalle de precios | `TicketPurchase` y su JSON `selected_seats` |
| Etiqueta y uso de cada entrada | `AdmissionTicket.seat_label` y `used_at` |
| Ocupación de la butaca para una función | `SeatPurchase.screening` y `label` |
| Bloqueo temporal durante la selección | `SeatReservation` |

Guardar únicamente `selected_seats` cambia el JSON, pero no actualiza entradas ni
ocupación. Las escrituras relacionadas se agrupan con `transaction.atomic()`.
Los servicios existentes utilizan además `select_for_update()` para coordinar
modificaciones concurrentes; la transacción por sí sola no bloquea esas filas.

### Servicio de reprogramación

`reprogram_purchase` está en `domain/tickets/services/reprogramming.py` y recibe
estos argumentos por nombre:

| Argumento | Contenido |
|---|---|
| `user` | Usuario dueño de la compra. |
| `purchase_pk` | Identificador de la compra. |
| `new_screening_pk` | Identificador de otra función de la misma película. |
| `selected_seats` | Selección de butacas de la función de destino. |

El servicio verifica propiedad, plazo de reprogramación, ausencia de devolución y
de entradas utilizadas, función de destino publicada con inicio futuro, cantidad,
disponibilidad y reservas del usuario. Luego actualiza la compra, reemplaza la
ocupación, ajusta las etiquetas de las entradas y libera las reservas utilizadas.
Devuelve `(purchase, previous_total)` y utiliza `ValidationError` para los rechazos
de negocio. No admite reprogramar hacia la misma función.

## Rutas, controladores y formularios

Las rutas del cliente se declaran en `django/web/tickets/urls.py`. Este módulo usa
`from . import views`, por lo que los controladores que referencia se exportan desde
`django/web/tickets/views/__init__.py`.

| Nombre de ruta | Controlador | Uso |
|---|---|---|
| `my_tickets` | `my_tickets_view` | Listado de compras del usuario. |
| `ticket_detail` | `ticket_detail_view` | Detalle de una compra propia. |
| `seat_reprogram_selection` | `seat_reprogram_selection_view` | Selección de butacas para otra función. |
| `screening_reprogram_confirm` | `screening_reprogram_view` | Confirmación de reprogramación mediante POST. |

Los enlaces y redirecciones usan el `name` de la ruta, no su texto URL. Las rutas
de tickets no tienen namespace. Ejemplos para una vista y su template:

```python
from django.shortcuts import redirect

# Dentro de una vista, luego de completar una operación:
# return redirect("ticket_detail", pk=purchase.pk)
```

```django
<a href="{% url 'ticket_detail' purchase.pk %}">Ver compra</a>
```

### Validación y respuestas

- Los GET consultan y muestran pantallas; las operaciones de escritura usan POST.
- `@login_required` exige sesión, pero la propiedad de la compra también se valida
  mediante `user=request.user` o `request.user.ticket_purchases`.
- Los formularios POST incluyen `{% csrf_token %}`. Los campos HTML deben tener el
  mismo nombre que los campos del formulario.
- Se ejecuta `form.is_valid()` antes de consultar `form.cleaned_data`.
- `clean_email()` valida un campo llamado `email`; el nombre debe coincidir.
- Las reglas del negocio se validan también en el servicio que modifica los datos.
- Toda vista retorna una respuesta: `return render(...)`, `return redirect(...)`
  o una respuesta HTTP equivalente.
- `form.as_p` incluye los errores del formulario. Si el HTML escribe los campos
  individualmente, también debe mostrar sus errores y `form.non_field_errors`.

El flujo existente de reprogramación muestra la separación entre formulario,
controlador y servicio: `TicketReprogramForm` convierte el JSON de selección,
`screening_reprogram_view` coordina la petición y `reprogram_purchase` valida y
persiste. `purchase_error_message` convierte los errores en un mensaje para la
pantalla; el controlador guarda ese mensaje en la sesión y redirige a la selección
cuando la operación se rechaza.

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
