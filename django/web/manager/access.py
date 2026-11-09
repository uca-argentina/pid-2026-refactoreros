"""Access."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from domain.cinema.models import CinemaSettings
from domain.users.roles import staff_role


def manager_role(user):
    return staff_role(user)


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
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["manager_role"] = self.manager_role
        context["cinema"] = CinemaSettings.current()
        return context


class ManagerRequiredMixin(StaffAccessMixin):
    def has_manager_access(self, role):
        return role == "manager"
