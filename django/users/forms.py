from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

User = get_user_model()


class EmailUnicoMixin:
    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()

        if not email:
            raise forms.ValidationError("El mail es obligatorio.")

        usuarios_con_mismo_mail = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            usuarios_con_mismo_mail = usuarios_con_mismo_mail.exclude(
                pk=self.instance.pk
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
