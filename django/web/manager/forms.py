from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
import json

from domain.movies.models import Pelicula
from domain.rooms.models import Sala
from domain.screenings.models import Funcion
from domain.seats.models import Seat

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

    MAX_ROW, MAX_COLUMN = 100,100

    layout_sala = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = Sala
        fields = ("nombre",)

    def clean_layout_sala(self):
        try:
            data_as_string = self.cleaned_data["layout"]
            data = json.loads(data_as_string)
        except ValueError:
            raise forms.ValidationError("El plano enviado no es válido.")

        if not isinstance(data, list) or not data:
            raise forms.ValidationError("Dibujá al menos un asiento.")
        if len(data) > (self.MAX_ROW*self.MAX_COLUMN):
            raise forms.ValidationError(f"Máximo {self.MAX_ROW*self.MAX_COLUMN} asientos por sala.")

        seats_data, positions = [] , set()
        for seat_data in data:
            try:
                row,column = seat_data["row"], seat_data["column"]
            except(KeyError, TypeError,ValueError):
                raise forms.ValidationError("El plano de la sala contiene datos incorrectos.")

            if(row > self.MAX_ROW or column > self.MAX_COLUMN):
                raise forms.ValidationError(f"Hay asientos fuera del limite (máximo de filas {self.MAX_ROW} y máximo de columnas {self.MAX_COLUMN}).")

            if((row,column) in positions):
                raise forms.ValidationError("Hay asientos duplicados.")
            positions.add((row,column))
            seats_data.append({"row":row,"column":column})

        return seats_data


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
