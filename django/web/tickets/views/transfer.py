from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from web.tickets.forms import TicketTransferForm

@login_required
def ticket_transfer_view(request,purchase_pk):
    purchase = get_object_or_404(
        request.user.ticket_purchases.select_related("screening__movie", "screening__room"),
        pk=purchase_pk,
    )
    return render(request,"ticket_transfer.html",{"purchase": purchase})

@login_required
@require_POST
def ticket_transfer_view_confirm(request,purchase_pk):
    form = TicketTransferForm(request.POST)
    if not form.is_valid():
        pass
    redirect("mis-entradas")