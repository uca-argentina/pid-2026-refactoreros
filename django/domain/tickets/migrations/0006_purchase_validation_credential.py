from django.db import migrations, models
from domain.tickets.models import generate_ticket_code, generate_ticket_token


def set_unique_credentials(apps, schema_editor):
    Purchase = apps.get_model("tickets", "CompraEntrada")
    used_codes = set()
    used_tokens = set()
    for purchase in Purchase.objects.order_by("pk").iterator():
        code = generate_ticket_code()
        while code in used_codes:
            code = generate_ticket_code()
        token = generate_ticket_token()
        while token in used_tokens:
            token = generate_ticket_token()
        Purchase.objects.filter(pk=purchase.pk).update(validation_code=code, validation_token=token)
        used_codes.add(code)
        used_tokens.add(token)


class Migration(migrations.Migration):
    dependencies = [("tickets", "0005_admission_tickets_and_refunds")]
    operations = [
        migrations.AddField(model_name="compraentrada", name="validation_code", field=models.CharField(max_length=6, null=True, editable=False)),
        migrations.AddField(model_name="compraentrada", name="validation_token", field=models.CharField(max_length=32, null=True, editable=False)),
        migrations.RunPython(set_unique_credentials, migrations.RunPython.noop),
        migrations.AlterField(model_name="compraentrada", name="validation_code", field=models.CharField(max_length=6, unique=True, default=generate_ticket_code, editable=False)),
        migrations.AlterField(model_name="compraentrada", name="validation_token", field=models.CharField(max_length=32, unique=True, default=generate_ticket_token, editable=False)),
    ]
