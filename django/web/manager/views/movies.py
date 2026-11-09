"""Movies."""

from django.db.models import Q
from django.urls import reverse_lazy
from domain.movies.models import Movie

from web.manager.forms import MovieForm
from web.manager.views.base import (
    ManagerCreateView,
    ManagerDeleteView,
    ManagerListView,
    ManagerUpdateView,
)


class MoviesListView(ManagerListView):
    model = Movie
    template_name = "manager_peliculas_list.html"
    section = "Peliculas"
    create_url_name = "manager:peliculas_create"
    columns = ("Titulo", "Genero", "Clasificacion", "Duracion")
    search_placeholder = "Buscar por título, género o sinopsis"
    ordering_options = (
        ("titulo_asc", "Título A-Z", ("title",)),
        ("titulo_desc", "Título Z-A", ("-title",)),
        ("genero_asc", "Género A-Z", ("genre", "title")),
        ("duracion_desc", "Más largas", ("-duration_minutes", "title")),
        ("duracion_asc", "Más cortas", ("duration_minutes", "title")),
    )

    def apply_search(self, queryset, search_query):
        return queryset.filter(
            Q(title__icontains=search_query)
            | Q(synopsis__icontains=search_query)
            | Q(genre__icontains=search_query)
        )


class MovieCreateView(ManagerCreateView):
    model = Movie
    form_class = MovieForm
    success_url = reverse_lazy("manager:peliculas_list")
    section = "Peliculas"
    enctype = "multipart/form-data"
    object_label = "La película"
    form_title = "Nueva pelicula"


class MovieUpdateView(ManagerUpdateView):
    model = Movie
    form_class = MovieForm
    success_url = reverse_lazy("manager:peliculas_list")
    section = "Peliculas"
    enctype = "multipart/form-data"
    object_label = "La película"
    form_title = "Editar pelicula"


class MovieDeleteView(ManagerDeleteView):
    model = Movie
    success_url = reverse_lazy("manager:peliculas_list")
    section = "Peliculas"
    object_label = "La película"
