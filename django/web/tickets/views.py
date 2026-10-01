from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from domain.cinema.models import ConfiguracionCine
from domain.screenings.models import Funcion
from domain.tickets.models import CompraEntrada
from web.catalog.views import build_seat_map, manager_role

from .forms import TicketPurchaseForm


@login_required
def seat_selection_view(request, pk):
    funcion = get_object_or_404(Funcion.funciones_publicadas(), pk=pk)
    funcion.entradas_disponibles = CompraEntrada.disponibles_para(funcion)
    funcion.seat_map = build_seat_map(funcion)
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
    funcion = get_object_or_404(Funcion.funciones_publicadas(), pk=pk)
    if request.method == "POST":
        form = TicketPurchaseForm(request.POST)
        if form.is_valid():
            try:
                compra = CompraEntrada.comprar(
                    usuario=request.user,
                    funcion=funcion,
                    cantidad=form.cleaned_data["cantidad"],
                    selected_seats=form.cleaned_data["selected_seats"],
                )
            except ValidationError as error:
                disponibles = CompraEntrada.disponibles_para(funcion)
                request.session["purchase_error"] = (
                    f"Solo tenemos disponibles {disponibles} entradas para esta función."
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
            request.session["purchase_error"] = "Elegí al menos una entrada."
    return redirect("seat_selection", pk=funcion.pk)


@login_required
def my_tickets_view(request):
    compras = (
        CompraEntrada.objects.filter(usuario=request.user)
        .select_related("funcion__pelicula", "funcion__sala")
        .order_by("-creada_en")
    )
    return render(
        request,
        "my_tickets.html",
        {
            "cinema": ConfiguracionCine.actual(),
            "compras": compras,
        },
    )
