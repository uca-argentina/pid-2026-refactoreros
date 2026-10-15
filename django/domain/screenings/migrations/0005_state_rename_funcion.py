import django.db.models.deletion
from django.db import migrations, models


STATUS_CHOICES = [
    ("borrador", "Borrador"),
    ("programada", "Programada"),
    ("publicada", "Publicada"),
    ("cancelada", "Cancelada"),
    ("finalizada", "Finalizada"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("movies", "0002_state_rename_pelicula"),
        ("rooms", "0008_state_rename_sala"),
        ("screenings", "0004_merge_funcion_estado_snapshot_precios"),
        ("tickets", "0009_purchaserefund_read_at"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameModel("Funcion", "Screening"),
                migrations.RenameField("screening", "pelicula", "movie"),
                migrations.RenameField("screening", "sala", "room"),
                migrations.RenameField("screening", "fecha_horario", "starts_at"),
                migrations.RenameField("screening", "estado", "status"),
                migrations.RenameField("screening", "precio_entrada", "ticket_price"),
                migrations.RenameField("screening", "precios_por_tipo", "prices_by_type"),
                migrations.RenameField(
                    "screening",
                    "sala_configuracion_snapshot",
                    "room_layout_snapshot",
                ),
                migrations.RenameField(
                    "screening",
                    "capacidad_snapshot",
                    "capacity_snapshot",
                ),
                migrations.AlterField(
                    "screening",
                    "movie",
                    models.ForeignKey(
                        db_column="pelicula_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="screenings",
                        to="movies.movie",
                        verbose_name="Pelicula",
                    ),
                ),
                migrations.AlterField(
                    "screening",
                    "room",
                    models.ForeignKey(
                        db_column="sala_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="screenings",
                        to="rooms.room",
                    ),
                ),
                migrations.AlterField(
                    "screening",
                    "starts_at",
                    models.DateTimeField(db_column="fecha_horario"),
                ),
                migrations.AlterField(
                    "screening",
                    "status",
                    models.CharField(
                        choices=STATUS_CHOICES,
                        db_column="estado",
                        default="borrador",
                        max_length=20,
                    ),
                ),
                migrations.AlterField(
                    "screening",
                    "ticket_price",
                    models.DecimalField(db_column="precio_entrada", decimal_places=2, max_digits=8),
                ),
                migrations.AlterField(
                    "screening",
                    "prices_by_type",
                    models.JSONField(blank=True, db_column="precios_por_tipo", default=dict),
                ),
                migrations.AlterField(
                    "screening",
                    "room_layout_snapshot",
                    models.JSONField(blank=True, db_column="sala_configuracion_snapshot", default=list),
                ),
                migrations.AlterField(
                    "screening",
                    "capacity_snapshot",
                    models.PositiveIntegerField(db_column="capacidad_snapshot", default=0),
                ),
                migrations.AlterModelOptions(
                    "screening",
                    {"ordering": ["starts_at"], "verbose_name": "función", "verbose_name_plural": "funciones"},
                ),
                migrations.AlterModelTable("screening", "screenings_funcion"),
            ],
        )
    ]
