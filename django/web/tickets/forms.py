import json

from django import forms
from domain.users.models import Customer


class CandyPurchaseForm(forms.Form):
    checkout_key = forms.UUIDField(widget=forms.HiddenInput)
    candy_items = forms.CharField(required=False)

    def clean_candy_items(self):
        value = self.cleaned_data.get("candy_items")
        if not value:
            return []
        try:
            candy_items = json.loads(value)
        except ValueError:
            raise forms.ValidationError("La selección de candy no es válida.")
        if not isinstance(candy_items, list):
            raise forms.ValidationError("La selección de candy no es válida.")
        return candy_items

class TicketPurchaseForm(CandyPurchaseForm):
    checkout_key = None
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

class TicketReprogramForm(TicketPurchaseForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("candy_items", None)


class TicketTransferForm(forms.Form):
    selected_user = forms.CharField(required=False)

    def clean_transferee_user(self):
            transferee_user = self.cleaned_data.get("email_transferee")
            user = Customer.objects.filter(email=transferee_user)
            if user != transferee_user.email:
                pass



