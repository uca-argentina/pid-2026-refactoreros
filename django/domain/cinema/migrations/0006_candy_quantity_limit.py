import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cinema", "0005_state_rename_configuracioncine")]

    operations = [
        migrations.AddField(
            model_name="cinemasettings",
            name="candy_max_item_quantity",
            field=models.PositiveIntegerField(default=10, validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AddConstraint(
            model_name="cinemasettings",
            constraint=models.CheckConstraint(condition=models.Q(candy_max_item_quantity__gte=1), name="cinema_candy_quantity_positive"),
        ),
    ]
