"""Screenings."""

from decimal import Decimal

from django.utils import timezone
from domain.screenings.models import Screening
from domain.seat_types.models import SeatType
from domain.seats.models import Seat

from django import forms


class ScreeningForm(forms.ModelForm):
    starts_at = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = Screening
        fields = ("movie", "room", "starts_at")
        labels = {
            "movie": "Película",
            "room": "Sala",
            "starts_at": "Fecha y horario",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["movie"].empty_label = "Seleccioná una película"
        self.fields["room"].empty_label = "Seleccioná una sala"
        if self.instance.pk:
            self.fields["room"].disabled = True
            self.fields[
                "room"
            ].help_text = "La sala queda bloqueada al crear la función para conservar la configuración de butacas publicada."
            self.fields["room"].widget.attrs.update(
                {
                    "class": "is-locked-field",
                    "data-locked": "true",
                }
            )

    def clean_starts_at(self):
        starts_at = self.cleaned_data["starts_at"]
        if starts_at <= timezone.now():
            raise forms.ValidationError("La fecha y horario deben ser futuros.")
        return starts_at

    def clean(self):
        cleaned_data = super().clean()
        room = cleaned_data.get("room")
        if not room:
            return cleaned_data

        required_type_ids = set(
            str(type_id)
            for type_id in Seat.objects.filter(room=room)
            .values_list("seat_type_id", flat=True)
            .distinct()
        )
        if not required_type_ids:
            required_type_ids = set(str(pk) for pk in SeatType.objects.values_list("pk", flat=True))

        base_prices = {
            str(pk): str(price) for pk, price in SeatType.objects.values_list("pk", "base_price")
        }
        completed_prices = {}
        missing = []
        for type_id in required_type_ids:
            price = base_prices.get(type_id)
            if price is None:
                missing.append(type_id)
            else:
                completed_prices[type_id] = str(Decimal(str(price)))

        if missing:
            raise forms.ValidationError("Indica el precio para cada tipo de butaca.")

        cleaned_data["prices_by_type"] = completed_prices
        cleaned_data["ticket_price"] = min(
            Decimal(str(price)) for price in completed_prices.values()
        )
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        prices = self.cleaned_data.get("prices_by_type") or {}
        instance.prices_by_type = prices
        if prices:
            instance.ticket_price = min(Decimal(str(price)) for price in prices.values())
        if commit:
            instance.save()
            self.save_m2m()
        return instance
