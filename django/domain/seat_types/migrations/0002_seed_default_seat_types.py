from django.db import migrations


DEFAULT_SEAT_TYPES = (
    ("Estándar", "1000.00", "#2563eb"),
    ("Preferencial", "1500.00", "#7c3aed"),
    ("Accesible", "800.00", "#059669"),
)


def create_default_seat_types(apps, schema_editor):
    SeatType = apps.get_model("seat_types", "SeatType")
    for nombre, precio_base, color in DEFAULT_SEAT_TYPES:
        SeatType.objects.get_or_create(
            nombre=nombre,
            defaults={
                "precio_base": precio_base,
                "color": color,
            },
        )


def remove_default_seat_types(apps, schema_editor):
    SeatType = apps.get_model("seat_types", "SeatType")
    SeatType.objects.filter(
        nombre__in=[nombre for nombre, _precio_base, _color in DEFAULT_SEAT_TYPES]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("seat_types", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_seat_types, remove_default_seat_types),
    ]
