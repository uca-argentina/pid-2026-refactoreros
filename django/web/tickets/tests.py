from datetime import timedelta
from decimal import Decimal
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.cinema.models import ConfiguracionCine
from domain.movies.models import Pelicula
from domain.rooms.models import Sala
from domain.screenings.models import Funcion
from domain.seats.models import Seat
from domain.seat_types.models import SeatType
from domain.tickets.models import CompraAsiento, CompraEntrada, ReservaAsiento


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


def crear_funcion_con_butacas(titulo="Con butacas"):
    pelicula = Pelicula.objects.create(
        titulo=titulo,
        sinopsis="Una pelicula de prueba.",
        genero=Pelicula.Genero.ACCION,
        clasificacion=Pelicula.Clasificacion.MAS_13,
        duracion_minutos=120,
        imagen="peliculas/test.jpg",
    )
    sala = Sala.objects.create(nombre=f"Sala {titulo}", capacidad=2)
    tipo = SeatType.objects.get(nombre="Estándar")
    Seat.objects.create(sala=sala, fila=0, columna=0, tipo=tipo)
    Seat.objects.create(sala=sala, fila=0, columna=1, tipo=tipo)
    return Funcion.objects.create(
        pelicula=pelicula,
        sala=sala,
        fecha_horario=timezone.now(),
        precio_entrada="1500.00",
        estado=Funcion.Estado.PUBLICADA,
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

        response = self.client.post(reverse("ticket_purchase", args=[funcion.pk]), data={})

        self.assertEqual(response.status_code, 404)

    def test_modelo_compra_legacy_por_cantidad_guarda_total(self):
        funcion = crear_funcion(estado=Funcion.Estado.PUBLICADA, titulo="Publicada")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )

        compra = CompraEntrada.comprar(usuario, funcion, 3)

        self.assertEqual(compra.usuario, usuario)
        self.assertEqual(compra.funcion, funcion)
        self.assertEqual(compra.cantidad, 3)
        self.assertEqual(compra.total, Decimal("4500.00"))

    def test_compra_web_con_butaca_muestra_mensaje_singular(self):
        funcion = crear_funcion_con_butacas(titulo="Publicada")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        ReservaAsiento.reservar(usuario, funcion, "1A")
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("ticket_purchase", args=[funcion.pk]),
            data={"selected_seats": json.dumps([{"label": "1A"}])},
            follow=True,
        )

        self.assertContains(
            response,
            "Pago aprobado. Compraste 1 entrada para Publicada. ¡Te esperamos!",
        )

    def test_compra_web_rechaza_confirmacion_sin_butacas(self):
        funcion = crear_funcion_con_butacas()
        usuario = get_user_model().objects.create_user(
            username="sinbutaca@mail.com",
            email="sinbutaca@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("ticket_purchase", args=[funcion.pk]),
            data={},
            follow=True,
        )

        self.assertRedirects(response, reverse("seat_selection", args=[funcion.pk]))
        self.assertContains(response, "Seleccioná al menos una butaca.")
        self.assertFalse(CompraEntrada.objects.exists())

    def test_compra_con_butacas_guarda_seleccion_y_bloquea_repetidas(self):
        funcion = crear_funcion_con_butacas()
        usuario = get_user_model().objects.create_user(
            username="ana2@mail.com",
            email="ana2@mail.com",
            password="PasswordSegura123!",
        )

        compra = CompraEntrada.comprar(
            usuario,
            funcion,
            1,
            selected_seats=[{"label": "1A"}],
        )

        self.assertEqual(compra.cantidad, 1)
        self.assertEqual(compra.asientos_seleccionados[0]["label"], "1A")
        self.assertIn("1A", CompraEntrada.asientos_ocupados(funcion))
        with self.assertRaises(ValidationError):
            CompraEntrada.comprar(
                usuario,
                funcion,
                1,
                selected_seats=[{"label": "1A"}],
            )

    def test_modelo_compra_legacy_falla_si_supera_disponibilidad(self):
        funcion = crear_funcion(estado=Funcion.Estado.PUBLICADA, titulo="Publicada", capacidad=2)
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )

        with self.assertRaises(ValidationError):
            CompraEntrada.comprar(usuario, funcion, 3)

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
        compra = CompraEntrada.comprar(usuario, funcion, 2)
        compra.asientos_seleccionados = [{"label": "1A"}, {"label": "1B"}]
        compra.save(update_fields=["asientos_seleccionados"])
        CompraEntrada.comprar(otro_usuario, funcion, 1)
        self.client.force_login(usuario)

        response = self.client.get(reverse("my_tickets"))

        self.assertContains(response, "Publicada")
        self.assertContains(response, "2")
        self.assertContains(response, "1A, 1B")
        self.assertNotContains(response, "otro@mail.com")

    def test_compra_no_permite_funcion_cancelada(self):
        funcion = crear_funcion(estado=Funcion.Estado.CANCELADA, titulo="Cancelada")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.post(reverse("ticket_purchase", args=[funcion.pk]), data={})

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

        response = self.client.post(reverse("ticket_purchase", args=[funcion.pk]), data={})

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

    def test_reserva_bloquea_butaca_para_otro_usuario(self):
        funcion = crear_funcion_con_butacas()
        usuario = get_user_model().objects.create_user(
            username="ana3@mail.com",
            email="ana3@mail.com",
            password="PasswordSegura123!",
        )
        otro_usuario = get_user_model().objects.create_user(
            username="otro3@mail.com",
            email="otro3@mail.com",
            password="PasswordSegura123!",
        )

        reserva = ReservaAsiento.reservar(usuario, funcion, "1A")

        self.assertEqual(reserva.label, "1A")
        self.assertIn("1A", CompraEntrada.asientos_bloqueados(funcion, usuario=otro_usuario))
        self.assertNotIn("1A", CompraEntrada.asientos_bloqueados(funcion, usuario=usuario))
        with self.assertRaises(ValidationError):
            ReservaAsiento.reservar(otro_usuario, funcion, "1A")

    def test_selector_usa_intervalo_de_recarga_configurado(self):
        ConfiguracionCine.objects.create(recarga_asientos_segundos=11)
        funcion = crear_funcion_con_butacas()
        usuario = get_user_model().objects.create_user(
            username="ana9@mail.com",
            email="ana9@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("seat_selection", args=[funcion.pk]))

        self.assertContains(response, 'data-refresh-interval-seconds="11"')

    def test_compra_web_requiere_reserva_vigente_de_butaca(self):
        funcion = crear_funcion_con_butacas()
        usuario = get_user_model().objects.create_user(
            username="ana4@mail.com",
            email="ana4@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("ticket_purchase", args=[funcion.pk]),
            data={"selected_seats": json.dumps([{"label": "1A"}])},
            follow=True,
        )

        self.assertRedirects(response, reverse("seat_selection", args=[funcion.pk]))
        self.assertContains(response, "Algunas butacas ya no estan reservadas")
        self.assertFalse(CompraEntrada.objects.exists())

    def test_compra_web_confirma_reserva_y_crea_asiento_vendido_unico(self):
        funcion = crear_funcion_con_butacas()
        usuario = get_user_model().objects.create_user(
            username="ana5@mail.com",
            email="ana5@mail.com",
            password="PasswordSegura123!",
        )
        ReservaAsiento.reservar(usuario, funcion, "1A")
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("ticket_purchase", args=[funcion.pk]),
            data={"selected_seats": json.dumps([{"label": "1A"}])},
            follow=True,
        )

        self.assertRedirects(response, reverse("my_tickets"))
        self.assertTrue(CompraAsiento.objects.filter(funcion=funcion, label="1A").exists())
        self.assertFalse(ReservaAsiento.objects.filter(funcion=funcion, label="1A").exists())
        with self.assertRaises(ValidationError):
            CompraEntrada.comprar(
                usuario,
                funcion,
                1,
                selected_seats=[{"label": "1A"}],
            )

    def test_reserva_ajax_devuelve_conflicto_si_butaca_esta_reservada(self):
        funcion = crear_funcion_con_butacas()
        usuario = get_user_model().objects.create_user(
            username="ana6@mail.com",
            email="ana6@mail.com",
            password="PasswordSegura123!",
        )
        otro_usuario = get_user_model().objects.create_user(
            username="otro6@mail.com",
            email="otro6@mail.com",
            password="PasswordSegura123!",
        )
        ReservaAsiento.reservar(otro_usuario, funcion, "1A")
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("seat_reservation", args=[funcion.pk]),
            data=json.dumps({"action": "reserve", "label": "1A"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["ok"])
        self.assertIn("1A", response.json()["unavailable"])

    def test_reserva_expirada_no_bloquea_butaca_abandonada(self):
        funcion = crear_funcion_con_butacas()
        usuario = get_user_model().objects.create_user(
            username="ana8@mail.com",
            email="ana8@mail.com",
            password="PasswordSegura123!",
        )
        otro_usuario = get_user_model().objects.create_user(
            username="otro8@mail.com",
            email="otro8@mail.com",
            password="PasswordSegura123!",
        )
        ReservaAsiento.objects.create(
            usuario=usuario,
            funcion=funcion,
            label="1A",
            expira_en=timezone.now() - timedelta(minutes=1),
        )

        self.assertNotIn("1A", CompraEntrada.asientos_bloqueados(funcion, usuario=otro_usuario))
        reserva = ReservaAsiento.reservar(otro_usuario, funcion, "1A")

        self.assertEqual(reserva.usuario, otro_usuario)
        self.assertGreater(reserva.expira_en, timezone.now())

    def test_sincronizar_asientos_vendidos_legacy_es_idempotente(self):
        funcion = crear_funcion_con_butacas()
        usuario = get_user_model().objects.create_user(
            username="ana7@mail.com",
            email="ana7@mail.com",
            password="PasswordSegura123!",
        )
        CompraEntrada.comprar(usuario, funcion, 1)

        CompraEntrada.sincronizar_asientos_vendidos(funcion)
        CompraEntrada.sincronizar_asientos_vendidos(funcion)

        self.assertEqual(CompraAsiento.objects.filter(funcion=funcion).count(), 1)
