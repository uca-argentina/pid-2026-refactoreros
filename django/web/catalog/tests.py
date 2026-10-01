from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.movies.models import Pelicula
from domain.rooms.models import Sala
from domain.seats.models import Seat
from domain.seat_types.models import SeatType
from domain.screenings.models import Funcion
from domain.tickets.models import CompraEntrada
from domain.users.models import Cliente, Gerente


def crear_funcion(publicada=True, titulo="Pelicula", capacidad=100, pelicula=None):
    pelicula = pelicula or Pelicula.objects.create(
        titulo=titulo,
        sinopsis="Una película de prueba.",
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


class CatalogFlowTests(TestCase):
    def test_home_redirige_a_login_si_no_hay_sesion(self):
        response = self.client.get(reverse("home"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('home')}")

    def test_home_renderiza_si_hay_sesion(self):
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")

    def test_home_muestra_cartelera_publicada(self):
        crear_funcion(publicada=True, titulo="Publicada")
        crear_funcion(publicada=False, titulo="Oculta")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Cartelera")
        self.assertContains(response, "Publicada")
        self.assertNotContains(response, "Oculta")

    def test_home_agrupa_funciones_por_pelicula(self):
        pelicula = Pelicula.objects.create(
            titulo="Misma película",
            sinopsis="Una película de prueba.",
            genero=Pelicula.Genero.ACCION,
            clasificacion=Pelicula.Clasificacion.MAS_13,
            duracion_minutos=120,
            imagen="peliculas/test.jpg",
        )
        crear_funcion(publicada=True, titulo="Funcion 1", pelicula=pelicula)
        crear_funcion(publicada=True, titulo="Funcion 2", pelicula=pelicula)
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "<h2>Misma película</h2>", count=1, html=True)

    def test_detalle_funcion_publicada_permite_comprar(self):
        funcion = crear_funcion(publicada=True, titulo="Publicada", capacidad=5)
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        CompraEntrada.comprar(usuario, funcion, 2)
        self.client.force_login(usuario)

        response = self.client.get(reverse("movie_detail", args=[funcion.pelicula.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "screening_detail.html")
        self.assertContains(response, "Elegí tu función")
        self.assertContains(response, reverse("seat_selection", args=[funcion.pk]))
        self.assertNotContains(response, "Disponibles")

    def test_detalle_muestra_pantalla_y_mapa_de_asientos_si_hay_snapshot(self):
        pelicula = Pelicula.objects.create(
            titulo="Con butacas",
            sinopsis="Una pelicula de prueba.",
            genero=Pelicula.Genero.ACCION,
            clasificacion=Pelicula.Clasificacion.MAS_13,
            duracion_minutos=120,
            imagen="peliculas/test.jpg",
        )
        sala = Sala.objects.create(nombre="Sala mapa", capacidad=2)
        tipo = SeatType.objects.get(nombre="Estándar")
        Seat.objects.create(sala=sala, fila=0, columna=0, tipo=tipo)
        Seat.objects.create(sala=sala, fila=0, columna=1, tipo=tipo)
        funcion = Funcion.objects.create(
            pelicula=pelicula,
            sala=sala,
            fecha_horario=timezone.now(),
            precio_entrada="1500.00",
            publicada=True,
        )
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("seat_selection", args=[funcion.pk]))

        self.assertTemplateUsed(response, "seat_selection.html")
        self.assertContains(response, "Pantalla")
        self.assertContains(response, "1A")
        self.assertContains(response, "1B")
        self.assertContains(response, "Fila 1, columna A")

    def test_detalle_muestra_pasillos_sin_saltar_letras_de_columnas(self):
        pelicula = Pelicula.objects.create(
            titulo="Con pasillos",
            sinopsis="Una pelicula de prueba.",
            genero=Pelicula.Genero.ACCION,
            clasificacion=Pelicula.Clasificacion.MAS_13,
            duracion_minutos=120,
            imagen="peliculas/test.jpg",
        )
        sala = Sala.objects.create(nombre="Sala pasillos", capacidad=2)
        tipo = SeatType.objects.get(nombre="Estándar")
        funcion = Funcion.objects.create(
            pelicula=pelicula,
            sala=sala,
            fecha_horario=timezone.now(),
            precio_entrada="1500.00",
            publicada=True,
            capacidad_snapshot=2,
            sala_configuracion_snapshot={
                "rows": 3,
                "columns": 3,
                "seats": [
                    {
                        "row": 0,
                        "column": 0,
                        "type": tipo.nombre,
                        "type_id": tipo.pk,
                        "price": str(tipo.precio_base),
                        "color": tipo.color,
                    },
                    {
                        "row": 0,
                        "column": 2,
                        "type": tipo.nombre,
                        "type_id": tipo.pk,
                        "price": str(tipo.precio_base),
                        "color": tipo.color,
                    },
                ],
            },
        )
        usuario = get_user_model().objects.create_user(
            username="ana2@mail.com",
            email="ana2@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("seat_selection", args=[funcion.pk]))

        self.assertContains(response, "1A")
        self.assertContains(response, "1B")
        self.assertNotContains(response, "1C")
        self.assertContains(response, "client-seat-row is-aisle-row")

    def test_detalle_muestra_entradas_agotadas_solo_para_funcion_seleccionada(self):
        pelicula = Pelicula.objects.create(
            titulo="Pelicula con varias funciones",
            sinopsis="Una pelicula de prueba.",
            genero=Pelicula.Genero.ACCION,
            clasificacion=Pelicula.Clasificacion.MAS_13,
            duracion_minutos=120,
            imagen="peliculas/test.jpg",
        )
        agotada = crear_funcion(
            publicada=True,
            titulo="Agotada",
            capacidad=1,
            pelicula=pelicula,
        )
        disponible = crear_funcion(
            publicada=True,
            titulo="Disponible",
            capacidad=3,
            pelicula=pelicula,
        )
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        CompraEntrada.comprar(usuario, agotada, 1)
        self.client.force_login(usuario)

        response = self.client.get(reverse("movie_detail", args=[pelicula.pk]))

        self.assertContains(response, "Función agotada")
        self.assertContains(response, reverse("seat_selection", args=[disponible.pk]))
        self.assertNotContains(response, reverse("seat_selection", args=[agotada.pk]))

    def test_url_vieja_de_funcion_redirige_a_seleccion_de_butacas(self):
        funcion = crear_funcion(publicada=True, titulo="Publicada")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("screening_detail", args=[funcion.pk]))

        self.assertRedirects(response, reverse("seat_selection", args=[funcion.pk]))

    def test_home_muestra_acceso_a_gestion_si_es_gerente(self):
        usuario = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password="PasswordSegura123!",
        )
        Gerente.objects.create(usuario=usuario)
        self.client.force_login(usuario)

        response = self.client.get(reverse("home"))

        self.assertContains(response, reverse("manager:home"))

    def test_home_no_muestra_acceso_a_gestion_si_es_cliente(self):
        usuario = get_user_model().objects.create_user(
            username="cliente@mail.com",
            email="cliente@mail.com",
            password="PasswordSegura123!",
        )
        Cliente.objects.create(usuario=usuario)
        self.client.force_login(usuario)

        response = self.client.get(reverse("home"))

        self.assertNotContains(response, reverse("manager:home"))
