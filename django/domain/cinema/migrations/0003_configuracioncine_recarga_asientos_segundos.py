from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cinema", "0002_configuracioncine_reserva_asientos_minutos"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncine",
            name="recarga_asientos_segundos",
            field=models.PositiveIntegerField(default=5),
        ),
    ]
