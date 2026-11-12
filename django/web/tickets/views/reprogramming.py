"""Reprogramming."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from domain.cinema.models import CinemaSettings
from domain.screenings.models import Screening
from domain.tickets.models import TicketPurchase
from domain.tickets.services import check_reprogramming_window, reprogram_purchase
from domain.users.roles import staff_role as manager_role

from web.catalog.presentation import build_seat_map
from web.tickets.forms import TicketReprogramForm
from web.tickets.views.common import purchase_error_message


@login_required
@never_cache
def seat_reprogram_selection_view(request, purchase_pk, screening_pk):
    Screening.finalize_expired()

    purchase = get_object_or_404(
        request.user.ticket_purchases.select_related("screening__movie", "screening__room"),
        pk=purchase_pk,
    )
    current_screening = purchase.screening

    try:
        check_reprogramming_window(current_screening)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("my_tickets")

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

