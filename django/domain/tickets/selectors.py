"""Lecturas de disponibilidad. Estas funciones no modifican la base de datos."""

from django.db.models import Sum


def sold_quantity(screening):
    from .models import TicketPurchase

    return (
        TicketPurchase.objects.filter(screening=screening).aggregate(total=Sum("quantity"))["total"]
        or 0
    )


def occupied_seats(screening):
    """Incluye ventas históricas aún no reparadas, sin escribir al consultarlas."""
    from domain.rooms.layout import seat_labels
    from .models import SeatPurchase, TicketPurchase

    sold = list(
        SeatPurchase.objects.filter(screening=screening).values_list("purchase_id", "label")
    )
    occupied = {label for _, label in sold}
    assigned = {}
    for purchase_id, label in sold:
        assigned.setdefault(purchase_id, set()).add(label)
    unassigned = 0
    for purchase in TicketPurchase.objects.filter(screening=screening).only(
        "selected_seats", "quantity"
    ):
        labels = TicketPurchase._labels_from_selected_seats(purchase.selected_seats)
        occupied.update(labels)
        unassigned += max(
            purchase.quantity - len(set(labels) | assigned.get(purchase.pk, set())), 0
        )
    for label in seat_labels(screening.room_layout_snapshot):
        if not unassigned:
            break
        if label not in occupied:
            occupied.add(label)
            unassigned -= 1
    return occupied
