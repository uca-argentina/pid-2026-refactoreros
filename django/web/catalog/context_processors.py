from datetime import timedelta

from django.utils import timezone

from domain.screenings.models import Screening
from domain.tickets.models import PurchaseRefund, TicketPurchase
from domain.users.roles import staff_role


def client_navigation(request):
    has_imminent_admission = False
    unread_notifications = 0
    if request.user.is_authenticated:
        now = timezone.now()
        candidates = TicketPurchase.objects.filter(
            user=request.user,
            screening__status__in=(Screening.Status.PUBLISHED, Screening.Status.IN_PROGRESS),
            screening__starts_at__lte=now + timedelta(hours=2),
            refund__isnull=True,
        ).select_related("screening__movie").prefetch_related("tickets")
        has_imminent_admission = any(
            purchase.screening.ends_at > now
            and any(ticket.used_at is None for ticket in purchase.tickets.all())
            for purchase in candidates
        )
        unread_notifications = PurchaseRefund.objects.filter(
            purchase__user=request.user,
            read_at__isnull=True,
        ).count()
    context = {
        "manager_role": staff_role(request.user),
        "has_imminent_admission": has_imminent_admission,
        "unread_notifications": unread_notifications,
    }
    match = request.resolver_match
    if match:
        if match.app_name == "games":
            context["client_nav_section"] = "prizes"
        elif match.url_name in {"my_tickets", "ticket_detail", "candy_detail", "ticket_admission_status"}:
            context["client_nav_section"] = "tickets"
        elif match.url_name in {"home", "listing", "movie_detail", "screening_detail", "screening_page", "seat_selection", "ticket_purchase"} and not match.app_name:
            context["client_nav_section"] = "movies"
    if match and match.url_name in ("home", "listing") and not match.app_name:
        from domain.games.services import state, wheel_layout
        context["game_initial"] = state(request.user) if request.user.is_authenticated else {
            "spins": 0, "extra_attempts": 0, "daily_ready": False, "run": None,
            "next_daily_at": None, "layout": wheel_layout(),
        }
    return context
