"""Dashboard: filters."""

from datetime import datetime, time
from urllib.parse import urlencode

from django.utils import timezone
from django.utils.formats import date_format

from .constants import DEFAULT_PERIOD, PERIODS


def filter_rows(rows, movie_id=None, room_id=None, date_range=None):
    return [
        row
        for row in rows
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
    if dashboard["view"] == "candy":
        params["view"] = "candy"
    dashboard["clear_filters_url"] = "?" + urlencode(params)
    selected = {
        "movie": str(dashboard["selected_movie"].pk) if dashboard["selected_movie"] else None,
        "room": str(dashboard["selected_room"].pk) if dashboard["selected_room"] else None,
        "revenue_date": dashboard["selected_revenue_date"].isoformat()
        if dashboard["selected_revenue_date"]
        else None,
    }
    params.update({key: value for key, value in selected.items() if value})
    dashboard["views"] = [
        {
            "key": key,
            "label": label,
            "icon": icon,
            "url": "?" + urlencode({**params, "view": key}),
            "active": dashboard["view"] == key,
        }
        for key, label, icon in (
            ("movies", "Películas", "clapperboard"),
            ("candy", "Candy", "popcorn"),
        )
    ]

    def link(key, value):
        updated = dict(params)
        if value is None or selected.get(key) == str(value):
            updated.pop(key, None)
        else:
            updated[key] = str(value)
        return "?" + urlencode(updated)

    for period in dashboard["periods"]:
        period["url"] = "?" + urlencode(
            {
                "period": period["key"],
                **({"view": "candy"} if dashboard["view"] == "candy" else {}),
                **{key: selected[key] for key in ("movie", "room") if selected[key]},
            }
        )
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
            dashboard["active_filters"].append(
                {
                    "key": key,
                    "label": label,
                    "value": text,
                    "icon": icon,
                    "remove_url": link(key, None),
                }
            )


def resolve_period(period):
    for value, _label, days in PERIODS:
        if value == period:
            return value, days
    return resolve_period(DEFAULT_PERIOD)


def start_of_day(date):
    return timezone.make_aware(datetime.combine(date, time.min))
