from django.db import migrations


def seed(apps, schema_editor):
    Question = apps.get_model("games", "Question")
    Slot = apps.get_model("games", "WheelSlot")
    Config = apps.get_model("games", "WheelConfig")
    Config.objects.using(schema_editor.connection.alias).get_or_create(pk=1)
    questions = [
        ("¿Quién dirigió Jurassic Park (1993)?", ["Steven Spielberg", "James Cameron", "Ridley Scott"], 0, 1),
        ("¿Qué película ganó el Oscar a mejor película en 2020?", ["1917", "Parásitos", "Joker"], 1, 2),
        ("¿Quién compuso la música de Cinema Paradiso junto a su hijo Andrea?", ["Nino Rota", "Hans Zimmer", "Ennio Morricone"], 2, 3),
    ]
    for text, options, correct, difficulty in questions:
        Question.objects.using(schema_editor.connection.alias).create(text=text, options=options, correct=correct, difficulty=difficulty)
    for position, (kind, label, count) in enumerate([
        ("over", "Game Over", 4), ("spin", "Una tirada más", 2), ("attempt", "Otra trivia", 2)
    ]):
        Slot.objects.using(schema_editor.connection.alias).create(kind=kind, label=label, count=count, position=position)


class Migration(migrations.Migration):
    dependencies = [("games", "0001_initial")]
    # Preserve administrator edits when reverting the starter content migration.
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
