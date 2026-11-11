"""Purchases."""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from domain.cinema.models import CinemaSettings
from domain.rooms.layout import summarize_seats
from domain.screenings.models import Screening
from domain.tickets.models import PurchaseRefund, TicketPurchase
from domain.tickets.services import reprogramming_deadline, reprogramming_window_is_open
from domain.users.roles import staff_role as manager_role


def admission_seat_summary(tickets):
    return summarize_seats(
        [ticket.seat_label or f"Entrada {ticket.number}" for ticket in tickets],
        row_title="Fila",
        separator=" · ",
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
    active_purchases.sort(
        key=lambda purchase: (not purchase.admission_open, purchase.screening.starts_at)
    )
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
    return render(
        request,
        "notifications.html",
        {
            "cinema": CinemaSettings.current(),
            "notifications": notifications,
        },
    )


@login_required
@never_cache
@require_GET
def ticket_detail_view(request, pk):
    purchase = get_object_or_404(
        TicketPurchase.objects.select_related(
            "screening__movie",
            "screening__room",
            "refund",
            "candy_order",
        ).prefetch_related("tickets"),
        pk=pk,
        user=request.user,
    )
    screening = purchase.screening
    tickets = list(purchase.tickets.all())
    used_tickets = [ticket for ticket in tickets if ticket.used_at is not None]
    used_count = len(used_tickets)
    is_expired = (
        screening.ends_at <= timezone.now() or screening.status == Screening.Status.FINISHED
    )
    available = (
        used_count < purchase.quantity
        and screening.status in (Screening.Status.PUBLISHED, Screening.Status.IN_PROGRESS)
        and screening.ends_at > timezone.now()
        and not hasattr(purchase, "refund")
    )
    cinema = CinemaSettings.current()
    reprogram_opition_avialable = reprogramming_window_is_open(screening, cinema=cinema)
    candy_order = getattr(purchase, "candy_order", None)
    return render(
        request,
        "ticket_detail.html",
        {
            "purchase": purchase,
            "used_count": used_count,
            "available": available,
            "is_expired": is_expired,
            "remaining_count": purchase.quantity - used_count,
            "used_seat_summary": admission_seat_summary(used_tickets),
            "candy_order": candy_order,
            "total_paid": purchase.total + (candy_order.total if candy_order else 0),
            "cinema": cinema,
            "manager_role": manager_role(request.user),
            "reprogram_opition_avialable": reprogram_opition_avialable,
            "reprogram_deadline": reprogramming_deadline(screening, cinema=cinema),
        },
    )


@login_required
@never_cache
@require_GET
def ticket_admission_status_view(request, pk):
    purchase = get_object_or_404(
        TicketPurchase.objects.select_related("screening__room").prefetch_related("tickets"),
        pk=pk,
        user=request.user,
    )
    tickets = list(purchase.tickets.all())
    used_tickets = [ticket for ticket in tickets if ticket.used_at is not None]
    return JsonResponse(
        {
            "used_count": len(used_tickets),
            "remaining_count": purchase.quantity - len(used_tickets),
            "room": purchase.screening.room.name,
            "used_seat_summary": admission_seat_summary(used_tickets),
        }
    )
