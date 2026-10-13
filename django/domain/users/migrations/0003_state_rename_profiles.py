from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_operator"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameModel("Cliente", "Customer"),
                migrations.RenameModel("Acomodador", "Usher"),
                migrations.RenameModel("Gerente", "Manager"),
                migrations.RenameField("customer", "id_cliente", "customer_id"),
                migrations.RenameField("customer", "usuario", "user"),
                migrations.RenameField("usher", "id_acomodador", "usher_id"),
                migrations.RenameField("usher", "usuario", "user"),
                migrations.RenameField("manager", "id_gerente", "manager_id"),
                migrations.RenameField("manager", "usuario", "user"),
                migrations.AlterField(
                    "customer",
                    "customer_id",
                    models.BigAutoField(db_column="id_cliente", primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    "customer",
                    "user",
                    models.OneToOneField(
                        db_column="id_usuario",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="customer_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    "usher",
                    "usher_id",
                    models.BigAutoField(db_column="id_acomodador", primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    "usher",
                    "user",
                    models.OneToOneField(
                        db_column="id_usuario",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="usher_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    "manager",
                    "manager_id",
                    models.BigAutoField(db_column="id_gerente", primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    "manager",
                    "user",
                    models.OneToOneField(
                        db_column="id_usuario",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="manager_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterModelOptions(
                    "customer",
                    {"ordering": ["user__username"], "verbose_name": "Cliente", "verbose_name_plural": "Clientes"},
                ),
                migrations.AlterModelOptions(
                    "usher",
                    {"ordering": ["user__username"], "verbose_name": "Acomodador", "verbose_name_plural": "Acomodadores"},
                ),
                migrations.AlterModelOptions(
                    "manager",
                    {"ordering": ["user__username"], "verbose_name": "Gerente", "verbose_name_plural": "Gerentes"},
                ),
                migrations.AlterModelTable("customer", "users_cliente"),
                migrations.AlterModelTable("usher", "users_acomodador"),
                migrations.AlterModelTable("manager", "users_gerente"),
            ],
        )
    ]
