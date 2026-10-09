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

from domain.cinema.models import ConfiguracionCine
from domain.movies.models import Pelicula
from domain.rooms.models import Sala
from domain.seats.models import Seat
from domain.seat_types.models import SeatType
from domain.screenings.models import Funcion
from domain.tickets.models import CompraAsiento, CompraEntrada
from domain.users.models import Acomodador, Cliente, Gerente

from .dashboard import DIAS_SEMANA, construir_dashboard
from .forms import PeliculaForm


def crear_sala_con_butacas(nombre, capacidad):
    sala = Sala.objects.create(nombre=nombre)
    tipo = SeatType.objects.order_by("pk").first()
    Seat.objects.bulk_create(
        Seat(sala=sala, fila=index // 20, columna=index % 20, tipo=tipo)
        for index in range(capacidad)
    )
    return sala


class ManagerAccessTests(TestCase):
    def setUp(self):
        self.password = "PasswordSegura123!"
        self.gerente = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password=self.password,
        )
        Gerente.objects.create(usuario=self.gerente)
        self.acomodador = get_user_model().objects.create_user(
            username="acomodador@mail.com",
            email="acomodador@mail.com",
            password=self.password,
        )
        Acomodador.objects.create(usuario=self.acomodador)
        self.cliente = get_user_model().objects.create_user(
            username="cliente@mail.com",
            email="cliente@mail.com",
            password=self.password,
        )
        Cliente.objects.create(usuario=self.cliente)

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
        sala = crear_sala_con_butacas("Sala progreso", 10)
        pelicula = Pelicula.objects.create(
            titulo="Pelicula progreso",
            sinopsis="Sinopsis",
            genero=Pelicula.Genero.ACCION,
            clasificacion=Pelicula.Clasificacion.MAS_13,
            duracion_minutos=120,
            imagen="peliculas/test.jpg",
        )
        funcion = Funcion.objects.create(
            pelicula=pelicula,
            sala=sala,
            fecha_horario=timezone.now() + timedelta(days=1),
            precio_entrada="1000.00",
            estado=Funcion.Estado.PUBLICADA,
        )
        CompraEntrada.comprar(self.cliente, funcion, 3)
        self.client.force_login(self.gerente)

        response = self.client.get(reverse("manager:home"))

        self.assertContains(response, "schedule-progress")
        self.assertContains(response, "3 vendidas")
        self.assertContains(response, "<strong>30%</strong>", html=True)

    def test_link_inicio_del_manager_apunta_al_home_de_gestion(self):
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
                "reserva_asientos_minutos": 7,
                "recarga_asientos_segundos": 12,
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("manager:configuracion"))
        configuracion = ConfiguracionCine.objects.get()
        self.assertEqual(configuracion.reserva_asientos_minutos, 7)
        self.assertEqual(configuracion.recarga_asientos_segundos, 12)

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
        Gerente.objects.create(usuario=self.gerente)
        self.otro_gerente = get_user_model().objects.create_user(
            username="otro-gerente@mail.com",
            email="otro-gerente@mail.com",
            password="PasswordSegura123!",
        )
        Gerente.objects.create(usuario=self.otro_gerente)
        self.usuario = get_user_model().objects.create_user(
            username="cliente@mail.com",
            email="cliente@mail.com",
            first_name="Ana",
            last_name="Gomez",
            password="PasswordSegura123!",
        )
        Cliente.objects.create(usuario=self.usuario)
        self.client.force_login(self.gerente)

    def test_gerente_lista_usuarios(self):
        response = self.client.get(reverse("manager:usuarios_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cliente@mail.com")
        self.assertContains(response, "cliente")
        self.assertContains(response, reverse("manager:usuarios_update", args=[self.gerente.pk]))
        self.assertNotContains(
            response, reverse("manager:usuarios_update", args=[self.otro_gerente.pk])
        )

    def test_gerente_modifica_usuario(self):
        response = self.client.post(
            reverse("manager:usuarios_update", args=[self.usuario.pk]),
            data={
                "first_name": "Ana Maria",
                "last_name": "Gomez",
                "email": "ana@mail.com",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, reverse("manager:usuarios_list"))
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.first_name, "Ana Maria")
        self.assertEqual(self.usuario.email, "ana@mail.com")
        self.assertEqual(self.usuario.username, "ana@mail.com")

    def test_edicion_usuario_muestra_boton_bloquear_sin_checkbox_activo(self):
        response = self.client.get(reverse("manager:usuarios_update", args=[self.usuario.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Usuario activo")
        self.assertContains(response, "Bloquear")
        self.assertContains(response, "no va a poder acceder al sitio")

    def test_gerente_bloquea_usuario(self):
        response = self.client.post(reverse("manager:usuarios_toggle", args=[self.usuario.pk]))

        self.assertRedirects(response, reverse("manager:usuarios_list"))
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.is_active)

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
        Gerente.objects.create(usuario=self.gerente)
        self.client.force_login(self.gerente)

    def test_gerente_crea_sala(self):
        tipo = SeatType.objects.order_by("pk").first()
        layout = {
            "rows": 1,
            "columns": 2,
            "seats": [
                {"row": 0, "column": 0, "type": tipo.nombre},
                {"row": 0, "column": 1, "type": tipo.nombre},
            ],
        }
        response = self.client.post(
            reverse("manager:salas_create"),
            data={
                "nombre": "Sala 1",
                "layout_sala": json.dumps(layout),
            },
        )

        self.assertRedirects(response, reverse("manager:salas_list"))
        sala = Sala.objects.get(nombre="Sala 1")
        self.assertEqual(sala.capacidad, 2)

    def test_sala_duplicada_mantiene_layout_en_formulario(self):
        crear_sala_con_butacas("Sala 1", 120)
        layout = {
            "rows": 8,
            "columns": 12,
            "seats": [
                {"row": 0, "column": 0, "type": "Estándar"},
                {"row": 0, "column": 1, "type": "Preferencial"},
            ],
        }

        response = self.client.post(
            reverse("manager:salas_create"),
            data={
                "nombre": "Sala 1",
                "layout_sala": json.dumps(layout),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"]["layout_sala"].value(), json.dumps(layout))

    def test_gerente_crea_sala_con_pasillos_y_guarda_tamano_de_layout(self):
        layout = {
            "rows": 3,
            "columns": 4,
            "seats": [
                {"row": 0, "column": 0, "type": "Estándar"},
                {"row": 2, "column": 3, "type": "Preferencial"},
            ],
        }

        response = self.client.post(
            reverse("manager:salas_create"),
            data={
                "nombre": "Sala con pasillos",
                "layout_sala": json.dumps(layout),
            },
        )

        self.assertRedirects(response, reverse("manager:salas_list"))
        sala = Sala.objects.get(nombre="Sala con pasillos")
        self.assertEqual(sala.capacidad, 2)
        self.assertEqual(sala.layout_configuracion["rows"], 3)
        self.assertEqual(sala.layout_configuracion["columns"], 4)
        self.assertEqual(sala.seats.count(), 2)

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
            {"order": "capacidad_desc"},
        )

        object_list = list(response.context["page_obj"].object_list)
        self.assertContains(response, "Ordenar por")
        self.assertEqual(object_list[0], grande)
        self.assertEqual(object_list[1], chica)

    def test_formulario_edicion_sala_muestra_titulo_especifico(self):
        sala = crear_sala_con_butacas("Sala 1", 120)

        response = self.client.get(reverse("manager:salas_update", args=[sala.pk]))

        self.assertContains(response, "Editar sala")
        self.assertNotContains(response, "Guardar registro")

    def test_formulario_edicion_sala_precarga_layout_existente(self):
        sala = Sala.objects.create(nombre="Sala 1")
        tipo_estandar = SeatType.objects.get(nombre="Estándar")
        tipo_preferencial = SeatType.objects.get(nombre="Preferencial")
        Seat.objects.create(sala=sala, fila=0, columna=0, tipo=tipo_estandar)
        Seat.objects.create(sala=sala, fila=1, columna=2, tipo=tipo_preferencial)

        response = self.client.get(reverse("manager:salas_update", args=[sala.pk]))

        layout_value = response.context["form"]["layout_sala"].value()
        layout = json.loads(layout_value)
        self.assertEqual(layout["rows"], 2)
        self.assertEqual(layout["columns"], 3)
        self.assertIn({"row": 0, "column": 0, "type": "Estándar"}, layout["seats"])
        self.assertIn({"row": 1, "column": 2, "type": "Preferencial"}, layout["seats"])

    def test_formulario_edicion_sala_normaliza_layout_guardado_con_ids(self):
        tipo_estandar = SeatType.objects.get(nombre="Estándar")
        sala = Sala.objects.create(
            nombre="Sala con layout viejo",
            layout_configuracion={
                "rows": 4,
                "columns": 6,
                "seats": [{"row": 2, "column": 5, "type": tipo_estandar.pk}],
            },
        )
        Seat.objects.create(sala=sala, fila=2, columna=5, tipo=tipo_estandar)

        response = self.client.get(reverse("manager:salas_update", args=[sala.pk]))

        layout = json.loads(response.context["form"]["layout_sala"].value())
        self.assertEqual(layout["rows"], 4)
        self.assertEqual(layout["columns"], 6)
        self.assertEqual(layout["seats"], [{"row": 2, "column": 5, "type": "Estándar"}])

    def test_gerente_elimina_sala(self):
        sala = crear_sala_con_butacas("Sala 1", 120)

        response = self.client.post(reverse("manager:salas_delete", args=[sala.pk]))

        self.assertRedirects(response, reverse("manager:salas_list"))
        self.assertFalse(Sala.objects.filter(pk=sala.pk).exists())


class ManagerSeatTypesTests(TestCase):
    def setUp(self):
        self.gerente = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password="PasswordSegura123!",
        )
        Gerente.objects.create(usuario=self.gerente)
        self.client.force_login(self.gerente)

    def test_gerente_lista_tipos_de_butaca(self):
        response = self.client.get(reverse("manager:seat_types_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Estándar")
        self.assertContains(response, "Precio")

    def test_gerente_crea_tipo_de_butaca_con_precio(self):
        response = self.client.post(
            reverse("manager:seat_types_create"),
            data={
                "nombre": "Premium",
                "precio_base": "2500.00",
                "color": "#111827",
            },
        )

        self.assertRedirects(response, reverse("manager:seat_types_list"))
        tipo = SeatType.objects.get(nombre="Premium")
        self.assertEqual(tipo.precio_base, Decimal("2500.00"))

    def test_no_permite_tipo_de_butaca_con_precio_cero(self):
        response = self.client.post(
            reverse("manager:seat_types_create"),
            data={
                "nombre": "Gratis",
                "precio_base": "0.00",
                "color": "#111827",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SeatType.objects.filter(nombre="Gratis").exists())
        self.assertIn("precio_base", response.context["form"].errors)

    def test_no_elimina_tipo_de_butaca_usado_en_sala(self):
        sala = Sala.objects.create(nombre="Sala 1")
        tipo = SeatType.objects.get(nombre="Estándar")
        Seat.objects.create(sala=sala, fila=0, columna=0, tipo=tipo)

        response = self.client.post(
            reverse("manager:seat_types_delete", args=[tipo.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse("manager:seat_types_list"))
        self.assertTrue(SeatType.objects.filter(pk=tipo.pk).exists())
        self.assertContains(response, "No se puede eliminar")


SMALL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"D\x01\x00;"
)

class ManagerPeliculasTests(TestCase):
    def test_pelicula_form_rechaza_imagen_muy_pesada(self):
        imagen = SimpleUploadedFile(
            "poster.gif",
            SMALL_GIF + (b"0" * (2 * 1024 * 1024 + 1)),
            content_type="image/gif",
        )
        form = PeliculaForm(
            data={
                "titulo": "Pelicula",
                "sinopsis": "Sinopsis",
                "genero": Pelicula.Genero.ACCION,
                "clasificacion": Pelicula.Clasificacion.MAS_13,
                "duracion_minutos": 100,
            },
            files={"imagen": imagen},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("imagen", form.errors)
        self.assertIn("La imagen no puede superar los 2 MB.", form.errors["imagen"])


class ManagerFuncionesTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp()
        cls.override_media_root = override_settings(MEDIA_ROOT=cls.media_root)
        cls.override_media_root.enable()

    @classmethod
    def tearDownClass(cls):
        cls.override_media_root.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.gerente = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password="PasswordSegura123!",
        )
        Gerente.objects.create(usuario=self.gerente)
        self.client.force_login(self.gerente)
        self.sala = crear_sala_con_butacas("Sala 1", 120)
        self.pelicula = Pelicula.objects.create(
            titulo="Pelicula",
            sinopsis="Sinopsis",
            genero=Pelicula.Genero.ACCION,
            clasificacion=Pelicula.Clasificacion.MAS_13,
            duracion_minutos=100,
            imagen=SimpleUploadedFile(
                "poster.gif",
                SMALL_GIF,
                content_type="image/gif",
            ),
        )

    def fecha_form(self, fecha):
        return timezone.localtime(fecha).strftime("%Y-%m-%dT%H:%M")

    def fecha_futura(self, hora=20, minuto=30):
        fecha = timezone.datetime.combine(
            timezone.localdate() + timedelta(days=30),
            timezone.datetime.min.time(),
        ).replace(hour=hora, minute=minuto)
        return timezone.make_aware(fecha)

    def precios_por_tipo_form(self, precio="1500.00"):
        return json.dumps({
            str(seat_type.pk): precio
            for seat_type in SeatType.objects.all()
        })

    def test_gerente_crea_funcion_sin_publicarla(self):
        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "pelicula": self.pelicula.pk,
                "sala": self.sala.pk,
                "fecha_horario": self.fecha_form(self.fecha_futura()),
                "precios_por_tipo": self.precios_por_tipo_form(),
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        funcion = Funcion.objects.get()
        self.assertEqual(funcion.estado, Funcion.Estado.BORRADOR)

    def test_no_permite_crear_funcion_con_precio_cero(self):
        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "pelicula": self.pelicula.pk,
                "sala": self.sala.pk,
                "fecha_horario": self.fecha_form(timezone.now() + timedelta(days=1)),
                "precios_por_tipo": self.precios_por_tipo_form("0.00"),
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        funcion = Funcion.objects.get()
        self.assertEqual(funcion.precio_entrada, Decimal("1000.00"))

    def test_no_permite_crear_funcion_con_precio_negativo(self):
        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "pelicula": self.pelicula.pk,
                "sala": self.sala.pk,
                "fecha_horario": self.fecha_form(timezone.now() + timedelta(days=1)),
                "precios_por_tipo": self.precios_por_tipo_form("-1500.00"),
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        funcion = Funcion.objects.get()
        self.assertEqual(funcion.precio_entrada, Decimal("1000.00"))

    def test_no_permite_crear_funcion_con_fecha_pasada(self):
        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "pelicula": self.pelicula.pk,
                "sala": self.sala.pk,
                "fecha_horario": self.fecha_form(timezone.now() - timedelta(days=1)),
                "precio_entrada": "1500.00",
            },
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("fecha_horario", form.errors)
        self.assertIn("deben ser futuros", form.errors["fecha_horario"][0])
        self.assertEqual(Funcion.objects.count(), 0)

    def test_modelo_funcion_valida_precio_y_fecha(self):
        funcion = Funcion(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=timezone.now() - timedelta(days=1),
            precio_entrada="0.00",
        )

        with self.assertRaises(ValidationError) as error:
            funcion.full_clean()

        self.assertIn("precio_entrada", error.exception.message_dict)
        self.assertIn("fecha_horario", error.exception.message_dict)

    def crear_funcion(self, estado=Funcion.Estado.BORRADOR, fecha_horario=None):
        return Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=fecha_horario or self.fecha_futura(),
            precio_entrada="1500.00",
            estado=estado,
        )

    def cambiar_estado(self, funcion, estado):
        return self.client.post(
            reverse("manager:funciones_estado", args=[funcion.pk]),
            data={"estado": estado},
        )

    def vender_entradas(self, funcion, cantidad=1):
        cliente = get_user_model().objects.create_user(
            username="cliente@mail.com",
            email="cliente@mail.com",
            password="PasswordSegura123!",
        )
        CompraEntrada.comprar(cliente, funcion, cantidad)

    def test_gerente_recorre_el_ciclo_borrador_programada_publicada(self):
        funcion = self.crear_funcion()

        response = self.cambiar_estado(funcion, Funcion.Estado.PROGRAMADA)
        self.assertRedirects(response, reverse("manager:funciones_list"))
        funcion.refresh_from_db()
        self.assertEqual(funcion.estado, Funcion.Estado.PROGRAMADA)

        self.cambiar_estado(funcion, Funcion.Estado.PUBLICADA)
        funcion.refresh_from_db()
        self.assertEqual(funcion.estado, Funcion.Estado.PUBLICADA)

        self.cambiar_estado(funcion, Funcion.Estado.PROGRAMADA)
        funcion.refresh_from_db()
        self.assertEqual(funcion.estado, Funcion.Estado.PROGRAMADA)

        self.cambiar_estado(funcion, Funcion.Estado.BORRADOR)
        funcion.refresh_from_db()
        self.assertEqual(funcion.estado, Funcion.Estado.BORRADOR)

    def test_borrador_no_se_puede_publicar_directamente(self):
        funcion = self.crear_funcion()

        response = self.cambiar_estado(funcion, Funcion.Estado.PUBLICADA)

        self.assertRedirects(response, reverse("manager:funciones_list"))
        funcion.refresh_from_db()
        self.assertEqual(funcion.estado, Funcion.Estado.BORRADOR)

    def test_no_se_puede_forzar_finalizada_a_mano(self):
        funcion = self.crear_funcion(Funcion.Estado.PUBLICADA)

        self.cambiar_estado(funcion, Funcion.Estado.FINALIZADA)

        funcion.refresh_from_db()
        self.assertEqual(funcion.estado, Funcion.Estado.PUBLICADA)

    def test_publicada_con_ventas_no_se_puede_ocultar(self):
        funcion = self.crear_funcion(Funcion.Estado.PUBLICADA)
        self.vender_entradas(funcion)

        self.cambiar_estado(funcion, Funcion.Estado.PROGRAMADA)

        funcion.refresh_from_db()
        self.assertEqual(funcion.estado, Funcion.Estado.PUBLICADA)

    def test_no_se_puede_programar_un_borrador_con_fecha_pasada(self):
        funcion = self.crear_funcion(
            fecha_horario=timezone.now() - timedelta(days=1),
        )

        response = self.cambiar_estado(funcion, Funcion.Estado.PROGRAMADA)

        funcion.refresh_from_db()
        self.assertEqual(funcion.estado, Funcion.Estado.BORRADOR)
        self.assertContains(
            self.client.get(response.url),
            "No se puede programar ni publicar una función con fecha pasada.",
        )

    def test_gerente_cancela_funcion_publicada_con_ventas(self):
        funcion = self.crear_funcion(Funcion.Estado.PUBLICADA)
        self.vender_entradas(funcion, 3)

        response = self.client.get(reverse("manager:funciones_cancelar", args=[funcion.pk]))
        self.assertContains(response, "Confirmar cancelación")
        self.assertContains(response, "<strong>3</strong> entradas")

        self.cambiar_estado(funcion, Funcion.Estado.CANCELADA)

        funcion.refresh_from_db()
        self.assertEqual(funcion.estado, Funcion.Estado.CANCELADA)

    def test_funcion_cancelada_no_admite_mas_cambios(self):
        funcion = self.crear_funcion(Funcion.Estado.CANCELADA)

        self.cambiar_estado(funcion, Funcion.Estado.PUBLICADA)
        response = self.client.get(reverse("manager:funciones_cancelar", args=[funcion.pk]))

        self.assertRedirects(response, reverse("manager:funciones_list"))
        funcion.refresh_from_db()
        self.assertEqual(funcion.estado, Funcion.Estado.CANCELADA)

    def test_borrador_no_se_puede_cancelar(self):
        funcion = self.crear_funcion()

        self.cambiar_estado(funcion, Funcion.Estado.CANCELADA)

        funcion.refresh_from_db()
        self.assertEqual(funcion.estado, Funcion.Estado.BORRADOR)

    def test_funcion_publicada_con_ventas_no_se_puede_editar_ni_eliminar(self):
        funcion = self.crear_funcion(Funcion.Estado.PUBLICADA)
        self.vender_entradas(funcion)

        response = self.client.get(reverse("manager:funciones_update", args=[funcion.pk]))
        self.assertEqual(response.status_code, 403)

        response = self.client.post(reverse("manager:funciones_delete", args=[funcion.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Funcion.objects.filter(pk=funcion.pk).exists())

    def test_funcion_publicada_sin_ventas_se_puede_editar_pero_no_eliminar(self):
        funcion = self.crear_funcion(Funcion.Estado.PUBLICADA)

        response = self.client.get(reverse("manager:funciones_update", args=[funcion.pk]))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse("manager:funciones_delete", args=[funcion.pk]))
        self.assertEqual(response.status_code, 403)

    def test_funciones_cancelada_y_finalizada_son_solo_lectura(self):
        for estado in (Funcion.Estado.CANCELADA, Funcion.Estado.FINALIZADA):
            funcion = self.crear_funcion(estado, fecha_horario=self.fecha_futura(10, 0))

            response = self.client.get(reverse("manager:funciones_update", args=[funcion.pk]))
            self.assertEqual(response.status_code, 403)
            response = self.client.post(reverse("manager:funciones_delete", args=[funcion.pk]))
            self.assertEqual(response.status_code, 403)

            funcion.delete()

    def test_funcion_cancelada_no_ocupa_la_sala(self):
        self.crear_funcion(Funcion.Estado.CANCELADA, fecha_horario=self.fecha_futura(20, 0))

        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "pelicula": self.pelicula.pk,
                "sala": self.sala.pk,
                "fecha_horario": self.fecha_form(self.fecha_futura(20, 0)),
                "precio_entrada": "1500.00",
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        self.assertEqual(Funcion.objects.count(), 2)

    def test_funcion_terminada_pasa_a_finalizada_al_listar(self):
        # La película dura 100 minutos: empezó hace 3 horas, ya terminó.
        terminada = self.crear_funcion(
            Funcion.Estado.PUBLICADA,
            fecha_horario=timezone.now() - timedelta(hours=3),
        )
        # Empezó hace 30 minutos: todavía está en curso.
        en_curso = self.crear_funcion(
            Funcion.Estado.PUBLICADA,
            fecha_horario=timezone.now() - timedelta(minutes=30),
        )
        borrador_vencido = self.crear_funcion(
            fecha_horario=timezone.now() - timedelta(days=2),
        )

        self.client.get(reverse("manager:funciones_list"))

        terminada.refresh_from_db()
        en_curso.refresh_from_db()
        borrador_vencido.refresh_from_db()
        self.assertEqual(terminada.estado, Funcion.Estado.FINALIZADA)
        self.assertEqual(en_curso.estado, Funcion.Estado.PUBLICADA)
        self.assertEqual(borrador_vencido.estado, Funcion.Estado.BORRADOR)

    def test_lista_funciones_muestra_acciones_de_borrador(self):
        funcion = self.crear_funcion()

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "status-borrador")
        self.assertContains(response, "Programar")
        self.assertContains(response, 'class="publish-action"')
        self.assertContains(response, "Eliminar")
        self.assertNotContains(response, 'value="publicada"')
        self.assertNotContains(response, reverse("manager:funciones_cancelar", args=[funcion.pk]))

    def test_lista_funciones_muestra_acciones_de_programada(self):
        funcion = self.crear_funcion(Funcion.Estado.PROGRAMADA)

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "Publicar")
        self.assertContains(response, 'class="publish-action"')
        self.assertContains(response, "Volver a borrador")
        self.assertContains(response, reverse("manager:funciones_cancelar", args=[funcion.pk]))
        self.assertNotContains(response, 'value="programada"')

    def test_funciones_cancelada_y_finalizada_muestran_plantilla_sin_menu(self):
        for estado in (Funcion.Estado.CANCELADA, Funcion.Estado.FINALIZADA):
            funcion = self.crear_funcion(estado)

            response = self.client.get(reverse("manager:funciones_list"))

            self.assertContains(
                response,
                f'{reverse("manager:funciones_create")}?plantilla={funcion.pk}',
            )
            self.assertNotContains(response, 'class="row-menu"')
            funcion.delete()

    def test_lista_funciones_muestra_acciones_de_publicada(self):
        funcion = self.crear_funcion(Funcion.Estado.PUBLICADA)

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "Ocultar")
        self.assertContains(response, reverse("manager:funciones_cancelar", args=[funcion.pk]))
        self.assertNotContains(response, 'class="publish-action"')
        self.assertNotContains(response, "Eliminar")

    def test_lista_funciones_muestra_precio_con_simbolo_pesos(self):
        Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(),
            precio_entrada="1500.00",
            estado=Funcion.Estado.BORRADOR,
        )

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "$1000,00")

    def test_lista_funciones_ordena_por_mayor_precio(self):
        tipo_caro = SeatType.objects.create(
            nombre="Premium",
            precio_base="2500.00",
            color="#111827",
        )
        sala_cara = Sala.objects.create(nombre="Sala premium")
        Seat.objects.create(sala=sala_cara, fila=0, columna=0, tipo=tipo_caro)
        barata = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(20, 30),
            precio_entrada="1.00",
            estado=Funcion.Estado.BORRADOR,
        )
        cara = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=sala_cara,
            fecha_horario=self.fecha_futura(22, 30),
            precio_entrada="1.00",
            estado=Funcion.Estado.BORRADOR,
        )

        response = self.client.get(
            reverse("manager:funciones_list"),
            {"order": "precio_desc"},
        )

        object_list = list(response.context["page_obj"].object_list)
        self.assertEqual(object_list[0], cara)
        self.assertEqual(object_list[1], barata)

    def test_lista_funciones_muestra_link_para_usar_como_plantilla(self):
        funcion = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(),
            precio_entrada="1500.00",
            estado=Funcion.Estado.BORRADOR,
        )

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "Usar como plantilla")
        self.assertContains(
            response,
            f'{reverse("manager:funciones_create")}?plantilla={funcion.pk}',
        )

    def test_crear_funcion_desde_plantilla_precarga_datos(self):
        funcion = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(),
            precio_entrada="1500.00",
            estado=Funcion.Estado.PUBLICADA,
        )

        response = self.client.get(
            reverse("manager:funciones_create"),
            {"plantilla": funcion.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial["pelicula"], self.pelicula)
        self.assertEqual(response.context["form"].initial["sala"], self.sala)
        self.assertEqual(
            response.context["form"].initial["fecha_horario"],
            funcion.fecha_horario,
        )
        self.assertNotIn("precios_por_tipo", response.context["form"].initial)
        self.assertContains(
            response,
            f'value="{self.fecha_form(funcion.fecha_horario)}"',
        )

    def test_lista_funciones_muestra_entradas_vendidas_y_disponibles(self):
        funcion = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(),
            precio_entrada="1500.00",
            estado=Funcion.Estado.PUBLICADA,
        )
        cliente = get_user_model().objects.create_user(
            username="cliente@mail.com",
            email="cliente@mail.com",
            password="PasswordSegura123!",
        )
        CompraEntrada.comprar(cliente, funcion, 35)

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "Vendidas")
        self.assertContains(response, "Disponibles")
        self.assertContains(response, '<td data-label="Vendidas">35</td>', html=True)
        self.assertNotContains(response, "sales-progress")
        self.assertContains(response, '<td data-label="Disponibles">85</td>', html=True)

    def test_funcion_publicada_mantiene_snapshot_de_capacidad_de_sala(self):
        funcion = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(),
            precio_entrada="1500.00",
            estado=Funcion.Estado.PUBLICADA,
        )

        self.sala.seats.exclude(pk=self.sala.seats.first().pk).delete()

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertEqual(funcion.capacidad_snapshot, 120)
        self.assertContains(response, '<td data-label="Disponibles">120</td>', html=True)

    def test_fecha_de_funcion_se_precarga_al_editar(self):
        funcion = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(),
            precio_entrada="1500.00",
            estado=Funcion.Estado.BORRADOR,
        )

        response = self.client.get(reverse("manager:funciones_update", args=[funcion.pk]))

        self.assertContains(
            response,
            f'value="{self.fecha_form(funcion.fecha_horario)}"',
        )

    def test_no_permite_funciones_solapadas_en_misma_sala(self):
        Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(20, 0),
            precio_entrada="1500.00",
            estado=Funcion.Estado.BORRADOR,
        )

        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "pelicula": self.pelicula.pk,
                "sala": self.sala.pk,
                "fecha_horario": self.fecha_form(self.fecha_futura(21, 0)),
                "precio_entrada": "1500.00",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La sala ya tiene una funcion programada")
        self.assertEqual(Funcion.objects.count(), 1)

    def test_permite_funciones_en_misma_sala_cuando_no_se_solapan(self):
        Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(20, 0),
            precio_entrada="1500.00",
            estado=Funcion.Estado.BORRADOR,
        )

        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "pelicula": self.pelicula.pk,
                "sala": self.sala.pk,
                "fecha_horario": self.fecha_form(self.fecha_futura(21, 40)),
                "precio_entrada": "1500.00",
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        self.assertEqual(Funcion.objects.count(), 2)

    def test_permite_funciones_solapadas_en_salas_distintas(self):
        otra_sala = crear_sala_con_butacas("Sala 2", 80)
        Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(20, 0),
            precio_entrada="1500.00",
            estado=Funcion.Estado.BORRADOR,
        )

        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "pelicula": self.pelicula.pk,
                "sala": otra_sala.pk,
                "fecha_horario": self.fecha_form(self.fecha_futura(21, 0)),
                "precio_entrada": "1500.00",
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        self.assertEqual(Funcion.objects.count(), 2)

    def test_editar_funcion_no_colisiona_consigo_misma(self):
        funcion = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(20, 0),
            precio_entrada="1500.00",
            estado=Funcion.Estado.BORRADOR,
        )
        SeatType.objects.filter(seats__sala=self.sala).update(precio_base="1600.00")

        response = self.client.post(
            reverse("manager:funciones_update", args=[funcion.pk]),
            data={
                "pelicula": self.pelicula.pk,
                "sala": self.sala.pk,
                "fecha_horario": self.fecha_form(self.fecha_futura(20, 0)),
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        funcion.refresh_from_db()
        self.assertEqual(str(funcion.precio_entrada), "1600.00")


class ManagerDashboardTests(TestCase):
    def setUp(self):
        self.gerente = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password="PasswordSegura123!",
        )
        Gerente.objects.create(usuario=self.gerente)
        self.cliente = get_user_model().objects.create_user(
            username="cliente@mail.com",
            email="cliente@mail.com",
            password="PasswordSegura123!",
        )
        self.sala = crear_sala_con_butacas("Sala 1", 10)
        self.pelicula = self.crear_pelicula("Pelicula A")
        self.ahora = timezone.make_aware(datetime(2026, 10, 8, 23, 0))

    def crear_pelicula(self, titulo):
        return Pelicula.objects.create(
            titulo=titulo,
            sinopsis="Sinopsis",
            genero=Pelicula.Genero.ACCION,
            clasificacion=Pelicula.Clasificacion.MAS_13,
            duracion_minutos=100,
            imagen="peliculas/poster.gif",
        )

    def crear_funcion(self, dias, hora=20, estado=Funcion.Estado.FINALIZADA, pelicula=None, ahora=None):
        fecha = timezone.localdate(ahora or self.ahora) + timedelta(days=dias)
        return Funcion.objects.create(
            pelicula=pelicula or self.pelicula,
            sala=self.sala,
            fecha_horario=timezone.make_aware(datetime.combine(fecha, datetime.min.time()).replace(hour=hora)),
            precio_entrada="1000.00",
            estado=estado,
        )

    def vender(self, funcion, cantidad, total, utilizadas=0):
        compra = CompraEntrada.objects.create(
            usuario=self.cliente,
            funcion=funcion,
            cantidad=cantidad,
            total=Decimal(total),
        )
        for indice in range(cantidad):
            CompraAsiento.objects.create(
                compra=compra,
                funcion=funcion,
                label=f"{compra.pk}-{indice}",
                utilizada_en=self.ahora if indice < utilizadas else None,
            )
        return compra

    def test_gerente_ve_dashboard(self):
        self.client.force_login(self.gerente)

        response = self.client.get(reverse("manager:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recaudación simulada")
        self.assertContains(response, "Vendidas vs. utilizadas")
        self.assertContains(response, "Películas más vistas")
        self.assertContains(response, "Ocupación por sala")
        self.assertContains(response, "Horarios de mayor demanda")

    def test_acomodador_no_puede_ver_dashboard(self):
        acomodador = get_user_model().objects.create_user(
            username="acomodador@mail.com",
            email="acomodador@mail.com",
            password="PasswordSegura123!",
        )
        Acomodador.objects.create(usuario=acomodador)
        self.client.force_login(acomodador)

        response = self.client.get(reverse("manager:dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_menu_del_gerente_enlaza_al_dashboard(self):
        self.client.force_login(self.gerente)

        response = self.client.get(reverse("manager:home"))

        self.assertContains(response, f'href="{reverse("manager:dashboard")}"')

    def test_resumen_calcula_recaudacion_ocupacion_y_asistencia(self):
        primera = self.crear_funcion(-2)
        self.vender(primera, 3, "3000.00", utilizadas=2)
        self.vender(primera, 2, "2500.00")
        segunda = self.crear_funcion(-1, hora=18, estado=Funcion.Estado.PUBLICADA)
        self.vender(segunda, 1, "1000.00")

        resumen = construir_dashboard("30", ahora=self.ahora)["resumen"]

        self.assertEqual(resumen["funciones"], 2)
        self.assertEqual(resumen["vendidas"], 6)
        self.assertEqual(resumen["recaudacion"], Decimal("6500.00"))
        self.assertEqual(resumen["capacidad"], 20)
        self.assertAlmostEqual(resumen["ocupacion"], 30.0)
        self.assertEqual(resumen["utilizadas"], 2)
        self.assertEqual(resumen["no_utilizadas"], 4)
        self.assertAlmostEqual(resumen["asistencia"], 100 / 3)

    def test_excluye_canceladas_y_separa_preventa(self):
        realizada = self.crear_funcion(-1)
        self.vender(realizada, 2, "2000.00")
        cancelada = self.crear_funcion(-1, hora=22, estado=Funcion.Estado.CANCELADA)
        self.vender(cancelada, 4, "4000.00")
        proxima = self.crear_funcion(2, estado=Funcion.Estado.PUBLICADA)
        self.vender(proxima, 5, "5000.00")

        dashboard = construir_dashboard("30", ahora=self.ahora)

        self.assertEqual(dashboard["resumen"]["vendidas"], 2)
        self.assertEqual(dashboard["resumen"]["recaudacion"], Decimal("2000.00"))
        self.assertEqual(dashboard["preventa"]["funciones"], 1)
        self.assertEqual(dashboard["preventa"]["vendidas"], 5)
        self.assertEqual(dashboard["preventa"]["recaudacion"], Decimal("5000.00"))

    def test_periodo_filtra_funciones_por_fecha(self):
        self.vender(self.crear_funcion(-3), 1, "1000.00")
        self.vender(self.crear_funcion(-20), 2, "2000.00")

        self.assertEqual(construir_dashboard("7", ahora=self.ahora)["resumen"]["vendidas"], 1)
        self.assertEqual(construir_dashboard("30", ahora=self.ahora)["resumen"]["vendidas"], 3)
        self.assertEqual(construir_dashboard("todo", ahora=self.ahora)["resumen"]["vendidas"], 3)

    def test_periodo_invalido_usa_ultimos_30_dias(self):
        dashboard = construir_dashboard("cualquiera", ahora=self.ahora)

        self.assertEqual(dashboard["periodo"], "30")
        self.assertEqual(dashboard["desde"], timezone.localdate(self.ahora) - timedelta(days=29))

    def test_variacion_compara_con_el_periodo_anterior(self):
        self.vender(self.crear_funcion(-2), 3, "3000.00")
        self.vender(self.crear_funcion(-9), 2, "2000.00")

        variaciones = construir_dashboard("7", ahora=self.ahora)["variaciones"]

        self.assertEqual(variaciones["recaudacion"]["direccion"], "up")
        self.assertAlmostEqual(variaciones["recaudacion"]["valor"], 50.0)
        self.assertEqual(variaciones["vendidas"]["signo"], "+")
        self.assertEqual(variaciones["ocupacion"]["direccion"], "up")
        self.assertAlmostEqual(variaciones["ocupacion"]["valor"], 10.0)

    def test_serie_de_recaudacion_agrupa_por_dia_o_semana(self):
        self.vender(self.crear_funcion(-1), 2, "2000.00")
        self.vender(self.crear_funcion(-1, hora=22), 1, "1500.00")

        serie_mensual = construir_dashboard("30", ahora=self.ahora)["recaudacion"]
        serie_trimestral = construir_dashboard("90", ahora=self.ahora)["recaudacion"]

        self.assertEqual(serie_mensual["granularidad"], "dia")
        self.assertEqual(len(serie_mensual["columnas"]), 30)
        pico = [columna for columna in serie_mensual["columnas"] if columna["es_maximo"]]
        self.assertEqual(len(pico), 1)
        self.assertEqual(pico[0]["recaudacion"], Decimal("3500.00"))
        self.assertEqual(pico[0]["altura_css"], "87.50%")
        self.assertEqual(serie_trimestral["granularidad"], "semana")
        self.assertEqual(
            sum(columna["recaudacion"] for columna in serie_trimestral["columnas"]),
            Decimal("3500.00"),
        )

    def test_peliculas_mas_vistas_ordena_por_entradas_vendidas(self):
        otra = self.crear_pelicula("Pelicula B")
        self.vender(self.crear_funcion(-2), 2, "2000.00")
        self.vender(self.crear_funcion(-1, pelicula=otra), 5, "5000.00")

        ranking = construir_dashboard("30", ahora=self.ahora)["peliculas"]

        self.assertEqual([datos["pelicula"].titulo for datos in ranking], ["Pelicula B", "Pelicula A"])
        self.assertEqual(ranking[0]["ancho_css"], "100.00%")
        self.assertEqual(ranking[1]["ancho_css"], "40.00%")

    def test_horarios_destaca_la_franja_con_mas_entradas(self):
        self.vender(self.crear_funcion(-2, hora=16), 1, "1000.00")
        noche = self.crear_funcion(-1, hora=21)
        self.vender(noche, 6, "6000.00")

        horarios = construir_dashboard("30", ahora=self.ahora)["horarios"]

        self.assertEqual(horarios["horas"], list(range(16, 22)))
        franja = horarios["top"][0]
        self.assertEqual(franja["hora"], 21)
        self.assertEqual(franja["dia"], DIAS_SEMANA[timezone.localtime(noche.fecha_horario).weekday()])
        self.assertEqual(franja["vendidas"], 6)
        self.assertAlmostEqual(franja["ocupacion"], 60.0)

    def test_dashboard_renderiza_anchos_css_con_punto_decimal(self):
        funcion = self.crear_funcion(-1, ahora=timezone.now())
        self.vender(funcion, 3, "3000.00", utilizadas=1)
        self.client.force_login(self.gerente)

        response = self.client.get(reverse("manager:dashboard"))

        self.assertContains(response, 'style="width: 33.33%"')
        self.assertContains(response, "33,3%")
