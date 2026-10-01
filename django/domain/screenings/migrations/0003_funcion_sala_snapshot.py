from django.db import migrations, models


def populate_existing_snapshots(apps, schema_editor):
    Funcion = apps.get_model("screenings", "Funcion")
    Seat = apps.get_model("seats", "Seat")

    for funcion in Funcion.objects.select_related("sala"):
        seats = Seat.objects.filter(sala_id=funcion.sala_id).select_related("tipo").order_by(
            "fila", "columna"
        )
        snapshot = [
            {
                "row": seat.fila,
                "column": seat.columna,
                "type": seat.tipo.nombre,
                "type_id": seat.tipo_id,
                "price": str(seat.tipo.precio_base),
                "color": seat.tipo.color,
            }
            for seat in seats
        ]
        funcion.sala_configuracion_snapshot = snapshot
        funcion.capacidad_snapshot = len(snapshot) if snapshot else funcion.sala.capacidad
        funcion.save(
            update_fields=["sala_configuracion_snapshot", "capacidad_snapshot"]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("rooms", "0003_sala_capacidad"),
        ("screenings", "0002_funcion_estado"),
        ("seats", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="funcion",
            name="sala_configuracion_snapshot",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="funcion",
            name="capacidad_snapshot",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(populate_existing_snapshots, migrations.RunPython.noop),
    ]
