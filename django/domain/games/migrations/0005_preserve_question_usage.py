import hashlib
import unicodedata
from django.db import migrations


def preserve_usage(apps, schema_editor):
    alias = schema_editor.connection.alias
    Run = apps.get_model("games", "TriviaRun")
    Question = apps.get_model("games", "Question")
    Use = apps.get_model("games", "QuestionUse")
    Slot = apps.get_model("games", "WheelSlot")
    Slot.objects.using(alias).filter(kind="attempt", label="Otra trivia", position=2, count=2).update(active=False)
    existing = set(Question.objects.using(alias).values_list("pk", flat=True))
    seen_ids, seen_texts = set(), set()
    for run in Run.objects.using(alias).order_by("pk").iterator():
        Run.objects.using(alias).filter(pk=run.pk).update(question_started_at=run.created_at)
        for question in run.questions:
            normalized = " ".join(unicodedata.normalize("NFKC", question["text"]).casefold().split())
            fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            pk = question.get("id")
            if fingerprint in seen_texts:
                continue
            Use.objects.using(alias).create(question_id=pk if pk in existing and pk not in seen_ids else None, fingerprint=fingerprint, run_id=run.pk)
            seen_ids.add(pk)
            seen_texts.add(fingerprint)


class Migration(migrations.Migration):
    dependencies = [("games", "0004_triviaanswer_timed_out_triviarun_question_seconds_and_more")]
    operations = [migrations.RunPython(preserve_usage, migrations.RunPython.noop)]
