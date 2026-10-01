from django.urls import path

from . import views

urlpatterns = [
    path("funciones/<int:pk>/asientos/", views.seat_selection_view, name="seat_selection"),
    path("funciones/<int:pk>/asientos/reserva/", views.seat_reservation_view, name="seat_reservation"),
    path("funciones/<int:pk>/asientos/estado/", views.seat_reservation_status_view, name="seat_reservation_status"),
    path("funciones/<int:pk>/comprar/", views.ticket_purchase_view, name="ticket_purchase"),
    path("mis-entradas/", views.my_tickets_view, name="my_tickets"),
]
