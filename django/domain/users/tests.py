from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from .forms import (
    AdminUserChangeForm,
    AdminUserCreationForm,
    CustomerSignupForm,
)
from .models import Usher, Customer, Manager


class PerfilesUsuarioTests(TestCase):
    def setUp(self):
        self.password = "PasswordSegura123!"
        self.user = get_user_model().objects.create_user(
            username="juan",
            email="juan@mail.com",
            password=self.password,
        )

    def test_al_crear_un_usuario_su_password_se_hashea(self):
        self.assertNotEqual(self.user.password, self.password)
        self.assertTrue(self.user.check_password(self.password))

    def test_crear_perfil_cliente(self):
        cliente = Customer.objects.create(user=self.user)

        self.assertEqual(cliente.user, self.user)
        self.assertEqual(str(cliente), "juan")

    def test_crear_perfil_acomodador(self):
        acomodador = Usher.objects.create(user=self.user)

        self.assertEqual(acomodador.user, self.user)
        self.assertEqual(str(acomodador), "juan")

    def test_crear_perfil_gerente(self):
        gerente = Manager.objects.create(user=self.user)

        self.assertEqual(gerente.user, self.user)
        self.assertEqual(str(gerente), "juan")

    def test_cuando_un_usuario_se_asigna_a_un_segundo_cliente_entonces_falla(self):
        Customer.objects.create(user=self.user)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Customer.objects.create(user=self.user)

    def test_cuando_un_usuario_se_elimina_entonces_se_elimina_el_cliente_asociado(self):
        Customer.objects.create(user=self.user)

        self.user.delete()

        self.assertEqual(Customer.objects.count(), 0)

    def test_cuando_un_usuario_se_elimina_entonces_se_elimina_el_acomodador_asociado(self):
        Usher.objects.create(user=self.user)

        self.user.delete()

        self.assertEqual(Usher.objects.count(), 0)

    def test_cuando_un_usuario_se_elimina_entonces_se_elimina_el_gerente_asociado(self):
        Manager.objects.create(user=self.user)

        self.user.delete()

        self.assertEqual(Manager.objects.count(), 0)


class ValidacionMailAdminUsuarioTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="juan",
            email="juan@mail.com",
            password="PasswordSegura123!",
        )

    def test_al_crear_usuario_el_mail_es_obligatorio(self):
        form = AdminUserCreationForm(
            data={
                "username": "ana",
                "email": "",
                "password1": "PasswordSegura123!",
                "password2": "PasswordSegura123!",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_al_crear_usuario_el_mail_no_puede_repetirse(self):
        form = AdminUserCreationForm(
            data={
                "username": "ana",
                "email": "JUAN@mail.com",
                "password1": "PasswordSegura123!",
                "password2": "PasswordSegura123!",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
        self.assertEqual(form.email_duplicado, "juan@mail.com")

    def test_al_editar_usuario_permite_conservar_su_mismo_mail(self):
        form = AdminUserChangeForm(
            instance=self.user,
            data={
                "username": "juan",
                "email": "juan@mail.com",
                "password": self.user.password,
                "date_joined": self.user.date_joined.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

        self.assertTrue(form.is_valid())

    def test_al_editar_usuario_no_permite_usar_mail_de_otro_usuario(self):
        otro_usuario = get_user_model().objects.create_user(
            username="ana",
            email="ana@mail.com",
            password="PasswordSegura123!",
        )
        form = AdminUserChangeForm(
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
        form = CustomerSignupForm(
            data={
                "name": "Ana",
                "last_name": "Gomez",
                "email": "ANA@mail.com",
                "password1": "PasswordSegura123!",
                "password2": "PasswordSegura123!",
            }
        )

        self.assertTrue(form.is_valid())

        user = form.save()

        self.assertEqual(user.username, "ana@mail.com")
        self.assertEqual(user.email, "ana@mail.com")
        self.assertEqual(user.first_name, "Ana")
        self.assertEqual(user.last_name, "Gomez")
        self.assertTrue(user.check_password("PasswordSegura123!"))

    def test_si_un_usuario_se_registra_con_password_invalida_entonces_devuelve_error(self):
        form = CustomerSignupForm(
            data={
                "name": "Ana",
                "last_name": "Gomez",
                "email": "ana@mail.com",
                "password1": "12345678",
                "password2": "12345678",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password1", form.errors)

    def test_si_un_usuario_se_registra_sin_numero_entonces_devuelve_error(self):
        form = CustomerSignupForm(
            data={
                "name": "Ana",
                "last_name": "Gomez",
                "email": "ana@mail.com",
                "password1": "PasswordSegura!",
                "password2": "PasswordSegura!",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password1", form.errors)
        self.assertIn(
            "La contraseña debe incluir al menos un número.",
            form.errors["password1"],
        )

    def test_si_un_usuario_se_registra_sin_caracter_especial_entonces_devuelve_error(self):
        form = CustomerSignupForm(
            data={
                "name": "Ana",
                "last_name": "Gomez",
                "email": "ana@mail.com",
                "password1": "PasswordSegura123",
                "password2": "PasswordSegura123",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password1", form.errors)
        self.assertIn(
            "La contraseña debe incluir al menos un carácter especial.",
            form.errors["password1"],
        )
