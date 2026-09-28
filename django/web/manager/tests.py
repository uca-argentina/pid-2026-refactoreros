import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from domain.movies.models import Pelicula
from domain.rooms.models import Sala
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

    def test_gerente_crea_funcion_sin_publicarla(self):
        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "pelicula": self.pelicula.pk,
                "sala": self.sala.pk,
                "fecha_horario": self.fecha_form(self.fecha_futura()),
                "precio_entrada": "1500.00",
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
                "precio_entrada": "0.00",
            },
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("precio_entrada", form.errors)
        self.assertIn("mayor a cero", form.errors["precio_entrada"][0])
        self.assertEqual(Funcion.objects.count(), 0)

    def test_no_permite_crear_funcion_con_precio_negativo(self):
        response = self.client.post(
            reverse("manager:funciones_create"),
            data={
                "pelicula": self.pelicula.pk,
                "sala": self.sala.pk,
                "fecha_horario": self.fecha_form(timezone.now() + timedelta(days=1)),
                "precio_entrada": "-1500.00",
            },
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("precio_entrada", form.errors)
        self.assertIn("mayor a cero", form.errors["precio_entrada"][0])
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
        self.assertNotContains(response, "Publicar")
        self.assertNotContains(response, "Ocultar")
        self.assertNotContains(response, reverse("manager:funciones_cancelar", args=[funcion.pk]))

    def test_lista_funciones_muestra_acciones_de_programada(self):
        funcion = self.crear_funcion(Funcion.Estado.PROGRAMADA)

        response = self.client.get(reverse("manager:funciones_list"))

        self.assertContains(response, "Publicar")
        self.assertContains(response, "Volver a borrador")
        self.assertContains(response, reverse("manager:funciones_cancelar", args=[funcion.pk]))
        self.assertNotContains(response, "Ocultar")

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

        self.assertContains(response, "$1500,00")

    def test_lista_funciones_ordena_por_mayor_precio(self):
        barata = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(20, 30),
            precio_entrada="1000.00",
            estado=Funcion.Estado.BORRADOR,
        )
        cara = Funcion.objects.create(
            pelicula=self.pelicula,
            sala=self.sala,
            fecha_horario=self.fecha_futura(22, 30),
            precio_entrada="2500.00",
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
        self.assertEqual(
            response.context["form"].initial["precio_entrada"],
            Decimal("1500.00"),
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
        self.assertContains(response, '<td data-label="Disponibles">85</td>', html=True)

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
        otra_sala = Sala.objects.create(nombre="Sala 2", capacidad=80)
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

        response = self.client.post(
            reverse("manager:funciones_update", args=[funcion.pk]),
            data={
                "pelicula": self.pelicula.pk,
                "sala": self.sala.pk,
                "fecha_horario": self.fecha_form(self.fecha_futura(20, 0)),
                "precio_entrada": "1600.00",
            },
        )

        self.assertRedirects(response, reverse("manager:funciones_list"))
        funcion.refresh_from_db()
        self.assertEqual(str(funcion.precio_entrada), "1600.00")
