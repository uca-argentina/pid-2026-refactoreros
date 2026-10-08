import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Creates an initial superuser from environment variables if it does not exist."

    def handle(self, *args, **options):
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip().lower()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

        if not email:
            raise CommandError("DJANGO_SUPERUSER_EMAIL is required.")

        if not password:
            raise CommandError("DJANGO_SUPERUSER_PASSWORD is required.")

        User = get_user_model()
        user = User.objects.filter(username__iexact=email).first()

        if user:
            updated_fields = []
            if not user.is_staff:
                user.is_staff = True
                updated_fields.append("is_staff")
            if not user.is_superuser:
                user.is_superuser = True
                updated_fields.append("is_superuser")
            if not user.email:
                user.email = email
                updated_fields.append("email")

            if updated_fields:
                user.save(update_fields=updated_fields)
                self.stdout.write(
                    self.style.SUCCESS(f"Updated existing superuser {email}.")
                )
            else:
                self.stdout.write(f"Superuser {email} already exists.")
            return

        User.objects.create_superuser(username=email, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Created initial superuser {email}."))
