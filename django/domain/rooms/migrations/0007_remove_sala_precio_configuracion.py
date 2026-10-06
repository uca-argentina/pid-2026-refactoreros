from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rooms", "0006_remove_sala_capacidad"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="sala",
            name="precio_configuracion",
        ),
    ]
