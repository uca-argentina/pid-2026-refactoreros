"""Validación de filtros de lectura del panel de gestión."""

from django import forms
from django.utils import timezone


class DashboardFilterForm(forms.Form):
    date_from = forms.DateField(
        required=False, error_messages={"invalid": "La fecha Desde no es válida."}
    )
    date_to = forms.DateField(
        required=False, error_messages={"invalid": "La fecha Hasta no es válida."}
    )

    def clean(self):
        data = super().clean()
        date_from, date_to = data.get("date_from"), data.get("date_to")
        today = timezone.localdate()
        for name, label in (("date_from", "Desde"), ("date_to", "Hasta")):
            if data.get(name) and data[name] > today:
                self.add_error(name, f"La fecha {label} no puede ser posterior a hoy.")
        if date_from and date_to and date_from > date_to:
            self.add_error(None, "La fecha Desde debe ser anterior o igual a Hasta.")
        return data
