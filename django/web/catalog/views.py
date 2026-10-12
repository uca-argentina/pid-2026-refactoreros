from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render

from domain.cinema.models import CinemaSettings
from domain.movies.models import Movie
from domain.promotions.pricing import PromotionPriceCalculator
from domain.screenings.models import Screening
from domain.seat_types.models import SeatType
from domain.tickets.models import TicketPurchase
from web.manager.views import manager_role


def index_to_letters(index):
    label = ""
    value = index + 1
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


def build_seat_map(screening, user=None, price_calculator=None):
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
    seat_type_ids = {seat.get("type_id") for seat in seats if seat.get("type_id")}
    seat_type_names = {seat.get("type") for seat in seats if seat.get("type")}
    seat_types = SeatType.objects.filter(
        Q(pk__in=seat_type_ids) | Q(name__in=seat_type_names)
    )
    current_icons_by_type = {
        str(seat_type.pk): seat_type.icon.url if seat_type.icon else ""
        for seat_type in seat_types
    }
    current_icons_by_name = {
        seat_type.name: seat_type.icon.url if seat_type.icon else ""
        for seat_type in seat_types
    }
    unavailable_labels = TicketPurchase.blocked_seats(screening, user=user)
    price_quotes = TicketPurchase.seat_price_quotes(screening, price_calculator)
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
                quote = price_quotes.get(label)
                price = quote.final_price if quote else screening.price_for_type(seat.get("type_id"))
                base_price = quote.base_price if quote else price
                promotion_name = quote.promotion.name if quote and quote.promotion else ""
                icon_url = (
                    current_icons_by_type.get(str(seat.get("type_id")), "")
                    or current_icons_by_name.get(seat.get("type"), "")
                    or seat.get("icon_url", "")
                )
                if type_key not in legend_by_type:
                    legend_by_type[type_key] = {
                        "type": seat["type"],
                        "color": seat["color"],
                        "icon_url": icon_url,
                        "price": price,
                        "base_price": base_price,
                        "promotion": promotion_name,
                    }
                row["cells"].append(
                    {
                        "is_seat": True,
                        "label": label,
                        "accessibility_label": f"Fila {row_label}, columna {column_label}",
                        "type": seat["type"],
                        "type_id": seat.get("type_id"),
                        "price": price,
                        "base_price": base_price,
                        "promotion": promotion_name,
                        "color": seat["color"],
                        "icon_url": icon_url,
                        "is_unavailable": label in unavailable_labels,
                    }
                )
            else:
                row["cells"].append({"is_seat": False})
        rows.append(row)
    quote_prices = [quote.final_price for quote in price_quotes.values()]
    return {
        "columns": columns,
        "rows": rows,
        "legend": list(legend_by_type.values()),
        "price_from": min(quote_prices, default=screening.price_from),
    }


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
    price_calculator = PromotionPriceCalculator.current()
    for item in movie.published_screenings:
        item.tickets_available = TicketPurchase.available_for(item)
        item.seat_map = build_seat_map(
            item,
            user=request.user,
            price_calculator=price_calculator,
        )
        item.current_price_from = item.seat_map["price_from"] if item.seat_map else item.price_from
        item.promotion_names = sorted(
            {
                tier["promotion"]
                for tier in (item.seat_map or {}).get("legend", [])
                if tier["promotion"]
            }
        )
        item.has_promotion = bool(item.promotion_names)
        item.promotion_summary = ", ".join(item.promotion_names)
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


def _error_page(request, status, title, description, eyebrow):
    """Render project error pages without relying on the normal navigation."""
    try:
        cinema = CinemaSettings.current()
    except Exception:
        cinema = CinemaSettings(name="Butaca Cero")
    return render(request, "error_page.html", {
        "cinema": cinema,
        "status": status,
        "title": title,
        "description": description,
        "eyebrow": eyebrow,
    }, status=status)


def bad_request_view(request, exception=None):
    return _error_page(
        request, 400, "No pudimos interpretar la solicitud.",
        "Revisá los datos e intentá nuevamente.", "Solicitud inválida",
    )


def permission_denied_view(request, exception=None):
    return _error_page(
        request, 403, "No tenés permiso para entrar acá.",
        "Si creés que deberías tener acceso, iniciá sesión con otra cuenta.", "Acceso restringido",
    )


def not_found_view(request, exception=None):
    return _error_page(
        request, 404, "Esta página se perdió en el multiverso.",
        "La página que buscás no existe o ya no está disponible.", "Página no encontrada",
    )


def server_error_view(request):
    return _error_page(
        request, 500, "Se apagaron las luces antes de tiempo.",
        "Tuvimos un problema inesperado. Esperá unos segundos e intentá de nuevo.", "Error inesperado",
    )
