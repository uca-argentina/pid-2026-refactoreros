from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render

from domain.cinema.models import ConfiguracionCine
from domain.movies.models import Pelicula
from domain.screenings.models import Funcion
from domain.tickets.models import CompraEntrada
from web.manager.views import manager_role


def index_to_letters(index):
    label = ""
    value = index + 1
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


def build_seat_map(funcion, usuario=None):
    snapshot = funcion.sala_configuracion_snapshot or {}
    if not snapshot:
        return None

    if isinstance(snapshot, dict):
        seats = snapshot.get("seats", [])
        rows_count = snapshot.get("rows") or max((seat["row"] for seat in seats), default=-1) + 1
        columns_count = snapshot.get("columns") or max((seat["column"] for seat in seats), default=-1) + 1
    else:
        seats = snapshot
        rows_count = max((seat["row"] for seat in seats), default=-1) + 1
        columns_count = max((seat["column"] for seat in seats), default=-1) + 1

    if rows_count <= 0 or columns_count <= 0:
        return None

    occupied_columns = {seat["column"] for seat in seats}
    column_labels = {}
    next_column_label = 0
    columns = []
    for column_index in range(columns_count):
        if column_index in occupied_columns:
            label = index_to_letters(next_column_label)
            next_column_label += 1
        else:
            label = ""
        column_labels[column_index] = label
        columns.append({"label": label, "is_aisle": not label})

    seats_by_position = {
        (seat["row"], seat["column"]): seat
        for seat in seats
    }
    unavailable_labels = CompraEntrada.asientos_bloqueados(funcion, usuario=usuario)
    legend_by_type = {}
    rows = []
    for row_index in range(rows_count):
        has_seats = any(
            (row_index, column_index) in seats_by_position
            for column_index in range(columns_count)
        )
        row_label = str(row_index + 1)
        row = {
            "label": row_label if has_seats else "",
            "is_aisle": not has_seats,
            "cells": [],
        }
        for column_index in range(columns_count):
            seat = seats_by_position.get((row_index, column_index))
            column_label = column_labels[column_index] or ""
            if seat:
                label = f"{row_label}{column_label}"
                type_key = str(seat.get("type_id") or seat["type"])
                if type_key not in legend_by_type:
                    legend_by_type[type_key] = {
                        "type": seat["type"],
                        "color": seat["color"],
                        "price": seat.get("price"),
                    }
                row["cells"].append(
                    {
                        "is_seat": True,
                        "label": label,
                        "accessibility_label": f"Fila {row_label}, columna {column_label}",
                        "type": seat["type"],
                        "type_id": seat.get("type_id"),
                        "price": seat.get("price"),
                        "color": seat["color"],
                        "is_unavailable": label in unavailable_labels,
                    }
                )
            else:
                row["cells"].append({"is_seat": False})
        rows.append(row)
    return {"columns": columns, "rows": rows, "legend": list(legend_by_type.values())}


@login_required
def home_view(request):
    Funcion.finalizar_vencidas()
    funciones_publicadas = Funcion.funciones_publicadas()
    peliculas = Pelicula.objects.filter(
        funciones__estado=Funcion.Estado.PUBLICADA
    ).prefetch_related(
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
    Funcion.finalizar_vencidas()
    funciones_publicadas = Funcion.funciones_publicadas()
    pelicula = get_object_or_404(
        Pelicula.objects.filter(
            funciones__estado=Funcion.Estado.PUBLICADA
        ).prefetch_related(
            Prefetch("funciones", queryset=funciones_publicadas, to_attr="publicadas")
        ).distinct(),
        pk=pk,
    )
    funcion = pelicula.publicadas[0]
    for item in pelicula.publicadas:
        item.entradas_disponibles = CompraEntrada.disponibles_para(item)
        item.seat_map = build_seat_map(item, usuario=request.user)
    return render(
        request,
        "screening_detail.html",
        {
            "cinema": ConfiguracionCine.actual(),
            "pelicula": pelicula,
            "funcion": funcion,
            "funciones": pelicula.publicadas,
            "entradas_disponibles": funcion.entradas_disponibles,
            "manager_role": manager_role(request.user),
        },
    )


@login_required
def screening_detail_view(request, pk):
    Funcion.finalizar_vencidas()
    funcion = get_object_or_404(Funcion.funciones_publicadas(), pk=pk)
    return redirect("seat_selection", pk=funcion.pk)
