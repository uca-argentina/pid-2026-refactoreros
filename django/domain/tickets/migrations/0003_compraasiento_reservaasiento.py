import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_selected_seats(apps, schema_editor):
    CompraEntrada = apps.get_model("tickets", "CompraEntrada")
    CompraAsiento = apps.get_model("tickets", "CompraAsiento")
    for compra in CompraEntrada.objects.all():
        seen = set()
        for seat in compra.asientos_seleccionados or []:
            label = seat.get("label") if isinstance(seat, dict) else str(seat)
            if not label or label in seen:
                continue
            seen.add(label)
            CompraAsiento.objects.get_or_create(
                compra=compra,
                funcion_id=compra.funcion_id,
                label=label,
            )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("screenings", "0004_funcion_precios_por_tipo"),
        ("tickets", "0002_compraentrada_asientos_seleccionados"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompraAsiento",
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
                ("label", models.CharField(max_length=12)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                (
                    "compra",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asientos_vendidos",
                        to="tickets.compraentrada",
                    ),
                ),
                (
                    "funcion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asientos_vendidos",
                        to="screenings.funcion",
                    ),
                ),
            ],
            options={
                "verbose_name": "Asiento vendido",
                "verbose_name_plural": "Asientos vendidos",
            },
        ),
        migrations.CreateModel(
            name="ReservaAsiento",
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
                ("label", models.CharField(max_length=12)),
                ("expira_en", models.DateTimeField()),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                ("actualizada_en", models.DateTimeField(auto_now=True)),
                (
                    "funcion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reservas_asientos",
                        to="screenings.funcion",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reservas_asientos",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Reserva temporal de asiento",
                "verbose_name_plural": "Reservas temporales de asientos",
            },
        ),
        migrations.AddConstraint(
            model_name="compraasiento",
            constraint=models.UniqueConstraint(
                fields=("funcion", "label"),
                name="unique_sold_seat_per_screening",
            ),
        ),
        migrations.AddConstraint(
            model_name="reservaasiento",
            constraint=models.UniqueConstraint(
                fields=("funcion", "label"),
                name="unique_reserved_seat_per_screening",
            ),
        ),
        migrations.RunPython(migrate_selected_seats, migrations.RunPython.noop),
    ]
