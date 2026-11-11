"""Seat types."""

from django.db.models import Count
from django.urls import reverse_lazy
from domain.seat_types.models import SeatType

from web.manager.forms import SeatTypeForm
from web.manager.views.base import (
    ManagerCreateView,
    ManagerDeleteView,
    ManagerListView,
    ManagerUpdateView,
)


class SeatTypesListView(ManagerListView):
    model = SeatType
    template_name = "manager_seat_types_list.html"
    section = "Butacas"
    create_url_name = "manager:seat_types_create"
    columns = ("Nombre", "Precio", "Color", "Butacas")
    search_placeholder = "Buscar por nombre"
    ordering_options = (
        ("nombre_asc", "Nombre A-Z", ("name",)),
        ("nombre_desc", "Nombre Z-A", ("-name",)),
        ("precio_asc", "Menor precio", ("base_price", "name")),
        ("precio_desc", "Mayor precio", ("-base_price", "name")),
    )

    def get_queryset(self):
        queryset = SeatType.objects.annotate(seat_count=Count("seats"))
        search_query = self.get_search_query()
        if search_query:
            queryset = self.apply_search(queryset, search_query)
        return self.apply_ordering(queryset)

    def apply_search(self, queryset, search_query):
        return queryset.filter(name__icontains=search_query)


class SeatTypeCreateView(ManagerCreateView):
    model = SeatType
    form_class = SeatTypeForm
    success_url = reverse_lazy("manager:seat_types_list")
    section = "Butacas"
    enctype = "multipart/form-data"
    object_label = "El tipo de butaca"
    form_title = "Nuevo tipo de butaca"


class SeatTypeUpdateView(ManagerUpdateView):
    model = SeatType
    form_class = SeatTypeForm
    success_url = reverse_lazy("manager:seat_types_list")
    section = "Butacas"
    enctype = "multipart/form-data"
    object_label = "El tipo de butaca"
    form_title = "Editar tipo de butaca"


class SeatTypeDeleteView(ManagerDeleteView):
    model = SeatType
    success_url = reverse_lazy("manager:seat_types_list")
    section = "Butacas"
    object_label = "El tipo de butaca"

    protected_error_message = "No se puede eliminar un tipo de butaca que esta usado en una sala."
