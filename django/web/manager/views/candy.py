"""Candy."""

from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.urls import reverse_lazy
from domain.candy.models import CandyCombo, CandyProduct

from web.manager.forms import CandyComboForm, CandyProductForm
from web.manager.views.base import (
    ManagerCreateView,
    ManagerDeleteView,
    ManagerListView,
    ManagerUpdateView,
)


class CandyProductsListView(ManagerListView):
    model = CandyProduct
    template_name = "manager_candy_products_list.html"
    section = "Candy"
    create_url_name = "manager:candy_products_create"
    columns = ("Producto", "Categoría", "Precio", "Stock", "Estado")
    search_placeholder = "Buscar por nombre"
    extra_context = {"candy_tab": "products"}
    ordering_options = (
        ("categoria", "Categoría", ("_category_rank", "name")),
        ("nombre_asc", "Nombre A-Z", ("name",)),
        ("stock_asc", "Menor stock", ("stock", "name")),
        ("precio_desc", "Mayor precio", ("-price", "name")),
    )

    def apply_ordering(self, queryset):
        queryset = queryset.annotate(
            _category_rank=Case(
                *(
                    When(category=category, then=Value(rank))
                    for rank, category in enumerate(CandyProduct.Category.values)
                ),
                output_field=IntegerField(),
            )
        )
        return super().apply_ordering(queryset)

    def apply_search(self, queryset, search_query):
        return queryset.filter(name__icontains=search_query)


class CandyProductCreateView(ManagerCreateView):
    model = CandyProduct
    form_class = CandyProductForm
    success_url = reverse_lazy("manager:candy_products_list")
    section = "Candy"
    enctype = "multipart/form-data"
    object_label = "El producto"
    form_title = "Nuevo producto de candy"


class CandyProductUpdateView(ManagerUpdateView):
    model = CandyProduct
    form_class = CandyProductForm
    success_url = reverse_lazy("manager:candy_products_list")
    section = "Candy"
    enctype = "multipart/form-data"
    object_label = "El producto"
    form_title = "Editar producto de candy"


class CandyProductDeleteView(ManagerDeleteView):
    model = CandyProduct
    success_url = reverse_lazy("manager:candy_products_list")
    section = "Candy"
    object_label = "El producto"

    protected_error_message = "No se puede eliminar un producto que forma parte de un combo. Quitalo del combo o desactivalo."


class CandyCombosListView(ManagerListView):
    model = CandyCombo
    template_name = "manager_candy_combos_list.html"
    section = "Candy"
    create_url_name = "manager:candy_combos_create"
    columns = ("Combo", "Contenido", "Precio", "Disponibles", "Estado")
    search_placeholder = "Buscar por nombre"
    extra_context = {"candy_tab": "combos"}
    ordering_options = (
        ("nombre_asc", "Nombre A-Z", ("name",)),
        ("precio_asc", "Menor precio", ("price", "name")),
        ("precio_desc", "Mayor precio", ("-price", "name")),
    )

    def get_queryset(self):
        return super().get_queryset().prefetch_related("items__product")

    def apply_search(self, queryset, search_query):
        return queryset.filter(name__icontains=search_query)


class CandyComboFormMixin:
    model = CandyCombo
    form_class = CandyComboForm
    template_name = "manager_candy_combo_form.html"
    success_url = reverse_lazy("manager:candy_combos_list")
    section = "Candy"
    enctype = "multipart/form-data"
    object_label = "El combo"

    def form_valid(self, form):
        with transaction.atomic():
            return super().form_valid(form)


class CandyComboCreateView(CandyComboFormMixin, ManagerCreateView):
    form_title = "Nuevo combo"


class CandyComboUpdateView(CandyComboFormMixin, ManagerUpdateView):
    form_title = "Editar combo"


class CandyComboDeleteView(ManagerDeleteView):
    model = CandyCombo
    success_url = reverse_lazy("manager:candy_combos_list")
    section = "Candy"
    object_label = "El combo"
