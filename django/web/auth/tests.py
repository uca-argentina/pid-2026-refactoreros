from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from domain.users.models import Usher, Customer, Manager


class AuthPageRenderingTests(TestCase):
    def test_login_renderiza_template_de_auth(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "auth.html")
        self.assertEqual(response.context["active_tab"], "login")

    def test_signup_renderiza_template_de_auth(self):
        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "auth.html")
        self.assertEqual(response.context["active_tab"], "signup")

    def test_login_con_mail_precargado_querystring_carga_exitosamente(self):
        response = self.client.get(reverse("login"), {"email": "ana@mail.com"})

        self.assertContains(response, 'value="ana@mail.com"')


class SignupFlowTests(TestCase):
    def test_signup_crea_usuario_cliente_y_sesion(self):
        response = self.client.post(
            reverse("signup"),
            data={
                "name": "Ana",
                "last_name": "Gomez",
                "email": "ana@mail.com",
                "password1": "PasswordSegura123!",
                "password2": "PasswordSegura123!",
            },
        )

        self.assertRedirects(response, reverse("home"))
        user = get_user_model().objects.get(email="ana@mail.com")
        self.assertTrue(Customer.objects.filter(user=user).exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_signup_respeta_next_local(self):
        next_url = "/funciones/1/asientos/"
        response = self.client.post(
            f"{reverse('signup')}?next={next_url}",
            data={
                "name": "Ana",
                "last_name": "Gomez",
                "email": "ana-next@mail.com",
                "password1": "PasswordSegura123!",
                "password2": "PasswordSegura123!",
            },
        )

        self.assertRedirects(response, next_url, fetch_redirect_response=False)

    def test_signup_con_email_existente_ofrece_ir_a_login(self):
        get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )

        response = self.client.post(
            reverse("signup"),
            data={
                "name": "Ana",
                "last_name": "Gomez",
                "email": "ana@mail.com",
                "password1": "PasswordSegura123!",
                "password2": "PasswordSegura123!",
            },
        )

        self.assertNotContains(response, "Ya existe un usuario con ese mail.")
        self.assertContains(response, "Ese email ya tiene cuenta.")
        self.assertContains(response, f"{reverse('login')}?email=ana%40mail.com")

    def test_auth_tabs_preservan_next(self):
        next_url = "/funciones/12/asientos/"

        response = self.client.get(reverse("signup"), {"next": next_url})

        self.assertContains(response, f"{reverse('login')}?next={next_url}")
        self.assertContains(response, f"{reverse('signup')}?next={next_url}")

    def test_signup_redirige_a_home_si_ya_hay_sesion(self):
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("signup"))

        self.assertRedirects(response, reverse("home"))


class LoginFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )

    def test_login_con_credenciales_validas_crea_sesion(self):
        response = self.client.post(
            reverse("login"),
            data={
                "username": "ana@mail.com",
                "password": "PasswordSegura123!",
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.id)

    def test_login_de_gerente_redirige_a_gestion(self):
        user = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password="PasswordSegura123!",
        )
        Manager.objects.create(user=user)

        response = self.client.post(
            reverse("login"),
            data={
                "username": "gerente@mail.com",
                "password": "PasswordSegura123!",
            },
        )

        self.assertRedirects(response, reverse("manager:home"))

    def test_login_de_acomodador_redirige_a_gestion(self):
        user = get_user_model().objects.create_user(
            username="acomodador@mail.com",
            email="acomodador@mail.com",
            password="PasswordSegura123!",
        )
        Usher.objects.create(user=user)

        response = self.client.post(
            reverse("login"),
            data={
                "username": "acomodador@mail.com",
                "password": "PasswordSegura123!",
            },
        )

        self.assertRedirects(response, reverse("manager:home"))

    def test_login_respeta_next_local(self):
        response = self.client.post(
            f"{reverse('login')}?next={reverse('home')}",
            data={
                "username": "ana@mail.com",
                "password": "PasswordSegura123!",
            },
        )

        self.assertRedirects(response, reverse("home"))

    def test_login_ignora_next_externo(self):
        response = self.client.post(
            f"{reverse('login')}?next=https://example.com/phishing",
            data={
                "username": "ana@mail.com",
                "password": "PasswordSegura123!",
            },
        )

        self.assertRedirects(response, reverse("home"))

    def test_login_con_credenciales_invalidas_muestra_error_simple(self):
        response = self.client.post(
            reverse("login"),
            data={
                "username": "nadie@mail.com",
                "password": "PasswordIncorrecta123",
            },
        )

        self.assertContains(response, "No encontramos una cuenta con esos datos.")
        self.assertNotContains(response, "mayúsculas/minúsculas")

    def test_login_redirige_a_home_si_ya_hay_sesion(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("login"))

        self.assertRedirects(response, reverse("home"))

    def test_login_redirige_a_gestion_si_ya_hay_sesion_de_gerente(self):
        user = get_user_model().objects.create_user(
            username="gerente@mail.com",
            email="gerente@mail.com",
            password="PasswordSegura123!",
        )
        Manager.objects.create(user=user)
        self.client.force_login(user)

        response = self.client.get(reverse("login"))

        self.assertRedirects(response, reverse("manager:home"))


class LogoutFlowTests(TestCase):
    def test_logout_cierra_sesion_y_redirige_a_login(self):
        user = get_user_model().objects.create_user(
            username="ana@mail.com",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("logout"))

        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)
