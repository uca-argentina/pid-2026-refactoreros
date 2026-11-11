"""Seat types."""

from domain.seat_types.models import SeatType

from django import forms

from .uploads import validate_image_size


class SeatTypeForm(forms.ModelForm):
    class Meta:
        model = SeatType
        fields = ("name", "base_price", "color", "icon")
        labels = {
            "name": "Nombre",
            "base_price": "Precio",
            "color": "Color",
            "icon": "Icono",
        }
        help_texts = {
            "icon": "Opcional. Se muestra en el mapa de selección del cliente en lugar de la coordenada de la butaca.",
        }
        widgets = {
            "color": forms.TextInput(attrs={"type": "color"}),
            "icon": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def clean_base_price(self):
        price = self.cleaned_data["base_price"]
        if price <= 0:
            raise forms.ValidationError("El precio debe ser mayor a cero.")
        return price

    def clean_icon(self):
        return validate_image_size(self.cleaned_data.get("icon"), "El icono")
