from django.urls import path

from . import views


urlpatterns = [
    path("candy/", views.candy_store_view, name="candy_store"),
    path("candy/comprar/", views.candy_purchase_view, name="candy_purchase"),
    path("candy/pedidos/<int:pk>/", views.candy_order_detail_view, name="candy_order_detail"),
    path("notificaciones/", views.notifications_view, name="notifications"),
    path("mis-entradas/<int:pk>/estado/", views.ticket_admission_status_view, name="ticket_admission_status"),
    path("mis-entradas/<int:pk>/", views.ticket_detail_view, name="ticket_detail"),
    path("mis-entradas/<int:pk>/candy/", views.candy_detail_view, name="candy_detail"),
    path("funciones/<int:pk>/asientos/", views.seat_selection_view, name="seat_selection"),

    path("reprogramacion/<int:purchase_pk>/funciones/<int:screening_pk>/asientos/", views.seat_reprogram_selection_view ,name="seat_reprogram_selection"),
    path("reprogramacion/<int:purchase_pk>/funciones/<int:screening_pk>/confirmar/", views.screening_reprogram_view ,name="screening_reprogram_confirm"),
    path("transferencia/<int:purchase_pk>", views.ticket_transfer_view, name="ticket_transfer"),
    path("transferencia/<int:purchase_pk>/confirmar", views.ticket_transfer_view_confirm, name="ticket_transfer_confirm"),


    path("funciones/<int:pk>/asientos/reserva/", views.seat_reservation_view, name="seat_reservation"),
    path("funciones/<int:pk>/asientos/reservas/", views.seat_reservation_batch_view, name="seat_reservation_batch"),
    path("funciones/<int:pk>/asientos/estado/", views.seat_reservation_status_view, name="seat_reservation_status"),
    path("funciones/<int:pk>/comprar/", views.ticket_purchase_view, name="ticket_purchase"),
    path("mis-entradas/", views.my_tickets_view, name="my_tickets"),
]
