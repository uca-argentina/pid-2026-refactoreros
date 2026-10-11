from datetime import timedelta

from django.utils import timezone

from domain.screenings.models import Screening
from domain.tickets.models import TicketPurchase
from domain.users.roles import staff_role


def client_navigation(request):
    """Shared state used by the public-site header on every client page."""
    has_imminent_admission = False
    if request.user.is_authenticated:
        now = timezone.now()
        candidates = TicketPurchase.objects.filter(
            user=request.user,
            screening__status=Screening.Status.PUBLISHED,
            screening__starts_at__lte=now + timedelta(hours=2),
            refund__isnull=True,
        ).select_related("screening__movie").prefetch_related("tickets")
        has_imminent_admission = any(
            purchase.screening.ends_at > now
            and any(ticket.used_at is None for ticket in purchase.tickets.all())
            for purchase in candidates
        )
    return {
        "manager_role": staff_role(request.user),
        "has_imminent_admission": has_imminent_admission,
    }
