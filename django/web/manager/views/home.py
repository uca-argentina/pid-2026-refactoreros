"""Home."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Case, Count, F, IntegerField, OuterRef, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, UpdateView
from domain.cinema.models import CinemaSettings
from domain.movies.models import Movie
from domain.rooms.models import Room
from domain.screenings.models import Screening
from domain.seats.models import Seat

from web.manager.access import ManagerRequiredMixin, StaffAccessMixin
from web.manager.dashboard import build_dashboard
from web.manager.filters import DashboardFilterForm
from web.manager.forms import CinemaSettingsForm

User = get_user_model()


class ManagementHomeView(StaffAccessMixin, TemplateView):
    template_name = "manager_home.html"

    def get(self, request, *args, **kwargs):
        if self.manager_role == "operator":
            return redirect("manager:validar_entradas")
        return super().get(request, *args, **kwargs)

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
        base_screenings = (
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
                occupancy_percentage=Case(
                    When(
                        room_capacity__gt=0,
                        then=100 * F("tickets_sold") / F("room_capacity"),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                )
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
        filters = DashboardFilterForm(self.request.GET)
        valid_filters = filters.is_valid()
        date_from = filters.cleaned_data.get("date_from") if valid_filters else None
        date_to = filters.cleaned_data.get("date_to") if valid_filters else None
        date_filter_error = next(
            (str(error) for errors in filters.errors.values() for error in errors), None
        )

        context["dashboard"] = build_dashboard(
            self.request.GET.get("period"),
            date_from=None if date_filter_error else date_from,
            date_to=None if date_filter_error else date_to,
            movie_id=self.request.GET.get("movie"),
            room_id=self.request.GET.get("room"),
            revenue_date=self.request.GET.get("revenue_date"),
            view=self.request.GET.get("view"),
        )
        context["date_filter_error"] = date_filter_error
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
