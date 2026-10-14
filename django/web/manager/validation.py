import re
from datetime import timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import FormView

from domain.tickets.models import AdmissionValidation
from domain.tickets.services import inspect_ticket, undo_ticket_validation, validate_ticket
from .views import StaffAccessMixin


def compact_customer_name(customer):
    first_name = customer.get("first_name", "").strip()
    last_name = customer.get("last_name", "").strip()
    if first_name:
        return f"{first_name} {last_name[:1]}." if last_name else first_name
    return customer.get("username", "Cliente")


def confirmation_seats(seat_labels):
    grouped = {}
    fallback = []
    for label in seat_labels:
        match = re.fullmatch(r"(\d+)([A-Z]+)", label)
        if not match:
            fallback.append(label)
            continue
        row, column = match.groups()
        grouped.setdefault(row, []).append(column)

    groups = []
    for row in sorted(grouped, key=int):
        columns = sorted(grouped[row])
        columns_text = columns[0] if len(columns) == 1 else f"{', '.join(columns[:-1])} y {columns[-1]}"
        seat_word = "asiento" if len(columns) == 1 else "asientos"
        groups.append(f"fila {row}, {seat_word} {columns_text}")
    return "; ".join(groups + fallback)


class TicketValidationForm(forms.Form):
    code = forms.CharField(
        label="Código de compra", max_length=36,
        widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "none", "spellcheck": "false"}),
    )


@method_decorator(never_cache, name="dispatch")
class TicketValidationView(StaffAccessMixin, FormView):
    template_name = "manager_validate_tickets.html"
    form_class = TicketValidationForm
    history_page_size = 15

    def has_manager_access(self, role):
        return role in {"operator", "manager"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = "Validar entradas"
        history = AdmissionValidation.objects.filter(
            operator=self.request.user,
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).select_related("purchase__screening__movie").prefetch_related("tickets").order_by("-created_at")
        history_page = Paginator(history, self.history_page_size).get_page(
            self.request.GET.get("page")
        )
        history = list(history_page)
        customer_ids = {validation.purchase.user_id for validation in history}
        customers = {
            customer["pk"]: customer
            for customer in get_user_model().objects.filter(pk__in=customer_ids).values(
                "pk", "first_name", "last_name", "username"
            )
        }
        for validation in history:
            customer = customers.get(validation.purchase.user_id, {})
            validation.customer_display_name = compact_customer_name(customer)
        context["validation_history"] = history
        context["validation_history_page"] = history_page
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "undo":
            try:
                _, tickets = undo_ticket_validation(request.POST.get("validation_id"), request.user)
            except ValidationError as error:
                messages.error(request, error.message)
            else:
                messages.success(request, f"Se deshizo la validación de {len(tickets)} butaca{'s' if len(tickets) != 1 else ''}.")
            return redirect(reverse("manager:validar_entradas"))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        code = form.cleaned_data["code"]
        action = self.request.POST.get("action")
        try:
            if action == "preview":
                purchase = inspect_ticket(code, self.request.user)
                customer = get_user_model().objects.filter(pk=purchase.user_id).values(
                    "first_name", "last_name", "username"
                ).first() or {}
                purchase.customer_display_name = compact_customer_name(customer)
                return self.render_to_response(self.get_context_data(form=form, purchase=purchase))
            if action != "validate":
                raise ValidationError("La acción no es válida.")
            purchase, tickets, _validation = validate_ticket(
                code, self.request.user, ticket_numbers=self.request.POST.getlist("ticket_numbers")
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        seat_labels = [ticket.seat_label or f"Entrada {ticket.number}" for ticket in tickets]
        seats = confirmation_seats(seat_labels)
        seat_phrase = f"la butaca: {seats}" if len(seat_labels) == 1 else f"las butacas: {seats}"
        farewell = "¡Que lo disfrutes!" if len(seat_labels) == 1 else "¡Que lo disfruten!"
        remaining = purchase.remaining_quantity
        if remaining:
            remaining_message = (
                "Te queda 1 butaca para entrar a la sala."
                if remaining == 1 else f"Te quedan {remaining} butacas para entrar a la sala."
            )
            message = (
                f"{purchase.screening.room.name}. Tenés {seat_phrase}. {remaining_message} {farewell}"
            )
        else:
            message = f"{purchase.screening.room.name}. Tenés {seat_phrase}. {farewell}"
        messages.success(self.request, message)
        return redirect(reverse('manager:validar_entradas'))
