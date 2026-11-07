"""Carga datos de demo (salas, películas reales y funciones) para desarrollo local.

Uso:
    docker compose exec web python manage.py seed_demo
    docker compose exec web python manage.py seed_demo --days 10

Los pósters se descargan de Wikipedia; si no hay conexión se genera uno simple.
"""

import json
import re
import time as time_module
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from domain.movies.models import Movie
from domain.rooms.models import Room
from domain.screenings.models import Screening
from domain.seat_types.models import SeatType
from domain.seats.models import Seat

SEAT_TYPES = {
    "Estándar": (Decimal("1000.00"), "#3b82f6"),
    "Preferencial": (Decimal("1500.00"), "#f59e0b"),
    "Accesible": (Decimal("800.00"), "#10b981"),
}

# (nombre, filas, columnas, filas preferenciales desde el fondo)
ROOMS = [
    ("Sala 1", 8, 12, 2),
    ("Sala 2", 6, 10, 1),
    ("Sala 3", 10, 14, 3),
]

# (título, sinopsis, género, clasificación, duración, color de respaldo, artículo de Wikipedia en inglés)
MOVIES = [
    ("Dune: Parte Dos", "Paul Atreides se une a los Fremen y emprende la guerra contra quienes destruyeron a su familia, mientras enfrenta una profecía que podría desatar el caos.", Movie.Genre.CIENCIA_FICCION, Movie.Rating.MAS_13, 166, "#b45309", "Dune: Part Two"),
    ("Oppenheimer", "La historia del físico J. Robert Oppenheimer y su papel en el desarrollo de la bomba atómica durante la Segunda Guerra Mundial.", Movie.Genre.DRAMA, Movie.Rating.MAS_13, 180, "#7c2d12", "Oppenheimer (film)"),
    ("Intensa-Mente 2", "Riley entra en la adolescencia y nuevas emociones, como Ansiedad, llegan al cuartel general para cambiarlo todo.", Movie.Genre.ANIMACION, Movie.Rating.ATP, 96, "#4c1d95", "Inside Out 2"),
    ("Deadpool & Wolverine", "Deadpool es reclutado por la TVA y debe convencer a una versión reticente de Wolverine para salvar su universo.", Movie.Genre.ACCION, Movie.Rating.MAS_16, 128, "#991b1b", "Deadpool & Wolverine"),
    ("Wicked", "La historia no contada de las brujas de Oz: la amistad entre Elphaba y Glinda antes de convertirse en leyenda.", Movie.Genre.MUSICAL, Movie.Rating.ATP, 160, "#15803d", "Wicked (2024 film)"),
    ("Gladiador II", "Años después de la muerte de Máximo, Lucio es esclavizado y debe luchar en el Coliseo para recuperar la gloria de Roma.", Movie.Genre.ACCION, Movie.Rating.MAS_16, 148, "#78350f", "Gladiator II"),
    ("Moana 2", "Moana recibe una llamada inesperada de sus ancestros y parte en un nuevo viaje hacia mares lejanos de Oceanía.", Movie.Genre.ANIMACION, Movie.Rating.ATP, 100, "#0e7490", "Moana 2"),
    ("Alien: Romulus", "Un grupo de jóvenes colonos explora una estación espacial abandonada y se enfrenta a la forma de vida más aterradora del universo.", Movie.Genre.TERROR, Movie.Rating.MAS_16, 119, "#1f2937", "Alien: Romulus"),
    ("Relatos salvajes", "Seis historias independientes sobre personas comunes que pierden el control ante situaciones de injusticia y estrés.", Movie.Genre.COMEDIA, Movie.Rating.MAS_16, 122, "#be185d", "Wild Tales (film)"),
    ("El secreto de sus ojos", "Un empleado judicial retirado escribe una novela sobre un asesinato sin resolver que lo marcó veinticinco años atrás.", Movie.Genre.SUSPENSO, Movie.Rating.MAS_16, 129, "#1e3a5f", "The Secret in Their Eyes"),
]

SHOW_TIMES = [time(14, 0), time(17, 30), time(21, 0)]

USER_AGENT = "ButacaCeroSeed/1.0 (local development)"


def fetch_wikipedia_poster(article):
    """Descarga el póster de la película desde Wikipedia. Devuelve None si falla."""
    try:
        query = urllib.parse.urlencode({
            "action": "query", "titles": article, "prop": "pageimages", "piprop": "thumbnail",
            "pithumbsize": 600, "pilicense": "any", "format": "json", "redirects": 1,
        })
        request = urllib.request.Request(
            f"https://en.wikipedia.org/w/api.php?{query}", headers={"User-Agent": USER_AGENT}
        )
        pages = json.load(urllib.request.urlopen(request, timeout=15))["query"]["pages"]
        source = next(iter(pages.values()))["thumbnail"]["source"]
        request = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})
        for attempt in range(5):
            try:
                data = urllib.request.urlopen(request, timeout=30).read()
                break
            except urllib.error.HTTPError as error:
                if error.code != 429 or attempt == 4:
                    raise
                time_module.sleep(2 ** (attempt + 1))
        image = Image.open(BytesIO(data)).convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        return ContentFile(buffer.getvalue())
    except Exception:
        return None


def make_poster(title, color):
    img = Image.new("RGB", (400, 600), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 380, 580], outline="white", width=4)
    lines, line = [], ""
    for word in title.split():
        candidate = f"{line} {word}".strip()
        if len(candidate) > 16 and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    lines.append(line)
    y = 300 - len(lines) * 14
    for text in lines:
        width = draw.textlength(text)
        draw.text(((400 - width) / 2, y), text, fill="white")
        y += 28
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return ContentFile(buffer.getvalue())


class Command(BaseCommand):
    help = "Carga salas, películas reales y funciones publicadas de demo para desarrollo local."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7, help="Cantidad de días con funciones (default 7).")
        parser.add_argument(
            "--refresh-posters",
            action="store_true",
            help="Reintenta descargar los pósters de las películas que quedaron con póster generado.",
        )

    def handle(self, *args, days, refresh_posters, **options):
        rooms = self.seed_rooms()
        movies = self.seed_movies(refresh_posters)
        with transaction.atomic():
            self.seed_screenings(rooms, movies, days)

    @transaction.atomic
    def seed_rooms(self):
        seat_types = {}
        for name, (price, color) in SEAT_TYPES.items():
            seat_types[name], _ = SeatType.objects.get_or_create(
                name=name, defaults={"base_price": price, "color": color}
            )

        rooms = []
        for name, rows, columns, preferential_rows in ROOMS:
            room, _ = Room.objects.get_or_create(name=name)
            if not room.seats.exists():
                seats = []
                for row in range(rows):
                    for column in range(columns):
                        if row == 0 and column in (0, columns - 1):
                            seat_type = seat_types["Accesible"]
                        elif row >= rows - preferential_rows:
                            seat_type = seat_types["Preferencial"]
                        else:
                            seat_type = seat_types["Estándar"]
                        seats.append(Seat(room=room, row=row, column=column, seat_type=seat_type))
                Seat.objects.bulk_create(seats)
                room.layout_configuration = {
                    "rows": rows,
                    "columns": columns,
                    "seats": [{"row": s.row, "column": s.column, "type": s.seat_type.name} for s in seats],
                }
                room.save()
            rooms.append(room)
        self.stdout.write(f"Salas: {', '.join(r.name for r in rooms)}")
        return rooms

    def seed_movies(self, refresh_posters=False):
        movies = []
        for title, synopsis, genre, rating, duration, color, article in MOVIES:
            movie = Movie.objects.filter(title=title).first()
            is_new = movie is None
            has_placeholder = not is_new and (not movie.image or "placeholder" in movie.image.name)
            if is_new or (refresh_posters and has_placeholder):
                if is_new:
                    movie = Movie(title=title, synopsis=synopsis, genre=genre, rating=rating, duration_minutes=duration)
                slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
                poster = fetch_wikipedia_poster(article)
                filename = f"{slug}.jpg"
                if poster is None:
                    if not is_new:
                        self.stdout.write(self.style.WARNING(f"Sigue sin póster: {title}"))
                        movies.append(movie)
                        continue
                    self.stdout.write(self.style.WARNING(
                        f"Sin póster para {title}, uso uno generado (reintentá luego con --refresh-posters)."
                    ))
                    poster = make_poster(title, color)
                    filename = f"{slug}-placeholder.jpg"
                if not is_new and movie.image:
                    movie.image.delete(save=False)
                movie.image.save(filename, poster, save=False)
                movie.save()
                time_module.sleep(2)
            movies.append(movie)
        self.stdout.write(f"Películas: {len(movies)}")
        return movies

    def seed_screenings(self, rooms, movies, days):
        tz = timezone.get_current_timezone()
        now = timezone.now()
        today = timezone.localdate()
        created = skipped = 0
        index = 0
        for day in range(days):
            date = today + timedelta(days=day)
            for room in rooms:
                for show_time in SHOW_TIMES:
                    starts_at = timezone.make_aware(datetime.combine(date, show_time), tz)
                    movie = movies[index % len(movies)]
                    index += 1
                    if starts_at <= now + timedelta(minutes=30):
                        continue
                    end = starts_at + timedelta(minutes=movie.duration_minutes)
                    overlaps = any(
                        s.starts_at < end and s.ends_at > starts_at
                        for s in Screening.objects.filter(
                            room=room,
                            starts_at__gte=starts_at - timedelta(hours=4),
                            starts_at__lt=end,
                        ).exclude(status=Screening.Status.CANCELED).select_related("movie")
                    )
                    if overlaps:
                        skipped += 1
                        continue
                    Screening.objects.create(
                        movie=movie,
                        room=room,
                        starts_at=starts_at,
                        status=Screening.Status.PUBLISHED,
                        ticket_price=Decimal("1000.00"),
                    )
                    created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Funciones creadas: {created} (omitidas por superposición: {skipped})"
        ))
