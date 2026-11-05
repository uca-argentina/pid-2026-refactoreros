from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache
import json
import re
import uuid

from domain.candy.models import CandyOrder
from domain.candy.services import buy_candy_only, buy_tickets_with_candy, candy_menu
from domain.tickets.services import reprogram_purchase
from domain.cinema.models import CinemaSettings
from domain.screenings.models import Screening
from domain.tickets.models import PurchaseRefund, TicketPurchase, SeatReservation
from web.catalog.views import build_seat_map, manager_role

from .forms import CandyPurchaseForm, TicketPurchaseForm, TicketReprogramForm
from django.db import OperationalError
from django.core.paginator import Paginator


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
@never_cache
@require_GET
def candy_store_view(request):
    return render(request, "candy_store.html", {
        "cinema": CinemaSettings.current(), "manager_role": manager_role(request.user),
        "candy": candy_menu(), "checkout_key": uuid.uuid4(),
        "purchase_error": request.session.pop("candy_purchase_error", ""),
        "orders": Paginator(CandyOrder.for_user(request.user), 12).get_page(request.GET.get("page")),
    })


@login_required
@never_cache
@require_POST
def candy_purchase_view(request):
    form = CandyPurchaseForm(request.POST)
    if form.is_valid():
        try:
            order = buy_candy_only(request.user, form.cleaned_data["candy_items"], form.cleaned_data["checkout_key"])
        except ValidationError as error:
            request.session["candy_purchase_error"] = purchase_error_message(error, "No se pudo completar el pedido.")
        except OperationalError:
            request.session["candy_purchase_error"] = "Hay otra compra en curso. Volvé a intentarlo."
        else:
            messages.success(request, "Pago aprobado. Tu pedido de Candy está listo para retirar con su QR. ¡Que lo disfrutes!")
            return redirect("candy_order_detail", pk=order.pk)
    else:
        request.session["candy_purchase_error"] = purchase_error_message(form.errors, "Revisá tu selección de Candy.")
    return redirect("candy_store")


@login_required
@never_cache
@require_GET
def candy_order_detail_view(request, pk):
    order = get_object_or_404(CandyOrder.for_user(request.user), pk=pk)
    return render(request, "candy_detail.html", {"order": order, "purchase": order.purchase, "cinema": CinemaSettings.current(), "manager_role": manager_role(request.user)})


@login_required
@never_cache
def seat_selection_view(request, pk):
    Screening.finalize_expired()
    screening = get_object_or_404(Screening.published(), pk=pk)
    screening.tickets_available = TicketPurchase.available_for(screening)
    screening.seat_map = build_seat_map(screening, user=request.user)
    screening.current_price_from = (
        screening.seat_map["price_from"] if screening.seat_map else screening.price_from
    )
    purchase_error = request.session.pop("purchase_error", "")
    return render(
        request,
        "seat_selection.html",
        {
            "cinema": CinemaSettings.current(),
            "screening": screening,
            "candy": candy_menu(),
            "purchase_error": purchase_error,
            "manager_role": manager_role(request.user),
        },
    )


@login_required
@never_cache
def seat_reprogram_selection_view(request, purchase_pk, screening_pk):
    Screening.finalize_expired()

    purchase = get_object_or_404(
        request.user.ticket_purchases.select_related("screening__movie", "screening__room"),
        pk=purchase_pk,
    )
    current_screening = purchase.screening

    if current_screening.starts_at <= timezone.now():
        return redirect("home")

    screening = get_object_or_404(
        Screening.published().exclude(pk=current_screening.pk),
        pk=screening_pk,
        movie=current_screening.movie,
    )

    screening.tickets_available = TicketPurchase.available_for(screening)

    if screening.tickets_available < purchase.quantity:
        messages.error(request, "No hay lugar suficiente en esa función.")
        return redirect("screening_reprogram", purchase_pk=purchase.pk)

    screening.seat_map = build_seat_map(screening, user=request.user)
    screening.current_price_from = (
        screening.seat_map["price_from"] if screening.seat_map else screening.price_from
    )
    purchase_error = request.session.pop("purchase_error", "")

    return render(
        request,
        "seat_reprogram_selection.html",
        {
            "cinema": CinemaSettings.current(),
            "purchase": purchase,
            "current_screening": current_screening,
            "screening": screening,
            "purchase_error": purchase_error,
            "manager_role": manager_role(request.user),
        },
    )

@login_required
@require_POST
def screening_reprogram_view(request, purchase_pk, screening_pk):
    Screening.finalize_expired()
    redirect_back = redirect(
        "seat_reprogram_selection", purchase_pk=purchase_pk, screening_pk=screening_pk
    )

    form = TicketReprogramForm(request.POST)
    if not form.is_valid():
        request.session["purchase_error"] = purchase_error_message(
            form.errors, "Seleccioná tus butacas."
        )
        return redirect_back

    try:
        purchase, previous_total = reprogram_purchase(
            user=request.user,
            purchase_pk=purchase_pk,
            new_screening_pk=screening_pk,
            selected_seats=form.cleaned_data["selected_seats"],
        )
    except ValidationError as error:
        request.session["purchase_error"] = purchase_error_message(
            error, "No pudimos reprogramar tus entradas."
        )
        return redirect_back

    ticket_label = "entrada" if purchase.quantity == 1 else "entradas"
    message = (
        f"Reprogramaste {purchase.quantity} {ticket_label} para "
        f"{purchase.screening.movie.title}: "
        f"{timezone.localtime(purchase.screening.starts_at):%d/%m %H:%M}. ¡Te esperamos!"
    )
    diff = purchase.total - previous_total
    if diff > 0:
        message += f" La nueva función cuesta ${diff:.2f} más."
    elif diff < 0:
        message += f" La nueva función cuesta ${-diff:.2f} menos."
    messages.success(request, message)
    return redirect("my_tickets")


@login_required
def ticket_purchase_view(request, pk):
    Screening.finalize_expired()
    screening = get_object_or_404(Screening.published(), pk=pk)
    if request.method == "POST":
        form = TicketPurchaseForm(request.POST)
        if form.is_valid():
            try:
                purchase = buy_tickets_with_candy(
                    user=request.user,
                    screening=screening,
                    selected_seats=form.cleaned_data["selected_seats"],
                    candy_items=form.cleaned_data["candy_items"],
                )
            except ValidationError as error:
                available = TicketPurchase.available_for(screening)
                request.session["purchase_error"] = purchase_error_message(
                    error,
                    f"Solo tenemos disponibles {available} entradas para esta función.",
                )
            else:
                ticket_label = "entrada" if purchase.quantity == 1 else "entradas"
                if CandyOrder.objects.filter(purchase=purchase).exists():
                    message = (
                        f"Pago aprobado. Compraste {purchase.quantity} {ticket_label} y candy "
                        f"para {screening.movie.title}. Retirá el candy con su código antes o "
                        "durante la función. ¡Te esperamos!"
                    )
                else:
                    message = (
                        "Pago aprobado. "
                        f"Compraste {purchase.quantity} {ticket_label} "
                        f"para {screening.movie.title}. ¡Te esperamos!"
                    )
                messages.success(request, message)
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


def admission_seat_summary(tickets):
    grouped = {}
    fallback = []
    for ticket in tickets:
        label = ticket.seat_label or f"Entrada {ticket.number}"
        match = re.fullmatch(r"(\d+)([A-Z]+)", label)
        if not match:
            fallback.append(label)
            continue
        row, column = match.groups()
        grouped.setdefault(row, []).append(column)

    summary = []
    for row in sorted(grouped, key=int):
        columns = sorted(grouped[row])
        seats = columns[0] if len(columns) == 1 else f"{', '.join(columns[:-1])} y {columns[-1]}"
        summary.append(f"Fila {row}, {'asiento' if len(columns) == 1 else 'asientos'} {seats}")
    return " · ".join(summary + fallback)


@login_required
@require_POST
def seat_reservation_view(request, pk):
    Screening.finalize_expired()
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
    Screening.finalize_expired()
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
    Screening.finalize_expired()
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
        .select_related("screening__movie", "screening__room", "refund", "candy_order")
        .prefetch_related("tickets")
        .order_by("screening__starts_at", "-created_at")
    )
    for purchase in purchases:
        purchase.candy = getattr(purchase, "candy_order", None)
        purchase.used_count = sum(ticket.used_at is not None for ticket in purchase.tickets.all())
        purchase.remaining_count = purchase.quantity - purchase.used_count
        purchase.is_history = (
            purchase.screening.ends_at <= now
            or purchase.screening.status in {Screening.Status.FINISHED, Screening.Status.CANCELED}
            or hasattr(purchase, "refund")
        )
        purchase.admission_open = (
            purchase.screening.status in (Screening.Status.PUBLISHED, Screening.Status.IN_PROGRESS)
            and purchase.screening.ends_at > now
            and purchase.remaining_count > 0
            and not purchase.is_history
        )
        purchase.is_imminent = (
            purchase.admission_open
            and now <= purchase.screening.starts_at <= now + timedelta(hours=2)
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
def notifications_view(request):
    notifications = list(
        PurchaseRefund.objects.filter(purchase__user=request.user)
        .select_related("purchase__screening__movie", "purchase__screening__room")
        .order_by("-created_at")
    )
    unread_ids = [notification.pk for notification in notifications if notification.read_at is None]
    if unread_ids:
        PurchaseRefund.objects.filter(pk__in=unread_ids).update(read_at=timezone.now())
    return render(request, "notifications.html", {
        "cinema": CinemaSettings.current(),
        "notifications": notifications,
    })


@login_required
@never_cache
@require_GET
def ticket_detail_view(request, pk):
    purchase = get_object_or_404(
        TicketPurchase.objects.select_related(
            "screening__movie", "screening__room", "refund", "candy_order",
        ).prefetch_related("tickets"),
        pk=pk, user=request.user,
    )
    screening = purchase.screening
    tickets = list(purchase.tickets.all())
    used_tickets = [ticket for ticket in tickets if ticket.used_at is not None]
    used_count = len(used_tickets)
    is_expired = screening.ends_at <= timezone.now() or screening.status == Screening.Status.FINISHED
    available = (
        used_count < purchase.quantity and screening.status in (Screening.Status.PUBLISHED, Screening.Status.IN_PROGRESS)
        and screening.ends_at > timezone.now() and not hasattr(purchase, "refund")
    )
    reprogram_opition_avialable = screening.starts_at >= timezone.now() + timedelta(hours=2)
    candy_order = getattr(purchase, "candy_order", None)
    return render(request, "ticket_detail.html", {
        "purchase": purchase, "used_count": used_count, "available": available, "is_expired": is_expired,
        "remaining_count": purchase.quantity - used_count,
        "used_seat_summary": admission_seat_summary(used_tickets),
        "candy_order": candy_order,
        "total_paid": purchase.total + (candy_order.total if candy_order else 0),
        "cinema": CinemaSettings.current(),
        "manager_role": manager_role(request.user),
        "reprogram_opition_avialable": reprogram_opition_avialable
    })


@login_required
@never_cache
@require_GET
def candy_detail_view(request, pk):
    order = get_object_or_404(
        CandyOrder.objects.select_related(
            "purchase__screening__movie", "purchase__screening__room", "purchase__refund",
        ),
        purchase__pk=pk, purchase__user=request.user,
    )
    return render(request, "candy_detail.html", {
        "order": order,
        "purchase": order.purchase,
        "client_nav_section": "candy",
        "cinema": CinemaSettings.current(),
        "manager_role": manager_role(request.user),
    })


@login_required
@never_cache
@require_GET
def ticket_admission_status_view(request, pk):
    purchase = get_object_or_404(
        TicketPurchase.objects.select_related("screening__room").prefetch_related("tickets"),
        pk=pk, user=request.user,
    )
    tickets = list(purchase.tickets.all())
    used_tickets = [ticket for ticket in tickets if ticket.used_at is not None]
    return JsonResponse({
        "used_count": len(used_tickets),
        "remaining_count": purchase.quantity - len(used_tickets),
        "room": purchase.screening.room.name,
        "used_seat_summary": admission_seat_summary(used_tickets),
    })
