from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cinema", "0006_candy_quantity_limit")]

    operations = [
        migrations.AddField(
            model_name="cinemasettings",
            name="ticket_reprogram_minutes",
            field=models.PositiveIntegerField(default=120),
        ),
    ]
