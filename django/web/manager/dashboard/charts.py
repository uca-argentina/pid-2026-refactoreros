"""Dashboard: charts."""

import math
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .constants import SHORT_WEEKDAYS, TIME_SLOT_MINUTES, TOP_TIME_SLOTS, WEEKDAYS, X_AXIS_LABELS
from .numbers import css_percentage, percentage


def first_date(rows):
    return rows[0]["starts_at"].date() if rows else None


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
        key: {
            "revenue": Decimal("0"),
            "ticket_revenue": Decimal("0"),
            "candy_revenue": Decimal("0"),
            "sold": 0,
            "screenings": 0,
        }
        for key in keys
    }
    for row in rows:
        data = accumulated[grouping_key(row["starts_at"].date(), granularity)]
        data["revenue"] += row["revenue"]
        data["ticket_revenue"] += row.get("ticket_revenue", row["revenue"])
        data["candy_revenue"] += row.get("candy_revenue", Decimal("0"))
        data["sold"] += row["sold"]
        data["screenings"] += row.get("screening") is not None

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
            {"value": tick, "position_css": css_percentage(percentage(tick, top))} for tick in ticks
        ],
    }


def time_slot_label(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


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
                "show_label": index == 0
                or (index >= 2 and minutes % (TIME_SLOT_MINUTES * label_interval) == 0),
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
