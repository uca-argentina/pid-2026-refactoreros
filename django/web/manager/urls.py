from django.urls import path

from . import views

app_name = "manager"

urlpatterns = [
    path("", views.ManagementHomeView.as_view(), name="home"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("configuracion/", views.CinemaSettingsUpdateView.as_view(), name="configuracion"),
    path("usuarios/", views.UsersListView.as_view(), name="usuarios_list"),
    path("usuarios/<int:pk>/editar/", views.UserUpdateView.as_view(), name="usuarios_update"),
    path("usuarios/<int:pk>/estado/", views.UserToggleActiveView.as_view(), name="usuarios_toggle"),
    path("salas/", views.RoomsListView.as_view(), name="salas_list"),
    path("salas/nueva/", views.RoomCreateView.as_view(), name="salas_create"),
    path("salas/<int:pk>/editar/", views.RoomUpdateView.as_view(), name="salas_update"),
    path("salas/<int:pk>/eliminar/", views.RoomDeleteView.as_view(), name="salas_delete"),
    path("butacas/", views.SeatTypesListView.as_view(), name="seat_types_list"),
    path("butacas/nueva/", views.SeatTypeCreateView.as_view(), name="seat_types_create"),
    path("butacas/<int:pk>/editar/", views.SeatTypeUpdateView.as_view(), name="seat_types_update"),
    path("butacas/<int:pk>/eliminar/", views.SeatTypeDeleteView.as_view(), name="seat_types_delete"),
    path("peliculas/", views.MoviesListView.as_view(), name="peliculas_list"),
    path("peliculas/nueva/", views.MovieCreateView.as_view(), name="peliculas_create"),
    path("peliculas/<int:pk>/editar/", views.MovieUpdateView.as_view(), name="peliculas_update"),
    path("peliculas/<int:pk>/eliminar/", views.MovieDeleteView.as_view(), name="peliculas_delete"),
    path("funciones/", views.ScreeningsListView.as_view(), name="funciones_list"),
    path("funciones/historial/", views.ScreeningsHistoryListView.as_view(), name="funciones_historial"),
    path("funciones/nueva/", views.ScreeningCreateView.as_view(), name="funciones_create"),
    path("funciones/<int:pk>/editar/", views.ScreeningUpdateView.as_view(), name="funciones_update"),
    path("funciones/<int:pk>/estado/", views.ScreeningChangeStatusView.as_view(), name="funciones_estado"),
    path("funciones/<int:pk>/cancelar/", views.ScreeningCancelView.as_view(), name="funciones_cancelar"),
    path("funciones/<int:pk>/eliminar/", views.ScreeningDeleteView.as_view(), name="funciones_delete"),
]
