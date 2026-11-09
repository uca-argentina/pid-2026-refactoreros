"""Screenings."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Case, Count, F, IntegerField, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce, Greatest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView
from domain.rooms.models import Room
from domain.screenings.models import Screening
from domain.tickets.models import TicketPurchase

from web.manager.access import ManagerRequiredMixin
from web.manager.forms import ScreeningForm
from web.manager.views.base import (
    ManagerCreateView,
    ManagerDeleteView,
    ManagerListView,
    ManagerUpdateView,
)


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
        if self.is_history:
            return queryset.filter(
                status__in=(Screening.Status.CANCELED, Screening.Status.FINISHED)
            )
        return queryset.exclude(status__in=(Screening.Status.CANCELED, Screening.Status.FINISHED))

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
            Q(movie__title__icontains=search_query) | Q(room__name__icontains=search_query)
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
    success_message = (
        "La función se creó correctamente. ¡No te olvides de publicarla o programarla!"
    )

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
