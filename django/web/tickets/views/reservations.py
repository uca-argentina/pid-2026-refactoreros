"""Reservations."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from domain.screenings.models import Screening
from domain.tickets.models import SeatReservation, TicketPurchase

from web.tickets.payloads import (
    MAX_RESERVATION_OPERATIONS,
    reservation_operation,
    reservation_request,
)


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
        "unavailable": list(TicketPurchase.blocked_seats(screening, user=user)),
        "reserved": [reservation_payload(reservation) for reservation in own_reservations],
    }


@login_required
@require_POST
def seat_reservation_view(request, pk):
    Screening.finalize_expired()
    screening = get_object_or_404(Screening.published(), pk=pk)
    try:
        payload = reservation_request(request)
    except ValidationError as error:
        return JsonResponse({"ok": False, "error": error.messages[0]}, status=400)

    try:
        label, action = reservation_operation(payload)
    except ValidationError as error:
        return JsonResponse({"ok": False, "error": error.messages[0]}, status=400)

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
                "unavailable": list(TicketPurchase.blocked_seats(screening, user=request.user)),
            },
            status=409,
        )
    return JsonResponse({"ok": True, "reservation": reservation_payload(reservation)})


@login_required
@require_POST
def seat_reservation_batch_view(request, pk):
    Screening.finalize_expired()
    screening = get_object_or_404(Screening.published(), pk=pk)
    try:
        payload = reservation_request(request)
    except ValidationError as error:
        return JsonResponse({"ok": False, "error": error.messages[0]}, status=400)

    operations = payload.get("operations", [])
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_RESERVATION_OPERATIONS:
        return JsonResponse({"ok": False, "error": "Solicitud inválida."}, status=400)

    errors = []
    processed = []
    for operation in operations:
        try:
            label, action = reservation_operation(operation)
        except ValidationError as error:
            errors.append({"error": error.messages[0]})
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
    Screening.finalize_expired()
    screening = get_object_or_404(Screening.published(), pk=pk)
    return JsonResponse(
        {
            "ok": True,
            **reservation_state_payload(screening, request.user),
        }
    )
