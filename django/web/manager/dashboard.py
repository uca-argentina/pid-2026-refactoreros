import math
from datetime import datetime, time, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Count, Sum
from django.db.models.functions import ExtractHour, ExtractMinute, ExtractWeekDay
from django.utils import timezone
from django.utils.formats import date_format

from domain.movies.models import Movie
from domain.rooms.models import Room
from domain.screenings.models import Screening
from domain.seats.models import Seat
from domain.tickets.models import SeatPurchase, TicketPurchase


PERIODS = (
    ("7", "7 días", 7),
    ("30", "30 días", 30),
    ("90", "90 días", 90),
    ("todo", "Todo", None),
)
DEFAULT_PERIOD = "30"
ACCOUNTED_STATUSES = (Screening.Status.FINISHED,)
PURCHASED_STATUSES = (
    Screening.Status.PUBLISHED,
    Screening.Status.IN_PROGRESS,
    Screening.Status.FINISHED,
)
WEEKDAYS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
SHORT_WEEKDAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
TOP_MOVIES = 5
TOP_TIME_SLOTS = 3
X_AXIS_LABELS = 8
TIME_SLOT_MINUTES = 30


def build_dashboard(
    period=None, date_from=None, date_to=None, now=None,
    movie_id=None, room_id=None, revenue_date=None,
):
    now = now or timezone.now()
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
    revenue = revenue_series(
        filter_rows(all_rows, movie_id, room_id), start, end_date,
        axis_start=first_date(all_rows),
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
        after = add_month(first) if granularity == "month" else first + timedelta(
            days=7 if granularity == "week" else 1
        )
        first = max(first, timezone.localdate(start)) if start else first
        after = min(after, end_date + timedelta(days=1))
        selected_range = (start_of_day(first), min(start_of_day(after), end))
    rows = filter_rows(all_rows, movie_id, room_id, selected_range)
    summary = summarize(rows)
    movies = top_movies(rows)
    time_slots = demand_by_purchase_time(start, end, movie_id, room_id, selected_range)
    previous = None
    comparison_start = selected_range[0] if selected_range else start
    comparison_days = (after - first).days if selected_range else days
    if comparison_start is not None and comparison_days:
        start_previous = comparison_start - timedelta(days=comparison_days)
        previous = summarize(filter_rows(
            screening_rows(completed_screenings(start_previous, comparison_start)),
            movie_id, room_id,
        ))

    dashboard = {
        "periods": [
            {"key": value, "label": label, "active": not has_custom_range and value == key}
            for value, label, _days in PERIODS
        ],
        "period": key,
        "date_from": date_from,
        "date_to": date_to,
        "has_custom_range": has_custom_range,
        "start": timezone.localdate(start) if start else first_date(all_rows),
        "end": end_date,
        "summary": summary,
        "deltas": build_deltas(summary, previous),
        "revenue": revenue,
        "movies": top_movies(filter_rows(all_rows, room_id=room_id, date_range=selected_range), movie_id),
        "rooms": occupancy_by_room(filter_rows(all_rows, movie_id=movie_id, date_range=selected_range)),
        "time_slots": time_slots,
        "insights": decision_insights(summary, movies, time_slots),
        "presale": presale(now, movie_id, room_id, selected_range),
        "selected_movie": movie,
        "selected_room": room,
        "selected_revenue_date": selected_column["date"] if selected_column else None,
    }
    add_filter_links(dashboard)
    return dashboard


def selected_object(model, value):
    try:
        value = int(value)
    except (ValueError, TypeError):
        return None
    if not 0 < value <= 9223372036854775807:
        return None
    return model.objects.filter(pk=value).first()


def filter_rows(rows, movie_id=None, room_id=None, date_range=None):
    return [
        row for row in rows
        if (not movie_id or row["screening"].movie_id == movie_id)
        and (not room_id or row["screening"].room_id == room_id)
        and (not date_range or date_range[0] <= row["starts_at"] < date_range[1])
    ]


def add_filter_links(dashboard):
    params = {}
    if dashboard["has_custom_range"]:
        for key in ("date_from", "date_to"):
            if dashboard[key]:
                params[key] = dashboard[key].isoformat()
    else:
        params["period"] = dashboard["period"]
    dashboard["clear_filters_url"] = "?" + urlencode(params)
    selected = {
        "movie": str(dashboard["selected_movie"].pk) if dashboard["selected_movie"] else None,
        "room": str(dashboard["selected_room"].pk) if dashboard["selected_room"] else None,
        "revenue_date": dashboard["selected_revenue_date"].isoformat() if dashboard["selected_revenue_date"] else None,
    }
    params.update({key: value for key, value in selected.items() if value})

    def link(key, value):
        updated = dict(params)
        if value is None or selected.get(key) == str(value):
            updated.pop(key, None)
        else:
            updated[key] = str(value)
        return "?" + urlencode(updated)

    for period in dashboard["periods"]:
        period["url"] = "?" + urlencode({
            "period": period["key"],
            **{key: selected[key] for key in ("movie", "room") if selected[key]},
        })
    for key, items, object_key in (
        ("movie", dashboard["movies"], "movie"),
        ("room", dashboard["rooms"], "room"),
    ):
        for item in items:
            value = str(item[object_key].pk)
            item["filter_url"] = link(key, value)
            item["is_selected"] = value == selected[key]
            item["is_muted"] = bool(selected[key]) and not item["is_selected"]
    if dashboard["revenue"]:
        for column in dashboard["revenue"]["columns"]:
            value = column["date"].isoformat()
            column["filter_url"] = link("revenue_date", value)
            column["is_selected"] = value == selected["revenue_date"]
            column["is_muted"] = bool(selected["revenue_date"]) and not column["is_selected"]

    dashboard["active_filters"] = []
    for key, label, icon, value in (
        ("movie", "Película", "clapperboard", dashboard["selected_movie"]),
        ("room", "Sala", "armchair", dashboard["selected_room"]),
        ("revenue_date", "Fecha de función", "calendar-days", dashboard["selected_revenue_date"]),
    ):
        if value is not None:
            if key == "movie":
                text = value.title
            elif key == "room":
                text = value.name
            else:
                granularity = dashboard["revenue"]["granularity"]
                text = date_format(value, "F Y" if granularity == "month" else "d/m/Y")
                if granularity == "week":
                    text = "Semana del " + text
            dashboard["active_filters"].append({
                "key": key, "label": label, "value": text,
                "icon": icon, "remove_url": link(key, None),
            })


def resolve_period(period):
    for value, _label, days in PERIODS:
        if value == period:
            return value, days
    return resolve_period(DEFAULT_PERIOD)


def start_of_day(date):
    return timezone.make_aware(datetime.combine(date, time.min))


def completed_screenings(start, end):
    screenings = Screening.objects.filter(
        status__in=ACCOUNTED_STATUSES,
        starts_at__lt=end,
    )
    if start is not None:
        screenings = screenings.filter(starts_at__gte=start)
    return screenings


def screening_rows(screenings):
    ids = screenings.values("pk")
    sales = {
        sale["screening_id"]: sale
        for sale in TicketPurchase.objects.filter(screening__in=ids)
        .order_by()
        .values("screening_id")
        .annotate(sold=Sum("quantity"), revenue=Sum("total"))
    }
    used = dict(
        SeatPurchase.objects.filter(screening__in=ids, used_at__isnull=False)
        .order_by()
        .values("screening_id")
        .annotate(total=Count("pk"))
        .values_list("screening_id", "total")
    )
    capacities = dict(
        Seat.objects.order_by()
        .values("room_id")
        .annotate(total=Count("pk"))
        .values_list("room_id", "total")
    )

    rows = []
    for screening in screenings.select_related("movie", "room").order_by("starts_at"):
        sale = sales.get(screening.pk, {})
        sold = sale.get("sold") or 0
        rows.append(
            {
                "screening": screening,
                "starts_at": timezone.localtime(screening.starts_at),
                "sold": sold,
                "revenue": sale.get("revenue") or Decimal("0"),
                "used": min(used.get(screening.pk, 0), sold),
                "capacity": screening.capacity_snapshot or capacities.get(screening.room_id, 0),
            }
        )
    return rows


def percentage(part, total):
    return float(part) * 100 / float(total) if total else 0


def summarize(rows):
    sold = sum(row["sold"] for row in rows)
    used = sum(row["used"] for row in rows)
    capacity = sum(row["capacity"] for row in rows)
    revenue = sum((row["revenue"] for row in rows), Decimal("0"))
    return {
        "screenings": len(rows),
        "sold": sold,
        "used": used,
        "unused": sold - used,
        "capacity": capacity,
        "revenue": revenue,
        "average_ticket": revenue / sold if sold else Decimal("0"),
        "occupancy": percentage(sold, capacity),
        "attendance": percentage(used, sold),
        "attendance_css": css_percentage(percentage(used, sold)),
    }


def first_date(rows):
    return rows[0]["starts_at"].date() if rows else None


def css_percentage(value):
    return f"{max(min(value, 100), 0):.2f}%"


def variation(value, unit):
    if value is None:
        return None
    if abs(value) < 0.05:
        direction = "flat"
    else:
        direction = "up" if value > 0 else "down"
    return {
        "value": abs(value),
        "sign": {"up": "+", "down": "−", "flat": ""}[direction],
        "direction": direction,
        "unit": unit,
    }


def percentage_delta(current, prior):
    if not prior:
        return None
    return float(current - prior) * 100 / float(prior)


def build_deltas(summary, previous):
    if previous is None:
        return {}
    occupancy = None
    if previous["capacity"]:
        occupancy = summary["occupancy"] - previous["occupancy"]
    return {
        "revenue": variation(
            percentage_delta(summary["revenue"], previous["revenue"]), "%"
        ),
        "sold": variation(
            percentage_delta(summary["sold"], previous["sold"]), "%"
        ),
        "occupancy": variation(occupancy, " p. p."),
    }


def scale(maximum, divisions=4):
    if maximum <= 0:
        return 0, []
    raw_step = maximum / divisions
    magnitude = 10 ** math.floor(math.log10(raw_step))
    step = next(m * magnitude for m in (1, 2, 5, 10) if m * magnitude >= raw_step)
    top = step * math.ceil(maximum / step)
    return top, [step * index for index in range(round(top / step) + 1)]


def add_month(date):
    return (date.replace(day=28) + timedelta(days=4)).replace(day=1)


def grouping_key(date, granularity):
    if granularity == "week":
        return date - timedelta(days=date.weekday())
    if granularity == "month":
        return date.replace(day=1)
    return date


def revenue_series(rows, start, today, axis_start=None):
    if not rows and axis_start is None:
        return None
    start = timezone.localdate(start) if start else axis_start or first_date(rows)
    total_days = (today - start).days + 1
    if total_days <= 31:
        granularity, advance = "day", lambda date: date + timedelta(days=1)
    elif total_days <= 26 * 7:
        granularity, advance = "week", lambda date: date + timedelta(days=7)
    else:
        granularity, advance = "month", add_month

    keys = []
    key = grouping_key(start, granularity)
    while key <= today:
        keys.append(key)
        key = advance(key)

    accumulated = {
        key: {"revenue": Decimal("0"), "sold": 0, "screenings": 0}
        for key in keys
    }
    for row in rows:
        data = accumulated[grouping_key(row["starts_at"].date(), granularity)]
        data["revenue"] += row["revenue"]
        data["sold"] += row["sold"]
        data["screenings"] += 1

    maximum = max(data["revenue"] for data in accumulated.values())
    top, ticks = scale(float(maximum))
    skip = math.ceil(len(keys) / X_AXIS_LABELS)
    columns = []
    marked_peak = False
    for index, key in enumerate(keys):
        data = accumulated[key]
        is_peak = bool(maximum) and not marked_peak and data["revenue"] == maximum
        marked_peak = marked_peak or is_peak
        columns.append(
            {
                "date": key,
                **data,
                "height_css": css_percentage(percentage(data["revenue"], top)),
                "show_label": index % skip == 0,
                "secondary_label": index % skip == 0 and (index // skip) % 2 == 1,
                "is_peak": is_peak,
            }
        )
    return {
        "granularity": granularity,
        "columns": columns,
        "ticks": [
            {"value": tick, "position_css": css_percentage(percentage(tick, top))}
            for tick in ticks
        ],
    }


def top_movies(rows, selected_id=None):
    by_movie = {}
    for row in rows:
        movie = row["screening"].movie
        data = by_movie.setdefault(
            movie.pk,
            {
                "movie": movie,
                "sold": 0,
                "used": 0,
                "revenue": Decimal("0"),
                "screenings": 0,
            },
        )
        data["sold"] += row["sold"]
        data["used"] += row["used"]
        data["revenue"] += row["revenue"]
        data["screenings"] += 1

    ranking = sorted(
        (data for data in by_movie.values() if data["sold"]),
        key=lambda data: (-data["sold"], -data["revenue"], data["movie"].title),
    )
    selected = next((data for data in ranking if data["movie"].pk == selected_id), None)
    ranking = ranking[:TOP_MOVIES]
    if selected and selected not in ranking:
        ranking.append(selected)
    for data in ranking:
        data["width_css"] = css_percentage(percentage(data["sold"], ranking[0]["sold"]))
    return ranking


def occupancy_by_room(rows):
    by_room = {}
    for row in rows:
        room = row["screening"].room
        data = by_room.setdefault(
            room.pk, {"room": room, "sold": 0, "capacity": 0, "screenings": 0}
        )
        data["sold"] += row["sold"]
        data["capacity"] += row["capacity"]
        data["screenings"] += 1

    rooms = list(by_room.values())
    for data in rooms:
        data["occupancy"] = percentage(data["sold"], data["capacity"])
        data["width_css"] = css_percentage(data["occupancy"])
    return sorted(rooms, key=lambda data: (-data["occupancy"], data["room"].name))


def time_slot_label(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def filter_screenings(screenings, movie_id=None, room_id=None, date_range=None):
    if movie_id:
        screenings = screenings.filter(movie_id=movie_id)
    if room_id:
        screenings = screenings.filter(room_id=room_id)
    if date_range:
        screenings = screenings.filter(starts_at__gte=date_range[0], starts_at__lt=date_range[1])
    return screenings


def demand_by_purchase_time(start, end, movie_id=None, room_id=None, date_range=None):
    purchases = TicketPurchase.objects.filter(
        screening__status__in=PURCHASED_STATUSES,
        created_at__lt=end,
    )
    if start is not None:
        purchases = purchases.filter(created_at__gte=start)
    if movie_id or room_id or date_range:
        screenings = filter_screenings(Screening.objects.all(), movie_id, room_id, date_range)
        purchases = purchases.filter(screening__in=screenings.values("pk"))

    current_timezone = timezone.get_current_timezone()
    grouped_purchases = (
        purchases.annotate(
            weekday=ExtractWeekDay("created_at", tzinfo=current_timezone),
            hour=ExtractHour("created_at", tzinfo=current_timezone),
            minute=ExtractMinute("created_at", tzinfo=current_timezone),
        )
        .values("weekday", "hour", "minute")
        .annotate(tickets=Sum("quantity"), purchases=Count("pk"))
    )
    return purchase_time_slots(grouped_purchases)


def purchase_time_slots(grouped_purchases):
    slots = {}
    for purchase in grouped_purchases:
        day = (int(purchase["weekday"]) + 5) % 7
        hour = int(purchase["hour"])
        minute = (int(purchase["minute"]) // TIME_SLOT_MINUTES) * TIME_SLOT_MINUTES
        starts_at_minutes = hour * 60 + minute
        data = slots.setdefault(
            (day, starts_at_minutes),
            {
                "day": WEEKDAYS[day],
                "short_day": SHORT_WEEKDAYS[day],
                "hour": hour,
                "minute": minute,
                "label": time_slot_label(starts_at_minutes),
                "tickets": 0,
                "purchases": 0,
            },
        )
        data["tickets"] += purchase["tickets"] or 0
        data["purchases"] += purchase["purchases"] or 0

    if not slots:
        return None

    maximum = max(data["tickets"] for data in slots.values())
    for data in slots.values():
        intensity = 18 + 82 * data["tickets"] / maximum if data["tickets"] else 0
        data["intensity_css"] = css_percentage(intensity)

    time_blocks = range(
        min(minutes for _day, minutes in slots),
        max(minutes for _day, minutes in slots) + TIME_SLOT_MINUTES,
        TIME_SLOT_MINUTES,
    )
    label_interval = 2 if len(time_blocks) <= 16 else 4
    return {
        "time_blocks": [
            {
                "minutes": minutes,
                "label": time_slot_label(minutes),
                "show_label": index == 0 or (
                    index >= 2 and minutes % (TIME_SLOT_MINUTES * label_interval) == 0
                ),
            }
            for index, minutes in enumerate(time_blocks)
        ],
        "days": [
            {
                "day": WEEKDAYS[day],
                "short_day": SHORT_WEEKDAYS[day],
                "slots": [
                    slots.get(
                        (day, minutes),
                        {
                            "day": WEEKDAYS[day],
                            "label": time_slot_label(minutes),
                            "tickets": 0,
                            "purchases": 0,
                        },
                    )
                    for minutes in time_blocks
                ],
            }
            for day in range(7)
        ],
        "top": sorted(
            (data for data in slots.values() if data["tickets"]),
            key=lambda data: (-data["tickets"], -data["purchases"], data["day"], data["label"]),
        )[:TOP_TIME_SLOTS],
        "detail": [slots[key] for key in sorted(slots)],
        "total_tickets": sum(data["tickets"] for data in slots.values()),
        "total_purchases": sum(data["purchases"] for data in slots.values()),
    }


def decision_insights(summary, movies, time_slots):
    insights = []
    if movies:
        movie = movies[0]
        share = percentage(movie["sold"], summary["sold"])
        insights.append(
            {
                "icon": "clapperboard",
                "label": "Mayor tracción",
                "value": movie["movie"].title,
                "detail": f"{movie['sold']} entradas: {share:.0f}% de la venta del período.",
            }
        )
    if time_slots and time_slots["top"]:
        peak = time_slots["top"][0]
        insights.append(
            {
                "icon": "shopping-bag",
                "label": "Pico de compra",
                "value": f"{peak['day']} · {peak['label']}",
                "detail": f"{peak['tickets']} entradas en {peak['purchases']} compra(s).",
            }
        )
    if summary["sold"]:
        if summary["unused"]:
            label, value = "Entradas sin usar", str(summary["unused"])
            detail = (
                f"{summary['attendance']:.0f}% de asistencia registrada "
                "en funciones realizadas."
            )
        else:
            label, value = "Asistencia registrada", "100%"
            detail = "Todas las entradas vendidas del período registran ingreso."
        insights.append(
            {
                "icon": "scan-line",
                "label": label,
                "value": value,
                "detail": detail,
            }
        )
    return insights


def presale(now, movie_id=None, room_id=None, date_range=None):
    screenings = filter_screenings(Screening.objects.filter(
        status=Screening.Status.PUBLISHED,
        starts_at__gte=now,
    ), movie_id, room_id, date_range)
    sales = TicketPurchase.objects.filter(screening__in=screenings.values("pk")).aggregate(
        sold=Sum("quantity"),
        revenue=Sum("total"),
    )
    return {
        "screenings": screenings.count(),
        "sold": sales["sold"] or 0,
        "revenue": sales["revenue"] or Decimal("0"),
    }
