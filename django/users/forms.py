from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class EmailUnicoMixin:
    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()

        if not email:
            raise forms.ValidationError("El mail es obligatorio.")

        usuarios_con_mismo_mail = User.objects.filter(email__iexact=email)
        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            usuarios_con_mismo_mail = usuarios_con_mismo_mail.exclude(
                pk=instance.pk
            )

        if usuarios_con_mismo_mail.exists():
            raise forms.ValidationError("Ya existe un usuario con ese mail.")

        return email


class UsuarioCreationForm(EmailUnicoMixin, UserCreationForm):
    email = forms.EmailField(label="Mail", required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class UsuarioChangeForm(EmailUnicoMixin, UserChangeForm):
    email = forms.EmailField(label="Mail", required=True)

    class Meta(UserChangeForm.Meta):
        model = User


class ClienteSignupForm(EmailUnicoMixin, forms.Form):
    nombre = forms.CharField(
        label="Nombre",
        max_length=75,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "given-name",
                "placeholder": "Nombre",
            }
        ),
    )
    apellido = forms.CharField(
        label="Apellido",
        max_length=75,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "family-name",
                "placeholder": "Apellido",
            }
        ),
    )
    email = forms.EmailField(
        label="Mail",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "Email",
            }
        ),
    )
    password1 = forms.CharField(
        label="Contrasena",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Contrasena",
            }
        ),
    )
    password2 = forms.CharField(
        label="Repetir contrasena",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Repetir contrasena",
            }
        ),
    )

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        if len(nombre) < 2:
            raise forms.ValidationError("El nombre debe tener al menos 2 caracteres.")
        return nombre

    def clean_apellido(self):
        apellido = self.cleaned_data["apellido"].strip()
        if len(apellido) < 2:
            raise forms.ValidationError("El apellido debe tener al menos 2 caracteres.")
        return apellido

    def clean(self):
        cleaned_data = super().clean()
        nombre = cleaned_data.get("nombre")
        apellido = cleaned_data.get("apellido")
        email = cleaned_data.get("email")
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Las contrasenas no coinciden.")
            return cleaned_data

        if password1:
            usuario = User(
                username=email or "",
                email=email or "",
                first_name=nombre or "",
                last_name=apellido or "",
            )
            try:
                validate_password(password1, usuario)
            except forms.ValidationError as error:
                self.add_error("password1", error)

        return cleaned_data

    def save(self):
        nombre = self.cleaned_data["nombre"]
        apellido = self.cleaned_data["apellido"]
        email = self.cleaned_data["email"]
        password = self.cleaned_data["password1"]
        return User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=nombre,
            last_name=apellido,
        )
