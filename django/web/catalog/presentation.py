"""Datos de presentaci?n del cat?logo y selecci?n de butacas."""

from django.db.models import Q
from django.utils import timezone
from domain.rooms.layout import index_to_letters
from domain.seat_types.models import SeatType
from domain.tickets.models import TicketPurchase


def build_seat_map(screening, user=None, price_calculator=None):
    snapshot = screening.room_layout_snapshot or {}
    if not snapshot:
        return None

    if isinstance(snapshot, dict):
        seats = snapshot.get("seats", [])
        rows_count = snapshot.get("rows") or max((seat["row"] for seat in seats), default=-1) + 1
        columns_count = (
            snapshot.get("columns") or max((seat["column"] for seat in seats), default=-1) + 1
        )
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

    seats_by_position = {(seat["row"], seat["column"]): seat for seat in seats}
    seat_type_ids = {seat.get("type_id") for seat in seats if seat.get("type_id")}
    seat_type_names = {seat.get("type") for seat in seats if seat.get("type")}
    seat_types = SeatType.objects.filter(Q(pk__in=seat_type_ids) | Q(name__in=seat_type_names))
    current_icons_by_type = {
        str(seat_type.pk): seat_type.icon.url if seat_type.icon else "" for seat_type in seat_types
    }
    current_icons_by_name = {
        seat_type.name: seat_type.icon.url if seat_type.icon else "" for seat_type in seat_types
    }
    unavailable_labels = TicketPurchase.blocked_seats(screening, user=user)
    price_quotes = TicketPurchase.seat_price_quotes(screening, price_calculator)
    legend_by_type = {}
    rows = []
    for row_index in range(rows_count):
        has_seats = any(
            (row_index, column_index) in seats_by_position for column_index in range(columns_count)
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
                price = (
                    quote.final_price if quote else screening.price_for_type(seat.get("type_id"))
                )
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


def add_details_to_screenings(screenings, user, price_calculator):
    for item in screenings:
        item.local_date = timezone.localdate(item.starts_at)
        item.tickets_available = TicketPurchase.available_for(item)
        item.seat_map = build_seat_map(
            item,
            user=user,
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
