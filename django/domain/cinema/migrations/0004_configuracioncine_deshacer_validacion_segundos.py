from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cinema", "0003_configuracioncine_recarga_asientos_segundos")]

    operations = [
        migrations.AddField(
            model_name="configuracioncine",
            name="deshacer_validacion_segundos",
            field=models.PositiveIntegerField(default=30),
        ),
    ]
