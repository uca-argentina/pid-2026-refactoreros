from django import forms


class TicketPurchaseForm(forms.Form):
    cantidad = forms.IntegerField(
        min_value=1,
        label="Cantidad",
        widget=forms.NumberInput(attrs={"min": 1}),
    )
