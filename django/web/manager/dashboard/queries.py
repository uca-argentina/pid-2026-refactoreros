"""Dashboard: queries."""

from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import ExtractHour, ExtractMinute, ExtractWeekDay
from django.utils import timezone
from domain.candy.models import CandyOrder
from domain.screenings.models import Screening
from domain.seats.models import Seat
from domain.tickets.models import SeatPurchase, TicketPurchase

from .charts import purchase_time_slots
from .constants import ACCOUNTED_STATUSES, PURCHASED_STATUSES
from .numbers import css_percentage, percentage


def standalone_candy_orders(start, end, movie_id=None, room_id=None, date_range=None):
    orders = CandyOrder.objects.filter(
        customer__isnull=False, restocked_at__isnull=True, created_at__lt=end
    )
    if movie_id or room_id:
        return orders.none()
    if start:
        orders = orders.filter(created_at__gte=start)
    if date_range:
        orders = orders.filter(created_at__gte=date_range[0], created_at__lt=date_range[1])
    return orders


def candy_metrics(rows, standalone=None):
    scope = Q(purchase__screening_id__in=[row["screening"].pk for row in rows])
    if standalone is not None:
        scope |= Q(pk__in=standalone.values("pk"))
    orders = CandyOrder.objects.filter(scope, restocked_at__isnull=True)
    ranking = {}
    total = Decimal("0")
    count = delivered = units = 0
    by_screening = {}
    for order in (
        orders.only("items", "total", "delivered_at", "purchase__screening_id")
        .select_related("purchase")
        .iterator()
    ):
        count += 1
        total += order.total
        delivered += order.delivered_at is not None
        if order.purchase_id:
            screening_id = order.purchase.screening_id
            by_screening[screening_id] = by_screening.get(screening_id, 0) + 1
        for line in order.items:
            quantity = line["quantity"]
            units += quantity
            item = ranking.setdefault(
                (line["kind"], line["id"]),
                {"name": line["name"], "kind": line["kind"], "units": 0, "revenue": Decimal("0")},
            )
            item["units"] += quantity
            item["revenue"] += Decimal(line["subtotal"])
    items = sorted(
        ranking.values(), key=lambda item: (-item["revenue"], -item["units"], item["name"])
    )
    maximum = max((item["revenue"] for item in items), default=Decimal("0"))
    for item in items:
        item["width_css"] = css_percentage(percentage(item["revenue"], maximum))
    return {
        "revenue": total,
        "orders": count,
        "units": units,
        "delivered": delivered,
        "pending": count - delivered,
        "average_order": total / count if count else Decimal("0"),
        "items": items,
        "orders_by_screening": by_screening,
    }


def selected_object(model, value):
    try:
        value = int(value)
    except (ValueError, TypeError):
        return None
    if not 0 < value <= 9223372036854775807:
        return None
    return model.objects.filter(pk=value).first()


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
    candy_sales = dict(
        CandyOrder.objects.filter(purchase__screening__in=ids, restocked_at__isnull=True)
        .order_by()
        .values("purchase__screening_id")
        .annotate(revenue=Sum("total"))
        .values_list("purchase__screening_id", "revenue")
    )
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
                "ticket_revenue": sale.get("revenue") or Decimal("0"),
                "candy_revenue": candy_sales.get(screening.pk) or Decimal("0"),
                "revenue": (sale.get("revenue") or Decimal("0"))
                + (candy_sales.get(screening.pk) or Decimal("0")),
                "used": min(used.get(screening.pk, 0), sold),
                "capacity": screening.capacity_snapshot or capacities.get(screening.room_id, 0),
            }
        )
    return rows


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


def presale(now, movie_id=None, room_id=None, date_range=None):
    screenings = filter_screenings(
        Screening.objects.filter(
            status=Screening.Status.PUBLISHED,
            starts_at__gte=now,
        ),
        movie_id,
        room_id,
        date_range,
    )
    sales = TicketPurchase.objects.filter(screening__in=screenings.values("pk")).aggregate(
        sold=Sum("quantity"),
        revenue=Sum("total"),
    )
    candy = CandyOrder.objects.filter(
        purchase__screening__in=screenings.values("pk"), restocked_at__isnull=True
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")
    return {
        "screenings": screenings.count(),
        "sold": sales["sold"] or 0,
        "ticket_revenue": sales["revenue"] or Decimal("0"),
        "candy_revenue": candy,
        "revenue": (sales["revenue"] or Decimal("0")) + candy,
    }
