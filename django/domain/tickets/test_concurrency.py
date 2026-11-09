from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from domain.seat_types.models import SeatType
from domain.tickets.models import SeatPurchase, SeatReservation, TicketPurchase
from web.tickets.tests import crear_funcion_con_butacas


class SeatConcurrencyTests(TransactionTestCase):
    def test_two_customers_competing_for_the_same_seat_produce_one_purchase(self):
        if connection.vendor != "postgresql":
            self.skipTest("Los bloqueos de fila se verifican con PostgreSQL.")
        SeatType.objects.get_or_create(
            name="Estándar", defaults={"base_price": 1000, "color": "#123456"}
        )
        screening = crear_funcion_con_butacas()
        users = [
            get_user_model().objects.create_user(username=f"race-{index}") for index in range(2)
        ]
        barrier = Barrier(2)

        def checkout(user):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                SeatReservation.reserve(user, screening, "1A")
                TicketPurchase.buy(
                    user, screening, 1, selected_seats=["1A"], require_reservation=True
                )
                return "purchased"
            except ValidationError:
                return "unavailable"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(checkout, users))
        self.assertCountEqual(results, ["purchased", "unavailable"])
        self.assertEqual(TicketPurchase.objects.filter(screening=screening).count(), 1)
        self.assertEqual(SeatPurchase.objects.filter(screening=screening, label="1A").count(), 1)
