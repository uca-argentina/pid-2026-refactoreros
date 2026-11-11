"""Rooms."""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse_lazy
from domain.rooms.models import Room
from domain.seat_types.models import SeatType
from domain.seats.models import Seat

from web.manager.forms import RoomForm
from web.manager.views.base import (
    ManagerCreateView,
    ManagerDeleteView,
    ManagerListView,
    ManagerUpdateView,
)


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

    def form_valid(self, form):
        room_layout = form.cleaned_data.get("room_layout")
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.layout_configuration = form.cleaned_data.get("layout_configuration", {})
            self.object.save()
            if room_layout:
                Seat.objects.bulk_create(self.build_seats(self.object, room_layout["seats"]))
        messages.success(self.request, f"{self.object_label} se creó correctamente.")
        return redirect(self.get_success_url())

    def build_seats(self, room, seats_layout):
        seats = []
        for seat_data in seats_layout:
            seats.append(
                Seat(
                    room=room,
                    row=seat_data["row"],
                    column=seat_data["column"],
                    seat_type_id=seat_data["type"],
                )
            )
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
