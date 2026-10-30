from pathlib import Path

from django.core.files import File
from django.db import migrations


SEED_IMAGES = Path(__file__).resolve().parent.parent / "seed_images"

PRODUCT_IMAGES = {
    "Pochoclos chicos": "pochoclos-chicos.jpg",
    "Pochoclos medianos": "pochoclos-medianos.jpg",
    "Pochoclos grandes": "pochoclos-grandes.jpg",
    "Gaseosa 500 ml": "gaseosa.jpg",
    "Agua mineral 500 ml": "agua.jpg",
    "Nachos con queso": "nachos.jpg",
    "Pancho": "pancho.jpg",
    "Chocolate": "chocolate.jpg",
    "Gomitas": "gomitas.jpg",
}

COMBO_IMAGES = {
    "Combo Individual": "combo-individual.jpg",
    "Combo Pareja": "combo-pareja.jpg",
    "Combo Nachos": "combo-nachos.jpg",
}


def attach_images(model, images):
    for name, filename in images.items():
        item = model.objects.filter(name=name, image="").first()
        if item is None:
            continue
        storage = item.image.storage
        target = f"candy/{filename}"
        if not storage.exists(target):
            with open(SEED_IMAGES / filename, "rb") as handle:
                target = storage.save(target, File(handle))
        item.image = target
        item.save(update_fields=["image"])


def add_seed_images(apps, schema_editor):
    attach_images(apps.get_model("candy", "CandyProduct"), PRODUCT_IMAGES)
    attach_images(apps.get_model("candy", "CandyCombo"), COMBO_IMAGES)


def remove_seed_images(apps, schema_editor):
    for model_name, images in (("CandyProduct", PRODUCT_IMAGES), ("CandyCombo", COMBO_IMAGES)):
        model = apps.get_model("candy", model_name)
        for name, filename in images.items():
            model.objects.filter(name=name, image=f"candy/{filename}").update(image="")


class Migration(migrations.Migration):

    dependencies = [
        ("candy", "0002_seed_default_candy"),
    ]

    operations = [
        migrations.RunPython(add_seed_images, remove_seed_images),
    ]
