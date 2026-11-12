from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from domain.cinema.models import CinemaSettings
from domain.movies.models import Movie
from domain.promotions.pricing import PromotionPriceCalculator
from domain.screenings.models import Screening
from domain.tickets.services import check_reprogramming_window
from domain.users.roles import staff_role as manager_role

from .presentation import add_details_to_screenings


def best_promotion_quote(screenings, price_calculator):
    quotes = (
        price_calculator.quote(
            base_price=price,
            seat_type_id=int(type_id),
            screening_starts_at=screening.starts_at,
        )
        for screening in screenings
        for type_id, price in (screening.prices_by_type or {}).items()
    )
    return max(
        (quote for quote in quotes if quote.promotion),
        key=lambda quote: quote.discount,
        default=None,
    )


def home_view(request):
    Screening.finalize_expired()
    published = Screening.published()
    movies = list(
        Movie.objects.filter(screenings__status=Screening.Status.PUBLISHED)
        .prefetch_related(
            Prefetch("screenings", queryset=published, to_attr="published_screenings")
        )
        .distinct()
    )
    price_calculator = PromotionPriceCalculator.current()
    for movie in movies:
        movie.promotion_quote = best_promotion_quote(movie.published_screenings, price_calculator)
    promotions = sorted(
        price_calculator.promotions,
        key=lambda promotion: not promotion.is_available_today,
    )
    return render(
        request,
        "home.html",
        {
            "cinema": CinemaSettings.current(),
            "movies": movies,
            "promotions": promotions if movies else [],
            "manager_role": manager_role(request.user),
        },
    )


@never_cache
def movie_detail_view(request, pk):
    Screening.finalize_expired()
    published = Screening.published()
    movie = get_object_or_404(
        Movie.objects.filter(screenings__status=Screening.Status.PUBLISHED)
        .prefetch_related(
            Prefetch("screenings", queryset=published, to_attr="published_screenings")
        )
        .distinct(),
        pk=pk,
    )
    screening = movie.published_screenings[0]
    price_calculator = PromotionPriceCalculator.current()
    add_details_to_screenings(movie.published_screenings, request.user, price_calculator)
    return render(
        request,
        "screening_detail.html",
        {
            "cinema": CinemaSettings.current(),
            "movie": movie,
            "screening": screening,
            "screenings": movie.published_screenings,
            "tickets_available": screening.tickets_available,
            "manager_role": manager_role(request.user),
        },
    )


@login_required
@never_cache
def movie_screening_reprogram(request, purchase_pk):
    Screening.finalize_expired()

    purchase = get_object_or_404(
        request.user.ticket_purchases.select_related("screening__movie"),
        pk=purchase_pk,
    )
    current_screening = purchase.screening
    movie = current_screening.movie
    try:
        check_reprogramming_window(current_screening)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("my_tickets")

    alternatives = list(
        Screening.published()
        .filter(movie=movie)
        .exclude(pk=current_screening.pk)
        .order_by("starts_at")
    )
    price_calculator = PromotionPriceCalculator.current()
    add_details_to_screenings(alternatives, request.user, price_calculator)

    return render(
        request,
        "screening_reprogram_detail.html",
        {
            "cinema": CinemaSettings.current(),
            "movie": movie,
            "purchase": purchase,
            "current_screening": current_screening,
            "screenings": alternatives,
            "manager_role": manager_role(request.user),
        },
    )


def screening_detail_view(request, pk):
    Screening.finalize_expired()
    screening = get_object_or_404(Screening.published(), pk=pk)
    return redirect("seat_selection", pk=screening.pk)


def _error_page(request, status, title, description, eyebrow):
    try:
        cinema = CinemaSettings.current()
    except Exception:
        cinema = CinemaSettings(name="Butaca Cero")
    return render(
        request,
        "error_page.html",
        {
            "cinema": cinema,
            "status": status,
            "title": title,
            "description": description,
            "eyebrow": eyebrow,
        },
        status=status,
    )


def bad_request_view(request, exception=None):
    return _error_page(
        request,
        400,
        "No pudimos interpretar la solicitud.",
        "Revisá los datos e intentá nuevamente.",
        "Solicitud inválida",
    )


def permission_denied_view(request, exception=None):
    return _error_page(
        request,
        403,
        "No tenés permiso para entrar acá.",
        "Si creés que deberías tener acceso, iniciá sesión con otra cuenta.",
        "Acceso restringido",
    )


def not_found_view(request, exception=None):
    return _error_page(
        request,
        404,
        "Esta página se perdió en el multiverso.",
        "La página que buscás no existe o ya no está disponible.",
        "Página no encontrada",
    )


def server_error_view(request):
    return _error_page(
        request,
        500,
        "Se apagaron las luces antes de tiempo.",
        "Tuvimos un problema inesperado. Esperá unos segundos e intentá de nuevo.",
        "Error inesperado",
    )