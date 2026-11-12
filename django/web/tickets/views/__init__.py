"""API pública conservada; editar cada funcionalidad en su módulo."""

from web.tickets.views.candy import candy_detail_view as candy_detail_view
from web.tickets.views.candy import candy_order_detail_view as candy_order_detail_view
from web.tickets.views.candy import candy_purchase_view as candy_purchase_view
from web.tickets.views.candy import candy_store_view as candy_store_view
from web.tickets.views.checkout import seat_selection_view as seat_selection_view
from web.tickets.views.checkout import ticket_purchase_view as ticket_purchase_view
from web.tickets.views.common import purchase_error_message as purchase_error_message
from web.tickets.views.purchases import admission_seat_summary as admission_seat_summary
from web.tickets.views.purchases import my_tickets_view as my_tickets_view
from web.tickets.views.purchases import notifications_view as notifications_view
from web.tickets.views.purchases import ticket_admission_status_view as ticket_admission_status_view
from web.tickets.views.purchases import ticket_detail_view as ticket_detail_view
from web.tickets.views.purchases import movie_ticket_transfer as movie_ticket_transfer
from web.tickets.views.reprogramming import screening_reprogram_view as screening_reprogram_view
from web.tickets.views.reprogramming import (
    seat_reprogram_selection_view as seat_reprogram_selection_view,
)
from web.tickets.views.reservations import reservation_payload as reservation_payload
from web.tickets.views.reservations import reservation_state_payload as reservation_state_payload
from web.tickets.views.reservations import (
    seat_reservation_batch_view as seat_reservation_batch_view,
)
from web.tickets.views.reservations import (
    seat_reservation_status_view as seat_reservation_status_view,
)
from web.tickets.views.reservations import seat_reservation_view as seat_reservation_view
