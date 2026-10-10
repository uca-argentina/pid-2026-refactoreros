import shutil
import tempfile
import json
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from domain.cinema.models import CinemaSettings
from domain.movies.models import Movie
from domain.rooms.models import Room
from domain.seats.models import Seat
from domain.seat_types.models import SeatType
from domain.screenings.models import Screening
from domain.tickets.models import SeatPurchase, TicketPurchase
from domain.users.models import Usher, Customer, Manager

from .dashboard import WEEKDAYS, build_dashboard
from .forms import MovieForm


def crear_sala_con_butacas(name, capacity):
    room = Room.objects.create(name=name)
    seat_type = SeatType.objects.order_by("pk").first()
    Seat.objects.bulk_create(
        Seat(room=room, row=index // 20, column=index % 20, seat_type=seat_type)
        for index in range(capacity)
    )
    return room


class ManagerAccessTests(TestCase):
    def setUp(self):
        self.password = "PasswordSegura123!"
        self.gerente = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password=self.password,
        )
        Manager.objects.create(user=self.gerente)
        self.acomodador = get_user_model().objects.create_user(
            username="acomodador@mail.com",
            email="acomodador@mail.com",
            password=self.password,
        )
        Usher.objects.create(user=self.acomodador)
        self.cliente = get_user_model().objects.create_user(
            username="cliente@mail.com",
            email="cliente@mail.com",
            password=self.password,
        )
        Customer.objects.create(user=self.cliente)

    def test_gestion_redirige_a_login_si_no_hay_sesion(self):
        response = self.client.get(reverse("manager:home"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('manager:home')}",
        )

    def test_gestion_rechaza_cliente_sin_rol_operativo(self):
        self.client.force_login(self.cliente)

        response = self.client.get(reverse("manager:home"))

        self.assertEqual(response.status_code, 403)

    def test_gestion_permite_acomodador_con_vista_limitada(self):
        self.client.force_login(self.acomodador)

        response = self.client.get(reverse("manager:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Panel de acomodador")
        self.assertNotContains(response, "Usuarios")

    def test_gestion_permite_gerente_con_accesos_de_abm(self):
        self.client.force_login(self.gerente)

        response = self.client.get(reverse("manager:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Usuarios")
        self.assertContains(response, "Salas")
        self.assertContains(response, "Butacas")
        self.assertContains(response, "Películas")
        self.assertContains(response, "Funciones")

    def test_home_muestra_ocupacion_de_proximas_funciones(self):
        room = crear_sala_con_butacas("Sala progreso", 10)
        movie = Movie.objects.create(
            title="Pelicula progreso",
            synopsis="Sinopsis",
            genre=Movie.Genre.ACCION,
            rating=Movie.Rating.MAS_13,
            duration_minutes=120,
            image="peliculas/test.jpg",
        )
        screening = Screening.objects.create(
            movie=movie,
            room=room,
            starts_at=timezone.now() + timedelta(days=1),
            ticket_price="1000.00",
            status=Screening.Status.PUBLISHED,
        )
        TicketPurchase.buy(self.cliente, screening, 3)
        self.client.force_login(self.gerente)

        response = self.client.get(reverse("manager:home"))

        self.assertContains(response, "schedule-progress")
        self.assertContains(response, "3 vendidas")
        self.assertContains(response, "<strong>30%</strong>", html=True)

    def test_link_starts_at_del_manager_apunta_al_home_de_gestion(self):
        self.client.force_login(self.gerente)

        response = self.client.get(reverse("manager:home"))

        self.assertContains(response, f'href="{reverse("manager:home")}"')

    def test_acomodador_no_puede_entrar_a_abm_de_gerente(self):
        self.client.force_login(self.acomodador)

        response = self.client.get(reverse("manager:salas_list"))

        self.assertEqual(response.status_code, 403)

    def test_gerente_puede_configurar_reserva_y_recarga_de_butacas(self):
        self.client.force_login(self.gerente)

        response = self.client.post(
            reverse("manager:configuracion"),
            data={
                "seat_reservation_minutes": 7,
                "seat_refresh_seconds": 12,
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("manager:configuracion"))
        cinema_settings = CinemaSettings.objects.get()
        self.assertEqual(cinema_settings.seat_reservation_minutes, 7)
        self.assertEqual(cinema_settings.seat_refresh_seconds, 12)

    def test_acomodador_no_puede_configurar_reserva_y_recarga_de_butacas(self):
        self.client.force_login(self.acomodador)

        response = self.client.get(reverse("manager:configuracion"))

        self.assertEqual(response.status_code, 403)


class ManagerUsuariosTests(TestCase):
    def setUp(self):
        self.gerente = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password="PasswordSegura123!",
        )
        Manager.objects.create(user=self.gerente)
        self.otro_gerente = get_user_model().objects.create_user(
            username="otro-gerente@mail.com",
            email="otro-gerente@mail.com",
            password="PasswordSegura123!",
        )
        Manager.objects.create(user=self.otro_gerente)
        self.user = get_user_model().objects.create_user(
            username="cliente@mail.com",
            email="cliente@mail.com",
            first_name="Ana",
            last_name="Gomez",
            password="PasswordSegura123!",
        )
        Customer.objects.create(user=self.user)
        self.client.force_login(self.gerente)

    def test_gerente_lista_usuarios(self):
        response = self.client.get(reverse("manager:usuarios_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cliente@mail.com")
        self.assertContains(response, "customer")
        self.assertContains(response, reverse("manager:usuarios_update", args=[self.gerente.pk]))
        self.assertNotContains(
            response, reverse("manager:usuarios_update", args=[self.otro_gerente.pk])
        )

    def test_gerente_modifica_usuario(self):
        response = self.client.post(
            reverse("manager:usuarios_update", args=[self.user.pk]),
            data={
                "first_name": "Ana Maria",
                "last_name": "Gomez",
                "email": "ana@mail.com",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, reverse("manager:usuarios_list"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Ana Maria")
        self.assertEqual(self.user.email, "ana@mail.com")
        self.assertEqual(self.user.username, "ana@mail.com")

    def test_edicion_usuario_muestra_boton_bloquear_sin_checkbox_active(self):
        response = self.client.get(reverse("manager:usuarios_update", args=[self.user.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Usuario active")
        self.assertContains(response, "Bloquear")
        self.assertContains(response, "no va a poder acceder al sitio")

    def test_gerente_bloquea_usuario(self):
        response = self.client.post(reverse("manager:usuarios_toggle", args=[self.user.pk]))

        self.assertRedirects(response, reverse("manager:usuarios_list"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_gerente_no_puede_autobloquearse(self):
        response = self.client.post(reverse("manager:usuarios_toggle", args=[self.gerente.pk]))

        self.assertRedirects(response, reverse("manager:usuarios_list"))
        self.gerente.refresh_from_db()
        self.assertTrue(self.gerente.is_active)

    def test_gerente_no_puede_editar_otro_gerente(self):
        response = self.client.get(
            reverse("manager:usuarios_update", args=[self.otro_gerente.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_gerente_no_puede_bloquear_otro_gerente(self):
        response = self.client.post(
            reverse("manager:usuarios_toggle", args=[self.otro_gerente.pk])
        )

        self.assertRedirects(response, reverse("manager:usuarios_list"))
        self.otro_gerente.refresh_from_db()
        self.assertTrue(self.otro_gerente.is_active)


class ManagerSalasTests(TestCase):
    def setUp(self):
        self.gerente = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password="PasswordSegura123!",
        )
        Manager.objects.create(user=self.gerente)
        self.client.force_login(self.gerente)

    def test_gerente_crea_sala(self):
        seat_type = SeatType.objects.order_by("pk").first()
        layout = {
            "rows": 1,
            "columns": 2,
            "seats": [
                {"row": 0, "column": 0, "type": seat_type.name},
                {"row": 0, "column": 1, "type": seat_type.name},
            ],
        }
        response = self.client.post(
            reverse("manager:salas_create"),
            data={
                "name": "Sala 1",
                "room_layout": json.dumps(layout),
            },
        )

        self.assertRedirects(response, reverse("manager:salas_list"))
        room = Room.objects.get(name="Sala 1")
        self.assertEqual(room.capacity, 2)

    def test_sala_duplicada_mantiene_layout_en_formulario(self):
        crear_sala_con_butacas("Sala 1", 120)
        standard_type = SeatType.objects.order_by("pk").first()
        preferred_type = SeatType.objects.get(name="Preferencial")
        layout = {
            "rows": 8,
            "columns": 12,
            "seats": [
                {"row": 0, "column": 0, "type": standard_type.name},
                {"row": 0, "column": 1, "type": preferred_type.name},
            ],
        }

        response = self.client.post(
            reverse("manager:salas_create"),
            data={
                "name": "Sala 1",
                "room_layout": json.dumps(layout),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"]["room_layout"].value(), json.dumps(layout))

    def test_gerente_crea_sala_con_pasillos_y_guarda_tamano_de_layout(self):
        standard_type = SeatType.objects.order_by("pk").first()
        preferred_type = SeatType.objects.get(name="Preferencial")
        layout = {
            "rows": 3,
            "columns": 4,
            "seats": [
                {"row": 0, "column": 0, "type": standard_type.name},
                {"row": 2, "column": 3, "type": preferred_type.name},
            ],
        }

        response = self.client.post(
            reverse("manager:salas_create"),
            data={
                "name": "Sala con pasillos",
                "room_layout": json.dumps(layout),
            },
        )

        self.assertRedirects(response, reverse("manager:salas_list"))
        room = Room.objects.get(name="Sala con pasillos")
        self.assertEqual(room.capacity, 2)
        self.assertEqual(room.layout_configuration["rows"], 3)
        self.assertEqual(room.layout_configuration["columns"], 4)
        self.assertEqual(room.seats.count(), 2)

    def test_gerente_busca_salas_y_limita_items_por_pagina(self):
        for index in range(12):
            crear_sala_con_butacas(f"Sala {index:02d}", 80)
        crear_sala_con_butacas("Microcine", 30)

        response = self.client.get(
            reverse("manager:salas_list"),
            {"q": "Sala", "per_page": "10"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 10)
        self.assertContains(response, "Sala 00")
        self.assertNotContains(response, "Microcine")

    def test_gerente_ordena_salas_por_capacidad(self):
        chica = crear_sala_con_butacas("Sala chica", 80)
        grande = crear_sala_con_butacas("Sala grande", 180)

        response = self.client.get(
            reverse("manager:salas_list"),
            {"order": "capacity_desc"},
        )

        object_list = list(response.context["page_obj"].object_list)
        self.assertContains(response, "Ordenar por")
        self.assertEqual(object_list[0], grande)
        self.assertEqual(object_list[1], chica)

    def test_formulario_edicion_sala_muestra_titulo_especifico(self):
        room = crear_sala_con_butacas("Sala 1", 120)

        response = self.client.get(reverse("manager:salas_update", args=[room.pk]))

        self.assertContains(response, "Editar sala")
        self.assertNotContains(response, "Guardar registro")

    def test_formulario_edicion_sala_precarga_layout_existente(self):
        room = Room.objects.create(name="Sala 1")
        tipo_estandar = SeatType.objects.order_by("pk").first()
        tipo_preferencial = SeatType.objects.get(name="Preferencial")
        Seat.objects.create(room=room, row=0, column=0, seat_type=tipo_estandar)
        Seat.objects.create(room=room, row=1, column=2, seat_type=tipo_preferencial)

        response = self.client.get(reverse("manager:salas_update", args=[room.pk]))

        layout_value = response.context["form"]["room_layout"].value()
        layout = json.loads(layout_value)
        self.assertEqual(layout["rows"], 2)
        self.assertEqual(layout["columns"], 3)
        {"row": 0, "column": 0, "type": tipo_estandar.name},
        self.assertIn({"row": 1, "column": 2, "type": "Preferencial"}, layout["seats"])

    def test_formulario_edicion_sala_normaliza_layout_guardado_con_ids(self):
        tipo_estandar = SeatType.objects.order_by("pk").first()
        room = Room.objects.create(
            name="Sala con layout viejo",
            layout_configuration={
                "rows": 4,
                "columns": 6,
                "seats": [{"row": 2, "column": 5, "type": tipo_estandar.pk}],
            },
        )
        Seat.objects.create(room=room, row=2, column=5, seat_type=tipo_estandar)

        response = self.client.get(reverse("manager:salas_update", args=[room.pk]))

        layout = json.loads(response.context["form"]["room_layout"].value())
        self.assertEqual(layout["rows"], 4)
        self.assertEqual(layout["columns"], 6)
        self.assertEqual(layout["seats"], [{"row": 2, "column": 5, "type": tipo_estandar.name}])

    def test_gerente_elimina_sala(self):
        room = crear_sala_con_butacas("Sala 1", 120)

        response = self.client.post(reverse("manager:salas_delete", args=[room.pk]))

        self.assertRedirects(response, reverse("manager:salas_list"))
        self.assertFalse(Room.objects.filter(pk=room.pk).exists())


class ManagerSeatTypesTests(TestCase):
    def setUp(self):
        self.gerente = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password="PasswordSegura123!",
        )
        Manager.objects.create(user=self.gerente)
        self.client.force_login(self.gerente)

    def test_gerente_lista_tipos_de_butaca(self):
        response = self.client.get(reverse("manager:seat_types_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, SeatType.objects.order_by("pk").first().name)
        self.assertContains(response, "Precio")

    def test_gerente_crea_tipo_de_butaca_con_precio(self):
        response = self.client.post(
            reverse("manager:seat_types_create"),
            data={
                "name": "Premium",
                "base_price": "2500.00",
                "color": "#111827",
            },
        )

        self.assertRedirects(response, reverse("manager:seat_types_list"))
        seat_type = SeatType.objects.get(name="Premium")
        self.assertEqual(seat_type.base_price, Decimal("2500.00"))

    def test_no_permite_tipo_de_butaca_con_precio_cero(self):
        response = self.client.post(
            reverse("manager:seat_types_create"),
            data={
                "name": "Gratis",
                "base_price": "0.00",
                "color": "#111827",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SeatType.objects.filter(name="Gratis").exists())
        self.assertIn("base_price", response.context["form"].errors)

    def test_no_elimina_tipo_de_butaca_usado_en_sala(self):
        room = Room.objects.create(name="Sala 1")
        seat_type = SeatType.objects.order_by("pk").first()
        Seat.objects.create(room=room, row=0, column=0, seat_type=seat_type)

        response = self.client.post(
            reverse("manager:seat_types_delete", args=[seat_type.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse("manager:seat_types_list"))
        self.assertTrue(SeatType.objects.filter(pk=seat_type.pk).exists())
        self.assertContains(response, "No se puede eliminar")


SMALL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"D\x01\x00;"
)

class ManagerPeliculasTests(TestCase):
    def test_pelicula_form_rechaza_imagen_muy_pesada(self):
        image = SimpleUploadedFile(
            "poster.gif",
            SMALL_GIF + (b"0" * (2 * 1024 * 1024 + 1)),
            content_type="image/gif",
        )
        form = MovieForm(
            data={
                "title": "Pelicula",
                "synopsis": "Sinopsis",
                "genre": Movie.Genre.ACCION,
                "rating": Movie.Rating.MAS_13,
                "duration_minutes": 100,
            },
            files={"image": image},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)
        self.assertIn("La imagen no puede superar los 2 MB.", form.errors["image"])


class ManagerFuncionesTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.meday_root = tempfile.mkdtemp()
        cls.override_meday_root = override_settings(MEDIA_ROOT=cls.meday_root)
        cls.override_meday_root.enable()

    @classmethod
    def tearDownClass(cls):
        cls.override_meday_root.disable()
        shutil.rmtree(cls.meday_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.gerente = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password="PasswordSegura123!",
        )
        Manager.objects.create(user=self.gerente)
        self.client.force_login(self.gerente)
        self.room = crear_sala_con_butacas("Sala 1", 120)
        self.movie = Movie.objects.create(
            title="Pelicula",
            synopsis="Sinopsis",
            genre=Movie.Genre.ACCION,
            rating=Movie.Rating.MAS_13,
            duration_minutes=100,
            image=SimpleUploadedFile(
                "poster.gif",
                SMALL_GIF,
                content_type="image/gif",
            ),
        )

    def date_form(self, date):
        return timezone.localtime(date).strftime("%Y-%m-%dT%H:%M")

    def date_futura(self, hour=20, minuto=30):
        date = timezone.datetime.combine(
            timezone.localdate() + timedelta(days=30),
            timezone.datetime.min.time(),
        ).replace(hour=hour, minute=minuto)
        return timezone.make_aware(date)

    def precios_por_tipo_form(self, precio="1500.00"):
        return json.dumps({
            str(seat_type.pk): precio
            for seat_type in SeatType.objects.all()
        })

    def test_gerente_crea_funcion_sin_publicarla(self):
        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "movie": self.movie.pk,
                "room": self.room.pk,
                "starts_at": self.date_form(self.date_futura()),
                "prices_by_type": self.precios_por_tipo_form(),
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        screening = Screening.objects.get()
        self.assertEqual(screening.status, Screening.Status.DRAFT)

    def test_no_permite_crear_funcion_con_precio_cero(self):
        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "movie": self.movie.pk,
                "room": self.room.pk,
                "starts_at": self.date_form(timezone.now() + timedelta(days=1)),
                "prices_by_type": self.precios_por_tipo_form("0.00"),
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        screening = Screening.objects.get()
        self.assertEqual(screening.ticket_price, Decimal("1000.00"))

    def test_no_permite_crear_funcion_con_precio_negativo(self):
        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "movie": self.movie.pk,
                "room": self.room.pk,
                "starts_at": self.date_form(timezone.now() + timedelta(days=1)),
                "prices_by_type": self.precios_por_tipo_form("-1500.00"),
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        screening = Screening.objects.get()
        self.assertEqual(screening.ticket_price, Decimal("1000.00"))

    def test_no_permite_crear_funcion_con_date_pasada(self):
        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "movie": self.movie.pk,
                "room": self.room.pk,
                "starts_at": self.date_form(timezone.now() - timedelta(days=1)),
                "ticket_price": "1500.00",
            },
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("starts_at", form.errors)
        self.assertIn("deben ser futuros", form.errors["starts_at"][0])
        self.assertEqual(Screening.objects.count(), 0)

    def test_modelo_funcion_valida_precio_y_date(self):
        screening = Screening(
            movie=self.movie,
            room=self.room,
            starts_at=timezone.now() - timedelta(days=1),
            ticket_price="0.00",
        )

        with self.assertRaises(ValidationError) as error:
            screening.full_clean()

        self.assertIn("ticket_price", error.exception.message_dict)
        self.assertIn("starts_at", error.exception.message_dict)

    def crear_funcion(self, status=Screening.Status.DRAFT, starts_at=None):
        return Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=starts_at or self.date_futura(),
            ticket_price="1500.00",
            status=status,
        )

    def change_status(self, screening, status):
        return self.client.post(
            reverse("manager:funciones_estado", args=[screening.pk]),
            data={"status": status},
        )

    def vender_entradas(self, screening, quantity=1):
        cliente = get_user_model().objects.create_user(
            username="cliente@mail.com",
            email="cliente@mail.com",
            password="PasswordSegura123!",
        )
        TicketPurchase.buy(cliente, screening, quantity)

    def test_gerente_recorre_el_ciclo_borrador_programada_publicada(self):
        screening = self.crear_funcion()

        response = self.change_status(screening, Screening.Status.SCHEDULED)
        self.assertRedirects(response, reverse("manager:funciones_list"))
        screening.refresh_from_db()
        self.assertEqual(screening.status, Screening.Status.SCHEDULED)

        self.change_status(screening, Screening.Status.PUBLISHED)
        screening.refresh_from_db()
        self.assertEqual(screening.status, Screening.Status.PUBLISHED)

        self.change_status(screening, Screening.Status.SCHEDULED)
        screening.refresh_from_db()
        self.assertEqual(screening.status, Screening.Status.SCHEDULED)

        self.change_status(screening, Screening.Status.DRAFT)
        screening.refresh_from_db()
        self.assertEqual(screening.status, Screening.Status.DRAFT)

    def test_borrador_se_puede_publicar_directamente(self):
        screening = self.crear_funcion()

        response = self.change_status(screening, Screening.Status.PUBLISHED)

        self.assertRedirects(response, reverse("manager:funciones_list"))
        screening.refresh_from_db()
        self.assertEqual(screening.status, Screening.Status.PUBLISHED)

    def test_no_se_puede_forzar_finalizada_a_mano(self):
        screening = self.crear_funcion(Screening.Status.PUBLISHED)

        self.change_status(screening, Screening.Status.FINISHED)

        screening.refresh_from_db()
        self.assertEqual(screening.status, Screening.Status.PUBLISHED)

    def test_publicada_con_sales_no_se_puede_ocultar(self):
        screening = self.crear_funcion(Screening.Status.PUBLISHED)
        self.vender_entradas(screening)

        self.change_status(screening, Screening.Status.SCHEDULED)

        screening.refresh_from_db()
        self.assertEqual(screening.status, Screening.Status.PUBLISHED)

    def test_no_se_puede_programar_un_borrador_con_date_pasada(self):
        screening = self.crear_funcion(
            starts_at=timezone.now() - timedelta(days=1),
        )

        response = self.change_status(screening, Screening.Status.SCHEDULED)

        screening.refresh_from_db()
        self.assertEqual(screening.status, Screening.Status.DRAFT)
        response = self.client.get(response.url)
        self.assertIn(
            "No se puede programar ni publicar una funci\u00f3n con fecha pasada.".encode("utf-8"),
            response.content,
        )

    def test_gerente_cancela_funcion_publicada_con_sales(self):
        screening = self.crear_funcion(Screening.Status.PUBLISHED)
        self.vender_entradas(screening, 3)

        response = self.client.get(reverse("manager:funciones_cancelar", args=[screening.pk]))
        self.assertIn("Confirmar cancelaci\u00f3n".encode("utf-8"), response.content)
        self.assertContains(response, "<strong>3</strong> entradas")

        self.change_status(screening, Screening.Status.CANCELED)

        screening.refresh_from_db()
        self.assertEqual(screening.status, Screening.Status.CANCELED)

    def test_funcion_cancelada_no_admite_mas_cambios(self):
        screening = self.crear_funcion(Screening.Status.CANCELED)

        self.change_status(screening, Screening.Status.PUBLISHED)
        response = self.client.get(reverse("manager:funciones_cancelar", args=[screening.pk]))

        self.assertRedirects(response, reverse("manager:funciones_list"))
        screening.refresh_from_db()
        self.assertEqual(screening.status, Screening.Status.CANCELED)

    def test_borrador_no_se_puede_cancelar(self):
        screening = self.crear_funcion()

        self.change_status(screening, Screening.Status.CANCELED)

        screening.refresh_from_db()
        self.assertEqual(screening.status, Screening.Status.DRAFT)

    def test_funcion_publicada_con_sales_no_se_puede_editar_ni_eliminar(self):
        screening = self.crear_funcion(Screening.Status.PUBLISHED)
        self.vender_entradas(screening)

        response = self.client.get(reverse("manager:funciones_update", args=[screening.pk]))
        self.assertEqual(response.status_code, 403)

        response = self.client.post(reverse("manager:funciones_delete", args=[screening.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Screening.objects.filter(pk=screening.pk).exists())

    def test_funcion_publicada_sin_sales_se_puede_editar_pero_no_eliminar(self):
        screening = self.crear_funcion(Screening.Status.PUBLISHED)

        response = self.client.get(reverse("manager:funciones_update", args=[screening.pk]))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse("manager:funciones_delete", args=[screening.pk]))
        self.assertEqual(response.status_code, 403)

    def test_funciones_cancelada_y_finalizada_son_solo_lectura(self):
        for status in (Screening.Status.CANCELED, Screening.Status.FINISHED):
            screening = self.crear_funcion(status, starts_at=self.date_futura(10, 0))

            response = self.client.get(reverse("manager:funciones_update", args=[screening.pk]))
            self.assertEqual(response.status_code, 403)
            response = self.client.post(reverse("manager:funciones_delete", args=[screening.pk]))
            self.assertEqual(response.status_code, 403)

            screening.delete()

    def test_funcion_cancelada_no_ocupa_la_sala(self):
        self.crear_funcion(Screening.Status.CANCELED, starts_at=self.date_futura(20, 0))

        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "movie": self.movie.pk,
                "room": self.room.pk,
                "starts_at": self.date_form(self.date_futura(20, 0)),
                "ticket_price": "1500.00",
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        self.assertEqual(Screening.objects.count(), 2)

    def test_funcion_terminada_pasa_a_finalizada_al_listar(self):
        # The movie lasts 100 minutes: it started 3 hours ago, so it has already finished.
        terminada = self.crear_funcion(
            Screening.Status.PUBLISHED,
            starts_at=timezone.now() - timedelta(hours=3),
        )
        # It started 30 minutes ago, so it is still in progress.
        en_curso = self.crear_funcion(
            Screening.Status.PUBLISHED,
            starts_at=timezone.now() - timedelta(minutes=30),
        )
        borrador_vencido = self.crear_funcion(
            starts_at=timezone.now() - timedelta(days=2),
        )

        self.client.get(reverse("manager:funciones_list"))

        terminada.refresh_from_db()
        en_curso.refresh_from_db()
        borrador_vencido.refresh_from_db()
        self.assertEqual(terminada.status, Screening.Status.FINISHED)
        self.assertEqual(en_curso.status, Screening.Status.PUBLISHED)
        self.assertEqual(borrador_vencido.status, Screening.Status.DRAFT)

    def test_lista_funciones_muestra_acciones_de_borrador(self):
        screening = self.crear_funcion()

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "status-borrador")
        self.assertContains(response, "Publicar")
        self.assertContains(response, "Programar")
        self.assertContains(response, "disabled-action")
        self.assertContains(response, 'class="publish-action"')
        self.assertContains(response, "Eliminar")
        self.assertContains(response, 'value="publicada"')
        self.assertNotContains(response, 'value="programada"')
        self.assertNotContains(response, reverse("manager:funciones_cancelar", args=[screening.pk]))

    def test_lista_funciones_muestra_acciones_de_programada(self):
        screening = self.crear_funcion(Screening.Status.SCHEDULED)

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "Publicar")
        self.assertContains(response, 'class="publish-action"')
        self.assertContains(response, "Volver a borrador")
        self.assertContains(response, reverse("manager:funciones_cancelar", args=[screening.pk]))
        self.assertNotContains(response, 'value="programada"')

    def test_funciones_cancelada_y_finalizada_muestran_plantilla_sin_menu(self):
        for status in (Screening.Status.CANCELED, Screening.Status.FINISHED):
            screening = self.crear_funcion(status)

            response = self.client.get(reverse("manager:funciones_historial"))

            self.assertContains(
                response,
                f'{reverse("manager:funciones_create")}?plantilla={screening.pk}',
            )
            self.assertNotContains(response, 'class="row-menu"')
            screening.delete()

    def test_lista_funciones_oculta_expiradas_y_el_historial_las_muestra(self):
        activa = self.crear_funcion(
            Screening.Status.PUBLISHED,
            starts_at=self.date_futura(),
        )
        expirada = self.crear_funcion(
            Screening.Status.PUBLISHED,
            starts_at=timezone.now() - timedelta(days=2),
        )

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, activa.movie.title)
        self.assertNotContains(response, f'?plantilla={expirada.pk}')

        response = self.client.get(reverse("manager:funciones_historial"))

        self.assertContains(response, "Historial de funciones")
        self.assertContains(response, f'?plantilla={expirada.pk}')
        self.assertNotContains(response, f'?plantilla={activa.pk}')

    def test_lista_funciones_muestra_acciones_de_publicada(self):
        screening = self.crear_funcion(Screening.Status.PUBLISHED)

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "Ocultar")
        self.assertContains(response, reverse("manager:funciones_cancelar", args=[screening.pk]))
        self.assertNotContains(response, 'class="publish-action"')
        self.assertNotContains(response, "Eliminar")

    def test_lista_funciones_muestra_precio_con_simbolo_pesos(self):
        Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=self.date_futura(),
            ticket_price="1500.00",
            status=Screening.Status.DRAFT,
        )

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "$1000,00")

    def test_lista_funciones_ordena_por_mayor_precio(self):
        tipo_caro = SeatType.objects.create(
            name="Premium",
            base_price="2500.00",
            color="#111827",
        )
        sala_cara = Room.objects.create(name="Sala premium")
        Seat.objects.create(room=sala_cara, row=0, column=0, seat_type=tipo_caro)
        barata = Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=self.date_futura(20, 30),
            ticket_price="1.00",
            status=Screening.Status.DRAFT,
        )
        cara = Screening.objects.create(
            movie=self.movie,
            room=sala_cara,
            starts_at=self.date_futura(22, 30),
            ticket_price="1.00",
            status=Screening.Status.DRAFT,
        )

        response = self.client.get(
            reverse("manager:funciones_list"),
            {"order": "precio_desc"},
        )

        object_list = list(response.context["page_obj"].object_list)
        self.assertEqual(object_list[0], cara)
        self.assertEqual(object_list[1], barata)

    def test_lista_funciones_muestra_link_para_usar_como_plantilla(self):
        screening = Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=self.date_futura(),
            ticket_price="1500.00",
            status=Screening.Status.DRAFT,
        )

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "Usar como plantilla")
        self.assertContains(
            response,
            f'{reverse("manager:funciones_create")}?plantilla={screening.pk}',
        )

    def test_crear_funcion_start_plantilla_precarga_data(self):
        screening = Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=self.date_futura(),
            ticket_price="1500.00",
            status=Screening.Status.PUBLISHED,
        )

        response = self.client.get(
            reverse("manager:funciones_create"),
            {"plantilla": screening.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial["movie"], self.movie)
        self.assertEqual(response.context["form"].initial["room"], self.room)
        self.assertEqual(
            response.context["form"].initial["starts_at"],
            screening.starts_at,
        )
        self.assertNotIn("prices_by_type", response.context["form"].initial)
        self.assertContains(
            response,
            f'value="{self.date_form(screening.starts_at)}"',
        )

    def test_lista_funciones_muestra_entradas_sold_y_disponibles(self):
        screening = Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=self.date_futura(),
            ticket_price="1500.00",
            status=Screening.Status.PUBLISHED,
        )
        cliente = get_user_model().objects.create_user(
            username="cliente@mail.com",
            email="cliente@mail.com",
            password="PasswordSegura123!",
        )
        TicketPurchase.buy(cliente, screening, 35)

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "Vendidas")
        self.assertContains(response, "Disponibles")
        self.assertContains(response, '<td data-label="Vendidas">35</td>', html=True)
        self.assertContains(response, '<td data-label="Disponibles">85</td>', html=True)

    def test_funcion_publicada_mantiene_snapshot_de_capacity_de_sala(self):
        screening = Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=self.date_futura(),
            ticket_price="1500.00",
            status=Screening.Status.PUBLISHED,
        )

        self.room.seats.exclude(pk=self.room.seats.first().pk).delete()

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertEqual(screening.capacity_snapshot, 120)
        self.assertContains(response, '<td data-label="Disponibles">120</td>', html=True)

    def test_date_de_funcion_se_precarga_al_editar(self):
        screening = Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=self.date_futura(),
            ticket_price="1500.00",
            status=Screening.Status.DRAFT,
        )

        response = self.client.get(reverse("manager:funciones_update", args=[screening.pk]))

        self.assertContains(
            response,
            f'value="{self.date_form(screening.starts_at)}"',
        )

    def test_no_permite_funciones_solapadas_en_misma_sala(self):
        Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=self.date_futura(20, 0),
            ticket_price="1500.00",
            status=Screening.Status.DRAFT,
        )

        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "movie": self.movie.pk,
                "room": self.room.pk,
                "starts_at": self.date_form(self.date_futura(21, 0)),
                "ticket_price": "1500.00",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("La sala ya tiene una funci\u00f3n programada".encode("utf-8"), response.content)
        self.assertEqual(Screening.objects.count(), 1)

    def test_permite_funciones_en_misma_sala_cuando_no_se_solapan(self):
        Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=self.date_futura(20, 0),
            ticket_price="1500.00",
            status=Screening.Status.DRAFT,
        )

        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "movie": self.movie.pk,
                "room": self.room.pk,
                "starts_at": self.date_form(self.date_futura(21, 40)),
                "ticket_price": "1500.00",
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        self.assertEqual(Screening.objects.count(), 2)

    def test_permite_funciones_solapadas_en_rooms_distintas(self):
        otra_sala = crear_sala_con_butacas("Sala 2", 80)
        Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=self.date_futura(20, 0),
            ticket_price="1500.00",
            status=Screening.Status.DRAFT,
        )

        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "movie": self.movie.pk,
                "room": otra_sala.pk,
                "starts_at": self.date_form(self.date_futura(21, 0)),
                "ticket_price": "1500.00",
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        self.assertEqual(Screening.objects.count(), 2)

    def test_editar_funcion_no_colisiona_consigo_misma(self):
        screening = Screening.objects.create(
            movie=self.movie,
            room=self.room,
            starts_at=self.date_futura(20, 0),
            ticket_price="1500.00",
            status=Screening.Status.DRAFT,
        )
        SeatType.objects.filter(seats__room=self.room).update(base_price="1600.00")

        response = self.client.post(
            reverse("manager:funciones_update", args=[screening.pk]),
            data={
                "movie": self.movie.pk,
                "room": self.room.pk,
                "starts_at": self.date_form(self.date_futura(20, 0)),
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        screening.refresh_from_db()
        self.assertEqual(str(screening.ticket_price), "1600.00")


class ManagerDashboardTests(TestCase):
    def setUp(self):
        self.gerente = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password="PasswordSegura123!",
        )
        Manager.objects.create(user=self.gerente)
        self.cliente = get_user_model().objects.create_user(
            username="cliente@mail.com",
            email="cliente@mail.com",
            password="PasswordSegura123!",
        )
        self.room = crear_sala_con_butacas("Sala 1", 10)
        self.movie = self.crear_pelicula("Pelicula A")
        self.now = timezone.make_aware(datetime(2026, 10, 8, 23, 0))

    def crear_pelicula(self, title):
        return Movie.objects.create(
            title=title,
            synopsis="Sinopsis",
            genre=Movie.Genre.ACCION,
            rating=Movie.Rating.MAS_13,
            duration_minutes=100,
            image="peliculas/poster.gif",
        )

    def crear_funcion(self, days, hour=20, status=Screening.Status.FINISHED, movie=None, now=None):
        date = timezone.localdate(now or self.now) + timedelta(days=days)
        return Screening.objects.create(
            movie=movie or self.movie,
            room=self.room,
            starts_at=timezone.make_aware(datetime.combine(date, datetime.min.time()).replace(hour=hour)),
            ticket_price="1000.00",
            status=status,
        )

    def vender(self, screening, quantity, total, used=0):
        purchase = TicketPurchase.objects.create(
            user=self.cliente,
            screening=screening,
            quantity=quantity,
            total=Decimal(total),
        )
        for index in range(quantity):
            SeatPurchase.objects.create(
                purchase=purchase,
                screening=screening,
                label=f"{purchase.pk}-{index}",
                used_at=self.now if index < used else None,
            )
        return purchase

    def test_gerente_ve_dashboard(self):
        self.client.force_login(self.gerente)

        response = self.client.get(reverse("manager:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("Recaudaci\u00f3n simulada".encode("utf-8"), response.content)
        self.assertContains(response, "Vendidas vs. utilizadas")
        self.assertIn("Pel\u00edculas m\u00e1s vistas".encode("utf-8"), response.content)
        self.assertIn("Ocupaci\u00f3n por sala".encode("utf-8"), response.content)
        self.assertContains(response, "Horarios de mayor demanda")

    def test_acomodador_no_puede_ver_dashboard(self):
        acomodador = get_user_model().objects.create_user(
            username="acomodador@mail.com",
            email="acomodador@mail.com",
            password="PasswordSegura123!",
        )
        Usher.objects.create(user=acomodador)
        self.client.force_login(acomodador)

        response = self.client.get(reverse("manager:dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_menu_del_gerente_enlaza_al_dashboard(self):
        self.client.force_login(self.gerente)

        response = self.client.get(reverse("manager:home"))

        self.assertContains(response, f'href="{reverse("manager:dashboard")}"')

    def test_summary_calcula_revenue_occupancy_y_attendance(self):
        primera = self.crear_funcion(-2)
        self.vender(primera, 3, "3000.00", used=2)
        self.vender(primera, 2, "2500.00")
        segunda = self.crear_funcion(-1, hour=18, status=Screening.Status.PUBLISHED)
        self.vender(segunda, 1, "1000.00")

        summary = build_dashboard("30", now=self.now)["summary"]

        self.assertEqual(summary["screenings"], 2)
        self.assertEqual(summary["sold"], 6)
        self.assertEqual(summary["revenue"], Decimal("6500.00"))
        self.assertEqual(summary["capacity"], 20)
        self.assertAlmostEqual(summary["occupancy"], 30.0)
        self.assertEqual(summary["used"], 2)
        self.assertEqual(summary["unused"], 4)
        self.assertAlmostEqual(summary["attendance"], 100 / 3)

    def test_excluye_canceladas_y_separa_presale(self):
        realizada = self.crear_funcion(-1)
        self.vender(realizada, 2, "2000.00")
        cancelada = self.crear_funcion(-1, hour=22, status=Screening.Status.CANCELED)
        self.vender(cancelada, 4, "4000.00")
        proxima = self.crear_funcion(2, status=Screening.Status.PUBLISHED)
        self.vender(proxima, 5, "5000.00")

        dashboard = build_dashboard("30", now=self.now)

        self.assertEqual(dashboard["summary"]["sold"], 2)
        self.assertEqual(dashboard["summary"]["revenue"], Decimal("2000.00"))
        self.assertEqual(dashboard["presale"]["screenings"], 1)
        self.assertEqual(dashboard["presale"]["sold"], 5)
        self.assertEqual(dashboard["presale"]["revenue"], Decimal("5000.00"))

    def test_period_filtra_funciones_por_date(self):
        self.vender(self.crear_funcion(-3), 1, "1000.00")
        self.vender(self.crear_funcion(-20), 2, "2000.00")

        self.assertEqual(build_dashboard("7", now=self.now)["summary"]["sold"], 1)
        self.assertEqual(build_dashboard("30", now=self.now)["summary"]["sold"], 3)
        self.assertEqual(build_dashboard("todo", now=self.now)["summary"]["sold"], 3)

    def test_period_invalido_usa_ultimos_30_days(self):
        dashboard = build_dashboard("cualquiera", now=self.now)

        self.assertEqual(dashboard["period"], "30")
        self.assertEqual(dashboard["start"], timezone.localdate(self.now) - timedelta(days=29))

    def test_variation_compares_with_previous_period(self):
        self.vender(self.crear_funcion(-2), 3, "3000.00")
        self.vender(self.crear_funcion(-9), 2, "2000.00")

        deltas = build_dashboard("7", now=self.now)["deltas"]

        self.assertEqual(deltas["revenue"]["direction"], "up")
        self.assertAlmostEqual(deltas["revenue"]["value"], 50.0)
        self.assertEqual(deltas["sold"]["sign"], "+")
        self.assertEqual(deltas["occupancy"]["direction"], "up")
        self.assertAlmostEqual(deltas["occupancy"]["value"], 10.0)

    def test_serie_de_revenue_agrupa_por_day_o_semana(self):
        self.vender(self.crear_funcion(-1), 2, "2000.00")
        self.vender(self.crear_funcion(-1, hour=22), 1, "1500.00")

        serie_mensual = build_dashboard("30", now=self.now)["revenue"]
        serie_trimestral = build_dashboard("90", now=self.now)["revenue"]

        self.assertEqual(serie_mensual["granularity"], "day")
        self.assertEqual(len(serie_mensual["columns"]), 30)
        pico = [column for column in serie_mensual["columns"] if column["is_peak"]]
        self.assertEqual(len(pico), 1)
        self.assertEqual(pico[0]["revenue"], Decimal("3500.00"))
        self.assertEqual(pico[0]["height_css"], "87.50%")
        self.assertEqual(serie_trimestral["granularity"], "week")
        self.assertEqual(
            sum(column["revenue"] for column in serie_trimestral["columns"]),
            Decimal("3500.00"),
        )

    def test_top_movies_ordena_por_entradas_sold(self):
        otra = self.crear_pelicula("Pelicula B")
        self.vender(self.crear_funcion(-2), 2, "2000.00")
        self.vender(self.crear_funcion(-1, movie=otra), 5, "5000.00")

        ranking = build_dashboard("30", now=self.now)["movies"]

        self.assertEqual([data["movie"].title for data in ranking], ["Pelicula B", "Pelicula A"])
        self.assertEqual(ranking[0]["width_css"], "100.00%")
        self.assertEqual(ranking[1]["width_css"], "40.00%")

    def test_time_slots_destaca_la_slot_con_mas_entradas(self):
        self.vender(self.crear_funcion(-2, hour=16), 1, "1000.00")
        noche = self.crear_funcion(-1, hour=21)
        self.vender(noche, 6, "6000.00")

        time_slots = build_dashboard("30", now=self.now)["time_slots"]

        self.assertEqual(time_slots["hours"], list(range(16, 22)))
        slot = time_slots["top"][0]
        self.assertEqual(slot["hour"], 21)
        self.assertEqual(slot["day"], WEEKDAYS[timezone.localtime(noche.starts_at).weekday()])
        self.assertEqual(slot["sold"], 6)
        self.assertAlmostEqual(slot["occupancy"], 60.0)

    def test_dashboard_renderiza_anchos_css_con_punto_decimal(self):
        screening = self.crear_funcion(-1, now=timezone.now())
        self.vender(screening, 3, "3000.00", used=1)
        self.client.force_login(self.gerente)

        response = self.client.get(reverse("manager:dashboard"))

        self.assertContains(response, 'style="width: 33.33%"')
        self.assertContains(response, "33,3%")
