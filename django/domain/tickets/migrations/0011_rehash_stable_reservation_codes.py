import hashlib
import secrets

from django.db import migrations


ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def reservation_code_for_token(token):
    digest = hashlib.sha256(f"ticket-reservation-code:{token}".encode()).digest()
    return "".join(ALPHABET[byte % len(ALPHABET)] for byte in digest[:6])


def reservation_code_digest(code):
    return hashlib.sha256(
        f"ticket-reservation-lookup:{code.upper()}".encode()
    ).hexdigest()


def rehash_reservation_codes(apps, schema_editor):
    Purchase = apps.get_model("tickets", "TicketPurchase")
    used_digests = set()
    for purchase in Purchase.objects.order_by("pk").iterator():
        token = purchase.validation_token
        digest = reservation_code_digest(reservation_code_for_token(token))
        while digest in used_digests:
            token = secrets.token_urlsafe(24)
            digest = reservation_code_digest(reservation_code_for_token(token))
        Purchase.objects.filter(pk=purchase.pk).update(
            validation_token=token,
            validation_code_digest=digest,
        )
        used_digests.add(digest)


class Migration(migrations.Migration):
    dependencies = [("tickets", "0010_state_rename_purchase_models")]

    operations = [
        migrations.RunPython(rehash_reservation_codes, migrations.RunPython.noop),
    ]
