import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0006_purchase_validation_credential"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AdmissionValidation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reverted_at", models.DateTimeField(blank=True, null=True)),
                ("operator", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="admission_validations", to=settings.AUTH_USER_MODEL)),
                ("purchase", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="admission_validations", to="tickets.compraentrada")),
                ("tickets", models.ManyToManyField(related_name="validation_events", to="tickets.admissionticket")),
            ],
            options={
                "verbose_name": "Validación de ingreso",
                "verbose_name_plural": "Validaciones de ingreso",
                "ordering": ["-created_at"],
            },
        ),
    ]
