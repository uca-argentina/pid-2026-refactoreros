"""Dashboard: metrics."""

from decimal import Decimal

from django.db.models import Sum

from .constants import TOP_MOVIES
from .numbers import css_percentage, percentage


def add_standalone_revenue(summary, orders):
    amount = orders.aggregate(total=Sum("total"))["total"] or Decimal("0")
    summary["standalone_candy_revenue"] = amount
    summary["revenue"] += amount
    summary["candy_revenue"] += amount


def summarize(rows):
    sold = sum(row["sold"] for row in rows)
    used = sum(row["used"] for row in rows)
    capacity = sum(row["capacity"] for row in rows)
    revenue = sum((row["revenue"] for row in rows), Decimal("0"))
    ticket_revenue = sum((row.get("ticket_revenue", row["revenue"]) for row in rows), Decimal("0"))
    candy_revenue = sum((row.get("candy_revenue", Decimal("0")) for row in rows), Decimal("0"))
    return {
        "screenings": len(rows),
        "sold": sold,
        "used": used,
        "unused": sold - used,
        "capacity": capacity,
        "revenue": revenue,
        "ticket_revenue": ticket_revenue,
        "candy_revenue": candy_revenue,
        "average_ticket": ticket_revenue / sold if sold else Decimal("0"),
        "occupancy": percentage(sold, capacity),
        "attendance": percentage(used, sold),
        "attendance_css": css_percentage(percentage(used, sold)),
    }


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
        "revenue": variation(percentage_delta(summary["revenue"], previous["revenue"]), "%"),
        "sold": variation(percentage_delta(summary["sold"], previous["sold"]), "%"),
        "occupancy": variation(occupancy, " p. p."),
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
                f"{summary['attendance']:.0f}% de asistencia registrada en funciones realizadas."
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
