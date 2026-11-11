"""Users."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import DetailView, UpdateView
from domain.users.models import Operator

from web.manager.access import ManagerRequiredMixin, manager_role
from web.manager.forms import UserManagementForm
from web.manager.views.base import ManagerListView

User = get_user_model()


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
                    "role_label": {
                        "manager": "Gerente",
                        "operator": "Operador",
                        "usher": "Acomodador",
                        "customer": "Cliente",
                    }[rol],
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
        context["can_toggle_operator"] = manager_role(self.object) != "manager"
        context["is_operator"] = Operator.objects.filter(user=self.object).exists()
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


class UserToggleOperatorView(ManagerRequiredMixin, DetailView):
    model = User

    def post(self, request, *args, **kwargs):
        user = self.get_object()
        if user.pk == request.user.pk or manager_role(user) == "manager":
            raise PermissionDenied
        operator, created = Operator.objects.get_or_create(user=user)
        if created:
            messages.success(request, "Usuario designado como operador de entradas.")
        else:
            operator.delete()
            messages.success(request, "Se quitó el rol de operador de entradas.")
        return redirect("manager:usuarios_update", pk=user.pk)
