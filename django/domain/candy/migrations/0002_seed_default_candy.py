from django.db import migrations


DEFAULT_PRODUCTS = (
    ("Pochoclos chicos", "pochoclos", "900.00"),
    ("Pochoclos medianos", "pochoclos", "1200.00"),
    ("Pochoclos grandes", "pochoclos", "1500.00"),
    ("Gaseosa 500 ml", "bebidas", "800.00"),
    ("Agua mineral 500 ml", "bebidas", "600.00"),
    ("Nachos con queso", "snacks", "1300.00"),
    ("Pancho", "snacks", "1000.00"),
    ("Chocolate", "golosinas", "700.00"),
    ("Gomitas", "golosinas", "500.00"),
)

DEFAULT_COMBOS = (
    ("Combo Individual", "1700.00", (("Pochoclos medianos", 1), ("Gaseosa 500 ml", 1))),
    ("Combo Pareja", "2600.00", (("Pochoclos grandes", 1), ("Gaseosa 500 ml", 2))),
    ("Combo Nachos", "1800.00", (("Nachos con queso", 1), ("Gaseosa 500 ml", 1))),
)

DEFAULT_STOCK = 100


def create_default_candy(apps, schema_editor):
    CandyProduct = apps.get_model("candy", "CandyProduct")
    CandyCombo = apps.get_model("candy", "CandyCombo")
    CandyComboItem = apps.get_model("candy", "CandyComboItem")
    products = {}
    for name, category, price in DEFAULT_PRODUCTS:
        products[name], _ = CandyProduct.objects.get_or_create(
            name=name,
            defaults={"category": category, "price": price, "stock": DEFAULT_STOCK},
        )
    for name, price, items in DEFAULT_COMBOS:
        combo, created = CandyCombo.objects.get_or_create(name=name, defaults={"price": price})
        if not created:
            continue
        for product_name, quantity in items:
            CandyComboItem.objects.create(combo=combo, product=products[product_name], quantity=quantity)


def remove_default_candy(apps, schema_editor):
    CandyProduct = apps.get_model("candy", "CandyProduct")
    CandyCombo = apps.get_model("candy", "CandyCombo")
    CandyCombo.objects.filter(name__in=[name for name, _price, _items in DEFAULT_COMBOS]).delete()
    CandyProduct.objects.filter(
        name__in=[name for name, _category, _price in DEFAULT_PRODUCTS],
        combo_items__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("candy", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_candy, remove_default_candy),
    ]
