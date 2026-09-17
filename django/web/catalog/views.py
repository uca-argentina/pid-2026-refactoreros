from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render

from domain.cinema.models import ConfiguracionCine
from domain.movies.models import Pelicula
from domain.screenings.models import Funcion
from domain.tickets.models import CompraEntrada
from web.manager.views import manager_role


@login_required
def home_view(request):
    funciones_publicadas = Funcion.funciones_publicadas()
    peliculas = Pelicula.objects.filter(funciones__publicada=True).prefetch_related(
        Prefetch("funciones", queryset=funciones_publicadas, to_attr="publicadas")
    ).distinct()
    return render(
        request,
        "home.html",
        {
            "cinema": ConfiguracionCine.actual(),
            "peliculas": peliculas,
            "manager_role": manager_role(request.user),
        },
    )


@login_required
def movie_detail_view(request, pk):
    funciones_publicadas = Funcion.funciones_publicadas()
    pelicula = get_object_or_404(
        Pelicula.objects.filter(funciones__publicada=True).prefetch_related(
            Prefetch("funciones", queryset=funciones_publicadas, to_attr="publicadas")
        ).distinct(),
        pk=pk,
    )
    selected_funcion_id = request.session.pop("selected_funcion_id", None)
    funcion = next(
        (
            item
            for item in pelicula.publicadas
            if str(item.pk) == str(selected_funcion_id)
        ),
        pelicula.publicadas[0],
    )
    for item in pelicula.publicadas:
        item.entradas_disponibles = CompraEntrada.disponibles_para(item)
    purchase_error = request.session.pop("purchase_error", "")
    return render(
        request,
        "screening_detail.html",
        {
            "cinema": ConfiguracionCine.actual(),
            "pelicula": pelicula,
            "funcion": funcion,
            "funciones": pelicula.publicadas,
            "entradas_disponibles": funcion.entradas_disponibles,
            "purchase_error": purchase_error,
            "manager_role": manager_role(request.user),
        },
    )


@login_required
def screening_detail_view(request, pk):
    funcion = get_object_or_404(Funcion.funciones_publicadas(), pk=pk)
    request.session["selected_funcion_id"] = funcion.pk
    return redirect("movie_detail", pk=funcion.pelicula_id)
