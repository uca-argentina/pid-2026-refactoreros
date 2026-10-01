from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Case, IntegerField, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
import json

from domain.cinema.models import ConfiguracionCine
from domain.screenings.models import Funcion
from domain.tickets.models import CompraEntrada, ReservaAsiento
from web.catalog.views import build_seat_map, manager_role

from .forms import TicketPurchaseForm


def purchase_error_message(error, fallback):
    if hasattr(error, "message_dict"):
        for messages_for_field in error.message_dict.values():
            if messages_for_field:
                return messages_for_field[0]
    if isinstance(error, dict):
        for messages_for_field in error.values():
            if messages_for_field:
                return messages_for_field[0]
    if getattr(error, "messages", None):
        return error.messages[0]
    return fallback


@login_required
def seat_selection_view(request, pk):
    funcion = get_object_or_404(Funcion.funciones_publicadas(), pk=pk)
    funcion.entradas_disponibles = CompraEntrada.disponibles_para(funcion)
    funcion.seat_map = build_seat_map(funcion, usuario=request.user)
    purchase_error = request.session.pop("purchase_error", "")
    return render(
        request,
        "seat_selection.html",
        {
            "cinema": ConfiguracionCine.actual(),
            "funcion": funcion,
            "purchase_error": purchase_error,
            "manager_role": manager_role(request.user),
        },
    )


@login_required
def ticket_purchase_view(request, pk):
    Funcion.finalizar_vencidas()
    funcion = get_object_or_404(Funcion.funciones_publicadas(), pk=pk)
    if request.method == "POST":
        form = TicketPurchaseForm(request.POST)
        if form.is_valid():
            selected_seats = form.cleaned_data["selected_seats"]
            try:
                compra = CompraEntrada.comprar(
                    usuario=request.user,
                    funcion=funcion,
                    cantidad=len(selected_seats),
                    selected_seats=selected_seats,
                    require_reservation=True,
                )
            except ValidationError as error:
                disponibles = CompraEntrada.disponibles_para(funcion)
                request.session["purchase_error"] = purchase_error_message(
                    error,
                    f"Solo tenemos disponibles {disponibles} entradas para esta función.",
                )
            else:
                entrada_label = "entrada" if compra.cantidad == 1 else "entradas"
                messages.success(
                    request,
                    (
                        "Pago aprobado. "
                        f"Compraste {compra.cantidad} {entrada_label} "
                        f"para {funcion.pelicula.titulo}. ¡Te esperamos!"
                    ),
                )
                return redirect("my_tickets")
        else:
            request.session["purchase_error"] = purchase_error_message(
                form.errors,
                "Seleccioná al menos una butaca.",
            )
    return redirect("seat_selection", pk=funcion.pk)


def reservation_payload(reserva):
    seconds_left = max(int((reserva.expira_en - timezone.now()).total_seconds()), 0)
    return {
        "label": reserva.label,
        "expires_at": reserva.expira_en.isoformat(),
        "seconds_left": seconds_left,
    }


@login_required
@require_POST
def seat_reservation_view(request, pk):
    funcion = get_object_or_404(Funcion.funciones_publicadas(), pk=pk)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return JsonResponse({"ok": False, "error": "Solicitud inválida."}, status=400)

    label = str(payload.get("label", "")).strip()
    action = payload.get("action")
    if not label or action not in {"reserve", "release"}:
        return JsonResponse({"ok": False, "error": "Solicitud inválida."}, status=400)

    if action == "release":
        ReservaAsiento.liberar(request.user, funcion, label)
        return JsonResponse({"ok": True, "label": label})

    try:
        reserva = ReservaAsiento.reservar(request.user, funcion, label)
    except ValidationError as error:
        return JsonResponse(
            {
                "ok": False,
                "label": label,
                "error": "; ".join(error.messages),
                "unavailable": list(
                    CompraEntrada.asientos_bloqueados(funcion, usuario=request.user)
                ),
            },
            status=409,
        )
    return JsonResponse({"ok": True, "reservation": reservation_payload(reserva)})


@login_required
@require_GET
def seat_reservation_status_view(request, pk):
    funcion = get_object_or_404(Funcion.funciones_publicadas(), pk=pk)
    own_reservations = ReservaAsiento.vigentes_para(funcion).filter(usuario=request.user)
    return JsonResponse(
        {
            "ok": True,
            "unavailable": list(
                CompraEntrada.asientos_bloqueados(funcion, usuario=request.user)
            ),
            "reserved": [reservation_payload(reserva) for reserva in own_reservations],
        }
    )


@login_required
def my_tickets_view(request):
    now = timezone.now()
    compras = (
        CompraEntrada.objects.filter(usuario=request.user)
        .select_related("funcion__pelicula", "funcion__sala")
        .annotate(
            fecha_bucket=Case(
                When(funcion__fecha_horario__gte=now, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("fecha_bucket", "funcion__fecha_horario", "-creada_en")
    )
    return render(
        request,
        "my_tickets.html",
        {
            "cinema": ConfiguracionCine.actual(),
            "compras": compras,
            "manager_role": manager_role(request.user),
        },
    )
