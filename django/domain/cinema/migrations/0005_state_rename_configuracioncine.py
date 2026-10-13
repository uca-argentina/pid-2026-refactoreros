from django.db import migrations, models


class Migration(migrations.Migration):
    """Align Django's migration state with the English runtime model names.

    The database has always used the legacy Spanish table and column names.
    Keep that schema intact while recording the Python-level renames.
    """

    dependencies = [("cinema", "0004_configuracioncine_deshacer_validacion_segundos")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameModel("ConfiguracionCine", "CinemaSettings"),
                migrations.RenameField("cinemasettings", "nombre", "name"),
                migrations.RenameField("cinemasettings", "imagen_login", "login_image"),
                migrations.RenameField(
                    "cinemasettings",
                    "reserva_asientos_minutos",
                    "seat_reservation_minutes",
                ),
                migrations.RenameField(
                    "cinemasettings",
                    "recarga_asientos_segundos",
                    "seat_refresh_seconds",
                ),
                migrations.RenameField(
                    "cinemasettings",
                    "deshacer_validacion_segundos",
                    "admission_undo_seconds",
                ),
                migrations.RenameField("cinemasettings", "actualizado_en", "updated_at"),
                migrations.AlterField(
                    "cinemasettings",
                    "name",
                    models.CharField(db_column="nombre", default="Butaca Cero", max_length=120),
                ),
                migrations.AlterField(
                    "cinemasettings",
                    "login_image",
                    models.ImageField(blank=True, db_column="imagen_login", upload_to="branding/"),
                ),
                migrations.AlterField(
                    "cinemasettings",
                    "seat_reservation_minutes",
                    models.PositiveIntegerField(db_column="reserva_asientos_minutos", default=5),
                ),
                migrations.AlterField(
                    "cinemasettings",
                    "seat_refresh_seconds",
                    models.PositiveIntegerField(db_column="recarga_asientos_segundos", default=5),
                ),
                migrations.AlterField(
                    "cinemasettings",
                    "admission_undo_seconds",
                    models.PositiveIntegerField(db_column="deshacer_validacion_segundos", default=30),
                ),
                migrations.AlterField(
                    "cinemasettings",
                    "updated_at",
                    models.DateTimeField(auto_now=True, db_column="actualizado_en"),
                ),
                migrations.AlterModelTable("cinemasettings", "cinema_configuracioncine"),
            ],
        )
    ]
