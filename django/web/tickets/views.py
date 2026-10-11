from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache
import json

from domain.cinema.models import CinemaSettings
from domain.screenings.models import Screening
from domain.tickets.models import TicketPurchase, SeatReservation
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
    screening = get_object_or_404(Screening.published(), pk=pk)
    screening.tickets_available = TicketPurchase.available_for(screening)
    screening.seat_map = build_seat_map(screening, user=request.user)
    purchase_error = request.session.pop("purchase_error", "")
    return render(
        request,
        "seat_selection.html",
        {
            "cinema": CinemaSettings.current(),
            "screening": screening,
            "purchase_error": purchase_error,
            "manager_role": manager_role(request.user),
        },
    )


@login_required
def ticket_purchase_view(request, pk):
    Screening.finalize_expired()
    screening = get_object_or_404(Screening.published(), pk=pk)
    if request.method == "POST":
        form = TicketPurchaseForm(request.POST)
        if form.is_valid():
            selected_seats = form.cleaned_data["selected_seats"]
            try:
                purchase = TicketPurchase.buy(
                    user=request.user,
                    screening=screening,
                    quantity=len(selected_seats),
                    selected_seats=selected_seats,
                    require_reservation=True,
                )
            except ValidationError as error:
                available = TicketPurchase.available_for(screening)
                request.session["purchase_error"] = purchase_error_message(
                    error,
                    f"Solo tenemos disponibles {available} entradas para esta función.",
                )
            else:
                ticket_label = "entrada" if purchase.quantity == 1 else "entradas"
                messages.success(
                    request,
                    (
                        "Pago aprobado. "
                        f"Compraste {purchase.quantity} {ticket_label} "
                        f"para {screening.movie.title}. ¡Te esperamos!"
                    ),
                )
                return redirect("my_tickets")
        else:
            request.session["purchase_error"] = purchase_error_message(
                form.errors,
                "Seleccioná al menos una butaca.",
            )
    return redirect("seat_selection", pk=screening.pk)


def reservation_payload(reservation):
    seconds_left = max(int((reservation.expires_at - timezone.now()).total_seconds()), 0)
    return {
        "label": reservation.label,
        "expires_at": reservation.expires_at.isoformat(),
        "seconds_left": seconds_left,
    }


def reservation_state_payload(screening, user):
    own_reservations = SeatReservation.active_for(screening).filter(user=user)
    return {
        "unavailable": list(
            TicketPurchase.blocked_seats(screening, user=user)
        ),
        "reserved": [reservation_payload(reservation) for reservation in own_reservations],
    }


@login_required
@require_POST
def seat_reservation_view(request, pk):
    screening = get_object_or_404(Screening.published(), pk=pk)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return JsonResponse({"ok": False, "error": "Solicitud inválida."}, status=400)

    label = str(payload.get("label", "")).strip()
    action = payload.get("action")
    if not label or action not in {"reserve", "release"}:
        return JsonResponse({"ok": False, "error": "Solicitud inválida."}, status=400)

    if action == "release":
        SeatReservation.release(request.user, screening, label)
        return JsonResponse({"ok": True, "label": label})

    try:
        reservation = SeatReservation.reserve(request.user, screening, label)
    except ValidationError as error:
        return JsonResponse(
            {
                "ok": False,
                "label": label,
                "error": "; ".join(error.messages),
                "unavailable": list(
                    TicketPurchase.blocked_seats(screening, user=request.user)
                ),
            },
            status=409,
        )
    return JsonResponse({"ok": True, "reservation": reservation_payload(reservation)})


@login_required
@require_POST
def seat_reservation_batch_view(request, pk):
    screening = get_object_or_404(Screening.published(), pk=pk)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return JsonResponse({"ok": False, "error": "Solicitud inválida."}, status=400)

    operations = payload.get("operations", [])
    if not isinstance(operations, list) or not operations:
        return JsonResponse({"ok": False, "error": "Solicitud inválida."}, status=400)

    errors = []
    processed = []
    for operation in operations:
        if not isinstance(operation, dict):
            errors.append({"error": "Solicitud inválida."})
            continue

        label = str(operation.get("label", "")).strip()
        action = operation.get("action")
        if not label or action not in {"reserve", "release"}:
            errors.append({"label": label, "error": "Solicitud inválida."})
            continue

        if action == "release":
            SeatReservation.release(request.user, screening, label)
            processed.append({"label": label, "action": action})
            continue

        try:
            reservation = SeatReservation.reserve(request.user, screening, label)
        except ValidationError as error:
            errors.append({"label": label, "error": "; ".join(error.messages)})
        else:
            processed.append(
                {
                    "label": label,
                    "action": action,
                    "reservation": reservation_payload(reservation),
                }
            )

    state = reservation_state_payload(screening, request.user)
    status = 409 if errors else 200
    return JsonResponse(
        {
            "ok": not errors,
            "processed": processed,
            "errors": errors,
            **state,
        },
        status=status,
    )


@login_required
@require_GET
def seat_reservation_status_view(request, pk):
    screening = get_object_or_404(Screening.published(), pk=pk)
    return JsonResponse(
        {
            "ok": True,
            **reservation_state_payload(screening, request.user),
        }
    )


@login_required
@never_cache
def my_tickets_view(request):
    now = timezone.now()
    Screening.finalize_expired()
    purchases = list(
        TicketPurchase.objects.filter(user=request.user)
        .select_related("screening__movie", "screening__room", "refund")
        .prefetch_related("tickets")
        .order_by("screening__starts_at", "-created_at")
    )
    for purchase in purchases:
        purchase.used_count = sum(ticket.used_at is not None for ticket in purchase.tickets.all())
        purchase.remaining_count = purchase.quantity - purchase.used_count
        purchase.is_history = (
            purchase.screening.ends_at <= now
            or purchase.screening.status in {Screening.Status.FINISHED, Screening.Status.CANCELED}
            or hasattr(purchase, "refund")
        )
        purchase.admission_open = (
            purchase.screening.status == Screening.Status.PUBLISHED
            and purchase.screening.ends_at > now
            and purchase.remaining_count > 0
            and not purchase.is_history
        )
    active_purchases = [purchase for purchase in purchases if not purchase.is_history]
    historical_purchases = [purchase for purchase in purchases if purchase.is_history]
    active_purchases.sort(key=lambda purchase: (not purchase.admission_open, purchase.screening.starts_at))
    historical_purchases.sort(key=lambda purchase: purchase.screening.starts_at, reverse=True)
    purchases = active_purchases + historical_purchases
    return render(
        request,
        "my_tickets.html",
        {
            "cinema": CinemaSettings.current(),
            "purchases": purchases,
            "manager_role": manager_role(request.user),
        },
    )


@login_required
@never_cache
@require_GET
def ticket_detail_view(request, pk):
    purchase = get_object_or_404(
        TicketPurchase.objects.select_related("screening__movie", "screening__room", "refund").prefetch_related("tickets"),
        pk=pk, user=request.user,
    )
    screening = purchase.screening
    used_count = sum(ticket.used_at is not None for ticket in purchase.tickets.all())
    is_expired = screening.ends_at <= timezone.now() or screening.status == Screening.Status.FINISHED
    available = (
        used_count < purchase.quantity and screening.status == Screening.Status.PUBLISHED
        and screening.ends_at > timezone.now() and not hasattr(purchase, "refund")
    )
    return render(request, "ticket_detail.html", {
        "purchase": purchase, "used_count": used_count, "available": available, "is_expired": is_expired,
        "cinema": CinemaSettings.current(),
        "manager_role": manager_role(request.user),
    })
