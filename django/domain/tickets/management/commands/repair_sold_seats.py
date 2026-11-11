"""Reparación explícita e idempotente de ventas anteriores al modelo de butacas."""

from django.core.management.base import BaseCommand
from django.db import transaction

from domain.screenings.models import Screening
from domain.tickets.models import TicketPurchase


class Command(BaseCommand):
    help = "Reconstruye asientos vendidos históricos sin eliminar compras ni reservas."

    def handle(self, *args, **options):
        count = 0
        for pk in Screening.objects.filter(ticket_purchases__isnull=False).values_list("pk", flat=True).distinct():
            with transaction.atomic():
                screening = Screening.objects.select_for_update().get(pk=pk)
                TicketPurchase.sync_sold_seats(screening)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Funciones revisadas: {count}"))
