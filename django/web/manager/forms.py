from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from domain.movies.models import Pelicula
from domain.rooms.models import Sala
from domain.screenings.models import Funcion

User = get_user_model()
MAX_MOVIE_IMAGE_SIZE_MB = 2
MAX_MOVIE_IMAGE_SIZE_BYTES = MAX_MOVIE_IMAGE_SIZE_MB * 1024 * 1024


class UsuarioGestionForm(forms.ModelForm):
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
        usuarios = User.objects.exclude(pk=self.instance.pk)
        if usuarios.filter(username__iexact=email).exists() or usuarios.filter(
            email__iexact=email
        ).exists():
            raise forms.ValidationError("Ya existe un usuario con ese email.")
        return email


class SalaForm(forms.ModelForm):
    class Meta:
        model = Sala
        fields = ("nombre", "capacidad")


class PeliculaForm(forms.ModelForm):
    class Meta:
        model = Pelicula
        fields = (
            "titulo",
            "sinopsis",
            "genero",
            "clasificacion",
            "duracion_minutos",
            "imagen",
        )
        widgets = {
            "imagen": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }
        help_texts = {
            "imagen": f"Peso maximo: {MAX_MOVIE_IMAGE_SIZE_MB} MB.",
        }

    def clean_imagen(self):
        imagen = self.cleaned_data.get("imagen")
        if imagen and getattr(imagen, "size", 0) > MAX_MOVIE_IMAGE_SIZE_BYTES:
            raise forms.ValidationError(
                f"La imagen no puede superar los {MAX_MOVIE_IMAGE_SIZE_MB} MB."
            )
        return imagen


class FuncionForm(forms.ModelForm):
    fecha_horario = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = Funcion
        fields = ("pelicula", "sala", "fecha_horario", "precio_entrada")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pelicula"].empty_label = "Seleccioná una película"
        self.fields["sala"].empty_label = "Seleccioná una sala"

    def clean_fecha_horario(self):
        fecha_horario = self.cleaned_data["fecha_horario"]
        if fecha_horario <= timezone.now():
            raise forms.ValidationError("La fecha y horario deben ser futuros.")
        return fecha_horario

    def clean_precio_entrada(self):
        precio_entrada = self.cleaned_data["precio_entrada"]
        if precio_entrada <= 0:
            raise forms.ValidationError("El precio de entrada debe ser mayor a cero.")
        return precio_entrada
