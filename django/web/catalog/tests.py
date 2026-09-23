from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.movies.models import Pelicula
from domain.rooms.models import Sala
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
        self.assertContains(response, "Comprar entrada")
        self.assertContains(response, "Elegí tu función")
        self.assertNotContains(response, "Disponibles")

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

        response = self.client.get(reverse("screening_detail", args=[agotada.pk]), follow=True)

        self.assertContains(response, "Entradas agotadas para esta función")
        self.assertContains(response, "disabled")
        self.assertContains(response, f'value="{agotada.pk}"')
        self.assertContains(response, 'data-available="0"')
        self.assertContains(response, f'value="{disponible.pk}"')
        self.assertContains(response, 'data-available="3"')

    def test_url_vieja_de_funcion_redirige_al_detalle_de_pelicula(self):
        funcion = crear_funcion(publicada=True, titulo="Publicada")
        usuario = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse("screening_detail", args=[funcion.pk]))

        self.assertRedirects(response, reverse("movie_detail", args=[funcion.pelicula.pk]))

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
