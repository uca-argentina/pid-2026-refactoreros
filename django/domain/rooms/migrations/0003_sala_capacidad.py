from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rooms", "0002_remove_sala_capacidad"),
    ]

    operations = [
        migrations.AddField(
            model_name="sala",
            name="capacidad",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
