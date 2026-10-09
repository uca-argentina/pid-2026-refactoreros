from datetime import timedelta
from decimal import Decimal
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.cinema.models import CinemaSettings
from domain.movies.models import Movie
from domain.rooms.models import Room
from domain.screenings.models import Screening
from domain.seats.models import Seat
from domain.seat_types.models import SeatType
from domain.tickets.models import SeatPurchase, TicketPurchase, SeatReservation


def crear_sala_con_butacas(name, capacity):
    room = Room.objects.create(name=name)
    seat_type = SeatType.objects.order_by("pk").first()
    Seat.objects.bulk_create(
        Seat(room=room, row=index // 20, column=index % 20, seat_type=seat_type)
        for index in range(capacity)
    )
    return room


def crear_funcion(status=Screening.Status.PUBLISHED, title="Pelicula", capacity=100):
    movie = Movie.objects.create(
        title=title,
        synopsis="Una pelicula de prueba.",
        genre=Movie.Genre.ACCION,
        rating=Movie.Rating.MAS_13,
        duration_minutes=120,
        image="peliculas/test.jpg",
    )
    room = crear_sala_con_butacas(f"Sala {title}", capacity)
    return Screening.objects.create(
        movie=movie,
        room=room,
        starts_at=timezone.now(),
        ticket_price="1500.00",
        status=status,
    )


def crear_funcion_con_butacas(title="Con butacas"):
    movie = Movie.objects.create(
        title=title,
        synopsis="Una pelicula de prueba.",
        genre=Movie.Genre.ACCION,
        rating=Movie.Rating.MAS_13,
        duration_minutes=120,
        image="peliculas/test.jpg",
    )
    room = Room.objects.create(name=f"Sala {title}")
    seat_type = SeatType.objects.get(name="Estándar")
    Seat.objects.create(room=room, row=0, column=0, seat_type=seat_type)
    Seat.objects.create(room=room, row=0, column=1, seat_type=seat_type)
    return Screening.objects.create(
        movie=movie,
        room=room,
        starts_at=timezone.now(),
        ticket_price="1500.00",
        status=Screening.Status.PUBLISHED,
    )


class TicketPurchaseTests(TestCase):
    def test_compra_no_permite_funcion_oculta(self):
        screening = crear_funcion(status=Screening.Status.DRAFT, title="Oculta")
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.post(reverse("ticket_purchase", args=[screening.pk]), data={})

        self.assertEqual(response.status_code, 404)

    def test_modelo_compra_legacy_por_cantidad_guarda_total(self):
        screening = crear_funcion(status=Screening.Status.PUBLISHED, title="Publicada")
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )

        purchase = TicketPurchase.buy(user, screening, 3)

        self.assertEqual(purchase.user, user)
        self.assertEqual(purchase.screening, screening)
        self.assertEqual(purchase.quantity, 3)
        self.assertEqual(purchase.total, Decimal("3000.00"))

    def test_compra_web_con_butaca_muestra_mensaje_singular(self):
        screening = crear_funcion_con_butacas(title="Publicada")
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        SeatReservation.reserve(user, screening, "1A")
        self.client.force_login(user)

        response = self.client.post(
            reverse("ticket_purchase", args=[screening.pk]),
            data={"selected_seats": json.dumps([{"label": "1A"}])},
            follow=True,
        )

        self.assertContains(
            response,
            "Pago aprobado. Compraste 1 entrada para Publicada. ¡Te esperamos!",
        )

    def test_compra_web_rechaza_confirmacion_sin_butacas(self):
        screening = crear_funcion_con_butacas()
        user = get_user_model().objects.create_user(
            username="sinbutaca@mail.com",
            email="sinbutaca@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("ticket_purchase", args=[screening.pk]),
            data={},
            follow=True,
        )

        self.assertRedirects(response, reverse("seat_selection", args=[screening.pk]))
        self.assertContains(response, "Seleccioná al menos una butaca.")
        self.assertFalse(TicketPurchase.objects.exists())

    def test_compra_con_butacas_guarda_seleccion_y_bloquea_repetidas(self):
        screening = crear_funcion_con_butacas()
        user = get_user_model().objects.create_user(
            username="ana2@mail.com",
            email="ana2@mail.com",
            password="PasswordSegura123!",
        )

        purchase = TicketPurchase.buy(
            user,
            screening,
            1,
            selected_seats=[{"label": "1A"}],
        )

        self.assertEqual(purchase.quantity, 1)
        self.assertEqual(purchase.selected_seats[0]["label"], "1A")
        self.assertIn("1A", TicketPurchase.occupied_seats(screening))
        with self.assertRaises(ValidationError):
            TicketPurchase.buy(
                user,
                screening,
                1,
                selected_seats=[{"label": "1A"}],
            )

    def test_modelo_compra_legacy_falla_si_supera_disponibilidad(self):
        screening = crear_funcion(status=Screening.Status.PUBLISHED, title="Publicada", capacity=2)
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )

        with self.assertRaises(ValidationError):
            TicketPurchase.buy(user, screening, 3)

        self.assertFalse(TicketPurchase.objects.exists())

    def test_mis_entradas_muestra_compras_del_usuario(self):
        screening = crear_funcion(status=Screening.Status.PUBLISHED, title="Publicada")
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        otro_usuario = get_user_model().objects.create_user(
            username="otro@mail.com",
            email="otro@mail.com",
            password="PasswordSegura123!",
        )
        purchase = TicketPurchase.buy(user, screening, 2)
        purchase.selected_seats = [{"label": "1A"}, {"label": "1B"}]
        purchase.save(update_fields=["selected_seats"])
        TicketPurchase.buy(otro_usuario, screening, 1)
        self.client.force_login(user)

        response = self.client.get(reverse("my_tickets"))

        self.assertContains(response, "Publicada")
        self.assertContains(response, "2")
        self.assertContains(response, "1A, 1B")
        self.assertNotContains(response, "otro@mail.com")

    def test_compra_no_permite_funcion_cancelada(self):
        screening = crear_funcion(status=Screening.Status.CANCELED, title="Cancelada")
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.post(reverse("ticket_purchase", args=[screening.pk]), data={})

        self.assertEqual(response.status_code, 404)
        self.assertFalse(TicketPurchase.objects.exists())

    def test_compra_no_permite_funcion_que_ya_termino(self):
        screening = crear_funcion(title="Terminada")
        Screening.objects.filter(pk=screening.pk).update(
            starts_at=timezone.now() - timedelta(hours=3)
        )
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.post(reverse("ticket_purchase", args=[screening.pk]), data={})

        self.assertEqual(response.status_code, 404)
        screening.refresh_from_db()
        self.assertEqual(screening.status, Screening.Status.FINISHED)

    def test_modelo_no_permite_comprar_funcion_no_publicada(self):
        screening = crear_funcion(status=Screening.Status.SCHEDULED, title="Programada")
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )

        with self.assertRaises(ValidationError):
            TicketPurchase.buy(user, screening, 1)

    def test_mis_entradas_marca_funcion_cancelada(self):
        screening = crear_funcion(title="Cancelada luego")
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        TicketPurchase.buy(user, screening, 2)
        screening.change_status(Screening.Status.CANCELED)
        self.client.force_login(user)

        response = self.client.get(reverse("my_tickets"))

        self.assertContains(response, "Función cancelada")
        self.assertContains(response, "is-cancelled")

    def test_reserva_bloquea_butaca_para_otro_usuario(self):
        screening = crear_funcion_con_butacas()
        user = get_user_model().objects.create_user(
            username="ana3@mail.com",
            email="ana3@mail.com",
            password="PasswordSegura123!",
        )
        otro_usuario = get_user_model().objects.create_user(
            username="otro3@mail.com",
            email="otro3@mail.com",
            password="PasswordSegura123!",
        )

        reserva = SeatReservation.reserve(user, screening, "1A")

        self.assertEqual(reserva.label, "1A")
        self.assertIn("1A", TicketPurchase.blocked_seats(screening, user=otro_usuario))
        self.assertNotIn("1A", TicketPurchase.blocked_seats(screening, user=user))
        with self.assertRaises(ValidationError):
            SeatReservation.reserve(otro_usuario, screening, "1A")

    def test_selector_usa_intervalo_de_recarga_configurado(self):
        CinemaSettings.objects.create(seat_refresh_seconds=11)
        screening = crear_funcion_con_butacas()
        user = get_user_model().objects.create_user(
            username="ana9@mail.com",
            email="ana9@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("seat_selection", args=[screening.pk]))

        self.assertContains(response, 'data-refresh-interval-seconds="11"')
        self.assertContains(response, 'data-reservation-batch-delay-ms="1000"')

    def test_compra_web_requiere_reserva_vigente_de_butaca(self):
        screening = crear_funcion_con_butacas()
        user = get_user_model().objects.create_user(
            username="ana4@mail.com",
            email="ana4@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("ticket_purchase", args=[screening.pk]),
            data={"selected_seats": json.dumps([{"label": "1A"}])},
            follow=True,
        )

        self.assertRedirects(response, reverse("seat_selection", args=[screening.pk]))
        self.assertContains(response, "Algunas butacas ya no estan reservadas")
        self.assertFalse(TicketPurchase.objects.exists())

    def test_compra_web_confirma_reserva_y_crea_asiento_vendido_unico(self):
        screening = crear_funcion_con_butacas()
        user = get_user_model().objects.create_user(
            username="ana5@mail.com",
            email="ana5@mail.com",
            password="PasswordSegura123!",
        )
        SeatReservation.reserve(user, screening, "1A")
        self.client.force_login(user)

        response = self.client.post(
            reverse("ticket_purchase", args=[screening.pk]),
            data={"selected_seats": json.dumps([{"label": "1A"}])},
            follow=True,
        )

        self.assertRedirects(response, reverse("my_tickets"))
        self.assertTrue(SeatPurchase.objects.filter(screening=screening, label="1A").exists())
        self.assertFalse(SeatReservation.objects.filter(screening=screening, label="1A").exists())
        with self.assertRaises(ValidationError):
            TicketPurchase.buy(
                user,
                screening,
                1,
                selected_seats=[{"label": "1A"}],
            )

    def test_reserva_ajax_devuelve_conflicto_si_butaca_esta_reservada(self):
        screening = crear_funcion_con_butacas()
        user = get_user_model().objects.create_user(
            username="ana6@mail.com",
            email="ana6@mail.com",
            password="PasswordSegura123!",
        )
        otro_usuario = get_user_model().objects.create_user(
            username="otro6@mail.com",
            email="otro6@mail.com",
            password="PasswordSegura123!",
        )
        SeatReservation.reserve(otro_usuario, screening, "1A")
        self.client.force_login(user)

        response = self.client.post(
            reverse("seat_reservation", args=[screening.pk]),
            data=json.dumps({"action": "reserve", "label": "1A"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["ok"])
        self.assertIn("1A", response.json()["unavailable"])

    def test_reserva_batch_reserva_y_libera_butacas(self):
        screening = crear_funcion_con_butacas()
        user = get_user_model().objects.create_user(
            username="batch@mail.com",
            email="batch@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("seat_reservation_batch", args=[screening.pk]),
            data=json.dumps(
                {
                    "operations": [
                        {"action": "reserve", "label": "1A"},
                        {"action": "reserve", "label": "1B"},
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(
            set(SeatReservation.objects.filter(screening=screening).values_list("label", flat=True)),
            {"1A", "1B"},
        )

        response = self.client.post(
            reverse("seat_reservation_batch", args=[screening.pk]),
            data=json.dumps({"operations": [{"action": "release", "label": "1A"}]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SeatReservation.objects.filter(screening=screening, label="1A").exists())
        self.assertTrue(SeatReservation.objects.filter(screening=screening, label="1B").exists())

    def test_reserva_batch_devuelve_conflictos(self):
        screening = crear_funcion_con_butacas()
        user = get_user_model().objects.create_user(
            username="batch-conflict@mail.com",
            email="batch-conflict@mail.com",
            password="PasswordSegura123!",
        )
        otro_usuario = get_user_model().objects.create_user(
            username="otro-batch@mail.com",
            email="otro-batch@mail.com",
            password="PasswordSegura123!",
        )
        SeatReservation.reserve(otro_usuario, screening, "1A")
        self.client.force_login(user)

        response = self.client.post(
            reverse("seat_reservation_batch", args=[screening.pk]),
            data=json.dumps({"operations": [{"action": "reserve", "label": "1A"}]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(response.json()["errors"][0]["label"], "1A")
        self.assertIn("1A", response.json()["unavailable"])

    def test_reserva_expirada_no_bloquea_butaca_abandonada(self):
        screening = crear_funcion_con_butacas()
        user = get_user_model().objects.create_user(
            username="ana8@mail.com",
            email="ana8@mail.com",
            password="PasswordSegura123!",
        )
        otro_usuario = get_user_model().objects.create_user(
            username="otro8@mail.com",
            email="otro8@mail.com",
            password="PasswordSegura123!",
        )
        SeatReservation.objects.create(
            user=user,
            screening=screening,
            label="1A",
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        self.assertNotIn("1A", TicketPurchase.blocked_seats(screening, user=otro_usuario))
        reserva = SeatReservation.reserve(otro_usuario, screening, "1A")

        self.assertEqual(reserva.user, otro_usuario)
        self.assertGreater(reserva.expires_at, timezone.now())

    def test_sincronizar_asientos_vendidos_legacy_es_idempotente(self):
        screening = crear_funcion_con_butacas()
        user = get_user_model().objects.create_user(
            username="ana7@mail.com",
            email="ana7@mail.com",
            password="PasswordSegura123!",
        )
        TicketPurchase.buy(user, screening, 1)

        TicketPurchase.sync_sold_seats(screening)
        TicketPurchase.sync_sold_seats(screening)

        self.assertEqual(SeatPurchase.objects.filter(screening=screening).count(), 1)
