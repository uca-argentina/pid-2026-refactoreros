"""Dashboard: service."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from domain.movies.models import Movie
from domain.rooms.models import Room

from .charts import add_month, first_date, revenue_series
from .constants import PERIODS
from .filters import add_filter_links, filter_rows, resolve_period, start_of_day
from .metrics import (
    add_standalone_revenue,
    build_deltas,
    decision_insights,
    occupancy_by_room,
    summarize,
    top_movies,
)
from .queries import (
    candy_metrics,
    completed_screenings,
    demand_by_purchase_time,
    presale,
    screening_rows,
    selected_object,
    standalone_candy_orders,
)


def build_dashboard(
    period=None,
    date_from=None,
    date_to=None,
    now=None,
    movie_id=None,
    room_id=None,
    revenue_date=None,
    view=None,
):
    now = now or timezone.now()
    view = "candy" if view == "candy" else "movies"
    today = timezone.localdate(now)
    has_custom_range = date_from is not None or date_to is not None

    if has_custom_range:
        key = "custom"
        end_date = min(date_to or today, today)
        start = start_of_day(date_from) if date_from else None
        end = min(start_of_day(end_date + timedelta(days=1)), now)
        days = (end_date - date_from).days + 1 if date_from else None
    else:
        key, days = resolve_period(period)
        start = start_of_day(today - timedelta(days=days - 1)) if days else None
        end = now
        end_date = today

    movie = selected_object(Movie, movie_id)
    room = selected_object(Room, room_id)
    movie_id = movie.pk if movie else None
    room_id = room.pk if room else None
    all_rows = screening_rows(completed_screenings(start, end))
    standalone = standalone_candy_orders(start, end, movie_id, room_id)
    plot_rows = filter_rows(all_rows, movie_id, room_id)
    if view == "candy":
        plot_candy = candy_metrics(plot_rows)
        plot_rows = [
            {
                **row,
                "revenue": row["candy_revenue"],
                "ticket_revenue": Decimal("0"),
                "sold": plot_candy["orders_by_screening"].get(row["screening"].pk, 0),
            }
            for row in plot_rows
        ]
    plot_rows += [
        {
            "starts_at": timezone.localtime(order.created_at),
            "revenue": order.total,
            "ticket_revenue": Decimal("0"),
            "candy_revenue": order.total,
            "sold": 1 if view == "candy" else 0,
            "screening": None,
        }
        for order in standalone
    ]
    axis_start = min((row["starts_at"].date() for row in plot_rows), default=first_date(all_rows))
    revenue = revenue_series(
        plot_rows,
        start,
        end_date,
        axis_start=axis_start,
    )
    selected_column = None
    if revenue and revenue_date:
        selected_column = next(
            (column for column in revenue["columns"] if column["date"].isoformat() == revenue_date),
            None,
        )
    selected_range = None
    if selected_column:
        first = selected_column["date"]
        granularity = revenue["granularity"]
        after = (
            add_month(first)
            if granularity == "month"
            else first + timedelta(days=7 if granularity == "week" else 1)
        )
        first = max(first, timezone.localdate(start)) if start else first
        after = min(after, end_date + timedelta(days=1))
        selected_range = (start_of_day(first), min(start_of_day(after), end))
    rows = filter_rows(all_rows, movie_id, room_id, selected_range)
    summary = summarize(rows)
    selected_standalone = standalone_candy_orders(start, end, movie_id, room_id, selected_range)
    add_standalone_revenue(summary, selected_standalone)
    movies = top_movies(rows)
    time_slots = demand_by_purchase_time(start, end, movie_id, room_id, selected_range)
    previous = None
    comparison_start = selected_range[0] if selected_range else start
    comparison_days = (after - first).days if selected_range else days
    if comparison_start is not None and comparison_days:
        start_previous = comparison_start - timedelta(days=comparison_days)
        previous = summarize(
            filter_rows(
                screening_rows(completed_screenings(start_previous, comparison_start)),
                movie_id,
                room_id,
            )
        )
        add_standalone_revenue(
            previous, standalone_candy_orders(start_previous, comparison_start, movie_id, room_id)
        )

    dashboard = {
        "view": view,
        "candy": candy_metrics(rows, selected_standalone) if view == "candy" else None,
        "periods": [
            {"key": value, "label": label, "active": not has_custom_range and value == key}
            for value, label, _days in PERIODS
        ],
        "period": key,
        "date_from": date_from,
        "date_to": date_to,
        "has_custom_range": has_custom_range,
        "start": timezone.localdate(start) if start else axis_start,
        "end": end_date,
        "summary": summary,
        "deltas": build_deltas(summary, previous),
        "revenue": revenue,
        "movies": top_movies(
            filter_rows(all_rows, room_id=room_id, date_range=selected_range), movie_id
        ),
        "rooms": occupancy_by_room(
            filter_rows(all_rows, movie_id=movie_id, date_range=selected_range)
        ),
        "time_slots": time_slots,
        "insights": decision_insights(summary, movies, time_slots),
        "presale": presale(now, movie_id, room_id, selected_range),
        "selected_movie": movie,
        "selected_room": room,
        "selected_revenue_date": selected_column["date"] if selected_column else None,
    }
    add_filter_links(dashboard)
    return dashboard
