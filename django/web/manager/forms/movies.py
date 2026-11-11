"""Movies."""

from domain.movies.models import Movie

from django import forms

from .uploads import MAX_MOVIE_IMAGE_SIZE_MB, validate_image_size


class MovieForm(forms.ModelForm):
    class Meta:
        model = Movie
        fields = (
            "title",
            "synopsis",
            "genre",
            "rating",
            "duration_minutes",
            "image",
        )
        widgets = {
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }
        labels = {
            "title": "Título",
            "synopsis": "Sinopsis",
            "genre": "Género",
            "rating": "Clasificación",
            "duration_minutes": "Duración en minutos",
            "image": "Imagen del cartel",
        }
        help_texts = {
            "image": f"Peso maximo: {MAX_MOVIE_IMAGE_SIZE_MB} MB.",
        }

    def clean_image(self):
        return validate_image_size(self.cleaned_data.get("image"), "La imagen")
