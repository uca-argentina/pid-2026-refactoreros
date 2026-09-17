from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.movies.models import Pelicula
from domain.rooms.models import Sala
from domain.screenings.models import Funcion
from domain.tickets.models import CompraEntrada


def crear_funcion(publicada=True, titulo="Pelicula", capacidad=100):
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
        publicada=publicada,
    )


class TicketPurchaseTests(TestCase):
    def test_compra_no_permite_funcion_oculta(self):
        funcion = crear_funcion(publicada=False, titulo="Oculta")
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
        funcion = crear_funcion(publicada=True, titulo="Publicada")
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
            "Pago aprobado. Compraste 3 entradas para Publicada. Te esperamos.",
        )
        compra = CompraEntrada.objects.get()
        self.assertEqual(compra.usuario, usuario)
        self.assertEqual(compra.funcion, funcion)
        self.assertEqual(compra.cantidad, 3)
        self.assertEqual(compra.total, funcion.precio_entrada * 3)

    def test_compra_funcion_publicada_muestra_mensaje_singular(self):
        funcion = crear_funcion(publicada=True, titulo="Publicada")
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
            "Pago aprobado. Compraste 1 entrada para Publicada. Te esperamos.",
        )

    def test_compra_falla_si_supera_disponibilidad(self):
        funcion = crear_funcion(publicada=True, titulo="Publicada", capacidad=2)
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

        self.assertRedirects(response, reverse("screening_detail", args=[funcion.pk]))
        self.assertContains(
            response,
            "Solo tenemos disponibles 2 entradas para esta función.",
        )
        self.assertFalse(CompraEntrada.objects.exists())

    def test_mis_entradas_muestra_compras_del_usuario(self):
        funcion = crear_funcion(publicada=True, titulo="Publicada")
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
