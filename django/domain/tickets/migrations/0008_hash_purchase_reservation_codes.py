import hashlib
import hmac
import secrets

from django.conf import settings
from django.db import migrations, models


ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def reservation_code_for_token(token):
    digest = hmac.new(
        settings.SECRET_KEY.encode(),
        f"ticket-reservation-code:{token}".encode(),
        hashlib.sha256,
    ).digest()
    return "".join(ALPHABET[byte % len(ALPHABET)] for byte in digest[:6])


def reservation_code_digest(code):
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"ticket-reservation-lookup:{code.upper()}".encode(),
        hashlib.sha256,
    ).hexdigest()


def migrate_reservation_codes(apps, schema_editor):
    Purchase = apps.get_model("tickets", "CompraEntrada")
    used_digests = set()
    for purchase in Purchase.objects.order_by("pk").iterator():
        token = purchase.validation_token
        code = reservation_code_for_token(token)
        digest = reservation_code_digest(code)
        while digest in used_digests:
            token = secrets.token_urlsafe(24)
            code = reservation_code_for_token(token)
            digest = reservation_code_digest(code)
        Purchase.objects.filter(pk=purchase.pk).update(
            validation_token=token,
            validation_code_digest=digest,
        )
        used_digests.add(digest)


class Migration(migrations.Migration):
    dependencies = [("tickets", "0007_admissionvalidation")]

    operations = [
        migrations.AddField(
            model_name="compraentrada",
            name="validation_code_digest",
            field=models.CharField(editable=False, max_length=64, null=True, unique=True),
        ),
        migrations.RunPython(migrate_reservation_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="compraentrada",
            name="validation_code_digest",
            field=models.CharField(editable=False, max_length=64, unique=True),
        ),
        migrations.RemoveField(model_name="compraentrada", name="validation_code"),
    ]
