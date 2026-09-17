from django.urls import path

from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("listing/", views.home_view, name="listing"),
    path("peliculas/<int:pk>/", views.movie_detail_view, name="movie_detail"),
    path("funciones/<int:pk>/", views.screening_detail_view, name="screening_detail"),
    path("funcion/<int:pk>/", views.screening_detail_view, name="screening_page"),
]
