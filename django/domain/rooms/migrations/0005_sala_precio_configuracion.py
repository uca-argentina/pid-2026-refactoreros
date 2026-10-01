from django.db import migrations, models


def populate_room_prices(apps, schema_editor):
    Sala = apps.get_model("rooms", "Sala")
    Seat = apps.get_model("seats", "Seat")
    SeatType = apps.get_model("seat_types", "SeatType")

    base_prices = {
        str(seat_type.pk): str(seat_type.precio_base)
        for seat_type in SeatType.objects.all()
    }
    for sala in Sala.objects.all():
        type_ids = set(
            str(type_id)
            for type_id in Seat.objects.filter(sala_id=sala.pk)
            .values_list("tipo_id", flat=True)
            .distinct()
        )
        if not type_ids:
            type_ids = set(base_prices)
        sala.precio_configuracion = {
            type_id: base_prices[type_id]
            for type_id in type_ids
            if type_id in base_prices
        }
        sala.save(update_fields=["precio_configuracion"])


class Migration(migrations.Migration):

    dependencies = [
        ("rooms", "0004_sala_layout_configuracion"),
        ("seat_types", "0002_seed_default_seat_types"),
        ("seats", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sala",
            name="precio_configuracion",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(populate_room_prices, migrations.RunPython.noop),
    ]
