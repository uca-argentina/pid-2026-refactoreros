import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    
    # No acoplamos estrictamente al modelo "User" sino al definido en settings (auth.User por def.)
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Cliente",
            fields=[
                ("id_cliente", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "usuario",
                    models.OneToOneField(
                        db_column="id_usuario",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cliente",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Cliente",
                "verbose_name_plural": "Clientes",
                "ordering": ["usuario__username"],
            },
        ),
        migrations.CreateModel(
            name="Acomodador",
            fields=[
                ("id_acomodador", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "usuario",
                    models.OneToOneField(
                        db_column="id_usuario",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="acomodador",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Acomodador",
                "verbose_name_plural": "Acomodadores",
                "ordering": ["usuario__username"],
            },
        ),
        migrations.CreateModel(
            name="Gerente",
            fields=[
                ("id_gerente", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "usuario",
                    models.OneToOneField(
                        db_column="id_usuario",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gerente",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Gerente",
                "verbose_name_plural": "Gerentes",
                "ordering": ["usuario__username"],
            },
        ),
    ]
