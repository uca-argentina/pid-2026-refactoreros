from django.urls import path
from . import views

app_name = "games"
urlpatterns = [
    path("", views.home, name="home"),
    path("api/state/", views.game_state, name="state"),
    path("api/<str:action>/", views.action, name="action"),
    path("premios/", views.coupons, name="coupons"),
    path("premios/retirar/", views.pickup, name="pickup"),
    path("premios/pedidos/<int:pk>/", views.pickup_detail, name="pickup_detail"),
    path("gestion/", views.dashboard, name="dashboard"),
    path("gestion/configuracion/", views.game_settings, name="settings"),
    path("gestion/importar/", views.import_questions, name="import"),
    path("gestion/exportar/", views.export_questions, name="export"),
    path("gestion/usuarios/<int:pk>/", views.user_detail, name="user"),
    path("gestion/<str:kind>/nuevo/", views.edit, name="create"),
    path("gestion/<str:kind>/<int:pk>/", views.edit, name="edit"),
    path("gestion/<str:kind>/<int:pk>/eliminar/", views.delete, name="delete"),
]
