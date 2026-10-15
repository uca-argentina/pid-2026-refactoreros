from django.db import migrations, models


GENRE_CHOICES = [
    ("ACCION", "Acción"),
    ("AVENTURA", "Aventura"),
    ("ANIMACION", "Animación"),
    ("COMEDIA", "Comedia"),
    ("DRAMA", "Drama"),
    ("TERROR", "Terror"),
    ("CIENCIA_FICCION", "Ciencia ficción"),
    ("SUSPENSO", "Suspenso"),
    ("ROMANCE", "Romance"),
    ("DOCUMENTAL", "Documental"),
    ("FANTASIA", "Fantasía"),
    ("MUSICAL", "Musical"),
]

RATING_CHOICES = [
    ("ATP", "ATP - Apta para todo público"),
    ("+13", "+13 años"),
    ("+16", "+16 años"),
    ("+18", "+18 años"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("movies", "0001_initial"),
        ("tickets", "0009_purchaserefund_read_at"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameModel("Pelicula", "Movie"),
                migrations.RenameField("movie", "titulo", "title"),
                migrations.RenameField("movie", "sinopsis", "synopsis"),
                migrations.RenameField("movie", "genero", "genre"),
                migrations.RenameField("movie", "clasificacion", "rating"),
                migrations.RenameField("movie", "duracion_minutos", "duration_minutes"),
                migrations.RenameField("movie", "imagen", "image"),
                migrations.AlterField("movie", "title", models.CharField(db_column="titulo", max_length=200)),
                migrations.AlterField("movie", "synopsis", models.TextField(db_column="sinopsis")),
                migrations.AlterField(
                    "movie",
                    "genre",
                    models.CharField(
                        choices=GENRE_CHOICES,
                        db_column="genero",
                        max_length=20,
                        verbose_name="Género",
                    ),
                ),
                migrations.AlterField(
                    "movie",
                    "rating",
                    models.CharField(
                        choices=RATING_CHOICES,
                        db_column="clasificacion",
                        max_length=5,
                        verbose_name="Clasificación",
                    ),
                ),
                migrations.AlterField(
                    "movie",
                    "duration_minutes",
                    models.PositiveIntegerField(
                        db_column="duracion_minutos",
                        help_text="Duración de la película en minutos",
                        verbose_name="Duración en minutos",
                    ),
                ),
                migrations.AlterField(
                    "movie",
                    "image",
                    models.ImageField(db_column="imagen", upload_to="peliculas/", verbose_name="Imagen del cartel"),
                ),
                migrations.AlterModelOptions(
                    "movie",
                    {"ordering": ["title"], "verbose_name": "Película", "verbose_name_plural": "Películas"},
                ),
                migrations.AlterModelTable("movie", "movies_pelicula"),
            ],
        )
    ]
