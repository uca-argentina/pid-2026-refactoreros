from django.urls import path

from . import views

app_name = "manager"

urlpatterns = [
    path("", views.GestionHomeView.as_view(), name="home"),
    path("usuarios/", views.UsuariosListView.as_view(), name="usuarios_list"),
    path("usuarios/<int:pk>/editar/", views.UsuarioUpdateView.as_view(), name="usuarios_update"),
    path("usuarios/<int:pk>/estado/", views.UsuarioToggleActiveView.as_view(), name="usuarios_toggle"),
    path("salas/", views.SalasListView.as_view(), name="salas_list"),
    path("salas/nueva/", views.SalaCreateView.as_view(), name="salas_create"),
    path("salas/<int:pk>/editar/", views.SalaUpdateView.as_view(), name="salas_update"),
    path("salas/<int:pk>/eliminar/", views.SalaDeleteView.as_view(), name="salas_delete"),
    path("peliculas/", views.PeliculasListView.as_view(), name="peliculas_list"),
    path("peliculas/nueva/", views.PeliculaCreateView.as_view(), name="peliculas_create"),
    path("peliculas/<int:pk>/editar/", views.PeliculaUpdateView.as_view(), name="peliculas_update"),
    path("peliculas/<int:pk>/eliminar/", views.PeliculaDeleteView.as_view(), name="peliculas_delete"),
    path("funciones/", views.FuncionesListView.as_view(), name="funciones_list"),
    path("funciones/nueva/", views.FuncionCreateView.as_view(), name="funciones_create"),
    path("funciones/<int:pk>/editar/", views.FuncionUpdateView.as_view(), name="funciones_update"),
    path("funciones/<int:pk>/publicacion/", views.FuncionTogglePublicadaView.as_view(), name="funciones_toggle"),
    path("funciones/<int:pk>/eliminar/", views.FuncionDeleteView.as_view(), name="funciones_delete"),
]
