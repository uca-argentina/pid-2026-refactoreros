from django.db import migrations, models


def populate_room_layouts(apps, schema_editor):
    Sala = apps.get_model("rooms", "Sala")
    Seat = apps.get_model("seats", "Seat")

    for sala in Sala.objects.all():
        seats = list(
            Seat.objects.filter(sala_id=sala.pk)
            .select_related("tipo")
            .order_by("fila", "columna")
        )
        if not seats:
            continue

        sala.layout_configuracion = {
            "rows": max(seat.fila for seat in seats) + 1,
            "columns": max(seat.columna for seat in seats) + 1,
            "seats": [
                {
                    "row": seat.fila,
                    "column": seat.columna,
                    "type": seat.tipo.nombre,
                }
                for seat in seats
            ],
        }
        sala.save(update_fields=["layout_configuracion"])


class Migration(migrations.Migration):

    dependencies = [
        ("rooms", "0003_sala_capacidad"),
        ("seats", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sala",
            name="layout_configuracion",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(populate_room_layouts, migrations.RunPython.noop),
    ]
