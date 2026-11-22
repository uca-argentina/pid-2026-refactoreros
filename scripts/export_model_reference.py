"""Exporta metadatos de Django y recetas de consulta a un PDF, sin consultar filas.

Desde la raíz: python scripts/export_model_reference.py
Dependencia opcional: python -m pip install -r scripts/requirements-docs.txt
"""

import argparse
import inspect
import os
from datetime import date
from pathlib import Path
import sys
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "django"))

DESCRIPTIONS = {
    "CinemaSettings": "Configuración del cine, identidad visual y plazos de reserva, ingreso y reprogramación.",
    "Movie": "Película del catálogo: título, sinopsis, género, clasificación y duración.",
    "Room": "Sala física y configuración de su distribución. Su capacidad se calcula desde las butacas.",
    "SeatType": "Tipo de butaca: precio base, color e icono. Las funciones conservan sus propias copias de precios.",
    "Seat": "Butaca física de una sala, identificada por fila y columna y asociada a un tipo.",
    "Screening": "Proyección de una película en una sala y horario. Conserva snapshots de distribución, capacidad y precios.",
    "Customer": "Perfil de cliente asociado a User. El correo y la contraseña pertenecen a User.",
    "Usher": "Perfil de acomodador asociado a User.",
    "Operator": "Perfil de operador asociado a User, utilizado para autorizar validaciones y retiros.",
    "Manager": "Perfil de gerente asociado a User. No equivale automáticamente a is_staff ni is_superuser.",
    "TicketPurchase": "Compra de entradas de un usuario para una función. Agrupa cantidad, importe, snapshot de butacas y credencial de ingreso.",
    "AdmissionTicket": "Entrada individual dentro de una compra. Identifica su número, butaca y uso; el dueño se obtiene de purchase.user.",
    "SeatPurchase": "Ocupación vendida de una butaca en una función. La unicidad función/etiqueta impide duplicarla.",
    "SeatReservation": "Bloqueo temporal de una butaca durante la selección. No es una entrada comprada.",
    "AdmissionValidation": "Evento de ingreso realizado por un operador. Su relación múltiple registra las entradas validadas.",
    "PurchaseRefund": "Devolución asociada a una compra, con importe y seguimiento de notificación.",
    "Promotion": "Regla de descuento porcentual o fijo, aplicable por día, horario y tipo de butaca.",
    "CandyProduct": "Producto individual del Candy, con categoría, precio, stock y disponibilidad comercial.",
    "CandyCombo": "Combo comercial con precio propio y componentes definidos mediante CandyComboItem.",
    "CandyComboItem": "Componente de un combo: producto y cantidad requerida por unidad del combo.",
    "CandyOrder": "Pedido Candy originado en una compra de entradas, compra independiente o premio. Guarda un snapshot de ítems y credencial de retiro.",
    "CandyPickup": "Evento de entrega de un pedido Candy, con operador y posibilidad de reversión temporal.",
    "GameAccount": "Estado de juego por usuario: intentos, tiradas, próximo acceso diario y revisión de concurrencia.",
    "Question": "Pregunta de trivia con tres opciones, respuesta correcta, dificultad y habilitación.",
    "WheelConfig": "Configuración de la ruleta y duración de preguntas; revisión utilizada para coordinar cambios.",
    "WheelSlot": "Tipo de resultado de la ruleta y cantidad/posición de sus casillas; puede entregar un producto Candy.",
    "TriviaRun": "Partida de trivia con snapshot privado de preguntas, avance y control de tiempo.",
    "TriviaAnswer": "Respuesta a un paso de una partida; registra opción, corrección y vencimiento del tiempo.",
    "QuestionUse": "Historial de asignación de preguntas utilizado para evitar repeticiones y aplicar el enfriamiento global.",
    "WheelSpin": "Resultado de una tirada con copia del layout, posición elegida y clave de idempotencia.",
    "PrizeCoupon": "Premio ganado en una tirada, con dueño, producto, estado y eventual pedido de retiro.",
    "GameEvent": "Registro de eventos del juego, usuario afectado, actor y datos adicionales.",
    "User": "Cuenta de autenticación de Django: identidad, contraseña cifrada, permisos y acceso. Los perfiles del cine son relaciones separadas. Para contraseñas usar create_user()/set_password(); no exponer hashes.",
    "Group": "Grupo de permisos de Django. No sustituye los perfiles de cliente, gerente, operador o acomodador.",
    "Permission": "Permiso de Django asociado a un tipo de contenido.",
    "ContentType": "Identifica una clase de modelo mediante aplicación y nombre; utilizado por permisos y admin.",
    "Session": "Sesión de Django, con datos codificados y fecha de vencimiento.",
    "LogEntry": "Registro de acciones del administrador de Django.",
}

MEANINGS = {
    "id": "Identificador automático del registro.", "name": "Nombre visible.",
    "title": "Título de la película.", "synopsis": "Descripción argumental.",
    "genre": "Código del género.", "rating": "Código de clasificación etaria.",
    "duration_minutes": "Duración en minutos.", "image": "Ruta o nombre del archivo de imagen; no sus bytes.",
    "logo": "Archivo de logotipo.", "login_image": "Imagen de acceso.",
    "slogan": "Texto de identidad del cine.",
    "seat_reservation_minutes": "Duración de la reserva, en minutos.",
    "seat_refresh_seconds": "Intervalo de actualización de butacas, en segundos.",
    "admission_undo_seconds": "Plazo para deshacer una validación, en segundos.",
    "candy_max_item_quantity": "Máximo de unidades por ítem Candy.",
    "ticket_reprogram_minutes": "Anticipación mínima de reprogramación, en minutos.",
    "layout_configuration": "Distribución configurable de la sala, como estructura JSON.",
    "row": "Índice de fila de la butaca.", "column": "Índice de columna de la butaca.",
    "base_price": "Precio base del tipo de butaca.", "color": "Texto del color de presentación.",
    "icon": "Ruta del archivo del icono.", "starts_at": "Inicio; su tipo determina si incluye fecha.",
    "ends_at": "Fin del intervalo horario.", "status": "Código de estado persistido.",
    "ticket_price": "Precio de entrada usado como respaldo.",
    "prices_by_type": "Mapa tipo_id como texto → precio como texto.",
    "room_layout_snapshot": "Copia histórica de filas, columnas y butacas de la función.",
    "capacity_snapshot": "Capacidad capturada al configurar/publicar la función.",
    "quantity": "Cantidad de unidades o entradas según la entidad.",
    "total": "Importe decimal del registro.",
    "selected_seats": "Lista de butacas con etiqueta y copia de precios/promociones.",
    "created_at": "Fecha y hora de creación.", "updated_at": "Fecha y hora de última actualización.",
    "validation_token": "Token único de la credencial de compra.",
    "validation_code_digest": "Hash del código corto de la compra; no el código legible.",
    "number": "Número de entrada dentro de la compra; no es su ID global.",
    "seat_label": "Etiqueta visible de butaca, por ejemplo 1A.",
    "code": "Token individual de entrada; el operador actual valida credenciales de compra.",
    "used_at": "Fecha/hora de utilización; NULL significa sin utilizar.",
    "label": "Etiqueta o texto descriptivo, según entidad.",
    "reverted_at": "Fecha/hora de reversión; NULL si no se revirtió.",
    "reference": "Referencia única de devolución.", "amount": "Importe de devolución.",
    "notice": "Texto de notificación.", "email_sent_at": "Envío del correo; NULL si falta.",
    "read_at": "Lectura de la notificación; NULL si falta.",
    "expires_at": "Vencimiento de la reserva temporal.",
    "is_active": "Habilitación del registro.", "active": "Habilitación del registro.",
    "discount_type": "Tipo de descuento: porcentaje o importe fijo.",
    "discount_value": "Valor del descuento; depende del tipo.",
    "weekdays": "Lista de días: lunes=0 a domingo=6; vacía indica todos.",
    "category": "Código de categoría del producto.", "price": "Precio decimal de venta.",
    "stock": "Unidades disponibles del producto.", "items": "Snapshot de líneas de pedido, precios y componentes.",
    "reward_key": "Clave de idempotencia del pedido de premios.",
    "checkout_key": "Clave de idempotencia de compra independiente.",
    "pickup_token": "Token único de retiro.", "pickup_code_digest": "Hash del código corto de retiro.",
    "delivered_at": "Fecha/hora de entrega; NULL si no se entregó.",
    "restocked_at": "Fecha/hora de reposición de inventario.",
    "extra_attempts": "Intentos adicionales de trivia.", "spins": "Tiradas disponibles.",
    "next_daily_at": "Fecha/hora del próximo acceso diario.",
    "revision": "Contador de revisión para coordinación de cambios.",
    "text": "Texto de la pregunta.", "options": "Lista JSON de tres respuestas.",
    "correct": "En Question: índice correcto 0–2; en TriviaAnswer: resultado booleano.",
    "difficulty": "Código numérico de dificultad.",
    "question_seconds": "Tiempo permitido por pregunta, en segundos.",
    "kind": "Código de tipo de resultado o evento.", "count": "Cantidad de casillas de ese resultado.",
    "position": "Posición de orden de configuración.",
    "key": "Clave de operación o idempotencia; ver restricciones compuestas.",
    "questions": "Snapshot privado de preguntas; no devolver íntegro al navegador.",
    "step": "Índice del paso de trivia.", "source": "Origen de la partida.",
    "finished_at": "Finalización de partida; NULL mientras está activa.",
    "question_started_at": "Inicio del tiempo de la pregunta actual.",
    "choice": "Índice de opción elegida; NULL cuando no se respondió.",
    "timed_out": "Indica vencimiento del tiempo de respuesta.",
    "fingerprint": "Huella de identidad de la pregunta para detectar repeticiones.",
    "layout": "Snapshot del layout de ruleta de esa tirada.", "index": "Índice de resultado elegido.",
    "redeemed_at": "Fecha/hora de canje del premio.", "data": "Datos JSON adicionales del evento.",
    "username": "Nombre de acceso único.", "email": "Correo; el User estándar no exige unicidad.",
    "first_name": "Nombre de la persona.", "last_name": "Apellido de la persona.",
    "password": "Hash de contraseña; modificar mediante set_password, no con texto plano.",
    "last_login": "Fecha/hora de último acceso.", "date_joined": "Alta de la cuenta.",
    "is_staff": "Permite acceso al admin si los permisos lo habilitan.",
    "is_superuser": "Otorga todos los permisos del sistema de autenticación.",
    "codename": "Código interno del permiso.", "app_label": "Etiqueta de aplicación.",
    "model": "Nombre interno del modelo.", "session_key": "Clave de sesión.",
    "session_data": "Contenido codificado de la sesión.", "expire_date": "Vencimiento de sesión.",
    "action_time": "Fecha y hora de acción en el admin.", "object_id": "Identificador del objeto afectado, como texto.",
    "object_repr": "Representación textual del objeto al registrar la acción.",
    "action_flag": "Código de acción del administrador.", "change_message": "Descripción o estructura de cambios del admin.",
}

SPECIAL_NOTES = {
    "TicketPurchase": "save() al crear genera quantity AdmissionTicket, calcula credenciales y reintenta colisiones. No crea SeatPurchase. full_clean() no se ejecuta automáticamente al llamar save(). Una edición no sincroniza entradas/ocupación. Usar el servicio de compra o reprogramación para operaciones completas.",
    "Screening": "Usar change_status() para transiciones. save() puede capturar configuración y, al cancelar, generar devoluciones y notificaciones. No cambiar status mediante update(). ends_at, available_capacity y price_from son propiedades calculadas, no columnas.",
    "CandyOrder": "Tiene un único origen: purchase, o reward_user+reward_key, o customer+checkout_key. save() calcula credenciales. Usar los servicios Candy para stock y pedidos. user_id es una propiedad calculada a partir del origen, no una columna.",
    "AdmissionTicket": "El servicio de ingreso consulta la credencial de TicketPurchase, no code ni BC1. El dueño de esta entrada es purchase.user. No mover solo su FK sin revisar ocupación y snapshot de la compra.",
    "Seat": "La posición física se define por room, row y column. La etiqueta de venta es otro dato. La ocupación es por función y se registra en SeatPurchase.",
    "Promotion": "Los tipos de butaca se vinculan mediante una tabla intermedia automática. Una lista vacía de tipos o días tiene significado de aplicación general según las reglas del modelo.",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/modelo-butaca-cero.pdf")
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "butacaCero.settings")
    # Solo inicialización de metadatos; no inicia servidor ni lee filas de la base.
    os.environ.setdefault("DJANGO_SECRET_KEY", "metadata-export-only")
    import django
    django.setup()
    from django.apps import apps
    from django.db import models
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table,
        TableStyle, PageBreak, Preformatted,
    )

    font_pairs = [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    ]
    normal, bold = next(((a, b) for a, b in font_pairs if a.exists() and b.exists()), (None, None))
    if normal:
        pdfmetrics.registerFont(TTFont("Doc", str(normal)))
        pdfmetrics.registerFont(TTFont("DocBold", str(bold)))
        pdfmetrics.registerFontFamily("Doc", normal="Doc", bold="DocBold", italic="Doc", boldItalic="DocBold")
        regular, strong = "Doc", "DocBold"
    else:
        regular, strong = "Helvetica", "Helvetica-Bold"
    navy, teal = colors.HexColor("#17283D"), colors.HexColor("#087F8C")
    styles = {
        "title": ParagraphStyle("title", fontName=strong, fontSize=23, leading=28, textColor=navy, spaceAfter=14),
        "h": ParagraphStyle("h", fontName=strong, fontSize=12, leading=16, textColor=teal, spaceBefore=11, spaceAfter=7, keepWithNext=True),
        "body": ParagraphStyle("body", fontName=regular, fontSize=9.3, leading=13, textColor=navy, spaceAfter=7),
        "guide": ParagraphStyle("guide", fontName=regular, fontSize=9.3, leading=12, textColor=navy, spaceAfter=6),
        "small": ParagraphStyle("small", fontName=regular, fontSize=7.4, leading=9.6, textColor=navy, spaceAfter=0, splitLongWords=True),
        "code": ParagraphStyle("code", fontName="Courier", fontSize=7.6, leading=11, spaceAfter=9),
    }
    story = []
    def p(text, style="body"):
        story.append(Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[style]))
    def h(text):
        p(text, "h")
    def code(text):
        story.append(Preformatted(text, styles["code"]))
    def table(rows, widths):
        data = [[Paragraph(escape(str(cell)).replace("\n", "<br/>"), styles["small"]) for cell in row] for row in rows]
        t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E4F1F3")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
            ("LINEBELOW", (0,0), (-1,0), 1, teal),
            ("LINEBELOW", (0,1), (-1,-1), .25, colors.HexColor("#DAE1E8")),
        ]))
        story.append(t)

    all_models = list(apps.get_models(include_auto_created=True))
    business = [m for m in all_models if m.__module__.startswith("domain.") and not m._meta.auto_created]
    infrastructure = [m for m in all_models if not m.__module__.startswith("domain.") and not m._meta.auto_created]
    joins = [m for m in all_models if m._meta.auto_created]
    business.sort(key=lambda m: (m._meta.app_label, m.__name__))
    model_order = business + infrastructure + joins
    p("Butaca Cero\nReferencia del modelo y del ORM", "title")
    p(f"Generado el {date.today():%d/%m/%Y} desde los modelos de Django {django.get_version()}.")
    p(f"Incluye {len(business)} entidades de dominio, {len(infrastructure)} modelos de infraestructura y {len(joins)} tablas de relación automáticas. No contiene datos de usuarios ni filas de la base.")
    h("Cómo leer esta guía")
    p("Los nombres Python se usan en filter(), order_by() y asignaciones. La columna SQL puede conservar un nombre distinto en español. El esquema descrito es el declarado por el código: no verifica migraciones aplicadas ni el estado real de la base.")
    p("Cada entidad incluye tabla física, ubicación, campos, tipo Python, restricciones, orden, relaciones, propiedades y métodos. Las propiedades calculadas no son campos y no admiten filter/order_by sin una anotación equivalente.")
    h("Mapa de relaciones principales")
    table([
        ["Origen", "Relación", "Destino"],
        ["User", "1 a muchas compras; 1 a 1 por perfil", "TicketPurchase; Customer/Manager/Operator/Usher"],
        ["Movie / Room", "1 a muchas funciones", "Screening"],
        ["Room / SeatType", "1 a muchas butacas físicas", "Seat"],
        ["Screening", "1 a muchas compras y ocupaciones", "TicketPurchase / SeatPurchase"],
        ["TicketPurchase", "1 a muchas entradas y butacas; 1 a 1 devolución", "AdmissionTicket / SeatPurchase / PurchaseRefund"],
        ["AdmissionValidation", "muchas a muchas entradas", "AdmissionTicket"],
        ["Promotion", "muchas a muchos tipos", "SeatType"],
        ["CandyCombo", "muchos productos con cantidad por componente", "CandyComboItem → CandyProduct"],
        ["CandyOrder", "un origen: compra, cliente o premio", "TicketPurchase / User"],
        ["User", "partidas, tiradas, premios y eventos", "TriviaRun / WheelSpin / PrizeCoupon / GameEvent"],
    ], [125, 210, 170])
    h("Persistencia y reglas")
    p("Asignar un atributo modifica memoria; save() persiste. save() no ejecuta full_clean() automáticamente. update()/bulk_update()/bulk_create() omiten el save() de cada objeto. atomic() agrupa escrituras; los servicios utilizan bloqueos para coordinar concurrencia. Una ForeignKey no sustituye la autorización del usuario.")
    p("Acceso inverso: en uno-a-uno se obtiene un atributo de objeto que puede no existir. En FK y muchos-a-muchos se obtiene un manager con all()/filter(). El nombre del atributo inverso puede diferir del nombre usado en filtros.")
    story.append(PageBreak())
    p("Consultas, tipos y ordenación", "title")
    h("Ascendente y descendente para cada campo")
    p("En las tablas, la columna Orden indica el nombre que debe pasarse a order_by. Ascendente: Modelo.objects.order_by('campo'). Descendente: Modelo.objects.order_by('-campo'). Para desempatar: order_by('campo', 'pk'). En los helpers: ordenar(Modelo, 'campo', descendente=True).")
    p("Texto: orden según colación de la base; números: valor numérico; fechas: cronología; booleanos: falso/verdadero. Los NULL y su posición pueden variar por base; usar expresiones asc/desc(nulls_last=True) cuando sea necesario. En relaciones se recomienda ordenar por nombre relacionado o por el atributo _id para ordenar identificadores explícitamente.")
    code("Movie.objects.order_by('title')\nMovie.objects.order_by('-title')\nTicketPurchase.objects.order_by('-created_at', 'pk')\nScreening.objects.order_by('movie__title', '-starts_at')\nSeat.objects.order_by('room_id', 'row', 'column')")
    h("Tipos y búsquedas habituales")
    table([
        ["Dato", "Tipo Python", "Ejemplo ORM"],
        ["CharField / TextField", "str", "filter(title__icontains='aventura')"],
        ["Integer / PositiveInteger", "int", "filter(quantity__gte=2)"],
        ["DecimalField", "Decimal", "filter(total__gte=Decimal('1000.00'))"],
        ["BooleanField", "bool", "filter(is_active=True)"],
        ["DateTimeField / TimeField", "datetime / time", "filter(starts_at__gt=timezone.now())"],
        ["ForeignKey / OneToOne", "modelo o ID vía _id", "filter(purchase__user=usuario)"],
        ["NULL", "None", "filter(used_at__isnull=True)"],
        ["UUIDField", "uuid.UUID", "filter(key=uuid.UUID(texto))"],
        ["JSONField", "list/dict y escalares JSON", "filter(prices_by_type__has_key='1')"],
        ["ImageField", "ImageFieldFile", "Ruta guardada; abrir mediante storage, no bytes SQL."],
    ], [122, 115, 268])
    p("PositiveIntegerField admite cero; para un mínimo de uno se necesita un validador o restricción adicional. Las tablas muestran validadores explícitos y restricciones declaradas, no todos los límites implícitos del tipo SQL.")
    p("Los campos JSON no tienen un orden de negocio general. Filtrar claves y ordenar valores internos depende de su estructura y de la base; para precios numéricos en JSON de texto hace falta convertir con Cast/Decimal. Muchos-a-muchos requiere consultas a relaciones; puede duplicar filas y necesitar distinct().")
    h("Un objeto, colección y diccionario")
    code("qs = TicketPurchase.objects.filter(user=usuario)\ncompra = qs.first()              # Objeto o None\ncompra = qs.get(pk=compra_id)     # Puede lanzar DoesNotExist\nqs.exists(); qs.count()\nlist(qs.values('id', 'quantity', 'total'))\nlist(qs.values_list('id', flat=True))")
    story.append(PageBreak())
    p("Utilidades opcionales", "title")
    p("Los módulos toolbox.orm, toolbox.candy y toolbox.juegos son utilidades adicionales, sin rutas y sin adopción automática por los controladores existentes. Se usan mediante imports explícitos desde manage.py shell o una vista.")
    code("from toolbox.orm import (\n    filtrar, ordenar, buscar_usuario_por_email,\n    compras_de, entrada_de, editar_campos,\n    a_diccionarios, separar_butaca, total_butacas,\n)\nfrom domain.movies.models import Movie\n\nusuario = buscar_usuario_por_email('cliente@local.test')\ncompras = ordenar(compras_de(usuario), 'created_at',\n                  descendente=True)\npeliculas = filtrar(Movie, 'title', 'aventura',\n                    comparacion='contiene')\ndatos = a_diccionarios(peliculas, 'id', 'title')")
    table([
        ["Función", "Resultado / uso"],
        ["filtrar(origen, campo, valor, comparacion=...)", "QuerySet. igual, igual_sin_mayusculas, contiene, empieza_con, mayor, mayor_o_igual, menor, menor_o_igual, en, es_nulo."],
        ["ordenar(origen, campo, descendente=False)", "QuerySet ordenado. Conserva el alcance del queryset recibido."],
        ["buscar_uno / exigir_uno", "Objeto o None / objeto o ValidationError. Ambas rechazan coincidencias múltiples."],
        ["buscar_usuario_por_email(email)", "Un User activo y no ambiguo; valida formato y normaliza espacios."],
        ["compras_de / entrada_de", "Consultas con filtro de propiedad. entrada_de devuelve None si no pertenece al usuario."],
        ["editar_campos(objeto, **cambios)", "Instancia nueva validada y guardada. Solo campos simples autorizados por el módulo."],
        ["separar_butaca / total_butacas", "Copias del snapshot y suma Decimal. No escriben ni transfieren entradas."],
    ], [235, 270])
    h("Límites de edición")
    p("editar_campos admite nombres/apellidos de User; título/sinopsis/género/clasificación de Movie; nombre de Room; nombre/color/precio de SeatType; datos comerciales simples de Candy y Promotion. Ver CAMPOS_EDITABLES y la sección de utilidades del README principal. El llamador valida permisos. Campos del modelo sin validadores adicionales conservan esa limitación.")
    p("Para compras, entradas, ocupación, estados de función, códigos y stock se utilizan los servicios de negocio. La lista de butacas por sí sola no representa toda la operación. reprogram_purchase sincroniza compra, entradas y ocupación, y exige reservas en la función nueva.")
    h("Verificación del módulo")
    code(".\\scripts\\local.ps1 Test -TestLabels toolbox")
    story.append(PageBreak())
    p("Consulta rápida de operaciones", "title")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = readme.split("## Utilidades de consulta y edición\n", 1)[1].split("\n## ", 1)[0]
    lines = guide.splitlines()
    paragraph = []
    code_lines = None

    def flush_paragraph():
        if paragraph:
            p(" ".join(paragraph).replace("`", ""), "guide")
            paragraph.clear()

    for line in lines:
        if line.startswith("```"):
            flush_paragraph()
            if code_lines is None:
                code_lines = []
            else:
                code("\n".join(code_lines))
                code_lines = None
        elif code_lines is not None:
            code_lines.append(line)
        elif line.startswith("# "):
            continue
        elif line.startswith("## ") or line.startswith("### "):
            flush_paragraph()
            h(line.lstrip("# ").replace("`", ""))
        elif line.startswith("- "):
            flush_paragraph()
            paragraph.append("• " + line[2:])
        elif not line.strip():
            flush_paragraph()
        else:
            paragraph.append(line.strip())
    flush_paragraph()
    story.append(PageBreak())
    p("Índice de entidades y tablas", "title")
    table([["Modelo", "Tabla SQL", "Grupo"]] + [
        [m._meta.label, m._meta.db_table,
         "Relación automática" if m._meta.auto_created else "Dominio" if m in business else "Infraestructura"]
        for m in model_order
    ], [170, 245, 90])

    def dtype(field):
        name = field.get_internal_type()
        if field.is_relation:
            return f"{name}\n→ {field.related_model.__name__}\nID: {field.target_field.get_internal_type()}"
        if isinstance(field, models.DecimalField):
            return f"Decimal\n({field.max_digits}, {field.decimal_places})"
        if isinstance(field, models.JSONField):
            return "JSON\nlist / dict / escalares"
        if isinstance(field, models.ImageField):
            return "Imagen\nImageFieldFile"
        if isinstance(field, models.DateTimeField):
            return "Fecha y hora\ndatetime"
        if isinstance(field, models.TimeField):
            return "Hora\ntime"
        if isinstance(field, models.BooleanField):
            return "Booleano\nbool"
        if isinstance(field, models.IntegerField):
            return name + "\nint"
        return name + ("\nstr" if isinstance(field, (models.CharField, models.TextField)) else "")

    def rules(field):
        values = []
        if field.primary_key:
            values.append("PK")
        elif field.unique:
            values.append("Único")
        values.append("NULL permitido" if field.null else "NOT NULL")
        if field.blank:
            values.append("Formulario: vacío permitido")
        if field.max_length is not None:
            values.append(f"Máx. {field.max_length} caracteres")
        if getattr(field, "auto_now_add", False):
            values.append("Alta automática")
        elif getattr(field, "auto_now", False):
            values.append("Actualización automática")
        elif field.has_default():
            default = field.default
            if callable(default):
                default = getattr(default, "__name__", type(default).__name__) + "()"
            else:
                default = repr(default)
            values.append(f"Default: {default}")
        if not field.editable:
            values.append("No editable en formulario")
        if field.is_relation:
            values.append("Borrado: " + field.remote_field.on_delete.__name__)
        for validator in field.deconstruct()[3].get("validators", []):
            if hasattr(validator, "limit_value") and not type(validator).__name__.startswith("MaxLength"):
                limit = validator.limit_value
                if not callable(limit):
                    values.append(f"{type(validator).__name__}: {limit}")
        return "\n".join(values)

    def meaning(model, field):
        if field.is_relation:
            return f"Referencia a {field.related_model._meta.label}. Atributo ID: {field.attname}."
        if field.primary_key:
            return "Identificador del registro; pk es su alias en el ORM."
        return MEANINGS.get(field.name, str(field.help_text or field.verbose_name))

    for model in model_order:
        story.append(PageBreak())
        opts = model._meta
        p(opts.label, "title")
        description = DESCRIPTIONS.get(model.__name__, "Tabla intermedia generada por Django para una relación muchos-a-muchos.")
        p(description)
        p(f"Tabla SQL: {opts.db_table}")
        if not opts.auto_created:
            source = Path(inspect.getfile(model))
            try:
                source = source.relative_to(ROOT)
            except ValueError:
                source = Path("Django") / str(source.name)
            p(f"Fuente: {source}")
        p("Orden por defecto: " + (", ".join(opts.ordering) if opts.ordering else "sin orden garantizado; indicar order_by explícitamente"))
        p("Orden: nombre ascendente; -nombre descendente. En FK se muestra el atributo _id para ordenar por identificador.")
        rows = [["Campo Python / columna SQL", "Tipo", "Qué guarda", "Reglas", "Orden"]]
        for field in opts.local_fields:
            order = "Por clave JSON" if isinstance(field, models.JSONField) else field.attname
            rows.append([f"{field.name}\nSQL: {field.column}", dtype(field), meaning(model, field), rules(field), order])
        table(rows, [110, 88, 125, 120, 62])
        choice_fields = [f for f in opts.local_fields if f.choices]
        if choice_fields:
            h("Valores de opciones")
            for field in choice_fields:
                p(field.name + ": " + "; ".join(f"{value!r} = {label}" for value, label in field.flatchoices))
        if opts.local_many_to_many:
            h("Relaciones muchos-a-muchos")
            for field in opts.local_many_to_many:
                p(f"{field.name} → {field.related_model._meta.label}; tabla intermedia: {field.remote_field.through._meta.db_table}. Usar {field.name}.all(), add(), remove(), set(). No es una columna de esta tabla.")
        reverse = [r for r in opts.related_objects if not r.hidden]
        if reverse:
            h("Acceso desde este objeto hacia otras entidades")
            p("; ".join(f"{r.get_accessor_name()} → {r.related_model.__name__}" for r in reverse))
        constraints = [str(c) for c in opts.constraints]
        if opts.unique_together:
            constraints.append(f"unique_together: {opts.unique_together}")
        if constraints:
            h("Restricciones de base declaradas")
            for constraint in constraints:
                p(constraint)
        if opts.indexes:
            h("Índices adicionales")
            p("; ".join(f"{i.name}: {list(i.fields)}" for i in opts.indexes))
        own_bases = [base for base in model.__mro__ if base is not models.Model and (base is model or base.__module__.startswith("domain."))]
        properties = list(dict.fromkeys(name for base in own_bases for name, value in vars(base).items() if isinstance(value, property)))
        methods = [name for name, value in vars(model).items() if not name.startswith("_") and (inspect.isfunction(value) or isinstance(value, (classmethod, staticmethod)))]
        if properties:
            h("Propiedades calculadas, sin columna")
            p(", ".join(properties))
        if methods and not opts.auto_created:
            h("Métodos propios")
            p(", ".join(methods))
        if model.__name__ in SPECIAL_NOTES:
            h("Comportamiento a tener en cuenta")
            p(SPECIAL_NOTES[model.__name__])
        if opts.auto_created:
            p("Acceso a esta tabla: atributo through de la relación muchos-a-muchos. No se importa como una clase declarada en models.py.")

    class ReferenceDoc(BaseDocTemplate):
        def afterFlowable(self, flowable):
            if isinstance(flowable, Paragraph) and flowable.style.name == "title":
                label = flowable.getPlainText()
                key = f"section-{self.page}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(label, key, 0, False)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#DAE1E8"))
        canvas.line(45, 39, A4[0]-45, 39)
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(navy)
        canvas.drawString(45, 26, "Butaca Cero · Modelo y consultas · " + date.today().strftime("%d/%m/%Y"))
        canvas.drawRightString(A4[0]-45, 26, str(doc.page))
        canvas.restoreState()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    doc = ReferenceDoc(str(args.output), pagesize=A4, title="Butaca Cero — Modelo y ORM", author="Butaca Cero")
    doc.addPageTemplates(PageTemplate(id="main", frames=[Frame(39, 48, 517, 758, leftPadding=6, rightPadding=6, topPadding=6, bottomPadding=6)], onPage=footer))
    doc.build(story)
    print(f"PDF generado: {args.output.resolve()}")
    print(f"Entidades: {len(business)}; infraestructura: {len(infrastructure)}; tablas automáticas: {len(joins)}")


if __name__ == "__main__":
    main()
