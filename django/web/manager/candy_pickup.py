from datetime import timedelta
import re

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import FormView

from domain.candy.models import CandyPickup
from domain.candy.services import deliver_candy_order, inspect_candy_order, undo_candy_pickup
from .validation import TicketValidationForm, customer_display_names
from .access import StaffAccessMixin


class CandyPickupForm(TicketValidationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].label = "Código de retiro"


@method_decorator(never_cache, name="dispatch")
class CandyPickupView(StaffAccessMixin, FormView):
    template_name = "manager_candy_pickup.html"
    form_class = CandyPickupForm
    history_page_size = 15

    def get_initial(self):
        initial = super().get_initial()
        code = self.request.GET.get("code", "")
        if re.fullmatch(r"BCC:[A-Za-z2-9]{6}", code, re.I):
            initial["code"] = code[4:].upper()
        return initial

    def has_manager_access(self, role):
        return role in {"operator", "manager"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = "Entregar candy"
        history = CandyPickup.objects.filter(
            operator=self.request.user,
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).select_related("order__purchase__screening__movie").order_by("-created_at")
        history_page = Paginator(history, self.history_page_size).get_page(
            self.request.GET.get("page")
        )
        history = list(history_page)
        names = customer_display_names({pickup.order.user_id for pickup in history})
        for pickup in history:
            pickup.customer_display_name = names.get(pickup.order.user_id, "Cliente")
        context["pickup_history"] = history
        context["pickup_history_page"] = history_page
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "undo":
            try:
                undo_candy_pickup(request.POST.get("pickup_id"), request.user)
            except ValidationError as error:
                messages.error(request, error.message)
            else:
                messages.success(request, "Se deshizo la entrega del candy.")
            return redirect(reverse("manager:entregar_candy"))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        code = form.cleaned_data["code"]
        action = self.request.POST.get("action")
        try:
            if action == "preview":
                order = inspect_candy_order(code, self.request.user)
                order.customer_display_name = customer_display_names([order.user_id]).get(
                    order.user_id, "Cliente"
                )
                return self.render_to_response(self.get_context_data(form=form, order=order))
            if action != "deliver":
                raise ValidationError("La acción no es válida.")
            order, _pickup = deliver_candy_order(code, self.request.user)
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Candy entregado: {order.summary}. ¡Que lo disfrute!",
        )
        return redirect(reverse("manager:entregar_candy"))
