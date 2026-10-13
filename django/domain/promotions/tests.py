from datetime import datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from domain.movies.models import Movie
from domain.rooms.models import Room
from domain.screenings.models import Screening
from domain.seats.models import Seat
from domain.seat_types.models import SeatType
from domain.tickets.models import TicketPurchase

from .models import Promotion


class PromotionPricingTests(TestCase):
    def setUp(self):
        self.seat_type = SeatType.objects.order_by("pk").first()
        self.room = Room.objects.create(name="Sala promociones")
        Seat.objects.create(room=self.room, row=0, column=0, seat_type=self.seat_type)
        self.movie = Movie.objects.create(
            title="Promociones",
            synopsis="Película de prueba.",
            genre=Movie.Genre.ACCION,
            rating=Movie.Rating.MAS_13,
            duration_minutes=100,
            image="peliculas/test.jpg",
        )
        self.screening = Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=timezone.make_aware(datetime(2030, 1, 7, 18, 30)),
            ticket_price="1000.00",
            status=Screening.Status.PUBLISHED,
        )
        self.customer = get_user_model().objects.create_user(
            username="promo@example.com",
            email="promo@example.com",
            password="PasswordSegura123!",
        )

    def create_promotion(self, **overrides):
        values = {
            "name": "Lunes tarde",
            "discount_type": Promotion.DiscountType.PERCENTAGE,
            "discount_value": Decimal("20.00"),
            "weekdays": [Promotion.Weekday.MONDAY],
            "starts_at": time(18, 0),
            "ends_at": time(20, 0),
        }
        values.update(overrides)
        promotion = Promotion.objects.create(**values)
        promotion.seat_types.add(self.seat_type)
        return promotion

    def test_applies_discount_only_when_day_time_and_seat_type_match(self):
        promotion = self.create_promotion()

        quote = TicketPurchase.seat_price_quotes(self.screening)["1A"]

        self.assertEqual(quote.base_price, Decimal("1000.00"))
        self.assertEqual(quote.final_price, Decimal("800.00"))
        self.assertEqual(quote.promotion, promotion)

    def test_uses_the_best_promotion_without_stacking_discounts(self):
        self.create_promotion(name="20 por ciento")
        best = self.create_promotion(
            name="Descuento fijo",
            discount_type=Promotion.DiscountType.FIXED,
            discount_value=Decimal("300.00"),
        )

        quote = TicketPurchase.seat_price_quotes(self.screening)["1A"]

        self.assertEqual(quote.final_price, Decimal("700.00"))
        self.assertEqual(quote.promotion, best)

    def test_does_not_apply_the_promotion_outside_its_scheduled_day(self):
        self.create_promotion()
        Screening.objects.filter(pk=self.screening.pk).update(
            starts_at=timezone.make_aware(datetime(2030, 1, 8, 18, 30))
        )
        self.screening.refresh_from_db()

        quote = TicketPurchase.seat_price_quotes(self.screening)["1A"]

        self.assertEqual(quote.final_price, Decimal("1000.00"))
        self.assertIsNone(quote.promotion)

    def test_purchase_persists_the_price_and_promotion_snapshot(self):
        promotion = self.create_promotion()

        purchase = TicketPurchase.buy(
            self.customer,
            self.screening,
            1,
            selected_seats=[{"label": "1A"}],
        )

        self.assertEqual(purchase.total, Decimal("800.00"))
        self.assertEqual(purchase.selected_seats, [
            {
                "label": "1A",
                "price": "800.00",
                "base_price": "1000.00",
                "discount": "200.00",
                "promotion": promotion.name,
            }
        ])
