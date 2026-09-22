from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import F, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from domain.cinema.models import ConfiguracionCine
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
        context["cinema"] = ConfiguracionCine.actual()
        return context


class GerenteRequiredMixin(ManagerAccessMixin):
    def has_manager_access(self, role):
        return role == "gerente"


class GestionHomeView(ManagerAccessMixin, TemplateView):
    template_name = "manager_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.manager_role != "gerente":
            return context

        now = timezone.now()
        today = timezone.localdate()
        funciones_base = Funcion.objects.select_related("pelicula", "sala").annotate(
            entradas_vendidas=Coalesce(
                Sum("compras_entradas__cantidad"),
                Value(0),
                output_field=IntegerField(),
            )
        )
        proximas_funciones = funciones_base.filter(fecha_horario__gte=now)
        context["dashboard_stats"] = [
            {
                "label": "Funciones hoy",
                "value": Funcion.objects.filter(fecha_horario__date=today).count(),
                "icon": "calendar-days",
                "tone": "teal",
            },
            {
                "label": "Películas activas",
                "value": Pelicula.objects.count(),
                "icon": "clapperboard",
                "tone": "amber",
            },
            {
                "label": "Salas disponibles",
                "value": Sala.objects.count(),
                "icon": "armchair",
                "tone": "violet",
            },
            {
                "label": "Usuarios activos",
                "value": User.objects.filter(is_active=True).count(),
                "icon": "users",
                "tone": "rose",
            },
        ]
        context["next_screenings"] = proximas_funciones.order_by("fecha_horario")[:5]
        context["hidden_upcoming_count"] = proximas_funciones.filter(
            publicada=False
        ).count()
        context["published_upcoming_count"] = proximas_funciones.filter(
            publicada=True
        ).count()
        context["total_room_capacity"] = (
            Sala.objects.aggregate(total=Coalesce(Sum("capacidad"), Value(0)))["total"]
        )
        return context


class GerenteListView(GerenteRequiredMixin, ListView):
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
        context["has_list_filters"] = (
            bool(self.get_search_query())
            or self.get_ordering_value()
            != (self.ordering_options[0][0] if self.ordering_options else "")
        )
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["list_querystring"] = query_params.urlencode()
        return context


class GerenteCreateView(GerenteRequiredMixin, CreateView):
    template_name = "manager_form.html"
    form_title = ""

    def form_valid(self, form):
        messages.success(self.request, f"{self.object_label} creado/a correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["submit_label"] = "Crear"
        context["form_title"] = self.form_title or f"Nuevo {self.object_label.lower()}"
        context["enctype"] = self.enctype
        return context


class GerenteUpdateView(GerenteRequiredMixin, UpdateView):
    template_name = "manager_form.html"
    form_title = ""

    def form_valid(self, form):
        messages.success(self.request, f"{self.object_label} actualizado/a correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["submit_label"] = "Guardar"
        context["form_title"] = self.form_title or f"Editar {self.object_label.lower()}"
        context["enctype"] = self.enctype
        return context


class GerenteDeleteView(GerenteRequiredMixin, DeleteView):
    template_name = "manager_confirm_delete.html"

    def form_valid(self, form):
        messages.success(self.request, f"Eliminado/a correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["object_label"] = self.object_label
        return context


class UsuariosListView(GerenteListView):
    model = User
    template_name = "manager_usuarios_list.html"
    section = "Usuarios"
    create_url_name = ""
    columns = ("Email", "Nombre", "Rol", "Estado")
    search_placeholder = "Buscar por email o nombre"
    ordering_options = (
        ("email_asc", "Email A-Z", ("email", "username")),
        ("email_desc", "Email Z-A", ("-email", "-username")),
        ("nombre_asc", "Nombre A-Z", ("first_name", "last_name", "email")),
        ("recientes", "Más recientes", ("-date_joined",)),
    )

    def apply_search(self, queryset, search_query):
        return queryset.filter(
            Q(email__icontains=search_query)
            | Q(username__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuarios = []
        for usuario in context["object_list"]:
            rol = manager_role(usuario) or "cliente"
            is_other_manager = rol == "gerente" and usuario.pk != self.request.user.pk
            usuarios.append(
                {
                    "usuario": usuario,
                    "rol": rol,
                    "can_edit": not is_other_manager,
                    "can_toggle": usuario.pk != self.request.user.pk and rol != "gerente",
                }
            )
        context["usuarios"] = usuarios
        return context

class UsuarioUpdateView(GerenteRequiredMixin, UpdateView):
    model = User
    form_class = UsuarioGestionForm
    template_name = "manager_form.html"
    success_url = reverse_lazy("manager:usuarios_list")
    section = "Usuarios"
    enctype = ""
    object_label = "Usuario"

    def get_object(self, queryset=None):
        usuario = super().get_object(queryset)
        if manager_role(usuario) == "gerente" and usuario.pk != self.request.user.pk:
            raise PermissionDenied
        return usuario

    def form_valid(self, form):
        form.instance.username = form.cleaned_data["email"]
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["submit_label"] = "Guardar"
        context["form_title"] = "Editar usuario"
        context["enctype"] = self.enctype
        context["show_user_status_action"] = self.object.pk != self.request.user.pk
        context["can_toggle_user_status"] = manager_role(self.object) != "gerente"
        return context


class UsuarioToggleActiveView(GerenteRequiredMixin, DetailView):
    model = User

    def post(self, request, *args, **kwargs):
        usuario = self.get_object()
        if usuario.pk == request.user.pk:
            messages.error(request, "No podés bloquear tu propio usuario.")
            return redirect("manager:usuarios_list")
        if manager_role(usuario) == "gerente":
            messages.error(request, "No podés cambiar el estado de otro gerente.")
            return redirect("manager:usuarios_list")
        usuario.is_active = not usuario.is_active
        usuario.save(update_fields=["is_active"])
        estado = "activado" if usuario.is_active else "bloqueado"
        messages.success(request, f"Usuario {estado} correctamente.")
        return redirect("manager:usuarios_list")


class SalasListView(GerenteListView):
    model = Sala
    template_name = "manager_salas_list.html"
    section = "Salas"
    create_url_name = "manager:salas_create"
    columns = ("Nombre", "Capacidad")
    search_placeholder = "Buscar por nombre"
    ordering_options = (
        ("nombre_asc", "Nombre A-Z", ("nombre",)),
        ("nombre_desc", "Nombre Z-A", ("-nombre",)),
        ("capacidad_desc", "Mayor capacidad", ("-capacidad", "nombre")),
        ("capacidad_asc", "Menor capacidad", ("capacidad", "nombre")),
    )

    def apply_search(self, queryset, search_query):
        return queryset.filter(nombre__icontains=search_query)


class SalaCreateView(GerenteCreateView):
    model = Sala
    form_class = SalaForm
    success_url = reverse_lazy("manager:salas_list")
    section = "Salas"
    enctype = ""
    object_label = "Sala"
    form_title = "Nueva sala"


class SalaUpdateView(GerenteUpdateView):
    model = Sala
    form_class = SalaForm
    success_url = reverse_lazy("manager:salas_list")
    section = "Salas"
    enctype = ""
    object_label = "Sala"
    form_title = "Editar sala"


class SalaDeleteView(GerenteDeleteView):
    model = Sala
    success_url = reverse_lazy("manager:salas_list")
    section = "Salas"
    object_label = "Sala"


class PeliculasListView(GerenteListView):
    model = Pelicula
    template_name = "manager_peliculas_list.html"
    section = "Peliculas"
    create_url_name = "manager:peliculas_create"
    columns = ("Titulo", "Genero", "Clasificacion", "Duracion")
    search_placeholder = "Buscar por título, género o sinopsis"
    ordering_options = (
        ("titulo_asc", "Título A-Z", ("titulo",)),
        ("titulo_desc", "Título Z-A", ("-titulo",)),
        ("genero_asc", "Género A-Z", ("genero", "titulo")),
        ("duracion_desc", "Más largas", ("-duracion_minutos", "titulo")),
        ("duracion_asc", "Más cortas", ("duracion_minutos", "titulo")),
    )

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
    form_title = "Nueva pelicula"


class PeliculaUpdateView(GerenteUpdateView):
    model = Pelicula
    form_class = PeliculaForm
    success_url = reverse_lazy("manager:peliculas_list")
    section = "Peliculas"
    enctype = "multipart/form-data"
    object_label = "Pelicula"
    form_title = "Editar pelicula"


class PeliculaDeleteView(GerenteDeleteView):
    model = Pelicula
    success_url = reverse_lazy("manager:peliculas_list")
    section = "Peliculas"
    object_label = "Pelicula"


class FuncionesListView(GerenteListView):
    model = Funcion
    template_name = "manager_funciones_list.html"
    section = "Funciones"
    create_url_name = "manager:funciones_create"
    columns = (
        "Pelicula",
        "Sala",
        "Fecha",
        "Publicada",
        "Precio",
        "Vendidas",
        "Disponibles",
    )
    search_placeholder = "Buscar por película o sala"
    ordering_options = (
        ("fecha_asc", "Fecha más próxima", ("fecha_horario",)),
        ("fecha_desc", "Fecha más lejana", ("-fecha_horario",)),
        ("pelicula_asc", "Película A-Z", ("pelicula__titulo", "fecha_horario")),
        ("sala_asc", "Sala A-Z", ("sala__nombre", "fecha_horario")),
        ("precio_desc", "Mayor precio", ("-precio_entrada", "fecha_horario")),
        ("precio_asc", "Menor precio", ("precio_entrada", "fecha_horario")),
    )

    def get_queryset(self):
        queryset = (
            Funcion.objects.select_related("pelicula", "sala")
            .annotate(
                entradas_vendidas=Coalesce(
                    Sum("compras_entradas__cantidad"),
                    Value(0),
                    output_field=IntegerField(),
                )
            )
            .annotate(
                entradas_disponibles=Greatest(
                    F("sala__capacidad") - F("entradas_vendidas"),
                    Value(0),
                    output_field=IntegerField(),
                )
            )
        )
        search_query = self.get_search_query()
        if search_query:
            queryset = self.apply_search(queryset, search_query)
        return self.apply_ordering(queryset)

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
    form_title = "Nueva función"

    def get_initial(self):
        initial = super().get_initial()
        plantilla_id = self.request.GET.get("plantilla")
        if not plantilla_id:
            return initial

        plantilla = get_object_or_404(Funcion, pk=plantilla_id)
        initial.update(
            {
                "pelicula": plantilla.pelicula,
                "sala": plantilla.sala,
                "fecha_horario": plantilla.fecha_horario,
                "precio_entrada": plantilla.precio_entrada,
            }
        )
        return initial

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
    form_title = "Editar función"


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
