from django.db import migrations, models


def publicada_a_estado(apps, schema_editor):
    Funcion = apps.get_model("screenings", "Funcion")
    Funcion.objects.filter(publicada=True).update(estado="publicada")
    Funcion.objects.filter(publicada=False).update(estado="borrador")


def estado_a_publicada(apps, schema_editor):
    Funcion = apps.get_model("screenings", "Funcion")
    Funcion.objects.filter(estado="publicada").update(publicada=True)
    Funcion.objects.exclude(estado="publicada").update(publicada=False)


class Migration(migrations.Migration):

    dependencies = [
        ("screenings", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="funcion",
            name="estado",
            field=models.CharField(
                choices=[
                    ("borrador", "Borrador"),
                    ("programada", "Programada"),
                    ("publicada", "Publicada"),
                    ("cancelada", "Cancelada"),
                    ("finalizada", "Finalizada"),
                ],
                default="borrador",
                max_length=20,
            ),
        ),
        migrations.RunPython(publicada_a_estado, estado_a_publicada),
        migrations.RemoveField(
            model_name="funcion",
            name="publicada",
        ),
    ]
