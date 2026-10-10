from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render

from domain.cinema.models import CinemaSettings
from domain.movies.models import Movie
from domain.screenings.models import Screening
from domain.tickets.models import TicketPurchase
from web.manager.views import manager_role


def index_to_letters(index):
    label = ""
    value = index + 1
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


def build_seat_map(screening, user=None):
    snapshot = screening.room_layout_snapshot or {}
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
    unavailable_labels = TicketPurchase.blocked_seats(screening, user=user)
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


def home_view(request):
    Screening.finalize_expired()
    published = Screening.published()
    movies = Movie.objects.filter(
        screenings__status=Screening.Status.PUBLISHED
    ).prefetch_related(
        Prefetch("screenings", queryset=published, to_attr="published_screenings")
    ).distinct()
    return render(
        request,
        "home.html",
        {
            "cinema": CinemaSettings.current(),
            "movies": movies,
            "manager_role": manager_role(request.user),
        },
    )


def movie_detail_view(request, pk):
    Screening.finalize_expired()
    published = Screening.published()
    movie = get_object_or_404(
        Movie.objects.filter(
            screenings__status=Screening.Status.PUBLISHED
        ).prefetch_related(
            Prefetch("screenings", queryset=published, to_attr="published_screenings")
        ).distinct(),
        pk=pk,
    )
    screening = movie.published_screenings[0]
    for item in movie.published_screenings:
        item.tickets_available = TicketPurchase.available_for(item)
        item.seat_map = build_seat_map(item, user=request.user)
    return render(
        request,
        "screening_detail.html",
        {
            "cinema": CinemaSettings.current(),
            "movie": movie,
            "screening": screening,
            "screenings": movie.published_screenings,
            "tickets_available": screening.tickets_available,
            "manager_role": manager_role(request.user),
        },
    )


def screening_detail_view(request, pk):
    Screening.finalize_expired()
    screening = get_object_or_404(Screening.published(), pk=pk)
    return redirect("seat_selection", pk=screening.pk)
