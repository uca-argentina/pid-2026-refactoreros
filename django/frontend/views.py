from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.shortcuts import redirect, render

from cinema.models import ConfiguracionCine
from users.forms import ClienteSignupForm
from users.models import Cliente
from screenings.models import Funcion
from movies.models import Pelicula


def _auth_context(request, active_tab, login_form=None, signup_form=None):
    return {
        "active_tab": active_tab,
        "cinema": ConfiguracionCine.actual(),
        "login_form": login_form or AuthenticationForm(request),
        "signup_form": signup_form or ClienteSignupForm(),
    }


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = AuthenticationForm(request, data=request.POST or None)
    form.fields["username"].widget.attrs.update(
        {
            "autocomplete": "username",
            "placeholder": "Email",
        }
    )
    form.fields["password"].widget.attrs.update(
        {
            "autocomplete": "current-password",
            "placeholder": "Contraseña",
        }
    )

    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect(request.GET.get("next") or "home")

    return render(
        request,
        "frontend/auth.html",
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
        "frontend/auth.html",
        _auth_context(request, "signup", signup_form=form),
    )


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def home_view(request):
    return render(
        request,
        "frontend/home.html",
        {
            "cinema": ConfiguracionCine.actual(),
        },
    )

#@login_requiered
def listing_view(request):
    return render(
        request,
        "frontend/listing.html",
        {
            "cinema": ConfiguracionCine.actual(),
            "funciones": Funcion.funciones_publicadas()

        }
    )