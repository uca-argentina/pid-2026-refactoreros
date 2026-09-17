from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from domain.movies.models import Pelicula
from domain.rooms.models import Sala
from domain.screenings.models import Funcion

from .forms import FuncionForm, PeliculaForm, SalaForm, UsuarioGestionForm

User = get_user_model()


def manager_role(user):
    if not user.is_authenticated:
        return ""
    if hasattr(user, "gerente"):
        return "gerente"
    if hasattr(user, "acomodador"):
        return "acomodador"
    return ""


class ManagerAccessMixin(LoginRequiredMixin):
    login_url = "login"

    def has_manager_access(self, role):
        return bool(role)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.manager_role = manager_role(request.user)
        if not self.has_manager_access(self.manager_role):
            raise PermissionDenied
        return super(LoginRequiredMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["manager_role"] = self.manager_role
        return context


class GerenteRequiredMixin(ManagerAccessMixin):
    def has_manager_access(self, role):
        return role == "gerente"


class GestionHomeView(ManagerAccessMixin, TemplateView):
    template_name = "manager/home.html"


class GerenteListView(GerenteRequiredMixin, ListView):
    paginate_by = 20
    page_size_options = (10, 20, 50, 100)
    search_placeholder = "Buscar"
    search_query_param = "q"

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

    def get_queryset(self):
        queryset = super().get_queryset()
        search_query = self.get_search_query()
        if search_query:
            queryset = self.apply_search(queryset, search_query)
        return queryset

    def apply_search(self, queryset, search_query):
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["create_url_name"] = self.create_url_name
        context["columns"] = self.columns
        context["search_query"] = self.get_search_query()
        context["search_placeholder"] = self.search_placeholder
        context["page_size"] = self.get_page_size()
        context["page_size_options"] = self.page_size_options
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["list_querystring"] = query_params.urlencode()
        return context


class GerenteCreateView(GerenteRequiredMixin, CreateView):
    template_name = "manager/form.html"

    def form_valid(self, form):
        messages.success(self.request, f"{self.object_label} creada correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["submit_label"] = "Crear"
        context["enctype"] = self.enctype
        return context


class GerenteUpdateView(GerenteRequiredMixin, UpdateView):
    template_name = "manager/form.html"

    def form_valid(self, form):
        messages.success(self.request, f"{self.object_label} actualizado correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["submit_label"] = "Guardar"
        context["enctype"] = self.enctype
        return context


class GerenteDeleteView(GerenteRequiredMixin, DeleteView):
    template_name = "manager/confirm_delete.html"

    def form_valid(self, form):
        messages.success(self.request, f"{self.object_label} eliminado correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        return context


class UsuariosListView(GerenteListView):
    model = User
    template_name = "manager/usuarios_list.html"
    section = "Usuarios"
    create_url_name = ""
    columns = ("Email", "Nombre", "Rol", "Estado")
    search_placeholder = "Buscar por email o nombre"

    def apply_search(self, queryset, search_query):
        return queryset.filter(
            Q(email__icontains=search_query)
            | Q(username__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["usuarios"] = [
            {
                "usuario": usuario,
                "rol": manager_role(usuario) or "cliente",
            }
            for usuario in context["object_list"]
        ]
        return context

    def get_queryset(self):
        return super().get_queryset().order_by("email", "username")


class UsuarioUpdateView(GerenteRequiredMixin, UpdateView):
    model = User
    form_class = UsuarioGestionForm
    template_name = "manager/form.html"
    success_url = reverse_lazy("manager:usuarios_list")
    section = "Usuarios"
    enctype = ""
    object_label = "Usuario"

    def form_valid(self, form):
        form.instance.username = form.cleaned_data["email"]
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["submit_label"] = "Guardar"
        context["enctype"] = self.enctype
        return context


class UsuarioToggleActiveView(GerenteRequiredMixin, DetailView):
    model = User

    def post(self, request, *args, **kwargs):
        usuario = self.get_object()
        usuario.is_active = not usuario.is_active
        usuario.save(update_fields=["is_active"])
        estado = "activado" if usuario.is_active else "bloqueado"
        messages.success(request, f"Usuario {estado} correctamente.")
        return redirect("manager:usuarios_list")


class SalasListView(GerenteListView):
    model = Sala
    template_name = "manager/salas_list.html"
    section = "Salas"
    create_url_name = "manager:salas_create"
    columns = ("Nombre", "Capacidad")
    search_placeholder = "Buscar por nombre"

    def apply_search(self, queryset, search_query):
        return queryset.filter(nombre__icontains=search_query)


class SalaCreateView(GerenteCreateView):
    model = Sala
    form_class = SalaForm
    success_url = reverse_lazy("manager:salas_list")
    section = "Salas"
    enctype = ""
    object_label = "Sala"


class SalaUpdateView(GerenteUpdateView):
    model = Sala
    form_class = SalaForm
    success_url = reverse_lazy("manager:salas_list")
    section = "Salas"
    enctype = ""
    object_label = "Sala"


class SalaDeleteView(GerenteDeleteView):
    model = Sala
    success_url = reverse_lazy("manager:salas_list")
    section = "Salas"
    object_label = "Sala"


class PeliculasListView(GerenteListView):
    model = Pelicula
    template_name = "manager/peliculas_list.html"
    section = "Peliculas"
    create_url_name = "manager:peliculas_create"
    columns = ("Titulo", "Genero", "Clasificacion", "Duracion")
    search_placeholder = "Buscar por titulo, genero o sinopsis"

    def apply_search(self, queryset, search_query):
        return queryset.filter(
            Q(titulo__icontains=search_query)
            | Q(sinopsis__icontains=search_query)
            | Q(genero__icontains=search_query)
        )


class PeliculaCreateView(GerenteCreateView):
    model = Pelicula
    form_class = PeliculaForm
    success_url = reverse_lazy("manager:peliculas_list")
    section = "Peliculas"
    enctype = "multipart/form-data"
    object_label = "Pelicula"


class PeliculaUpdateView(GerenteUpdateView):
    model = Pelicula
    form_class = PeliculaForm
    success_url = reverse_lazy("manager:peliculas_list")
    section = "Peliculas"
    enctype = "multipart/form-data"
    object_label = "Pelicula"


class PeliculaDeleteView(GerenteDeleteView):
    model = Pelicula
    success_url = reverse_lazy("manager:peliculas_list")
    section = "Peliculas"
    object_label = "Pelicula"


class FuncionesListView(GerenteListView):
    model = Funcion
    template_name = "manager/funciones_list.html"
    section = "Funciones"
    create_url_name = "manager:funciones_create"
    columns = ("Pelicula", "Sala", "Fecha", "Publicada", "Precio")
    search_placeholder = "Buscar por pelicula o sala"

    def get_queryset(self):
        queryset = Funcion.objects.select_related("pelicula", "sala")
        search_query = self.get_search_query()
        if search_query:
            queryset = self.apply_search(queryset, search_query)
        return queryset

    def apply_search(self, queryset, search_query):
        return queryset.filter(
            Q(pelicula__titulo__icontains=search_query)
            | Q(sala__nombre__icontains=search_query)
        )


class FuncionCreateView(GerenteCreateView):
    model = Funcion
    form_class = FuncionForm
    success_url = reverse_lazy("manager:funciones_list")
    section = "Funciones"
    enctype = ""
    object_label = "Funcion"

    def form_valid(self, form):
        form.instance.publicada = False
        return super().form_valid(form)


class FuncionUpdateView(GerenteUpdateView):
    model = Funcion
    form_class = FuncionForm
    success_url = reverse_lazy("manager:funciones_list")
    section = "Funciones"
    enctype = ""
    object_label = "Funcion"


class FuncionDeleteView(GerenteDeleteView):
    model = Funcion
    success_url = reverse_lazy("manager:funciones_list")
    section = "Funciones"
    object_label = "Funcion"


class FuncionTogglePublicadaView(GerenteRequiredMixin, DetailView):
    model = Funcion

    def post(self, request, *args, **kwargs):
        funcion = self.get_object()
        funcion.publicada = not funcion.publicada
        funcion.save(update_fields=["publicada"])
        estado = "publicada" if funcion.publicada else "oculta"
        messages.success(request, f"Funcion {estado} correctamente.")
        return redirect("manager:funciones_list")
