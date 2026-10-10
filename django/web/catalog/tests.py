from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.movies.models import Movie
from domain.rooms.models import Room
from domain.seats.models import Seat
from domain.seat_types.models import SeatType
from domain.screenings.models import Screening
from domain.tickets.models import TicketPurchase
from domain.users.models import Customer, Manager


def crear_sala_con_butacas(name, capacity):
    room = Room.objects.create(name=name)
    seat_type = SeatType.objects.order_by("pk").first()
    Seat.objects.bulk_create(
        Seat(room=room, row=index // 20, column=index % 20, seat_type=seat_type)
        for index in range(capacity)
    )
    return room


def crear_funcion(
    status=Screening.Status.PUBLISHED, title="Pelicula", capacity=100, movie=None
):
    movie = movie or Movie.objects.create(
        title=title,
        synopsis="Una película de prueba.",
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


class CatalogFlowTests(TestCase):
    def test_home_renderiza_sin_sesion(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")
        self.assertContains(response, reverse("login"))

    def test_home_renderiza_si_hay_sesion(self):
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")

    def test_home_muestra_cartelera_publicada(self):
        crear_funcion(status=Screening.Status.PUBLISHED, title="Publicada")
        crear_funcion(status=Screening.Status.DRAFT, title="Oculta")
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Cartelera")
        self.assertContains(response, "Publicada")
        self.assertNotContains(response, "Oculta")

    def test_home_solo_muestra_funciones_publicadas(self):
        crear_funcion(status=Screening.Status.PUBLISHED, title="Visible")
        crear_funcion(status=Screening.Status.SCHEDULED, title="Programada")
        crear_funcion(status=Screening.Status.CANCELED, title="Cancelada")
        crear_funcion(status=Screening.Status.FINISHED, title="Finalizada")
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Visible")
        self.assertNotContains(response, "Programada")
        self.assertNotContains(response, "Cancelada")
        self.assertNotContains(response, "Finalizada")

    def test_home_agrupa_funciones_por_pelicula(self):
        movie = Movie.objects.create(
            title="Misma película",
            synopsis="Una película de prueba.",
            genre=Movie.Genre.ACCION,
            rating=Movie.Rating.MAS_13,
            duration_minutes=120,
            image="peliculas/test.jpg",
        )
        crear_funcion(status=Screening.Status.PUBLISHED, title="Funcion 1", movie=movie)
        crear_funcion(status=Screening.Status.PUBLISHED, title="Funcion 2", movie=movie)
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "<h2>Misma película</h2>", count=1, html=True)

    def test_detalle_funcion_publicada_permite_comprar(self):
        screening = crear_funcion(status=Screening.Status.PUBLISHED, title="Publicada", capacity=5)
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        TicketPurchase.buy(user, screening, 2)
        self.client.force_login(user)

        response = self.client.get(reverse("movie_detail", args=[screening.movie.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "screening_detail.html")
        self.assertContains(response, "Elegí tu función")
        self.assertContains(response, reverse("seat_selection", args=[screening.pk]))
        self.assertNotContains(response, "Disponibles")

    def test_detalle_pelicula_renderiza_sin_sesion(self):
        screening = crear_funcion(status=Screening.Status.PUBLISHED, title="Publica anonima")

        response = self.client.get(reverse("movie_detail", args=[screening.movie.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "screening_detail.html")
        self.assertContains(response, "Publica anonima")
        self.assertContains(response, reverse("seat_selection", args=[screening.pk]))

    def test_seleccion_de_butacas_requiere_login_y_preserva_next(self):
        screening = crear_funcion(status=Screening.Status.PUBLISHED, title="Publicada")
        seat_url = reverse("seat_selection", args=[screening.pk])

        response = self.client.get(seat_url)

        self.assertRedirects(response, f"{reverse('login')}?next={seat_url}")

    def test_detalle_muestra_pantalla_y_mapa_de_asientos_si_hay_snapshot(self):
        movie = Movie.objects.create(
            title="Con butacas",
            synopsis="Una pelicula de prueba.",
            genre=Movie.Genre.ACCION,
            rating=Movie.Rating.MAS_13,
            duration_minutes=120,
            image="peliculas/test.jpg",
        )
        room = Room.objects.create(name="Sala mapa")
        seat_type = SeatType.objects.get(name="Estándar")
        Seat.objects.create(room=room, row=0, column=0, seat_type=seat_type)
        Seat.objects.create(room=room, row=0, column=1, seat_type=seat_type)
        screening = Screening.objects.create(
            movie=movie,
            room=room,
            starts_at=timezone.now(),
            ticket_price="1500.00",
            status=Screening.Status.PUBLISHED,
        )
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("seat_selection", args=[screening.pk]))

        self.assertTemplateUsed(response, "seat_selection.html")
        self.assertContains(response, "Pantalla")
        self.assertContains(response, "1A")
        self.assertContains(response, "1B")
        self.assertContains(response, "Fila 1, columna A")

    def test_detalle_muestra_pasillos_sin_saltar_letras_de_columnas(self):
        movie = Movie.objects.create(
            title="Con pasillos",
            synopsis="Una pelicula de prueba.",
            genre=Movie.Genre.ACCION,
            rating=Movie.Rating.MAS_13,
            duration_minutes=120,
            image="peliculas/test.jpg",
        )
        room = Room.objects.create(name="Sala pasillos")
        seat_type = SeatType.objects.get(name="Estándar")
        screening = Screening.objects.create(
            movie=movie,
            room=room,
            starts_at=timezone.now(),
            ticket_price="1500.00",
            status=Screening.Status.PUBLISHED,
            capacity_snapshot=2,
            room_layout_snapshot={
                "rows": 3,
                "columns": 3,
                "seats": [
                    {
                        "row": 0,
                        "column": 0,
                        "type": seat_type.name,
                        "type_id": seat_type.pk,
                        "price": str(seat_type.base_price),
                        "color": seat_type.color,
                    },
                    {
                        "row": 0,
                        "column": 2,
                        "type": seat_type.name,
                        "type_id": seat_type.pk,
                        "price": str(seat_type.base_price),
                        "color": seat_type.color,
                    },
                ],
            },
        )
        user = get_user_model().objects.create_user(
            username="ana2@mail.com",
            email="ana2@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("seat_selection", args=[screening.pk]))

        self.assertContains(response, "1A")
        self.assertContains(response, "1B")
        self.assertNotContains(response, "1C")
        self.assertContains(response, "client-seat-row is-aisle-row")

    def test_detalle_muestra_entradas_agotadas_solo_para_funcion_seleccionada(self):
        movie = Movie.objects.create(
            title="Pelicula con varias funciones",
            synopsis="Una pelicula de prueba.",
            genre=Movie.Genre.ACCION,
            rating=Movie.Rating.MAS_13,
            duration_minutes=120,
            image="peliculas/test.jpg",
        )
        agotada = crear_funcion(
            status=Screening.Status.PUBLISHED,
            title="Agotada",
            capacity=1,
            movie=movie,
        )
        disponible = crear_funcion(
            status=Screening.Status.PUBLISHED,
            title="Disponible",
            capacity=3,
            movie=movie,
        )
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        TicketPurchase.buy(user, agotada, 1)
        self.client.force_login(user)

        response = self.client.get(reverse("movie_detail", args=[movie.pk]))

        self.assertContains(response, "Función agotada")
        self.assertContains(response, reverse("seat_selection", args=[disponible.pk]))
        self.assertNotContains(response, reverse("seat_selection", args=[agotada.pk]))

    def test_url_vieja_de_funcion_redirige_a_seleccion_de_butacas(self):
        screening = crear_funcion(status=Screening.Status.PUBLISHED, title="Publicada")
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("screening_detail", args=[screening.pk]))

        self.assertRedirects(response, reverse("seat_selection", args=[screening.pk]))

    def test_home_muestra_acceso_a_gestion_si_es_gerente(self):
        user = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password="PasswordSegura123!",
        )
        Manager.objects.create(user=user)
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, reverse("manager:home"))

    def test_home_no_muestra_acceso_a_gestion_si_es_cliente(self):
        user = get_user_model().objects.create_user(
            username="cliente@mail.com",
            email="cliente@mail.com",
            password="PasswordSegura123!",
        )
        Customer.objects.create(user=user)
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertNotContains(response, reverse("manager:home"))
