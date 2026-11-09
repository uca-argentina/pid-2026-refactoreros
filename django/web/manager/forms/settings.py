"""Settings."""

from domain.cinema.models import CinemaSettings

from django import forms


class CinemaSettingsForm(forms.ModelForm):
    ticket_reprogram_minutes = forms.IntegerField(
        min_value=0,
        label="Anticipación mínima para cambiar de función (minutos)",
        help_text="120 equivale a 2 horas antes del inicio. Con 0 se permite cambiar hasta que comienza la función.",
    )
    candy_max_item_quantity = forms.IntegerField(
        min_value=1,
        label="Máximo de unidades por producto o combo de Candy en cada pedido",
        help_text="Se aplica al Candy comprado solo o con entradas. Si el stock es menor, prevalece el stock disponible.",
    )
    seat_reservation_minutes = forms.IntegerField(
        min_value=1,
        label="Reserva temporal de butacas (minutos)",
        help_text="Tiempo durante el checkout antes de liberar butacas no confirmadas.",
    )
    seat_refresh_seconds = forms.IntegerField(
        min_value=1,
        label="Recarga automática de butacas (segundos)",
        help_text="Frecuencia con la que el cliente vuelve a consultar disponibilidad.",
    )
    admission_undo_seconds = forms.IntegerField(
        min_value=5,
        max_value=600,
        label="Deshacer validación de entradas (segundos)",
        help_text="Tiempo que tiene el operador para deshacer una validación por error.",
    )

    class Meta:
        model = CinemaSettings
        fields = (
            "seat_reservation_minutes",
            "seat_refresh_seconds",
            "admission_undo_seconds",
            "candy_max_item_quantity",
            "ticket_reprogram_minutes",
        )
