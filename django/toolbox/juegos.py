"""Consultas con dueño y edición validada; no simula ni reescribe partidas."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import model_to_dict

from domain.games import services
from domain.games.forms import QuestionForm
from domain.games.models import GameEvent, PrizeCoupon, Question, TriviaRun
from toolbox.orm import buscar_uno


def _del_usuario(modelo, usuario):
    if not getattr(usuario, "is_authenticated", False) or usuario.pk is None:
        return modelo.objects.none()
    return modelo.objects.filter(user=usuario)


def cupones_de(usuario, *, estado=None):
    """QuerySet del usuario; estado debe ser un código de PrizeCoupon.Status."""
    consulta = _del_usuario(PrizeCoupon, usuario).select_related("product", "pickup_order")
    if estado is not None:
        if estado not in PrizeCoupon.Status.values:
            raise ValidationError("Estado de cupón desconocido.")
        consulta = consulta.filter(status=estado)
    return consulta


def partida_publica_de(usuario, partida_id):
    """Snapshot público o None. No vence partidas; para estado actualizado usar state()."""
    partida = buscar_uno(_del_usuario(TriviaRun, usuario), pk=partida_id)
    return services.public_run(partida) if partida is not None else None


def historial_juegos_de(usuario):
    """Eventos cuyo usuario afectado es usuario; no incluye eventos globales de gestión."""
    return _del_usuario(GameEvent, usuario).select_related("actor").order_by("-created_at", "-pk")


def editar_pregunta(actor, pregunta_id, **cambios):
    """Edita con QuestionForm, revisión de ruleta y auditoría; exige gerente.

    options recibe una lista de tres textos. No modifica snapshots de partidas
    existentes ni elimina QuestionUse. Devuelve una nueva instancia de Question.
    """
    services.require_manager(actor)
    if not cambios or set(cambios) - set(QuestionForm.Meta.fields):
        raise ValidationError("Indicá campos de pregunta válidos para editar.")
    with transaction.atomic():
        services.lock_wheel()
        pregunta = buscar_uno(Question.objects.select_for_update(), pk=pregunta_id)
        if pregunta is None:
            raise ValidationError("No se encontró la pregunta.")
        datos = model_to_dict(pregunta, fields=QuestionForm.Meta.fields)
        datos.update(cambios)
        formulario = QuestionForm(datos, instance=pregunta)
        if not formulario.is_valid():
            raise ValidationError(dict(formulario.errors))
        pregunta = formulario.save()
        services.audit(None, "question_saved", {"id": pregunta.pk}, actor)
        return pregunta
