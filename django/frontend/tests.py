from django.contrib.auth import get_user_model
from django.test import TestCase

from users.models import Cliente


class SignupFrontendTests(TestCase):
    def test_signup_crea_usuario_cliente_y_sesion(self):
        response = self.client.post(
            "/signup/",
            data={
                "nombre": "Ana",
                "email": "ana@mail.com",
                "password1": "PasswordSegura123",
                "password2": "PasswordSegura123",
            },
        )

        self.assertRedirects(response, "/")
        usuario = get_user_model().objects.get(email="ana@mail.com")
        self.assertTrue(Cliente.objects.filter(usuario=usuario).exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), usuario.id)

    def test_home_redirige_a_login_si_no_hay_sesion(self):
        response = self.client.get("/")

        self.assertRedirects(response, "/login/?next=/")

    def test_login_renderiza_template_de_frontend(self):
        response = self.client.get("/login/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/auth.html")

    def test_signup_renderiza_template_de_frontend(self):
        response = self.client.get("/signup/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/auth.html")
