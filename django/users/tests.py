from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from .forms import ClienteSignupForm, UsuarioChangeForm, UsuarioCreationForm
from .models import Acomodador, Cliente, Gerente


class PerfilesUsuarioTests(TestCase):
    def setUp(self):
        self.password = "PasswordSegura123"
        self.usuario = get_user_model().objects.create_user(
            username="juan",
            email="juan@mail.com",
            password=self.password,
        )

    def test_al_crear_un_usuario_su_password_se_hashea(self):
        self.assertNotEqual(self.usuario.password, self.password)
        self.assertTrue(self.usuario.check_password(self.password))

    def test_crear_perfil_cliente(self):
        cliente = Cliente.objects.create(usuario=self.usuario)

        self.assertEqual(cliente.usuario, self.usuario)
        self.assertEqual(str(cliente), "juan")

    def test_crear_perfil_acomodador(self):
        acomodador = Acomodador.objects.create(usuario=self.usuario)

        self.assertEqual(acomodador.usuario, self.usuario)
        self.assertEqual(str(acomodador), "juan")

    def test_crear_perfil_gerente(self):
        gerente = Gerente.objects.create(usuario=self.usuario)

        self.assertEqual(gerente.usuario, self.usuario)
        self.assertEqual(str(gerente), "juan")

    def test_cuando_un_usuario_se_asigna_a_un_segundo_cliente_entonces_falla(self):
        Cliente.objects.create(usuario=self.usuario)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cliente.objects.create(usuario=self.usuario)

    def test_cuando_un_usuario_se_elimina_entonces_se_elimina_el_cliente_asociado(self):
        Cliente.objects.create(usuario=self.usuario)

        self.usuario.delete()

        self.assertEqual(Cliente.objects.count(), 0)

    def test_cuando_un_usuario_se_elimina_entonces_se_elimina_el_acomodador_asociado(self):
        Acomodador.objects.create(usuario=self.usuario)

        self.usuario.delete()

        self.assertEqual(Acomodador.objects.count(), 0)

    def test_cuando_un_usuario_se_elimina_entonces_se_elimina_el_gerente_asociado(self):
        Gerente.objects.create(usuario=self.usuario)

        self.usuario.delete()

        self.assertEqual(Gerente.objects.count(), 0)


class ValidacionMailUsuarioTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="juan",
            email="juan@mail.com",
            password="PasswordSegura123",
        )

    def test_al_crear_usuario_el_mail_es_obligatorio(self):
        form = UsuarioCreationForm(
            data={
                "username": "ana",
                "email": "",
                "password1": "PasswordSegura123",
                "password2": "PasswordSegura123",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_al_crear_usuario_el_mail_no_puede_repetirse(self):
        form = UsuarioCreationForm(
            data={
                "username": "ana",
                "email": "JUAN@mail.com",
                "password1": "PasswordSegura123",
                "password2": "PasswordSegura123",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_al_editar_usuario_permite_conservar_su_mismo_mail(self):
        form = UsuarioChangeForm(
            instance=self.usuario,
            data={
                "username": "juan",
                "email": "juan@mail.com",
                "password": self.usuario.password,
                "date_joined": self.usuario.date_joined.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

        self.assertTrue(form.is_valid())

    def test_al_editar_usuario_no_permite_usar_mail_de_otro_usuario(self):
        otro_usuario = get_user_model().objects.create_user(
            username="ana",
            email="ana@mail.com",
            password="PasswordSegura123",
        )
        form = UsuarioChangeForm(
            instance=otro_usuario,
            data={
                "username": "ana",
                "email": "JUAN@mail.com",
                "password": otro_usuario.password,
                "date_joined": otro_usuario.date_joined.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


class SignupClienteFormTests(TestCase):
    def test_signup_form_crea_usuario_con_email_como_username(self):
        form = ClienteSignupForm(
            data={
                "nombre": "Ana",
                "email": "ANA@mail.com",
                "password1": "PasswordSegura123",
                "password2": "PasswordSegura123",
            }
        )

        self.assertTrue(form.is_valid())

        usuario = form.save()

        self.assertEqual(usuario.username, "ana@mail.com")
        self.assertEqual(usuario.email, "ana@mail.com")
        self.assertEqual(usuario.first_name, "Ana")
        self.assertTrue(usuario.check_password("PasswordSegura123"))

    def test_signup_form_valida_password_con_reglas_de_django(self):
        form = ClienteSignupForm(
            data={
                "nombre": "Ana",
                "email": "ana@mail.com",
                "password1": "12345678",
                "password2": "12345678",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password1", form.errors)
