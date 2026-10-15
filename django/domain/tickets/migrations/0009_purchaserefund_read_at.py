from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tickets", "0008_hash_purchase_reservation_codes")]

    operations = [
        migrations.AddField(
            model_name="purchaserefund",
            name="read_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
