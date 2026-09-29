from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.movies.models import Pelicula
from domain.rooms.models import Sala
from domain.screenings.models import Funcion
from domain.tickets.models import CompraEntrada


def crear_funcion(estado=Funcion.Estado.PUBLICADA, titulo="Pelicula", capacidad=100):
    pelicula = Pelicula.objects.create(
        titulo=titulo,
        sinopsis="Una pelicula de prueba.",
        genero=Pelicula.Genero.ACCION,
        clasificacion=Pelicula.Clasificacion.MAS_13,
        duracion_minutos=120,
        imagen="peliculas/test.jpg",
    )
    sala = Sala.objects.create(nombre=f"Sala {titulo}", capacidad=capacidad)
    return Funcion.objects.create(
        pelicula=pelicula,
        sala=sala,
        fecha_horario=timezone.now(),
        precio_entrada="1500.00",
        estado=estado,
    )


class TicketPurchaseTests(TestCase):
    def test_compra_no_permite_funcion_oculta(self):
        funcion = crear_funcion(estado=Funcion.Estado.BORRADOR, titulo="Oculta")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("ticket_purchase", args=[funcion.pk]),
            data={"cantidad": 1},
        )

        self.assertEqual(response.status_code, 404)

    def test_compra_funcion_publicada_guarda_cantidad_y_total(self):
        funcion = crear_funcion(estado=Funcion.Estado.PUBLICADA, titulo="Publicada")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("ticket_purchase", args=[funcion.pk]),
            data={"cantidad": 3},
            follow=True,
        )

        self.assertRedirects(response, reverse("my_tickets"))
        self.assertContains(
            response,
            "Pago aprobado. Compraste 3 entradas para Publicada. ¡Te esperamos!",
        )
        compra = CompraEntrada.objects.get()
        self.assertEqual(compra.usuario, usuario)
        self.assertEqual(compra.funcion, funcion)
        self.assertEqual(compra.cantidad, 3)
        self.assertEqual(compra.total, Decimal("4500.00"))

    def test_compra_funcion_publicada_muestra_mensaje_singular(self):
        funcion = crear_funcion(estado=Funcion.Estado.PUBLICADA, titulo="Publicada")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("ticket_purchase", args=[funcion.pk]),
            data={"cantidad": 1},
            follow=True,
        )

        self.assertContains(
            response,
            "Pago aprobado. Compraste 1 entrada para Publicada. ¡Te esperamos!",
        )

    def test_compra_falla_si_supera_disponibilidad(self):
        funcion = crear_funcion(estado=Funcion.Estado.PUBLICADA, titulo="Publicada", capacidad=2)
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("ticket_purchase", args=[funcion.pk]),
            data={"cantidad": 3},
            follow=True,
        )

        self.assertRedirects(response, reverse("movie_detail", args=[funcion.pelicula.pk]))
        self.assertContains(
            response,
            "Solo tenemos disponibles 2 entradas para esta función.",
        )
        self.assertFalse(CompraEntrada.objects.exists())

    def test_mis_entradas_muestra_compras_del_usuario(self):
        funcion = crear_funcion(estado=Funcion.Estado.PUBLICADA, titulo="Publicada")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        otro_usuario = get_user_model().objects.create_user(
            username="otro@mail.com",
            email="otro@mail.com",
            password="PasswordSegura123!",
        )
        CompraEntrada.comprar(usuario, funcion, 2)
        CompraEntrada.comprar(otro_usuario, funcion, 1)
        self.client.force_login(usuario)

        response = self.client.get(reverse("my_tickets"))

        self.assertContains(response, "Publicada")
        self.assertContains(response, "2")
        self.assertNotContains(response, "otro@mail.com")

    def test_compra_no_permite_funcion_cancelada(self):
        funcion = crear_funcion(estado=Funcion.Estado.CANCELADA, titulo="Cancelada")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("ticket_purchase", args=[funcion.pk]),
            data={"cantidad": 1},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(CompraEntrada.objects.exists())

    def test_compra_no_permite_funcion_que_ya_termino(self):
        funcion = crear_funcion(titulo="Terminada")
        Funcion.objects.filter(pk=funcion.pk).update(
            fecha_horario=timezone.now() - timedelta(hours=3)
        )
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("ticket_purchase", args=[funcion.pk]),
            data={"cantidad": 1},
        )

        self.assertEqual(response.status_code, 404)
        funcion.refresh_from_db()
        self.assertEqual(funcion.estado, Funcion.Estado.FINALIZADA)

    def test_modelo_no_permite_comprar_funcion_no_publicada(self):
        funcion = crear_funcion(estado=Funcion.Estado.PROGRAMADA, titulo="Programada")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )

        with self.assertRaises(ValidationError):
            CompraEntrada.comprar(usuario, funcion, 1)

    def test_mis_entradas_marca_funcion_cancelada(self):
        funcion = crear_funcion(titulo="Cancelada luego")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        CompraEntrada.comprar(usuario, funcion, 2)
        funcion.cambiar_estado(Funcion.Estado.CANCELADA)
        self.client.force_login(usuario)

        response = self.client.get(reverse("my_tickets"))

        self.assertContains(response, "Función cancelada")
        self.assertContains(response, "is-cancelled")
