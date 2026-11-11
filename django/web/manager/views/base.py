"""Base."""

from django.contrib import messages
from django.db.models.deletion import ProtectedError
from django.shortcuts import redirect
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from web.manager.access import ManagerRequiredMixin


class ManagerListView(ManagerRequiredMixin, ListView):
    paginate_by = 20
    page_size_options = (10, 20, 50, 100)
    search_placeholder = "Buscar"
    search_query_param = "q"
    ordering_query_param = "order"
    ordering_options = ()

    def get_page_size(self):
        try:
            page_size = int(self.request.GET.get("per_page", self.paginate_by))
        except (TypeError, ValueError):
            return self.paginate_by
        if page_size in self.page_size_options:
            return page_size
        return self.paginate_by

    def get_paginate_by(self, queryset):
        return self.get_page_size()

    def get_search_query(self):
        return self.request.GET.get(self.search_query_param, "").strip()

    def get_ordering_value(self):
        requested_ordering = self.request.GET.get(self.ordering_query_param, "")
        allowed_orderings = {option[0] for option in self.ordering_options}
        if requested_ordering in allowed_orderings:
            return requested_ordering
        if self.ordering_options:
            return self.ordering_options[0][0]
        return ""

    def get_ordering_fields(self):
        selected_ordering = self.get_ordering_value()
        for value, _label, fields in self.ordering_options:
            if value == selected_ordering:
                return fields
        return ()

    def apply_ordering(self, queryset):
        ordering_fields = self.get_ordering_fields()
        if ordering_fields:
            return queryset.order_by(*ordering_fields)
        return queryset

    def get_queryset(self):
        queryset = super().get_queryset()
        search_query = self.get_search_query()
        if search_query:
            queryset = self.apply_search(queryset, search_query)
        return self.apply_ordering(queryset)

    def apply_search(self, queryset, search_query):
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["create_url_name"] = self.create_url_name
        context["columns"] = self.columns
        context["search_query"] = self.get_search_query()
        context["search_placeholder"] = self.search_placeholder
        context["ordering_options"] = self.ordering_options
        context["selected_ordering"] = self.get_ordering_value()
        context["page_size"] = self.get_page_size()
        context["page_size_options"] = self.page_size_options
        context["has_list_filters"] = bool(
            self.get_search_query()
        ) or self.get_ordering_value() != (
            self.ordering_options[0][0] if self.ordering_options else ""
        )
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["list_querystring"] = query_params.urlencode()
        return context


class ManagerCreateView(ManagerRequiredMixin, CreateView):
    template_name = "manager_form.html"
    form_title = ""
    success_message = ""

    def form_valid(self, form):
        messages.success(
            self.request,
            self.success_message or f"{self.object_label} se creó correctamente.",
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["submit_label"] = "Crear"
        context["form_title"] = self.form_title or f"Nuevo {self.object_label.lower()}"
        context["enctype"] = self.enctype
        return context


class ManagerUpdateView(ManagerRequiredMixin, UpdateView):
    template_name = "manager_form.html"
    form_title = ""

    def form_valid(self, form):
        messages.success(self.request, f"{self.object_label} se actualizó correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["submit_label"] = "Guardar"
        context["form_title"] = self.form_title or f"Editar {self.object_label.lower()}"
        context["enctype"] = self.enctype
        return context


class ManagerDeleteView(ManagerRequiredMixin, DeleteView):
    template_name = "manager_confirm_delete.html"
    protected_error_message = (
        "No se puede eliminar: tiene registros relacionados. Se conserva el historial."
    )

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, self.protected_error_message)
            return redirect(self.get_success_url())
        messages.success(self.request, "Se eliminó correctamente.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["object_label"] = self.object_label
        return context
