from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="compraentrada",
            name="asientos_seleccionados",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
