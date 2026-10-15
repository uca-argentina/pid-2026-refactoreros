import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone
from domain.tickets.models import generate_ticket_token


def backfill_tickets(apps, schema_editor):
    Purchase = apps.get_model("tickets", "CompraEntrada")
    Seat = apps.get_model("tickets", "CompraAsiento")
    Ticket = apps.get_model("tickets", "AdmissionTicket")
    Refund = apps.get_model("tickets", "PurchaseRefund")
    alias = schema_editor.connection.alias
    for purchase in Purchase.objects.using(alias).select_related("funcion__pelicula").iterator():
        seats = list(Seat.objects.using(alias).filter(compra_id=purchase.pk).order_by("pk"))
        labels = []
        for item in purchase.asientos_seleccionados or []:
            label = item.get("label") if isinstance(item, dict) else str(item)
            if label and label not in labels:
                labels.append(label)
        if not labels:
            labels = [seat.label for seat in seats]
        used_by_label = {seat.label: seat.utilizada_en for seat in seats}
        for index in range(purchase.cantidad):
            label = labels[index] if index < len(labels) else ""
            Ticket.objects.using(alias).create(
                purchase_id=purchase.pk, number=index + 1, seat_label=label,
                code=generate_ticket_token(), used_at=used_by_label.get(label),
            )
        if purchase.funcion.estado == "cancelada":
            screening = purchase.funcion
            Refund.objects.using(alias).get_or_create(
                purchase_id=purchase.pk,
                defaults={
                    "amount": purchase.total,
                    "notice": (
                        f"Se canceló la función de {screening.pelicula.titulo} del "
                        f"{timezone.localtime(screening.fecha_horario):%d/%m/%Y %H:%M}. "
                        f"Registramos una devolución simulada de ${purchase.total:.2f} "
                        f"por tu compra #{purchase.pk}. No se realizó un movimiento de dinero real."
                    ),
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0004_compraasiento_utilizada_en"),
        ("screenings", "0004_merge_funcion_estado_snapshot_precios"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="AdmissionTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.PositiveIntegerField()),
                ("seat_label", models.CharField(max_length=12, blank=True)),
                ("code", models.CharField(max_length=32, unique=True, default=generate_ticket_token, editable=False)),
                ("used_at", models.DateTimeField(null=True, blank=True, editable=False)),
                ("used_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True, editable=False, related_name="validated_tickets", on_delete=django.db.models.deletion.SET_NULL)),
                ("purchase", models.ForeignKey(to="tickets.compraentrada", related_name="tickets", on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                "ordering": ["number"], "verbose_name": "Entrada individual", "verbose_name_plural": "Entradas individuales",
                "constraints": [models.UniqueConstraint(fields=["purchase", "number"], name="unique_ticket_number_per_purchase")],
            },
        ),
        migrations.CreateModel(
            name="PurchaseRefund",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference", models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
                ("amount", models.DecimalField(max_digits=10, decimal_places=2)),
                ("notice", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("email_sent_at", models.DateTimeField(null=True, blank=True)),
                ("purchase", models.OneToOneField(to="tickets.compraentrada", related_name="refund", on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={"verbose_name": "Devolución simulada", "verbose_name_plural": "Devoluciones simuladas"},
        ),
        migrations.RunPython(backfill_tickets, migrations.RunPython.noop),
    ]
