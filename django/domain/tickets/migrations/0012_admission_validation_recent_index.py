from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tickets", "0011_rehash_stable_reservation_codes")]

    operations = [
        migrations.AddIndex(
            model_name="admissionvalidation",
            index=models.Index(
                fields=["operator", "-created_at"],
                name="admission_operator_recent_idx",
            ),
        ),
    ]
