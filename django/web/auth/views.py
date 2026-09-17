from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from domain.cinema.models import ConfiguracionCine
from domain.users.forms import ClienteSignupForm, LoginForm
from domain.users.models import Cliente
from web.manager.views import manager_role


def _auth_context(request, active_tab, login_form=None, signup_form=None):
    return {
        "active_tab": active_tab,
        "cinema": ConfiguracionCine.actual(),
        "login_form": login_form or LoginForm(request),
        "signup_form": signup_form or ClienteSignupForm(),
    }


def login_view(request):
    if request.user.is_authenticated:
        if manager_role(request.user):
            return redirect("manager:home")
        return redirect("home")

    initial = {}
    if request.method == "GET":
        email = request.GET.get("email", "").strip()
        if email:
            initial["username"] = email

    form = LoginForm(request, data=request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        next_url = request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        if manager_role(request.user):
            return redirect("manager:home")
        return redirect("home")

    return render(
        request,
        "auth/auth.html",
        _auth_context(request, "login", login_form=form),
    )


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = ClienteSignupForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            usuario = form.save()
            Cliente.objects.create(usuario=usuario)
        login(request, usuario)
        return redirect("home")

    return render(
        request,
        "auth/auth.html",
        _auth_context(request, "signup", signup_form=form),
    )


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def home_view(request):
    return render(
        request,
        "auth/home.html",
        {
            "cinema": ConfiguracionCine.actual(),
            "manager_role": manager_role(request.user),
        },
    )
