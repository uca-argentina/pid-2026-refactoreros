"""Candy."""

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import OperationalError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from domain.candy.models import CandyOrder
from domain.candy.services import buy_candy_only, candy_menu
from domain.cinema.models import CinemaSettings
from domain.users.roles import staff_role as manager_role

from web.tickets.forms import CandyPurchaseForm
from web.tickets.views.common import purchase_error_message


@login_required
@never_cache
@require_GET
def candy_store_view(request):
    return render(
        request,
        "candy_store.html",
        {
            "cinema": CinemaSettings.current(),
            "manager_role": manager_role(request.user),
            "candy": candy_menu(),
            "checkout_key": uuid.uuid4(),
            "purchase_error": request.session.pop("candy_purchase_error", ""),
            "orders": Paginator(CandyOrder.for_user(request.user), 12).get_page(
                request.GET.get("page")
            ),
        },
    )


@login_required
@never_cache
@require_POST
def candy_purchase_view(request):
    form = CandyPurchaseForm(request.POST)
    if form.is_valid():
        try:
            order = buy_candy_only(
                request.user, form.cleaned_data["candy_items"], form.cleaned_data["checkout_key"]
            )
        except ValidationError as error:
            request.session["candy_purchase_error"] = purchase_error_message(
                error, "No se pudo completar el pedido."
            )
        except OperationalError:
            request.session["candy_purchase_error"] = (
                "Hay otra compra en curso. Volvé a intentarlo."
            )
        else:
            messages.success(
                request,
                "Pago aprobado. Tu pedido de Candy está listo para retirar con su QR. ¡Que lo disfrutes!",
            )
            return redirect("candy_order_detail", pk=order.pk)
    else:
        request.session["candy_purchase_error"] = purchase_error_message(
            form.errors, "Revisá tu selección de Candy."
        )
    return redirect("candy_store")


@login_required
@never_cache
@require_GET
def candy_order_detail_view(request, pk):
    order = get_object_or_404(CandyOrder.for_user(request.user), pk=pk)
    return render(
        request,
        "candy_detail.html",
        {
            "order": order,
            "purchase": order.purchase,
            "cinema": CinemaSettings.current(),
            "manager_role": manager_role(request.user),
        },
    )


@login_required
@never_cache
@require_GET
def candy_detail_view(request, pk):
    order = get_object_or_404(
        CandyOrder.objects.select_related(
            "purchase__screening__movie",
            "purchase__screening__room",
            "purchase__refund",
        ),
        purchase__pk=pk,
        purchase__user=request.user,
    )
    return render(
        request,
        "candy_detail.html",
        {
            "order": order,
            "purchase": order.purchase,
            "client_nav_section": "candy",
            "cinema": CinemaSettings.current(),
            "manager_role": manager_role(request.user),
        },
    )
