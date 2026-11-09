"""Promotions."""

from django.urls import reverse_lazy
from domain.promotions.models import Promotion

from web.manager.forms import PromotionForm
from web.manager.views.base import (
    ManagerCreateView,
    ManagerDeleteView,
    ManagerListView,
    ManagerUpdateView,
)


class PromotionsListView(ManagerListView):
    model = Promotion
    template_name = "manager_promotions_list.html"
    section = "Promociones"
    create_url_name = "manager:promotions_create"
    columns = ("Nombre", "Descuento", "Días", "Horario", "Butacas", "Estado")
    search_placeholder = "Buscar por nombre"
    ordering_options = (
        ("activas", "Activas primero", ("-is_active", "name")),
        ("nombre_asc", "Nombre A-Z", ("name",)),
        ("nombre_desc", "Nombre Z-A", ("-name",)),
        ("descuento_desc", "Mayor descuento", ("-discount_value", "name")),
    )

    def get_queryset(self):
        queryset = Promotion.objects.prefetch_related("seat_types")
        search_query = self.get_search_query()
        if search_query:
            queryset = self.apply_search(queryset, search_query)
        return self.apply_ordering(queryset)

    def apply_search(self, queryset, search_query):
        return queryset.filter(name__icontains=search_query)


class PromotionCreateView(ManagerCreateView):
    model = Promotion
    form_class = PromotionForm
    template_name = "manager_promotion_form.html"
    success_url = reverse_lazy("manager:promotions_list")
    section = "Promociones"
    enctype = ""
    object_label = "La promoción"
    form_title = "Nueva promoción"


class PromotionUpdateView(ManagerUpdateView):
    model = Promotion
    form_class = PromotionForm
    template_name = "manager_promotion_form.html"
    success_url = reverse_lazy("manager:promotions_list")
    section = "Promociones"
    enctype = ""
    object_label = "La promoción"
    form_title = "Editar promoción"


class PromotionDeleteView(ManagerDeleteView):
    model = Promotion
    success_url = reverse_lazy("manager:promotions_list")
    section = "Promociones"
    object_label = "La promoción"
