"""Checkout."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from domain.candy.models import CandyOrder
from domain.candy.services import buy_tickets_with_candy, candy_menu
from domain.cinema.models import CinemaSettings
from domain.screenings.models import Screening
from domain.tickets.models import TicketPurchase
from domain.users.roles import staff_role as manager_role

from web.catalog.presentation import build_seat_map
from web.tickets.forms import TicketPurchaseForm
from web.tickets.views.common import purchase_error_message


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
