import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("seat_types", "0002_seed_default_seat_types"),
        ("seats", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="seat",
            name="tipo",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="seats",
                to="seat_types.seattype",
            ),
        ),
    ]
