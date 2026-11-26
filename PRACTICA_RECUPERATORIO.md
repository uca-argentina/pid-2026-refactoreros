# Práctica del parcial: Transferir una entrada a otro usuario

Resolución en casa de la consigna del parcial (Grupo 8), paso a paso, separando qué parte es **Model**, **View** y **Controller**, y todo lo que aprendí en el camino.

---

## La consigna

1. Desde el detalle de una compra, permití que el comprador seleccione una entrada e indique el correo de otro usuario registrado.
2. Validá que la función esté pendiente, que la entrada pertenezca al usuario que solicita la transferencia y que todavía no se haya utilizado.
3. Al confirmar, mostrá la entrada en la cuenta del destinatario. Conservá la función y la butaca, generá un nuevo código de acceso e invalidá el anterior.

**Caso de validación:** transferí una entrada y comprobá desde la pantalla del operador que el código anterior se rechaza y el nuevo permite el ingreso.

### Decisión de producto mínimo viable
En lugar de elegir **una** entrada, se transfiere **la compra completa**. Pierdo parte del punto 1 (no hay selector), pero todo lo demás queda mucho más simple:
- No hay que crear compras nuevas ni mover butacas.
- La función y la butaca se conservan solas.
- El código viejo deja de existir por completo, así que el caso de validación sale limpio.

---

## MVC en mi proyecto (Django)

Django lo llama **MTV**, y su "View" en realidad es el **Controller**.

| MVC | Dónde está | Qué hace |
|---|---|---|
| **Model** | `domain/<app>/models.py` | Tablas, campos, estados |
| | `domain/<app>/services/*.py` | Reglas de negocio: validan con `raise ValidationError` y guardan |
| **Controller** | `web/<área>/urls.py` | La ruta: qué URL llama a qué función |
| | `web/<área>/views/*.py` | Recibe el request, llama al service, muestra el mensaje y redirige |
| | `web/<área>/views/__init__.py` | "Puerta de entrada": `urls.py` solo ve lo que se exporta acá |
| **View** | `web/<área>/templates/*.html` | Botones, formularios, lo que ve el usuario |

**Feature gemela que usé de modelo:** la reprogramación de entradas ("Cambiar función"):
- `web/tickets/templates/ticket_detail.html` (botón)
- `web/tickets/views/reprogramming.py` (controller)
- `domain/tickets/services/reprogramming.py` (model)

---

## Paso a paso

### Paso 1 · 🟦 VIEW: el formulario en el detalle de la compra

**Archivo:** `web/tickets/templates/ticket_detail.html`, debajo del bloque "Cambiar función".

```html
{% if available %}
  <p>¿Querés transferir tu entrada a otra persona?</p>
  <form method="post" action="{% url 'ticket_transfer' purchase.pk %}">
    {% csrf_token %}
    <input type="email" name="email" placeholder="Correo del destinatario" required>
    <button type="submit">Transferir</button>
  </form>
{% endif %}
```

- `{% if available %}`: `available` ya lo calcula `ticket_detail_view`. El form solo aparece si la compra se puede usar.
- `method="post"`: se usa POST porque **modifica datos**. Un link `<a>` hace GET.
- `{% csrf_token %}`: sin esto, Django rechaza el POST con un **403**.
- `name="email"`: es la clave con la que el controller lo lee en `request.POST`.
- **Mientras la ruta no existe,** usar `action=""`. Un `{% url %}` a una ruta inexistente rompe la página con `NoReverseMatch`.

**Prueba:** apretar "Transferir" con `action=""` da **405 Method Not Allowed**. Es lo esperado: el form envía, pero `ticket_detail_view` solo acepta GET.

---

### Paso 2 · 🟨 CONTROLLER: ruta y view mínima

Son 4 piezas, en este orden.

**a) La view**, en `web/tickets/views/purchases.py`:
```python
@login_required
@require_POST
def ticket_transfer_view(request, pk):
    email = request.POST.get("email")
    messages.success(request, f"Solicitud de transferencia recibida para {email}")
    return redirect("my_tickets")
```
Imports necesarios: `require_POST`, `redirect` y `from django.contrib import messages`.

**b) El export**, en `web/tickets/views/__init__.py`:
```python
from web.tickets.views.purchases import ticket_transfer_view as ticket_transfer_view
```

**c) La ruta**, en `web/tickets/urls.py`:
```python
path("mis-entradas/<int:pk>/transferir/", views.ticket_transfer_view, name="ticket_transfer"),
```

**d) Conectar el form:** `action="{% url 'ticket_transfer' purchase.pk %}"`.

- Se redirige a **`my_tickets`** y no al detalle porque `ticket_detail.html` **no muestra** los mensajes de Django, y `my_tickets.html` sí.

**Prueba:** al transferir, terminás en Mis entradas con el mensaje.

---

### Paso 3 · 🟩 MODEL: el service con las validaciones

**Archivo nuevo:** `domain/tickets/services/transfers.py`

```python
@transaction.atomic
def transfer_purchase(*, user, purchase_pk, email):
    # 1. La compra existe Y es del usuario (el filtro por user cubre "pertenece al usuario")
    purchase = TicketPurchase.objects.filter(pk=purchase_pk, user=user).first()
    if purchase is None:
        raise ValidationError("No encontramos esa compra.")

    # 2. La función está pendiente: publicada Y todavía no empezó
    if purchase.screening.status != Screening.Status.PUBLISHED or purchase.screening.starts_at <= timezone.now():
        raise ValidationError("La función no está pendiente.")

    # 3. No se usó ninguna entrada de la compra
    if AdmissionTicket.objects.filter(purchase=purchase, used_at__isnull=False).exists():
        raise ValidationError("Ya usaste entradas de esta compra, no se puede transferir.")

    # 4. No transferirse a uno mismo
    if email.lower() == user.email.lower():
        raise ValidationError("No podés transferirte la entrada a vos mismo.")
    ...
```

🟨 **CONTROLLER:** conectarlo en la view con `try/except`:
```python
try:
    transfer_purchase(user=request.user, purchase_pk=pk, email=email)
except ValidationError as error:
    messages.error(request, error.messages[0])
    return redirect("my_tickets")
```
Import en la view: `from domain.tickets.services.transfers import transfer_purchase` y `ValidationError`.

**Prueba:** con tu propio correo tiene que aparecer el error; con otro correo, el mensaje de éxito.

---

### Paso 4 · 🟩 MODEL: el cambio real (dueño + código nuevo)

Al final del service:

```python
    # Buscar al destinatario: hace falta el OBJETO usuario, no el correo
    recipient = get_user_model().objects.filter(email=email).first()
    if recipient is None:
        raise ValidationError("No encontramos ningún usuario con ese correo.")

    purchase.user = recipient                             # pasa a la cuenta del destinatario
    purchase.validation_token = generate_ticket_token()   # código nuevo (QR + código corto)
    purchase.save()                                       # save() recalcula el digest
    return purchase
```

Imports: `get_user_model` (de `django.contrib.auth`), `transaction` (de `django.db`) y `generate_ticket_token` (de `domain.tickets.models`).

🟨 **CONTROLLER:** el mensaje de éxito pasa a ser el real:
```python
messages.success(request, f"Transferiste tus entradas a {email}. Se generó un nuevo código de acceso.")
```

**Por qué con 3 líneas se cumple todo el punto 3 de la consigna:**
- **"Mostrá la entrada en la cuenta del destinatario":** Mis entradas hace `TicketPurchase.objects.filter(user=request.user)`. Al cambiar `usuario_id`, la compra deja de aparecer en la cuenta del dueño anterior y aparece en la del destinatario. No se borra nada: es un `UPDATE` sobre la misma fila.
- **"Conservá la función y la butaca":** `AdmissionTicket` y `SeatPurchase` apuntan a la **compra**, no al usuario, así que viajan con ella.
- **"Generá un código nuevo e invalidá el anterior":** el token es la base de los dos códigos (QR de 32 caracteres y código corto de 6 letras, que es una `@property` calculada desde el token). Al reemplazarlo, el viejo deja de existir.

---

### Paso 5 · Caso de validación (demo)

Usuarios de staff que hay en la base local: `operador@local.test` (operador) y `gerente@local.test` (gerente).

1. Abrir el detalle de una compra con función futura y **anotar el código de reserva** de 6 letras.
2. Transferir a otro usuario registrado. La compra desaparece de mis Mis entradas.
3. Iniciar sesión como el destinatario: la compra aparece con **otro código**.
4. Iniciar sesión como operador, ir a `/gestion/` → validar entradas:
   - Código viejo → "No encontramos una entrada con ese código." ✅
   - Código nuevo → permite el ingreso ✅

Verificado con una prueba automática (compra de 2 butacas, con los cambios deshechos al final): el vendedor ve 0 compras y el destinatario ve 1, las butacas A1 y A2 y la función se conservan, el código viejo y el QR viejo se rechazan, y el código nuevo se acepta.

---

## Lo que aprendí

### Sobre cómo encarar el parcial
- **Buscar la "feature gemela"** y copiar su recorrido completo (template → url → view → service). Para acciones del cliente sobre su compra, la gemela es la **reprogramación**.
- **Construir de afuera hacia adentro: View → Controller → Model.** Cada paso es demostrable aunque el siguiente no salga.
- **Producto mínimo viable:** simplificar la consigna (compra completa en vez de una entrada, sin validar que el destinatario exista) cuando el tiempo no alcanza. Un 4 se logra con una parte hecha.
- **Sin CSS:** los estilos no suman puntos.
- **Probar cada validación con un caso que debería fallar.** Si solo pruebo el camino feliz, no me entero de que una validación nunca salta.

### Sobre Django
- **Los campos del modelo son atributos.** Un `ForeignKey` llamado `screening` da `purchase.screening` (el objeto) y `purchase.screening_id` (el número). Para saber qué atributos tiene algo: abrir su `models.py`, hacer Ctrl+clic sobre la clase, o buscar con Ctrl+Shift+F cómo lo usa otro código.
- **El `related_name` crea el camino inverso:** `purchase.tickets.all()`, `user.ticket_purchases.all()`. En los templates, `.all` va sin paréntesis.
- **`filter(pk=..., user=user).first()`** busca la compra y valida que sea del usuario en una sola línea. Si es ajena, da `None`, y el mensaje "No encontramos esa compra" no revela que existe.
- **El estado de una función no cambia solo con la hora.** `finalize_expired()` lo actualiza solo cuando alguien lo llama. Por eso "pendiente" se valida con **estado Y hora**.
- **`messages.success` / `messages.error`** solo se ven en templates que tienen `{% for message in messages %}`. `my_tickets.html` lo tiene; `ticket_detail.html` no.
- **`request.session["purchase_error"]`** (lo que usa la reprogramación) solo funciona si la pantalla destino lee esa variable. Copiar un patrón sin ver si el destino lo soporta hace que el error "desaparezca".
- **`error.messages[0]`** es el texto del `raise ValidationError("...")`.
- **`@transaction.atomic`** asegura que, si algo falla a mitad de camino, no quede nada a medias.
- **`save()` vs `save(update_fields=[...])`:** con `update_fields` solo se guardan los campos de la lista. Si me olvido de `validation_code_digest`, el código corto viejo **sigue funcionando** sin que se note. En el parcial, usar `save()` sin argumentos.
- **`get_user_model()`** es la forma de obtener el modelo de usuarios. `email__iexact` compara sin mayúsculas.
- **Asignar `None` a un campo obligatorio** (`purchase.user = None`) hace que la base lo rechace y la página da **500**. Por eso hay que validar que el destinatario exista antes de asignarlo.

### Sobre Python
- **`email.lower` sin paréntesis** es la *función*, no el resultado. `email.lower == algo` es siempre `False`: no da error, pero la validación nunca salta. Va `email.lower()`, y en **los dos lados** de la comparación.
- **Un `pk` es un número, no un objeto.** `purchase_pk.screening` explota con `AttributeError: 'int' object has no attribute ...`. Primero hay que buscar el objeto en la base.

### Sobre imports (el error que tira todo el sitio)
- **`from paquete import algo`** solo funciona si el `__init__.py` del paquete lo expone. Hay dos soluciones: agregarlo al `__init__.py`, o importarlo directo del archivo (`from domain.tickets.services.transfers import transfer_purchase`).
- Un import roto en un archivo de views **hace caer TODAS las páginas**, no solo la feature. **Hábito:** después de cada cambio en Python, recargar una página cualquiera o correr `python manage.py check`.

### Sobre la base de datos y git
- **`git reset` / `git stash` no deshacen migraciones aplicadas.** Si descarto código que tenía migraciones ya corridas, la base queda con columnas que el código no conoce (me pasó con `idioma` y `movies_favorite`). Antes de descartar: `python manage.py migrate <app> <migración_anterior>`.
- Para cargar funciones de prueba: `docker compose exec web python manage.py seed_demo --offline --days 7`.

---

## Tabla rápida de errores

| Veo… | Significa… |
|---|---|
| **405** Method Not Allowed | El form envía POST a una view que solo acepta GET (o al revés) |
| **403** CSRF | Falta `{% csrf_token %}` en el form |
| `NoReverseMatch` | El nombre en `{% url '...' %}` no coincide con ningún `name=` de urls.py |
| `AttributeError: module 'web.tickets.views' has no attribute ...` | Falta exportar la view en `views/__init__.py` |
| `ImportError: cannot import name ...` (se cae todo el sitio) | El `__init__.py` del paquete no expone esa función |
| `NameError: name 'messages' is not defined` | Falta un import |
| `AttributeError: 'int' object has no attribute ...` | Uso un `pk` como si fuera el objeto |
| La validación nunca salta, sin errores | Revisar paréntesis (`.lower()`) y probar con un caso que debería fallar |
| El error no se muestra al usuario | La pantalla destino no muestra `messages` (o no lee la variable de sesión) |
| **500** al guardar | Asigné `None` a un campo obligatorio, o la base tiene columnas que el código no conoce |
| `NoReverseMatch` en un `redirect(...)` de la vista | Mismo error que en el template: el nombre está mal escrito o le falta el namespace (`manager:`). Copiar el `name=` de `urls.py`, no escribirlo de memoria |
| **500** `ValueError: invalid literal for int()` | `int()` sin `try/except` (con `abc`, `2.5` o vacío) |
| **500** `MultiValueDictKeyError` | `request.POST["x"]` con corchetes y el campo no llegó → usar `request.POST.get("x", "")` |
| **403** siendo cliente en una vista del gerente | Es lo esperado: lo pone el `ManagerRequiredMixin`. Si **no** da 403, falta el mixin |
| **Localhost caído** (el contenedor `web` dice "Restarting") | Error de sintaxis o de import en **cualquier** archivo `.py`, aunque no sea el de la feature. Correr `docker compose logs --tail 30 web`: las últimas líneas dicen archivo y línea |

---

## Receta para cualquier feature del recuperatorio (90 min)

1. **(5 min) Leer la consigna** y separar: ¿qué ve el usuario? (View) ¿qué URL y acción? (Controller) ¿qué reglas y qué datos cambian? (Model)
2. **(5 min) Encontrar la feature gemela** y abrir sus 3 archivos: template, view y service.
3. **🟦 View:** botón o form en el template existente. Probar: aparece.
4. **🟨 Controller:** view mínima + export en `__init__` + ruta + `action`. Probar: aparece el mensaje.
5. **🟩 Model:** service solo con validaciones (`if <malo>: raise ValidationError`) + `try/except` en la view. Probar cada error.
6. **🟩 Model:** el cambio real de datos + `save()`. Probar el camino feliz.
7. **Caso de validación** de la consigna, preparado para mostrar.

Después de cada paso: **recargar la página** (o `manage.py check`) para cazar errores de import a tiempo.

---

# Recap: todas las features que practiqué

Toda vista web responde a un **GET**, a un **POST** o a los dos.

- **GET** = solo **mira** datos. Links (`<a>`) y forms de búsqueda/filtro. **Sin** `csrf_token`.
- **POST** = **cambia** datos. Forms con `{% csrf_token %}`. Después: `redirect` + mensaje.

Matiz: en algunas features **no escribí la vista**. Metí la regla en un flujo que ya existía (la vista del proyecto ya recibía el POST; yo agregué la validación adentro).

## Tabla de features

| # | Feature | Lado | Método | Cómo es la vista | Lo nuevo que aprendí |
|---|---|---|---|---|---|
| 1 | Transferir entrada | Cliente | **POST** | Función + `@require_POST` | El patrón completo: form → ruta → vista con `try/except` → service con `raise` → `save()` |
| 2 | Cancelar compra | Cliente | **POST** | Función + `@require_POST` | `delete()` heredado y el `CASCADE` |
| 3 | Reponer stock | Gerente | **POST** | Clase `DetailView` + `def post` | Vistas con clases, `{% url %}` con namespace, objeto vs pk |
| 4 | Asistentes de una función | Gerente | **GET** | Clase `DetailView` + `get_context_data` | Pantallas que solo muestran, `related_name`, `{% empty %}` |
| 5 | Calificar función | Cliente | **POST** | Función + `@require_POST` | Campo nuevo con migración, `null` vs `blank` |
| 6 | Ranking de películas | Gerente | **GET** | Clase `ListView` + `get_queryset` | `annotate`/`Sum`/`Coalesce`, form GET con filtros, filtros en **un solo** `.filter()` |
| 7 | Buscar en Mis entradas | Cliente | **GET** | Función existente + `request.GET` | Queryset vs lista; filtrar en la base o en Python |
| 8 | Filtrar cartelera por género | Cliente | **GET** | Función existente + `request.GET` | `<select>` desde `choices`; valor guardado vs texto mostrado |
| 9 | Límite de entradas por cliente | Gerente + cliente | **POST** (existente) | Sin vista nueva: regla en `buy_tickets` | Campo en `CinemaSettings`, `aggregate`, tocar un service grande |
| 10 | Cancelar candy | Cliente | **POST** | Función + `@require_POST` | Reutilizar un método del modelo (`restock()`) |
| 11 | Vigencia de promociones | Gerente | **POST** (existente) | Sin vista nueva: el `UpdateView` ya hace GET (form) y POST (guardar) | `clean()` en el modelo, campo vs widget, `date` vs `datetime`, rangos |
| 12 | Horario de apertura de sala | Operador + cliente | **POST** (existente) + **GET** | Regla en `check_purchase` | Flujo del operador, `timedelta`, hora local |
| 13 | Aumento de precio de butaca | Gerente | **POST** | Clase `DetailView` + `def post` | `Decimal`, redondeo, snapshots de precios |
| 14 | Devolver stock de candy al cancelar compra | Cliente | **POST** (existente) | Sin vista nueva: consecuencia en `ticket_cancel` | Efectos automáticos de una acción que ya existe |
| 15 | Idioma de funciones | Gerente + cliente | **POST** (existente) + **GET** | Campo con `choices` + form existente | Campo nuevo con choices, mostrarlo con `get_..._display` |
| 16 | Productos sin TACC | Gerente + cliente | **POST** (existente) + **GET** | Campo en el form existente + templates | `BooleanField` para sí/no, partials compartidos, `@property` con el mismo nombre en dos modelos |
| 17 | Regenerar código de acceso | Cliente | **POST** | Función + `@require_POST` | Reutilizar una gemela propia (la transferencia) casi entera |
| 18 | Registrar merma de candy | Gerente | **POST** | Clase `DetailView` + `def post` | Bordes de una comparación (`0`, el stock exacto), `int()` protegido, `ManagerRequiredMixin` |

## Las 3 formas que se repiten

**A. Acción que modifica (POST)**: features 1, 2, 3, 5, 10, 13, 17, 18

```
Template: <form method="post"> + {% csrf_token %}
Vista:    @require_POST (o def post)
          try: service(...)
          except ValidationError: messages.error + return redirect
          messages.success + redirect
Service:  buscar → if malo: raise → cambiar → save() / delete()
```

**B. Pantalla que muestra (GET)**: features 4, 6, 7, 8

```
Template: <a href> o <form method="get"> (sin csrf_token)
Vista:    request.GET.get("x", "") → if x: filter(...) → annotate → context
Template: {% for %} ... {% empty %}
```

**C. Regla en un flujo existente**: features 9, 11, 12, 14 (y 15, 16: campo nuevo en un form que ya existe)

```
Buscar dónde el proyecto ya valida (service, clean(), applies_to)
→ agregar un if más del mismo estilo
→ si hay que configurarla: campo en CinemaSettings + en CinemaSettingsForm + migrar
```

> **Primera pregunta al leer la consigna:** ¿esto **modifica**, **muestra**, o **agrega una regla** a algo que ya existe? Eso define la forma y la gemela a copiar.

## Imports que suelo necesitar

**Vista (Controller), en `web/<área>/views/*.py`**

```python
# De Django
from django.contrib import messages                                  # messages.success / messages.error
from django.contrib.auth.decorators import login_required            # vistas función (cliente)
from django.core.exceptions import ValidationError                   # para el except
from django.shortcuts import redirect                                # redirect después del POST
from django.views.decorators.http import require_GET, require_POST   # vistas función
from django.views.generic import DetailView, ListView                # vistas clase (gerente)

# Míos
from web.manager.access import ManagerRequiredMixin                  # solo vistas del gerente
from domain.<app>.services.<archivo> import <mi_funcion>             # el service de la feature
from domain.<app>.models import <MiModelo>                           # si la vista usa el modelo (model = ...)
```

**Service (Model), en `domain/<app>/services/*.py` o `domain/candy/services.py`**

```python
from django.contrib.auth import get_user_model       # buscar usuarios: get_user_model().objects...
from django.core.exceptions import ValidationError   # raise ValidationError("...")
from django.db import transaction                    # @transaction.atomic
from django.utils import timezone                    # timezone.now(), timezone.localdate(), timezone.localtime()
from datetime import timedelta                       # sumar/restar minutos u horas
from decimal import Decimal, ROUND_HALF_UP           # plata

from domain.screenings.models import Screening       # Screening.Status.PUBLISHED
from domain.tickets.models import AdmissionTicket, TicketPurchase, generate_ticket_token
from domain.candy.models import CandyProduct, CandyCombo
from domain.cinema.models import CinemaSettings      # CinemaSettings.current()
```

**Export para `urls.py`**, en `web/<área>/views/__init__.py`:

```python
from web.tickets.views.purchases import mi_vista as mi_vista
```

**Consultas (en services o vistas GET)**

```python
from django.db.models import Count, Q, Sum            # annotate / aggregate / filtros con OR
from django.db.models.functions import Coalesce       # Coalesce(Sum("x"), 0)
```

> Si no me acuerdo de un import: **Ctrl+Shift+F** buscando el nombre (por ejemplo `import messages` o `ManagerRequiredMixin`) y copio la línea de otro archivo del proyecto.
> Después de agregar imports: `docker compose exec -T web python manage.py check`.

## Vista de cliente vs vista de gerente

| | **Cliente** (`web/tickets`) | **Gerente** (`web/manager`) |
|---|---|---|
| Tipo de vista | **Función** | **Clase** |
| Quién puede entrar | `@login_required` | `ManagerRequiredMixin`, **primero** en la herencia |
| Solo POST | `@require_POST` | Escribo solo `def post(...)`: por GET muestra el detalle (o nada si no tiene template) |
| El request | `request` | `request` (dentro de `post`) o `self.request` (en otros métodos) |
| El objeto | Lo busco en el service con `pk` y `user=request.user` | `self.get_object()` (usa `model = ...` y el `pk` de la URL) |
| Validar que sea **suyo** | Sí: `filter(pk=pk, user=user)` | No hace falta: el gerente puede tocar cualquiera |
| Nombre en `redirect` / `{% url %}` | Sin namespace: `"my_tickets"` | Con namespace: `"manager:candy_products_list"` |
| Ruta en `urls.py` | `views.mi_vista` | `views.MiVista.as_view()` |
| Si entra quien no debe | Redirige al login | **403** |

**Cliente (función):**

```python
@login_required
@require_POST
def ticket_algo_view(request, pk):
    try:
        mi_service(user=request.user, purchase_pk=pk)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("my_tickets")
    messages.success(request, "Lo que pasó de verdad.")
    return redirect("my_tickets")
```

```python
path("mis-entradas/<int:pk>/algo/", views.ticket_algo_view, name="ticket_algo"),
```

**Gerente (clase):**

```python
class CandyAlgoView(ManagerRequiredMixin, DetailView):
    model = CandyProduct

    def post(self, request, *args, **kwargs):
        producto = self.get_object()
        cantidad = request.POST.get("quantity", "")
        try:
            mi_service(producto, cantidad)
        except ValidationError as error:
            messages.error(request, error.messages[0])
            return redirect("manager:candy_products_list")
        messages.success(request, "Lo que pasó de verdad.")
        return redirect("manager:candy_products_list")
```

```python
path("candy/productos/<int:pk>/algo/", views.CandyAlgoView.as_view(), name="candy_products_algo"),
```

```html
<form method="post" action="{% url 'manager:candy_products_algo' product.pk %}">
```

Lo que **no cambia** entre las dos: `try/except ValidationError` + `return redirect` en el `except`, `messages`, `{% csrf_token %}` en el form y el service con `raise`.

## Vistas con clases: cuál elegir

| Pantalla | Clase | URL con `pk` | Método que sobrescribo |
|---|---|---|---|
| Acción POST sobre un objeto | `DetailView` (o `View`) | Sí | `post` + `self.get_object()` |
| Mostrar un objeto | `DetailView` | Sí | `get_context_data` |
| Mostrar una lista | `ListView` | No | `get_queryset` (y `get_context_data`) |
| Crear/editar con form | `ManagerCreateView` / `ManagerUpdateView` | Editar: sí | Ninguno: solo atributos |

- En clases, el request es `self.request`. En funciones, `request`.
- La `ListView`/`DetailView` de Django **no** ponen `section` sola: `context["section"] = "..."` (si no, el menú marca "Inicio").
- En el template, un `DetailView` llama al objeto `object`; un `ListView`, `object_list`.

## Lookups de filtros (sin internet)

Forma: `camino__campo__operador=valor`

| Operador | Significa |
|---|---|
| (nada) | igual |
| `__gte` / `__lte` / `__gt` / `__lt` | ≥ / ≤ / > / < |
| `__isnull=True/False` | es / no es NULL |
| `__in=[...]` | está en la lista |
| `__iexact` | igual sin importar mayúsculas |
| `__icontains` | contiene, sin importar mayúsculas |
| `__date` | solo el día de un datetime |

- Siempre **doble** guion bajo. `date_lte` → `Unsupported lookup`.
- Ejemplos reales: **Ctrl+Shift+F** buscando `__gte`, `__icontains`, `__date`.
- Probar antes en `docker compose exec web python manage.py shell`.
- `Cannot resolve keyword ... Choices are:` → lista los nombres válidos.
- Si sumo/cuento a través de una relación "muchos": **todos los filtros en un mismo `.filter()`** (si no, los totales se multiplican).

## Cosas de Django que tengo que recordar

- **Todo modelo hereda** `save()`, `delete()`, `refresh_from_db()`. Lo propio del negocio (`restock()`, `applies_to()`) está escrito en el modelo.
- **Migrar solo si cambia la tabla**: campos u opciones de campos. Una `@property` o método no se migra. Si dudo: `makemigrations` → "No changes detected".
- **`null=True` + `blank=True`** para campos opcionales. Solo `null` → "Este campo no puede estar en blanco".
- **El template solo ve lo que está en el context.** Una variable que no existe se muestra vacía, sin error.
- **En el `<option>` y en los `choices`**: viaja/se guarda el **valor** (`"ACCION"`), se muestra el **texto** (`"Acción"`).
- **Campo vs widget**: `forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))`.
- **Validación del navegador** (`min`, `max`, `type="number"`) no protege: siempre validar en el servidor. Para probarlo: F12 y agregar `step="any"`.
- **`date` vs `datetime`**: `timezone.localdate()` para `DateField`, `timezone.now()` para `DateTimeField`, `.date()` para pasar de uno a otro.
- **Hora local en mensajes**: `timezone.localtime(x)` y `f"{x:%H:%M}"`. En templates, `|date:"H:i"` ya convierte.
- **Plata = `Decimal`**, nunca `float`. Redondear el **resultado**: `.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`.
- **Snapshots**: funciones y compras guardan una **foto** de precios/capacidad al crearse. Cambiar el precio base no afecta lo ya creado.
- **`aggregate(total=Sum("x"))["total"] or 0`**: un solo total. `annotate`: un total por cada objeto.
- **Sí/no = `BooleanField(default=False)`**. Con eso, el form ya muestra un checkbox y no hace falta `@property`.
- **`request.POST.get("x", "")`** en vez de `request.POST["x"]`: si el campo no llega, la versión con corchetes da 500.
- **Leer el `save()` del modelo** antes de tocar campos especiales: puede tener lógica escondida (por ejemplo, `TicketPurchase.save()` genera el token si está vacío y recalcula el digest).
- **Vistas del gerente:** `ManagerRequiredMixin` primero. Probar entrando como cliente: tiene que dar **403**.

## Mis errores más repetidos (revisar antes de entregar)

1. **`None` sin proteger** antes de comparar → `if x is not None and ...` / `if a and b:`.
2. **`int()` sin `try/except ValueError`** → convertir el error en `ValidationError`. ⚠️ **Repetido en 3 features (reponer stock, aumento de precio, merma).** Antes de la demo, probar con `abc`, `2.5` y vacío.
3. **Imports con `django.` adelante** (autocompletado de VS Code). Mis módulos: `web.` o `domain.`.
4. **Mensajes que no dicen la verdad** (copiados de la gemela o antes de que exista la lógica).
5. **Signos invertidos** en comparaciones → poner **el dato a evaluar a la izquierda**: `dia < inicio or dia > fin`.
6. **`except` sin `return redirect(...)`** → la vista sigue de largo y explota.
7. **Cambiar un atributo no guarda nada**: falta `save()`; y `x = None` no borra: es `delete()`.
8. **Bordes de las comparaciones**: `<` vs `<=`. Leer la consigna ("mayor a cero" → el `0` se rechaza) y probar el valor justo en el límite.
9. **Olvidar el `ManagerRequiredMixin`** en vistas del gerente → cualquier cliente puede usarlas.
10. **Tipo de campo más complicado que la consigna** (`CharField` con choices para un sí/no) → más código y más lugares donde equivocarse.

### Checklist de 2 minutos antes de la demo

- [ ] ¿El mensaje de éxito dice lo que pasó de verdad? ¿Los mensajes de error son míos o copiados de la gemela?
- [ ] ¿Probé `abc`, `2.5`, vacío, `0` y el valor límite en cada input?
- [ ] ¿Cada `except` termina en `return redirect(...)`?
- [ ] ¿La vista del gerente tiene `ManagerRequiredMixin`?
