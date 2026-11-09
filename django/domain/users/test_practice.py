from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from domain.candy.models import CandyOrder, CandyProduct
from domain.screenings.models import Screening
from domain.tickets.models import TicketPurchase


class PracticeSeedTests(TestCase):
    @override_settings(DEBUG=True)
    @patch(
        "urllib.request.urlopen",
        side_effect=AssertionError("El seed offline no debe usar internet"),
    )
    def test_seed_is_offline_and_preserves_existing_passwords_and_orders(self, network):
        call_command("seed_practice", stdout=StringIO())
        user = get_user_model().objects.get(username="cliente@local.test")
        user.set_password("UnaClaveCambiada123!")
        user.save(update_fields=["password"])
        counts = (
            Screening.objects.count(),
            TicketPurchase.objects.count(),
            CandyOrder.objects.count(),
        )
        stock = list(CandyProduct.objects.order_by("pk").values_list("pk", "stock"))
        call_command("seed_practice", stdout=StringIO())
        user.refresh_from_db()
        self.assertTrue(user.check_password("UnaClaveCambiada123!"))
        self.assertEqual(
            counts,
            (Screening.objects.count(), TicketPurchase.objects.count(), CandyOrder.objects.count()),
        )
        self.assertEqual(
            stock, list(CandyProduct.objects.order_by("pk").values_list("pk", "stock"))
        )
        network.assert_not_called()

    @override_settings(DEBUG=False)
    def test_practice_accounts_are_disabled_outside_development(self):
        with self.assertRaises(CommandError):
            call_command("seed_practice", stdout=StringIO())
