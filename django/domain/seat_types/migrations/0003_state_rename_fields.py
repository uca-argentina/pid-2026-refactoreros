from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("seat_types", "0002_seed_default_seat_types"),
        ("tickets", "0009_purchaserefund_read_at"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameField("seattype", "nombre", "name"),
                migrations.RenameField("seattype", "precio_base", "base_price"),
                migrations.RenameField("seattype", "icono", "icon"),
                migrations.AlterField(
                    "seattype",
                    "name",
                    models.CharField(db_column="nombre", max_length=100, unique=True),
                ),
                migrations.AlterField(
                    "seattype",
                    "base_price",
                    models.DecimalField(
                        db_column="precio_base",
                        decimal_places=2,
                        max_digits=8,
                        validators=[MinValueValidator(Decimal("0.01"))],
                    ),
                ),
                migrations.AlterField(
                    "seattype",
                    "icon",
                    models.ImageField(blank=True, db_column="icono", upload_to="seat_icons/"),
                ),
                migrations.AlterModelOptions(
                    "seattype",
                    {
                        "ordering": ["name"],
                        "verbose_name": "Tipo de Asiento",
                        "verbose_name_plural": "Tipos de Asientos",
                    },
                ),
            ],
        )
    ]
