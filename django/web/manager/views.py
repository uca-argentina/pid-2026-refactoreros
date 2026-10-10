from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Case, Count, F, IntegerField, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce, Greatest
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction
from django.urls import reverse_lazy
from django.utils import timezone
import json

from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from domain.cinema.models import CinemaSettings
from domain.movies.models import Movie
from domain.rooms.models import Room
from domain.screenings.models import Screening
from domain.seats.models import Seat
from domain.seat_types.models import SeatType
from domain.tickets.models import TicketPurchase

from .dashboard import build_dashboard
from .forms import (
    CinemaSettingsForm,
    ScreeningForm,
    MovieForm,
    RoomForm,
    SeatTypeForm,
    UserManagementForm,
)

User = get_user_model()


def manager_role(user):
    if not user.is_authenticated:
        return ""
    if hasattr(user, "manager_profile"):
        return "manager"
    if hasattr(user, "usher_profile"):
        return "usher"
    return ""


class StaffAccessMixin(LoginRequiredMixin):
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
        context["cinema"] = CinemaSettings.current()
        return context


class ManagerRequiredMixin(StaffAccessMixin):
    def has_manager_access(self, role):
        return role == "manager"


class ManagementHomeView(StaffAccessMixin, TemplateView):
    template_name = "manager_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.manager_role != "manager":
            return context

        Screening.finalize_expired()
        now = timezone.now()
        today = timezone.localdate()
        current_room_capacity = (
            Room.objects.filter(pk=OuterRef("room_id"))
            .annotate(total=Count("seats"))
            .values("total")[:1]
        )
        base_screenings = Screening.objects.select_related("movie", "room").annotate(
            tickets_sold=Coalesce(
                Sum("ticket_purchases__quantity"),
                Value(0),
                output_field=IntegerField(),
            ),
            current_room_capacity=Coalesce(
                Subquery(current_room_capacity),
                Value(0),
                output_field=IntegerField(),
            ),
            room_capacity=Case(
                When(capacity_snapshot=0, then=F("current_room_capacity")),
                default=F("capacity_snapshot"),
                output_field=IntegerField(),
            ),
        ).annotate(
            occupancy_percentage=Case(
                When(
                    room_capacity__gt=0,
                    then=100 * F("tickets_sold") / F("room_capacity"),
                ),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        upcoming_screenings = base_screenings.filter(starts_at__gte=now)
        context["dashboard_stats"] = [
            {
                "label": "Funciones hoy",
                "value": Screening.objects.filter(starts_at__date=today).count(),
                "icon": "calendar-days",
                "tone": "teal",
            },
            {
                "label": "Películas activas",
                "value": Movie.objects.count(),
                "icon": "clapperboard",
                "tone": "amber",
            },
            {
                "label": "Salas disponibles",
                "value": Room.objects.count(),
                "icon": "building-2",
                "tone": "violet",
            },
            {
                "label": "Usuarios activos",
                "value": User.objects.filter(is_active=True).count(),
                "icon": "users",
                "tone": "rose",
            },
        ]
        context["next_screenings"] = upcoming_screenings.order_by("starts_at")[:5]
        context["hidden_upcoming_count"] = upcoming_screenings.filter(
            status__in=(Screening.Status.DRAFT, Screening.Status.SCHEDULED)
        ).count()
        context["published_upcoming_count"] = upcoming_screenings.filter(
            status=Screening.Status.PUBLISHED
        ).count()
        context["total_room_capacity"] = Seat.objects.count()
        return context


class DashboardView(ManagerRequiredMixin, TemplateView):
    template_name = "manager_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        Screening.finalize_expired()
        context["section"] = "Dashboard"
        context["dashboard"] = build_dashboard(self.request.GET.get("period"))
        return context


class CinemaSettingsUpdateView(ManagerRequiredMixin, UpdateView):
    model = CinemaSettings
    form_class = CinemaSettingsForm
    template_name = "manager_form.html"
    success_url = reverse_lazy("manager:configuracion")

    def get_object(self, queryset=None):
        cinema_settings = CinemaSettings.objects.order_by("id").first()
        if cinema_settings:
            return cinema_settings
        return CinemaSettings.objects.create()

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "La configuración se actualizó correctamente.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "section": "Configuración",
                "form_title": "Configuración",
                "submit_label": "Guardar configuración",
            }
        )
        return context


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
        context["has_list_filters"] = (
            bool(self.get_search_query())
            or self.get_ordering_value()
            != (self.ordering_options[0][0] if self.ordering_options else "")
        )
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["list_querystring"] = query_params.urlencode()
        return context


class ManagerCreateView(ManagerRequiredMixin, CreateView):
    template_name = "manager_form.html"
    form_title = ""

    def form_valid(self, form):
        messages.success(self.request, f"{self.object_label} se creó correctamente.")
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

    def form_valid(self, form):
        messages.success(self.request, "Se eliminó correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["object_label"] = self.object_label
        return context


class UsersListView(ManagerListView):
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
        users = []
        for user in context["object_list"]:
            rol = manager_role(user) or "customer"
            is_other_manager = rol == "manager" and user.pk != self.request.user.pk
            users.append(
                {
                    "user": user,
                    "role": rol,
                    "can_edit": not is_other_manager,
                    "can_toggle": user.pk != self.request.user.pk and rol != "manager",
                }
            )
        context["users"] = users
        return context

class UserUpdateView(ManagerRequiredMixin, UpdateView):
    model = User
    form_class = UserManagementForm
    template_name = "manager_form.html"
    success_url = reverse_lazy("manager:usuarios_list")
    section = "Usuarios"
    enctype = ""
    object_label = "El usuario"

    def get_object(self, queryset=None):
        user = super().get_object(queryset)
        if manager_role(user) == "manager" and user.pk != self.request.user.pk:
            raise PermissionDenied
        return user

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
        context["can_toggle_user_status"] = manager_role(self.object) != "manager"
        return context


class UserToggleActiveView(ManagerRequiredMixin, DetailView):
    model = User

    def post(self, request, *args, **kwargs):
        user = self.get_object()
        if user.pk == request.user.pk:
            messages.error(request, "No podés bloquear tu propio usuario.")
            return redirect("manager:usuarios_list")
        if manager_role(user) == "manager":
            messages.error(request, "No podés cambiar el estado de otro gerente.")
            return redirect("manager:usuarios_list")
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        status = "activado" if user.is_active else "bloqueado"
        messages.success(request, f"Usuario {status} correctamente.")
        return redirect("manager:usuarios_list")


class RoomsListView(ManagerListView):
    model = Room
    template_name = "manager_salas_list.html"
    section = "Salas"
    create_url_name = "manager:salas_create"
    columns = ("Nombre", "Capacidad")
    search_placeholder = "Buscar por nombre"
    ordering_options = (
        ("nombre_asc", "Nombre A-Z", ("name",)),
        ("nombre_desc", "Nombre Z-A", ("-name",)),
        ("capacity_desc", "Mayor capacidad", ("-_capacity", "name")),
        ("capacity_asc", "Menor capacidad", ("_capacity", "name")),
    )

    def get_queryset(self):
        queryset = Room.objects.annotate(_capacity=Count("seats"))
        search_query = self.get_search_query()
        if search_query:
            queryset = self.apply_search(queryset, search_query)
        return self.apply_ordering(queryset)

    def apply_search(self, queryset, search_query):
        return queryset.filter(name__icontains=search_query)


class RoomCreateView(ManagerCreateView):
    model = Room
    form_class = RoomForm
    success_url = reverse_lazy("manager:salas_list")
    section = "Salas"
    enctype = ""
    object_label = "La sala"
    form_title = "Nueva sala"

    template_name = "manager_nueva_sala_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["seat_types"] = list(SeatType.objects.all())
        return context

    def form_valid(self,form):
        room_layout = form.cleaned_data.get("room_layout")
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.layout_configuration = form.cleaned_data.get("layout_configuration", {})
            self.object.save()
            if room_layout:
                Seat.objects.bulk_create(self.build_seats(self.object, room_layout["seats"]))
        messages.success(self.request, f"{self.object_label} se creó correctamente.")
        return redirect(self.get_success_url())
    

    def build_seats(self,room, seats_layout):
        seats = []
        for seat_data in seats_layout:
            seats.append(Seat(room=room, row=seat_data["row"], column=seat_data["column"], seat_type_id=seat_data["type"]))
        return seats


class RoomUpdateView(ManagerUpdateView):
    model = Room
    form_class = RoomForm
    success_url = reverse_lazy("manager:salas_list")
    section = "Salas"
    enctype = ""
    object_label = "La sala"
    form_title = "Editar sala"

    template_name = "manager_nueva_sala_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["seat_types"] = list(SeatType.objects.all())
        return context

    def form_valid(self, form):
        room_layout = form.cleaned_data.get("room_layout")
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.layout_configuration = form.cleaned_data.get("layout_configuration", {})
            self.object.save()
            if room_layout:
                self.sync_seats(self.object, room_layout["seats"])
        messages.success(self.request, f"{self.object_label} se actualizó correctamente.")
        return redirect(self.get_success_url())

    def sync_seats(self, room, seats_layout):
        existing = {(s.row, s.column): s for s in Seat.objects.filter(room=room)}
        new_keys = {(d["row"], d["column"]) for d in seats_layout}

        to_delete = [s.pk for key, s in existing.items() if key not in new_keys]
        if to_delete:
            Seat.objects.filter(pk__in=to_delete).delete()

        layout_by_key = {(d["row"], d["column"]): d["type"] for d in seats_layout}
        to_update = []
        for key, seat in existing.items():
            if key in layout_by_key and seat.seat_type_id != layout_by_key[key]:
                seat.seat_type_id = layout_by_key[key]
                to_update.append(seat)
        if to_update:
            Seat.objects.bulk_update(to_update, ["seat_type"])

        to_create = [
            Seat(room=room, row=row, column=col, seat_type_id=layout_by_key[(row, col)])
            for (row, col) in new_keys
            if (row, col) not in existing
        ]
        Seat.objects.bulk_create(to_create)


class RoomDeleteView(ManagerDeleteView):
    model = Room
    success_url = reverse_lazy("manager:salas_list")
    section = "Salas"
    object_label = "La sala"


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

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                "No se puede eliminar un tipo de butaca que esta usado en una sala.",
            )
            return redirect(self.success_url)


class MoviesListView(ManagerListView):
    model = Movie
    template_name = "manager_peliculas_list.html"
    section = "Peliculas"
    create_url_name = "manager:peliculas_create"
    columns = ("Titulo", "Genero", "Clasificacion", "Duracion")
    search_placeholder = "Buscar por título, género o sinopsis"
    ordering_options = (
        ("titulo_asc", "Título A-Z", ("title",)),
        ("titulo_desc", "Título Z-A", ("-title",)),
        ("genero_asc", "Género A-Z", ("genre", "title")),
        ("duracion_desc", "Más largas", ("-duration_minutes", "title")),
        ("duracion_asc", "Más cortas", ("duration_minutes", "title")),
    )

    def apply_search(self, queryset, search_query):
        return queryset.filter(
            Q(title__icontains=search_query)
            | Q(synopsis__icontains=search_query)
            | Q(genre__icontains=search_query)
        )


class MovieCreateView(ManagerCreateView):
    model = Movie
    form_class = MovieForm
    success_url = reverse_lazy("manager:peliculas_list")
    section = "Peliculas"
    enctype = "multipart/form-data"
    object_label = "La película"
    form_title = "Nueva pelicula"


class MovieUpdateView(ManagerUpdateView):
    model = Movie
    form_class = MovieForm
    success_url = reverse_lazy("manager:peliculas_list")
    section = "Peliculas"
    enctype = "multipart/form-data"
    object_label = "La película"
    form_title = "Editar pelicula"


class MovieDeleteView(ManagerDeleteView):
    model = Movie
    success_url = reverse_lazy("manager:peliculas_list")
    section = "Peliculas"
    object_label = "La película"


class ScreeningsListView(ManagerListView):
    model = Screening
    template_name = "manager_funciones_list.html"
    section = "Funciones"
    create_url_name = "manager:funciones_create"
    columns = (
        "Pelicula",
        "Sala",
        "Fecha",
        "Estado",
        "Desde",
        "Vendidas",
        "Disponibles",
    )
    search_placeholder = "Buscar por película o sala"
    ordering_options = (
        ("date_asc", "Fecha más próxima", ("starts_at",)),
        ("date_desc", "Fecha más lejana", ("-starts_at",)),
        ("pelicula_asc", "Película A-Z", ("movie__title", "starts_at")),
        ("sala_asc", "Sala A-Z", ("room__name", "starts_at")),
        ("precio_desc", "Mayor precio inicial", ("-ticket_price", "starts_at")),
        ("precio_asc", "Menor precio inicial", ("ticket_price", "starts_at")),
    )
    is_history = False

    def get_annotated_queryset(self):
        Screening.finalize_expired()
        current_room_capacity = (
            Room.objects.filter(pk=OuterRef("room_id"))
            .annotate(total=Count("seats"))
            .values("total")[:1]
        )
        return (
            Screening.objects.select_related("movie", "room")
            .annotate(
                tickets_sold=Coalesce(
                    Sum("ticket_purchases__quantity"),
                    Value(0),
                    output_field=IntegerField(),
                ),
                current_room_capacity=Coalesce(
                    Subquery(current_room_capacity),
                    Value(0),
                    output_field=IntegerField(),
                ),
                room_capacity=Case(
                    When(capacity_snapshot=0, then=F("current_room_capacity")),
                    default=F("capacity_snapshot"),
                    output_field=IntegerField(),
                ),
            )
            .annotate(
                tickets_available=Greatest(
                    F("room_capacity") - F("tickets_sold"),
                    Value(0),
                    output_field=IntegerField(),
                )
            )
        )

    def apply_history_filter(self, queryset):
        now = timezone.now()
        if self.is_history:
            return queryset.filter(
                Q(starts_at__lt=now)
                | Q(status__in=(Screening.Status.CANCELED, Screening.Status.FINISHED))
            )
        return queryset.filter(
            starts_at__gte=now,
        ).exclude(status__in=(Screening.Status.CANCELED, Screening.Status.FINISHED))

    def get_queryset(self):
        queryset = self.apply_history_filter(self.get_annotated_queryset())
        search_query = self.get_search_query()
        if search_query:
            queryset = self.apply_search(queryset, search_query)
        return self.apply_ordering(queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_history"] = self.is_history
        hidden_queryset = (
            self.get_annotated_queryset()
            .filter(
                status__in=(Screening.Status.DRAFT, Screening.Status.SCHEDULED),
                starts_at__gte=timezone.now(),
            )
            .order_by("starts_at")
        )
        context["hidden_priority_functions"] = hidden_queryset[:6]
        context["hidden_priority_count"] = hidden_queryset.count()
        return context

    def apply_search(self, queryset, search_query):
        return queryset.filter(
            Q(movie__title__icontains=search_query)
            | Q(room__name__icontains=search_query)
        )


class ScreeningsHistoryListView(ScreeningsListView):
    section = "Historial de funciones"
    create_url_name = ""
    is_history = True
    ordering_options = (
        ("date_desc", "Fecha mas reciente", ("-starts_at",)),
        ("date_asc", "Fecha mas antigua", ("starts_at",)),
        ("pelicula_asc", "Pelicula A-Z", ("movie__title", "-starts_at")),
        ("sala_asc", "Sala A-Z", ("room__name", "-starts_at")),
        ("precio_desc", "Mayor precio inicial", ("-ticket_price", "-starts_at")),
        ("precio_asc", "Menor precio inicial", ("ticket_price", "-starts_at")),
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["hidden_priority_functions"] = []
        context["hidden_priority_count"] = 0
        return context


class ScreeningCreateView(ManagerCreateView):
    model = Screening
    form_class = ScreeningForm
    success_url = reverse_lazy("manager:funciones_list")
    section = "Funciones"
    enctype = ""
    object_label = "La función"
    form_title = "Nueva función"

    def get_initial(self):
        initial = super().get_initial()
        template_screening_id = self.request.GET.get("plantilla")
        if not template_screening_id:
            return initial

        template_screening = get_object_or_404(Screening, pk=template_screening_id)
        initial.update(
            {
                "movie": template_screening.movie,
                "room": template_screening.room,
                "starts_at": template_screening.starts_at,
            }
        )
        return initial

    def form_valid(self, form):
        form.instance.status = Screening.Status.DRAFT
        form.instance.capture_room_configuration()
        return super().form_valid(form)


class ScreeningUpdateView(ManagerUpdateView):
    model = Screening
    form_class = ScreeningForm
    success_url = reverse_lazy("manager:funciones_list")
    section = "Funciones"
    enctype = ""
    object_label = "La función"
    form_title = "Editar función"

    def get_object(self, queryset=None):
        screening = super().get_object(queryset)
        if not screening.is_editable:
            raise PermissionDenied
        return screening

    def form_valid(self, form):
        if self.object.status != Screening.Status.PUBLISHED:
            form.instance.capture_room_configuration()
        return super().form_valid(form)


class ScreeningDeleteView(ManagerDeleteView):
    model = Screening
    success_url = reverse_lazy("manager:funciones_list")
    section = "Funciones"
    object_label = "La función"

    def get_object(self, queryset=None):
        screening = super().get_object(queryset)
        if not screening.is_deletable:
            raise PermissionDenied
        return screening


class ScreeningChangeStatusView(ManagerRequiredMixin, DetailView):
    model = Screening
    messages_by_status = {
        Screening.Status.DRAFT: "La función volvió a borrador.",
        Screening.Status.SCHEDULED: "Función programada correctamente.",
        Screening.Status.PUBLISHED: "Función publicada correctamente.",
        Screening.Status.CANCELED: "Función cancelada correctamente.",
    }

    def post(self, request, *args, **kwargs):
        screening = self.get_object()
        new_status = request.POST.get("status", "")
        if new_status not in self.messages_by_status:
            messages.error(request, "Estado inválido.")
            return redirect("manager:funciones_list")
        try:
            screening.change_status(new_status)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, self.messages_by_status[new_status])
        return redirect("manager:funciones_list")


class ScreeningCancelView(ManagerRequiredMixin, DetailView):
    model = Screening
    template_name = "manager_confirm_cancel.html"

    def get(self, request, *args, **kwargs):
        screening = self.get_object()
        if not screening.can_transition_to(Screening.Status.CANCELED):
            messages.error(request, "Esta función no se puede cancelar.")
            return redirect("manager:funciones_list")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = "Funciones"
        context["tickets_sold"] = TicketPurchase.sold_quantity(self.object)
        return context
