"""Promotions."""

from domain.promotions.models import Promotion
from domain.seat_types.models import SeatType

from django import forms


class PromotionForm(forms.ModelForm):
    weekdays = forms.TypedMultipleChoiceField(
        choices=Promotion.Weekday.choices,
        coerce=int,
        required=False,
        label="Días de la semana",
        help_text="Sin días seleccionados, la promoción aplica todos los días.",
        widget=forms.CheckboxSelectMultiple,
    )
    starts_at = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        label="Horario desde",
        help_text="Se evalúa según el horario de inicio de la función.",
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
    )
    ends_at = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        label="Horario hasta",
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
    )

    class Meta:
        model = Promotion
        fields = (
            "name",
            "is_active",
            "discount_type",
            "discount_value",
            "weekdays",
            "starts_at",
            "ends_at",
            "seat_types",
        )
        labels = {
            "name": "Nombre",
            "is_active": "Activa",
            "discount_type": "Tipo de descuento",
            "discount_value": "Descuento",
            "seat_types": "Tipos de butaca",
        }
        help_texts = {
            "discount_value": "Elegí porcentaje o un monto fijo a descontar.",
            "seat_types": "Sin tipos seleccionados, aplica a todas las butacas.",
        }
        widgets = {
            "seat_types": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        seat_types = SeatType.objects.order_by("name")
        self.fields["seat_types"].queryset = seat_types

        selected_weekdays = {str(value) for value in (self["weekdays"].value() or [])}
        self.weekday_chips = [
            {
                "value": str(value),
                "label": label,
                "id": f"{self['weekdays'].auto_id}_{value}",
                "checked": str(value) in selected_weekdays,
            }
            for value, label in Promotion.Weekday.choices
        ]

        selected_seat_types = {str(value) for value in (self["seat_types"].value() or [])}
        self.seat_type_chips = [
            {
                "value": str(seat_type.pk),
                "name": seat_type.name,
                "color": seat_type.color,
                "id": f"{self['seat_types'].auto_id}_{seat_type.pk}",
                "checked": str(seat_type.pk) in selected_seat_types,
            }
            for seat_type in seat_types
        ]

    def clean(self):
        cleaned_data = super().clean()
        starts_at = cleaned_data.get("starts_at")
        ends_at = cleaned_data.get("ends_at")
        if bool(starts_at) != bool(ends_at):
            message = "Indicá ambos horarios o dejá los dos vacíos."
            self.add_error("starts_at", message)
            self.add_error("ends_at", message)
        return cleaned_data
