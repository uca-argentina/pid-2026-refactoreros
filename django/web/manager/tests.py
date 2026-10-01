import shutil
import tempfile
import json
from datetime import timedelta
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
from domain.tickets.models import CompraEntrada
from domain.users.models import Acomodador, Cliente, Gerente

from .forms import PeliculaForm


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
        self.assertContains(response, "Películas")
        self.assertContains(response, "Funciones")

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
        response = self.client.post(
            reverse("manager:salas_create"),
            data={
                "nombre": "Sala 1",
                "capacidad": 120,
            },
        )

        self.assertRedirects(response, reverse("manager:salas_list"))
        self.assertTrue(Sala.objects.filter(nombre="Sala 1", capacidad=120).exists())

    def test_sala_duplicada_mantiene_layout_en_formulario(self):
        Sala.objects.create(nombre="Sala 1", capacidad=120)
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
            Sala.objects.create(nombre=f"Sala {index:02d}", capacidad=80)
        Sala.objects.create(nombre="Microcine", capacidad=30)

        response = self.client.get(
            reverse("manager:salas_list"),
            {"q": "Sala", "per_page": "10"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 10)
        self.assertContains(response, "Sala 00")
        self.assertNotContains(response, "Microcine")

    def test_gerente_ordena_salas_por_capacidad(self):
        chica = Sala.objects.create(nombre="Sala chica", capacidad=80)
        grande = Sala.objects.create(nombre="Sala grande", capacidad=180)

        response = self.client.get(
            reverse("manager:salas_list"),
            {"order": "capacidad_desc"},
        )

        object_list = list(response.context["page_obj"].object_list)
        self.assertContains(response, "Ordenar por")
        self.assertEqual(object_list[0], grande)
        self.assertEqual(object_list[1], chica)

    def test_formulario_edicion_sala_muestra_titulo_especifico(self):
        sala = Sala.objects.create(nombre="Sala 1", capacidad=120)

        response = self.client.get(reverse("manager:salas_update", args=[sala.pk]))

        self.assertContains(response, "Editar sala")
        self.assertNotContains(response, "Guardar registro")

    def test_formulario_edicion_sala_precarga_layout_existente(self):
        sala = Sala.objects.create(nombre="Sala 1", capacidad=2)
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
            capacidad=1,
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
        sala = Sala.objects.create(nombre="Sala 1", capacidad=120)

        response = self.client.post(reverse("manager:salas_delete", args=[sala.pk]))

        self.assertRedirects(response, reverse("manager:salas_list"))
        self.assertFalse(Sala.objects.filter(pk=sala.pk).exists())


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
        self.sala = Sala.objects.create(nombre="Sala 1", capacidad=120)
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
        self.assertFalse(funcion.publicada)

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

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("precios_por_tipo", form.errors)
        self.assertIn("mayores a cero", form.errors["precios_por_tipo"][0])
        self.assertEqual(Funcion.objects.count(), 0)

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

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("precios_por_tipo", form.errors)
        self.assertIn("mayores a cero", form.errors["precios_por_tipo"][0])
        self.assertEqual(Funcion.objects.count(), 0)

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

    def test_gerente_publica_y_oculta_funcion_desde_la_lista(self):
        funcion = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(),
            precio_entrada="1500.00",
            publicada=False,
        )

        response = self.client.post(reverse("manager:funciones_toggle", args=[funcion.pk]))

        self.assertRedirects(response, reverse("manager:funciones_list"))
        funcion.refresh_from_db()
        self.assertTrue(funcion.publicada)

        response = self.client.post(reverse("manager:funciones_toggle", args=[funcion.pk]))

        self.assertRedirects(response, reverse("manager:funciones_list"))
        funcion.refresh_from_db()
        self.assertFalse(funcion.publicada)

    def test_lista_funciones_muestra_boton_segun_estado(self):
        Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(),
            precio_entrada="1500.00",
            publicada=False,
        )

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "Publicar")
        self.assertContains(response, 'class="publish-action"')
        self.assertNotContains(response, 'title="Ocultar"')

    def test_lista_funciones_muestra_ocultar_sin_estilo_verde(self):
        Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(),
            precio_entrada="1500.00",
            publicada=True,
        )

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "Ocultar")
        self.assertNotContains(response, 'class="publish-action"')

    def test_lista_funciones_muestra_precio_con_simbolo_pesos(self):
        Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(),
            precio_entrada="1500.00",
            publicada=False,
        )

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "$1500,00")

    def test_lista_funciones_ordena_por_mayor_precio(self):
        barata = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(20, 30),
            precio_entrada="1000.00",
            publicada=False,
        )
        cara = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(22, 30),
            precio_entrada="2500.00",
            publicada=False,
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
            publicada=False,
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
            publicada=True,
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
        self.assertEqual(
            response.context["form"].initial["precios_por_tipo"],
            funcion.precios_por_tipo,
        )
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
            publicada=True,
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
        self.assertContains(response, '<td data-label="Disponibles">85</td>', html=True)

    def test_funcion_publicada_mantiene_snapshot_de_capacidad_de_sala(self):
        funcion = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(),
            precio_entrada="1500.00",
            publicada=True,
        )

        self.sala.capacidad = 1
        self.sala.save(update_fields=["capacidad"])

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertEqual(funcion.capacidad_snapshot, 120)
        self.assertContains(response, '<td data-label="Disponibles">120</td>', html=True)

    def test_fecha_de_funcion_se_precarga_al_editar(self):
        funcion = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(),
            precio_entrada="1500.00",
            publicada=False,
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
            publicada=False,
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
            publicada=False,
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
        otra_sala = Sala.objects.create(nombre="Sala 2", capacidad=80)
        Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(20, 0),
            precio_entrada="1500.00",
            publicada=False,
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
            publicada=False,
        )

        response = self.client.post(
            reverse("manager:funciones_update", args=[funcion.pk]),
            data={
                "pelicula": self.pelicula.pk,
                "sala": self.sala.pk,
                "fecha_horario": self.fecha_form(self.fecha_futura(20, 0)),
                "precios_por_tipo": self.precios_por_tipo_form("1600.00"),
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        funcion.refresh_from_db()
        self.assertEqual(str(funcion.precio_entrada), "1600.00")
