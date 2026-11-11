"""Users."""

from django.contrib.auth import get_user_model

from django import forms

User = get_user_model()


class UserManagementForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellido",
            "email": "Email",
        }

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("El email es obligatorio.")
        users = User.objects.exclude(pk=self.instance.pk)
        if (
            users.filter(username__iexact=email).exists()
            or users.filter(email__iexact=email).exists()
        ):
            raise forms.ValidationError("Ya existe un usuario con ese email.")
        return email
