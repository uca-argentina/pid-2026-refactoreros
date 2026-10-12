import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("screenings", "0005_state_rename_funcion"),
        ("tickets", "0009_purchaserefund_read_at"),
        ("users", "0003_state_rename_profiles"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameModel("CompraEntrada", "TicketPurchase"),
                migrations.RenameModel("CompraAsiento", "SeatPurchase"),
                migrations.RenameModel("ReservaAsiento", "SeatReservation"),
                migrations.RenameField("ticketpurchase", "usuario", "user"),
                migrations.RenameField("ticketpurchase", "funcion", "screening"),
                migrations.RenameField("ticketpurchase", "cantidad", "quantity"),
                migrations.RenameField("ticketpurchase", "asientos_seleccionados", "selected_seats"),
                migrations.RenameField("ticketpurchase", "creada_en", "created_at"),
                migrations.RenameField("seatpurchase", "compra", "purchase"),
                migrations.RenameField("seatpurchase", "funcion", "screening"),
                migrations.RenameField("seatpurchase", "creada_en", "created_at"),
                migrations.RenameField("seatpurchase", "utilizada_en", "used_at"),
                migrations.RenameField("seatreservation", "usuario", "user"),
                migrations.RenameField("seatreservation", "funcion", "screening"),
                migrations.RenameField("seatreservation", "expira_en", "expires_at"),
                migrations.RenameField("seatreservation", "creada_en", "created_at"),
                migrations.RenameField("seatreservation", "actualizada_en", "updated_at"),
                migrations.AlterField(
                    "ticketpurchase",
                    "user",
                    models.ForeignKey(
                        db_column="usuario_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ticket_purchases",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    "ticketpurchase",
                    "screening",
                    models.ForeignKey(
                        db_column="funcion_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ticket_purchases",
                        to="screenings.screening",
                    ),
                ),
                migrations.AlterField(
                    "ticketpurchase",
                    "quantity",
                    models.PositiveIntegerField(db_column="cantidad"),
                ),
                migrations.AlterField(
                    "ticketpurchase",
                    "selected_seats",
                    models.JSONField(blank=True, db_column="asientos_seleccionados", default=list),
                ),
                migrations.AlterField(
                    "ticketpurchase",
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_column="creada_en"),
                ),
                migrations.AlterField(
                    "seatpurchase",
                    "purchase",
                    models.ForeignKey(
                        db_column="compra_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sold_seats",
                        to="tickets.ticketpurchase",
                    ),
                ),
                migrations.AlterField(
                    "seatpurchase",
                    "screening",
                    models.ForeignKey(
                        db_column="funcion_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sold_seats",
                        to="screenings.screening",
                    ),
                ),
                migrations.AlterField(
                    "seatpurchase",
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_column="creada_en"),
                ),
                migrations.AlterField(
                    "seatpurchase",
                    "used_at",
                    models.DateTimeField(blank=True, db_column="utilizada_en", null=True),
                ),
                migrations.AlterField(
                    "seatreservation",
                    "user",
                    models.ForeignKey(
                        db_column="usuario_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="seat_reservations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    "seatreservation",
                    "screening",
                    models.ForeignKey(
                        db_column="funcion_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="seat_reservations",
                        to="screenings.screening",
                    ),
                ),
                migrations.AlterField(
                    "seatreservation",
                    "expires_at",
                    models.DateTimeField(db_column="expira_en"),
                ),
                migrations.AlterField(
                    "seatreservation",
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_column="creada_en"),
                ),
                migrations.AlterField(
                    "seatreservation",
                    "updated_at",
                    models.DateTimeField(auto_now=True, db_column="actualizada_en"),
                ),
                migrations.AlterModelOptions(
                    "ticketpurchase",
                    {"ordering": ["-created_at"], "verbose_name": "Compra de entrada", "verbose_name_plural": "Compras de entradas"},
                ),
                migrations.AlterModelOptions(
                    "seatpurchase",
                    {"verbose_name": "Asiento vendido", "verbose_name_plural": "Asientos vendidos"},
                ),
                migrations.AlterModelOptions(
                    "seatreservation",
                    {"verbose_name": "Reserva temporal de asiento", "verbose_name_plural": "Reservas temporales de asientos"},
                ),
                migrations.AlterModelTable("ticketpurchase", "tickets_compraentrada"),
                migrations.AlterModelTable("seatpurchase", "tickets_compraasiento"),
                migrations.AlterModelTable("seatreservation", "tickets_reservaasiento"),
                migrations.RemoveConstraint("seatpurchase", "unique_sold_seat_per_screening"),
                migrations.AddConstraint(
                    "seatpurchase",
                    models.UniqueConstraint(
                        fields=("screening", "label"),
                        name="unique_sold_seat_per_screening",
                    ),
                ),
                migrations.RemoveConstraint("seatreservation", "unique_reserved_seat_per_screening"),
                migrations.AddConstraint(
                    "seatreservation",
                    models.UniqueConstraint(
                        fields=("screening", "label"),
                        name="unique_reserved_seat_per_screening",
                    ),
                ),
            ],
        )
    ]
