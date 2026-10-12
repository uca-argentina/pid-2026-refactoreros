import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rooms", "0008_state_rename_sala"),
        ("seat_types", "0003_state_rename_fields"),
        ("seats", "0002_alter_seat_tipo"),
        ("tickets", "0009_purchaserefund_read_at"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameField("seat", "sala", "room"),
                migrations.RenameField("seat", "fila", "row"),
                migrations.RenameField("seat", "columna", "column"),
                migrations.RenameField("seat", "tipo", "seat_type"),
                migrations.AlterField(
                    "seat",
                    "room",
                    models.ForeignKey(
                        db_column="sala_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="seats",
                        to="rooms.room",
                    ),
                ),
                migrations.AlterField("seat", "row", models.PositiveIntegerField(db_column="fila")),
                migrations.AlterField("seat", "column", models.PositiveIntegerField(db_column="columna")),
                migrations.AlterField(
                    "seat",
                    "seat_type",
                    models.ForeignKey(
                        db_column="tipo_id",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="seats",
                        to="seat_types.seattype",
                    ),
                ),
                migrations.AlterModelOptions(
                    "seat",
                    {"ordering": ["room"], "verbose_name": "Asiento", "verbose_name_plural": "Asientos"},
                ),
            ],
        )
    ]
