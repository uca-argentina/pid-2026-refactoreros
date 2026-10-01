from django.db import migrations, models


def populate_screening_type_prices(apps, schema_editor):
    Funcion = apps.get_model("screenings", "Funcion")

    for funcion in Funcion.objects.all():
        snapshot = funcion.sala_configuracion_snapshot or {}
        seats = snapshot.get("seats", []) if isinstance(snapshot, dict) else snapshot
        prices = {}
        for seat in seats or []:
            type_id = seat.get("type_id")
            price = seat.get("price")
            if type_id and price:
                prices[str(type_id)] = str(price)
        if not prices and funcion.precio_entrada:
            prices = {"legacy": str(funcion.precio_entrada)}
        funcion.precios_por_tipo = prices
        funcion.save(update_fields=["precios_por_tipo"])


class Migration(migrations.Migration):

    dependencies = [
        ("screenings", "0003_funcion_sala_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="funcion",
            name="precios_por_tipo",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(populate_screening_type_prices, migrations.RunPython.noop),
    ]
