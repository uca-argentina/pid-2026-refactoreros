"""Escenarios locales para recorrer el sistema y practicar hotfixes."""

from datetime import timedelta
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from domain.candy.models import CandyProduct
from domain.candy.services import buy_candy_only, buy_tickets_with_candy
from domain.promotions.models import Promotion
from domain.screenings.models import Screening
from domain.tickets.models import SeatReservation, TicketPurchase
from domain.users.models import Customer, Manager, Operator

PRACTICE_PASSWORD = "PracticaLocal2026!"
PRACTICE_ACCOUNTS = (
    ("gerente@local.test", Manager),
    ("operador@local.test", Operator),
    ("cliente@local.test", Customer),
)


class Command(BaseCommand):
    help = "Crea datos offline y tres cuentas de práctica; solo con DJANGO_DEBUG=True."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("El seed de práctica solo está habilitado en desarrollo local.")
        call_command("seed_demo", offline=True, days=7, stdout=self.stdout)
        with transaction.atomic():
            users = {}
            for email, profile in PRACTICE_ACCOUNTS:
                user, created = get_user_model().objects.get_or_create(
                    username=email,
                    defaults={"email": email, "first_name": profile._meta.verbose_name},
                )
                if created:
                    user.set_password(PRACTICE_PASSWORD)
                    user.save(update_fields=["password"])
                    profile.objects.create(user=user)
                elif not profile.objects.filter(user=user).exists():
                    self.stdout.write(
                        self.style.WARNING(f"Se conserva sin cambios la cuenta existente {email}.")
                    )
                    continue
                users[email] = user
                self.stdout.write(
                    f"{email}: {'creada' if created else 'conservada (contraseña sin cambios)'}"
                )
            Promotion.objects.get_or_create(
                name="Práctica: 10%",
                defaults={
                    "discount_type": Promotion.DiscountType.PERCENTAGE,
                    "discount_value": 10,
                },
            )
            customer = users.get("cliente@local.test")
            if customer:
                self.seed_purchases(customer)
        self.stdout.write(
            self.style.SUCCESS(
                f"Listo. Contraseña de cuentas NUEVAS: {PRACTICE_PASSWORD}. Las existentes no se modifican."
            )
        )

    def seed_purchases(self, customer):
        product = CandyProduct.objects.filter(is_active=True, stock__gte=2).first()
        if not product:
            return
        items = [{"kind": "product", "id": product.pk, "quantity": 1}]
        screening = (
            Screening.published().filter(starts_at__gt=timezone.now() + timedelta(hours=3)).first()
        )
        if screening and not TicketPurchase.objects.filter(user=customer).exists():
            label = next(iter(TicketPurchase.seat_prices(screening)), None)
            if label and label not in TicketPurchase.blocked_seats(screening):
                SeatReservation.reserve(customer, screening, label)
                buy_tickets_with_candy(customer, screening, [label], items)
        key = uuid.uuid5(uuid.NAMESPACE_URL, "butacacero/local-practice/candy")
        from domain.candy.models import CandyOrder

        if not CandyOrder.objects.filter(customer=customer, checkout_key=key).exists():
            buy_candy_only(customer, items, key)
