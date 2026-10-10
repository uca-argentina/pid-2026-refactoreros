import math
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

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
# Only published screenings can sell; finished screenings keep their sales.
SELLABLE_STATUSES = (Screening.Status.PUBLISHED, Screening.Status.FINISHED)
WEEKDAYS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
SHORT_WEEKDAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
TOP_MOVIES = 5
TOP_TIME_SLOTS = 3
X_AXIS_LABELS = 8


def build_dashboard(period=None, now=None):
    now = now or timezone.now()
    key, days = resolve_period(period)
    today = timezone.localdate(now)
    start = start_of_day(today - timedelta(days=days - 1)) if days else None

    rows = screening_rows(completed_screenings(start, now))
    summary = summarize(rows)
    previous = None
    if start is not None:
        start_previous = start_of_day(today - timedelta(days=days * 2 - 1))
        previous = summarize(screening_rows(completed_screenings(start_previous, start)))

    return {
        "periods": [
            {"key": value, "label": label, "active": value == key}
            for value, label, _days in PERIODS
        ],
        "period": key,
        "start": timezone.localdate(start) if start else first_date(rows),
        "end": today,
        "summary": summary,
        "deltas": build_deltas(summary, previous),
        "revenue": revenue_series(rows, start, today),
        "movies": top_movies(rows),
        "rooms": occupancy_by_room(rows),
        "time_slots": demand_by_time(rows),
        "presale": presale(now),
    }


def resolve_period(period):
    for value, _label, days in PERIODS:
        if value == period:
            return value, days
    return resolve_period(DEFAULT_PERIOD)


def start_of_day(date):
    return timezone.make_aware(datetime.combine(date, time.min))


def completed_screenings(start, end):
    screenings = Screening.objects.filter(
        status__in=SELLABLE_STATUSES,
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
    # Se formatea acá para que la localización de la plantilla no use coma decimal en el CSS.
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


def revenue_series(rows, start, today):
    if not rows:
        return None
    start = timezone.localdate(start) if start else first_date(rows)
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
                # On small screens, hide every other axis label.
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


def top_movies(rows):
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
    )[:TOP_MOVIES]
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


def demand_by_time(rows):
    if not rows:
        return None
    slots = {}
    for row in rows:
        day, hour = row["starts_at"].weekday(), row["starts_at"].hour
        data = slots.setdefault(
            (day, hour),
            {
                "day": WEEKDAYS[day],
                "short_day": SHORT_WEEKDAYS[day],
                "hour": hour,
                "sold": 0,
                "capacity": 0,
                "screenings": 0,
            },
        )
        data["sold"] += row["sold"]
        data["capacity"] += row["capacity"]
        data["screenings"] += 1

    maximum = max(data["sold"] for data in slots.values())
    for data in slots.values():
        data["occupancy"] = percentage(data["sold"], data["capacity"])
        # Las slots con sales arrancan en 18% para no confundirse con las vacías.
        intensity = 18 + 82 * data["sold"] / maximum if data["sold"] else 0
        data["intensity_css"] = css_percentage(intensity)

    hours = range(min(hour for _day, hour in slots), max(hour for _day, hour in slots) + 1)
    return {
        "hours": list(hours),
        "days": [
            {
                "day": WEEKDAYS[day],
                "short_day": SHORT_WEEKDAYS[day],
                "slots": [
                    slots.get(
                        (day, hour),
                        {"day": WEEKDAYS[day], "hour": hour, "screenings": 0},
                    )
                    for hour in hours
                ],
            }
            for day in range(7)
        ],
        "top": sorted(
            (data for data in slots.values() if data["sold"]),
            key=lambda data: (-data["sold"], -data["occupancy"]),
        )[:TOP_TIME_SLOTS],
        "detail": [slots[key] for key in sorted(slots)],
    }


def presale(now):
    screenings = Screening.objects.filter(
        status=Screening.Status.PUBLISHED,
        starts_at__gte=now,
    )
    sales = TicketPurchase.objects.filter(screening__in=screenings.values("pk")).aggregate(
        sold=Sum("quantity"),
        revenue=Sum("total"),
    )
    return {
        "screenings": screenings.count(),
        "sold": sales["sold"] or 0,
        "revenue": sales["revenue"] or Decimal("0"),
    }
