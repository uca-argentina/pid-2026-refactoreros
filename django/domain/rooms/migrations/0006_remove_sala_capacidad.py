from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rooms", "0005_sala_precio_configuracion"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="sala",
            name="capacidad",
        ),
    ]
