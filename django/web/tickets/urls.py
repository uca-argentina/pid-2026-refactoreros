from django.urls import path

from . import views

urlpatterns = [
    path("funciones/<int:pk>/comprar/", views.ticket_purchase_view, name="ticket_purchase"),
    path("mis-entradas/", views.my_tickets_view, name="my_tickets"),
]
