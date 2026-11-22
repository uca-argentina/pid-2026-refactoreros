"""Ayudas optativas para la selección y configuración de Candy."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from domain.candy.models import CandyCombo, CandyOrder, CandyProduct
from domain.users.roles import staff_role
from toolbox.orm import buscar_uno


def seleccion_candy(*, productos=None, combos=None):
    """Construye el payload de compra desde mapas {id: cantidad}, sin escribir.

    Cero omite una línea. No acepta bool como identificador/cantidad. El servicio
    de compra sigue comprobando precios, stock y máximo por ítem.
    """
    seleccion = []
    for tipo, cantidades in (("product", productos), ("combo", combos)):
        if cantidades is None:
            continue
        if not isinstance(cantidades, dict):
            raise ValidationError("Usá un diccionario de identificadores y cantidades.")
        for identificador, cantidad in cantidades.items():
            if type(identificador) is not int or identificador < 1 or type(cantidad) is not int or cantidad < 0:
                raise ValidationError("Los identificadores deben ser enteros positivos y las cantidades enteros no negativos.")
            if cantidad:
                seleccion.append({"kind": tipo, "id": identificador, "quantity": cantidad})
    return seleccion


def pedidos_de(usuario):
    """Pedidos de entradas, independientes y premios; reutiliza prioridad existente."""
    return CandyOrder.for_user(usuario)


def pedido_de(usuario, pedido_id):
    """Pedido propio o None, cualquiera sea su origen."""
    return buscar_uno(pedidos_de(usuario), pk=pedido_id)


def editar_componentes_combo(actor, combo_id, cantidades):
    """Reemplaza la composición usando CandyComboForm; no altera stock ni pedidos.

    cantidades es {producto_id: unidades_por_combo}; cero elimina un componente.
    Reutiliza el mínimo de dos unidades y el máximo por componente del formulario.
    Devuelve una nueva instancia de CandyCombo. Requiere gerente activo.
    """
    if staff_role(actor) != "manager":
        raise PermissionDenied
    seleccion_candy(productos=cantidades)
    if not isinstance(cantidades, dict):
        raise ValidationError("Indicá un diccionario de componentes.")
    from web.manager.forms.candy import CandyComboForm

    class ComponentesForm(CandyComboForm):
        class Meta(CandyComboForm.Meta):
            # Esta operación no cambia imágenes ni necesita abrir su archivo.
            fields = ("name", "price", "is_active")

    with transaction.atomic():
        combo = buscar_uno(CandyCombo.objects.select_for_update(), pk=combo_id)
        if combo is None:
            raise ValidationError("No se encontró el combo.")
        existentes = set(CandyProduct.objects.filter(pk__in=cantidades).values_list("pk", flat=True))
        if existentes != set(cantidades):
            raise ValidationError("Algún producto no existe.")
        datos = {"name": combo.name, "price": combo.price, "is_active": combo.is_active}
        datos.update({f"product_{pk}": cantidad for pk, cantidad in cantidades.items()})
        formulario = ComponentesForm(datos, instance=combo)
        if not formulario.is_valid():
            raise ValidationError(dict(formulario.errors))
        return formulario.save()
