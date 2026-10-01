import json

from django import forms


class TicketPurchaseForm(forms.Form):
    cantidad = forms.IntegerField(
        min_value=1,
        label="Cantidad",
        widget=forms.NumberInput(attrs={"min": 1}),
    )
    selected_seats = forms.CharField(required=False)

    def clean_selected_seats(self):
        value = self.cleaned_data.get("selected_seats")
        if not value:
            return []
        try:
            selected_seats = json.loads(value)
        except ValueError:
            raise forms.ValidationError("La seleccion de asientos no es valida.")
        if not isinstance(selected_seats, list):
            raise forms.ValidationError("La seleccion de asientos no es valida.")
        return selected_seats
