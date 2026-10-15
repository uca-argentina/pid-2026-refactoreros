from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rooms", "0007_remove_sala_precio_configuracion"),
        ("tickets", "0009_purchaserefund_read_at"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameModel("Sala", "Room"),
                migrations.RenameField("room", "nombre", "name"),
                migrations.RenameField("room", "layout_configuracion", "layout_configuration"),
                migrations.AlterField(
                    "room",
                    "name",
                    models.CharField(db_column="nombre", max_length=100, unique=True),
                ),
                migrations.AlterField(
                    "room",
                    "layout_configuration",
                    models.JSONField(blank=True, db_column="layout_configuracion", default=dict),
                ),
                migrations.AlterModelOptions(
                    "room",
                    {"ordering": ["name"], "verbose_name": "Sala", "verbose_name_plural": "Salas"},
                ),
                migrations.AlterModelTable("room", "rooms_sala"),
            ],
        )
    ]
