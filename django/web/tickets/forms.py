import json

from django import forms


class TicketPurchaseForm(forms.Form):
    selected_seats = forms.CharField(required=False)

    def clean_selected_seats(self):
        value = self.cleaned_data.get("selected_seats")
        if not value:
            raise forms.ValidationError("Seleccioná al menos una butaca.")
        try:
            selected_seats = json.loads(value)
        except ValueError:
            raise forms.ValidationError("La seleccion de asientos no es valida.")
        if not isinstance(selected_seats, list) or not selected_seats:
            raise forms.ValidationError("La seleccion de asientos no es valida.")
        return selected_seats
