from django.db import migrations


def seed(apps, schema_editor):
    Question = apps.get_model("games", "Question")
    rows = [
        (1, "¿Cuál es la identidad de Spider-Man en la trilogía protagonizada por Tobey Maguire?", ["Bruce Wayne", "Peter Parker", "Clark Kent"], 1),
        (1, "¿Qué juguete es Woody en Toy Story?", ["Un astronauta", "Un dinosaurio", "Un vaquero"], 2),
        (1, "¿Cómo se llama la escuela de magia a la que asiste Harry Potter?", ["Hogwarts", "Narnia", "Gondor"], 0),
        (1, "¿Qué tipo de criatura es Shrek?", ["Un dragón", "Un ogro", "Un elfo"], 1),
        (1, "¿Qué personaje dice «Yo soy tu padre» en El imperio contraataca?", ["Yoda", "Obi-Wan Kenobi", "Darth Vader"], 2),
        (1, "¿Qué animal es Simba en El rey león?", ["Un león", "Un tigre", "Un leopardo"], 0),
        (2, "¿Quién dirigió Pulp Fiction?", ["Martin Scorsese", "Quentin Tarantino", "David Fincher"], 1),
        (2, "¿Quién compuso la música principal de Star Wars?", ["John Williams", "Hans Zimmer", "Danny Elfman"], 0),
        (2, "¿Qué actor interpretó a Jack Dawson en Titanic?", ["Brad Pitt", "Matt Damon", "Leonardo DiCaprio"], 2),
        (2, "¿Quién escribió las novelas en las que se basa El señor de los anillos?", ["J. K. Rowling", "J. R. R. Tolkien", "C. S. Lewis"], 1),
        (2, "¿Quién dirigió El origen (Inception)?", ["Christopher Nolan", "Steven Spielberg", "Denis Villeneuve"], 0),
        (2, "¿Qué actor interpreta a Neo en Matrix?", ["Tom Cruise", "Johnny Depp", "Keanu Reeves"], 2),
        (3, "¿Qué película de Orson Welles sigue la vida del magnate Charles Foster Kane?", ["El tercer hombre", "Ciudadano Kane", "Sed de mal"], 1),
        (3, "¿Quién dirigió Los siete samuráis?", ["Akira Kurosawa", "Hayao Miyazaki", "Bong Joon-ho"], 0),
        (3, "¿Cómo se llama la computadora de 2001: Odisea del espacio?", ["Skynet", "Mother", "HAL 9000"], 2),
        (3, "¿Qué película argentina ganó el Oscar a película extranjera en 2010?", ["Relatos salvajes", "El secreto de sus ojos", "Nueve reinas"], 1),
        (3, "¿Qué director realizó El viaje de Chihiro?", ["Hayao Miyazaki", "Isao Takahata", "Satoshi Kon"], 0),
        (3, "¿Qué actriz interpreta a Clarice Starling en El silencio de los inocentes?", ["Julianne Moore", "Sigourney Weaver", "Jodie Foster"], 2),
    ]
    for difficulty, text, options, correct in rows:
        Question.objects.using(schema_editor.connection.alias).get_or_create(text=text, defaults={"options": options, "correct": correct, "difficulty": difficulty})


class Migration(migrations.Migration):
    dependencies = [("games", "0005_preserve_question_usage")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
