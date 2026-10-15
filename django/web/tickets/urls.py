from django.urls import path

from . import views

urlpatterns = [
    path("notificaciones/", views.notifications_view, name="notifications"),
    path("mis-entradas/<int:pk>/estado/", views.ticket_admission_status_view, name="ticket_admission_status"),
    path("mis-entradas/<int:pk>/", views.ticket_detail_view, name="ticket_detail"),
    path("funciones/<int:pk>/asientos/", views.seat_selection_view, name="seat_selection"),
    path("funciones/<int:pk>/asientos/reserva/", views.seat_reservation_view, name="seat_reservation"),
    path("funciones/<int:pk>/asientos/reservas/", views.seat_reservation_batch_view, name="seat_reservation_batch"),
    path("funciones/<int:pk>/asientos/estado/", views.seat_reservation_status_view, name="seat_reservation_status"),
    path("funciones/<int:pk>/comprar/", views.ticket_purchase_view, name="ticket_purchase"),
    path("mis-entradas/", views.my_tickets_view, name="my_tickets"),
]
