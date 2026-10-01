from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cinema", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncine",
            name="reserva_asientos_minutos",
            field=models.PositiveIntegerField(default=5),
        ),
    ]
