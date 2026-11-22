"""Funciones optativas para usar desde una vista o desde manage.py shell.

No reemplazan permisos ni servicios de negocio. Los QuerySets recibidos conservan
sus filtros, por ejemplo el filtro de propiedad aplicado por una vista.
"""

from copy import deepcopy
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q, QuerySet


COMPARACIONES = {
    "igual": "exact",
    "igual_sin_mayusculas": "iexact",
    "contiene": "icontains",
    "empieza_con": "istartswith",
    "mayor": "gt",
    "mayor_o_igual": "gte",
    "menor": "lt",
    "menor_o_igual": "lte",
    "en": "in",
    "es_nulo": "isnull",
}

# La edición simple queda limitada a datos que no requieren sincronizar otras
# entidades. Para compras, credenciales, estados, stock y permisos usar servicios.
CAMPOS_EDITABLES = {
    "auth.user": {"first_name", "last_name"},
    "movies.movie": {"title", "synopsis", "genre", "rating"},
    "rooms.room": {"name"},
    "seat_types.seattype": {"name", "color", "base_price"},
    "candy.candyproduct": {"name", "category", "price", "is_active"},
    "candy.candycombo": {"name", "price", "is_active"},
    "promotions.promotion": {"name", "is_active", "discount_type", "discount_value"},
}


def listar(origen):
    """Acepta un modelo, manager o QuerySet; devuelve un QuerySet sin evaluarlo."""
    if isinstance(origen, QuerySet):
        return origen.all()
    manager = getattr(origen, "objects", origen)
    return manager.all()


def filtrar(origen, campo, valor, *, comparacion="igual"):
    """Combinar llamadas expresa AND; campo admite relaciones como screening__status."""
    if comparacion not in COMPARACIONES:
        raise ValidationError(f"Comparación desconocida: {comparacion}.")
    if comparacion == "es_nulo" and not isinstance(valor, bool):
        raise ValidationError("Para es_nulo usá True o False.")
    if comparacion == "en" and not isinstance(valor, (list, tuple, set, QuerySet)):
        raise ValidationError("Para en usá una colección, por ejemplo [1, 2].")
    lookup = f"{campo}__{COMPARACIONES[comparacion]}"
    return listar(origen).filter(**{lookup: valor})


def ordenar(origen, campo, *, descendente=False):
    """Ordena por un campo o relación; para varios criterios usar order_by()."""
    if not isinstance(campo, str) or not campo or campo.startswith("-") or campo == "?":
        raise ValidationError("Indicá el campo sin prefijo; usá descendente=True para invertir.")
    return listar(origen).order_by(f"{'-' if descendente else ''}{campo}")


def buscar_texto(origen, texto, *campos):
    """Busca con OR entre campos, preservando filtros anteriores del queryset."""
    if not isinstance(texto, str) or not campos or any(not isinstance(c, str) or not c for c in campos):
        raise ValidationError("Indicá un texto y al menos un nombre de campo.")
    consulta = listar(origen)
    texto = texto.strip()
    if not texto:
        return consulta
    condicion = Q()
    for campo in campos:
        condicion |= Q(**{f"{campo}__icontains": texto})
    return consulta.filter(condicion).distinct()


def describir_campos(origen):
    """Metadatos sin consultar filas; excluye propiedades y relaciones inversas."""
    modelo = origen if hasattr(origen, "_meta") else origen.model
    return [
        {
            "nombre": campo.name,
            "tipo": campo.get_internal_type(),
            "columna": None if campo.many_to_many else campo.column,
            "opciones": list(campo.flatchoices) if campo.choices else [],
            "relacion": campo.related_model._meta.label if campo.is_relation else None,
        }
        for campo in [*modelo._meta.fields, *modelo._meta.many_to_many]
    ]


def buscar_uno(origen, **campos):
    """Devuelve una instancia o None; rechaza coincidencias ambiguas."""
    consulta = listar(origen)
    try:
        return consulta.get(**campos)
    except consulta.model.DoesNotExist:
        return None
    except consulta.model.MultipleObjectsReturned as error:
        raise ValidationError("La búsqueda coincide con más de un registro.") from error


def exigir_uno(origen, **campos):
    """Como buscar_uno, pero convierte también la ausencia en ValidationError."""
    objeto = buscar_uno(origen, **campos)
    if objeto is None:
        raise ValidationError("No se encontró el registro solicitado.")
    return objeto


def a_diccionarios(origen, *campos):
    """Materializa una lista de diccionarios. No entregar datos privados al cliente."""
    return list(listar(origen).values(*campos))


def valores(origen, campo):
    """Materializa una lista simple, por ejemplo ['A1', 'A2']."""
    return list(listar(origen).values_list(campo, flat=True))


def buscar_usuario_por_email(email):
    """Un User activo; email vacío, inválido, repetido o inexistente produce error."""
    if not isinstance(email, str):
        raise ValidationError("Indicá un correo válido.")
    email = email.strip()
    validate_email(email)
    return exigir_uno(get_user_model().objects.filter(is_active=True), email__iexact=email)


def compras_de(usuario):
    """Compras del usuario; un usuario anónimo no obtiene resultados."""
    from domain.tickets.models import TicketPurchase

    consulta = TicketPurchase.objects.select_related("screening__movie", "screening__room")
    if not getattr(usuario, "is_authenticated", False) or usuario.pk is None:
        return consulta.none()
    return consulta.filter(user=usuario)


def entrada_de(usuario, compra_id, entrada_id):
    """Entrada propia o None. Los identificadores deben estar convertidos a enteros."""
    from domain.tickets.models import AdmissionTicket

    return buscar_uno(
        AdmissionTicket.objects.filter(purchase__in=compras_de(usuario)),
        pk=entrada_id,
        purchase_id=compra_id,
    )


def entradas_sin_usar(compra):
    """Filtra uso; no comprueba plazo, devolución ni habilitación de la función."""
    return compra.tickets.filter(used_at__isnull=True)


def editar_campos(objeto, **cambios):
    """Valida y guarda una edición simple sobre una fila bloqueada y actualizada.

    Devuelve una NUEVA instancia con los valores persistidos. No modifica la
    instancia recibida. El llamador debe comprobar autorización sobre el objeto.
    """
    permitidos = CAMPOS_EDITABLES.get(objeto._meta.label_lower, set())
    invalidos = set(cambios) - permitidos
    if invalidos:
        raise ValidationError(f"Campos fuera de la edición simple: {', '.join(sorted(invalidos))}.")
    if objeto.pk is None or objeto._state.adding:
        raise ValidationError("La edición requiere un objeto ya guardado.")
    if not cambios:
        raise ValidationError("Indicá al menos un campo para editar.")
    alias = objeto._state.db or "default"
    with transaction.atomic(using=alias):
        actual = type(objeto).objects.using(alias).select_for_update().get(pk=objeto.pk)
        for nombre, valor in cambios.items():
            campo = actual._meta.get_field(nombre)
            setattr(actual, nombre, campo.clean(valor, actual))
        actual.full_clean()
        actual.save(using=alias)
    return actual


def separar_butaca(asientos, etiqueta):
    """Devuelve (diccionario_elegido, lista_restante), sin guardar ni mutar datos."""
    if not isinstance(asientos, list) or any(not isinstance(a, dict) for a in asientos):
        raise ValidationError("Se esperaba una lista de diccionarios de butacas.")
    etiquetas = [a.get("label") for a in asientos]
    if any(not isinstance(e, str) or not e.strip() for e in etiquetas):
        raise ValidationError("Cada butaca necesita una etiqueta válida.")
    if len(etiquetas) != len(set(etiquetas)):
        raise ValidationError("Hay etiquetas de butaca repetidas.")
    if etiqueta not in etiquetas:
        raise ValidationError("La butaca no pertenece a la selección.")
    elegida = next(a for a in asientos if a["label"] == etiqueta)
    restantes = [a for a in asientos if a["label"] != etiqueta]
    return deepcopy(elegida), deepcopy(restantes)


def total_butacas(asientos):
    """Suma precios del snapshot como Decimal; no cotiza ni escribe en la base."""
    if not isinstance(asientos, list):
        raise ValidationError("Se esperaba una lista de butacas.")
    total = Decimal("0")
    for asiento in asientos:
        try:
            precio = Decimal(str(asiento["price"]))
        except (KeyError, TypeError, InvalidOperation) as error:
            raise ValidationError("Cada butaca necesita un precio numérico.") from error
        if not precio.is_finite() or precio < 0:
            raise ValidationError("Los precios deben ser finitos y no negativos.")
        total += precio
    return total
