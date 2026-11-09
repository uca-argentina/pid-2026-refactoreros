from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from domain.movies.models import Movie
from domain.rooms.models import Room
from domain.tickets.models import TicketPurchase
from domain.users.models import Manager
from web.tickets.tests import crear_funcion_con_butacas


class ManagementRegressionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="manager-regressions")
        Manager.objects.create(user=self.user)
        self.client.force_login(self.user)
        self.screening = crear_funcion_con_butacas()
        self.purchase = TicketPurchase.buy(self.user, self.screening, 1, selected_seats=["1A"])

    def test_impossible_date_renders_validation_instead_of_500(self):
        for field in ("date_from", "date_to"):
            response = self.client.get(reverse("manager:dashboard"), {field: "2026-02-30"})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["date_filter_error"])

    def test_room_and_movie_deletion_preserve_commercial_history(self):
        for route, obj in (
            ("manager:salas_delete", self.screening.room),
            ("manager:peliculas_delete", self.screening.movie),
        ):
            with self.subTest(route=route):
                response = self.client.post(reverse(route, args=[obj.pk]), follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(TicketPurchase.objects.filter(pk=self.purchase.pk).exists())
                self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())
                with self.assertRaises(ProtectedError):
                    obj.delete()

    def test_unused_room_can_still_be_deleted(self):
        room = Room.objects.create(name="Sin funciones")
        self.client.post(reverse("manager:salas_delete", args=[room.pk]))
        self.assertFalse(Room.objects.filter(pk=room.pk).exists())

    def test_screening_with_sales_is_protected_outside_the_management_view(self):
        with self.assertRaises(ProtectedError):
            self.screening.delete()
        self.assertTrue(TicketPurchase.objects.filter(pk=self.purchase.pk).exists())

    def test_unused_movie_can_still_be_deleted(self):
        movie = Movie.objects.create(title="Sin funciones", duration_minutes=90)
        self.client.post(reverse("manager:peliculas_delete", args=[movie.pk]))
        self.assertFalse(Movie.objects.filter(pk=movie.pk).exists())
