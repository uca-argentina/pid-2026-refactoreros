import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("screenings", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompraEntrada",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("cantidad", models.PositiveIntegerField()),
                ("total", models.DecimalField(decimal_places=2, max_digits=10)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                (
                    "funcion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="compras_entradas",
                        to="screenings.funcion",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="compras_entradas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Compra de entrada",
                "verbose_name_plural": "Compras de entradas",
                "ordering": ["-creada_en"],
            },
        ),
    ]
