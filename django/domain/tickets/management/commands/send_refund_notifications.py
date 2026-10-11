from django.core.management.base import BaseCommand
from domain.tickets.services import send_refund_notifications


class Command(BaseCommand):
    help = "Reintenta los correos pendientes de cancelación y devolución simulada."

    def handle(self, *args, **options):
        sent = send_refund_notifications()
        self.stdout.write(self.style.SUCCESS(f"Avisos enviados: {sent}"))
