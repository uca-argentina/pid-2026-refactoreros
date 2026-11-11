"""Candy."""

from domain.candy.models import CandyCombo, CandyComboItem, CandyProduct

from django import forms

from .uploads import MAX_MOVIE_IMAGE_SIZE_MB, validate_image_size


class CandyFormMixin:
    def clean_image(self):
        return validate_image_size(self.cleaned_data.get("image"), "La imagen")

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price <= 0:
            raise forms.ValidationError("El precio debe ser mayor a cero.")
        return price


class CandyProductForm(CandyFormMixin, forms.ModelForm):
    class Meta:
        model = CandyProduct
        fields = ("name", "category", "price", "stock", "is_active", "image")
        labels = {
            "name": "Nombre",
            "category": "Categoría",
            "price": "Precio",
            "stock": "Stock",
            "is_active": "A la venta",
            "image": "Imagen",
        }
        help_texts = {
            "stock": "Unidades disponibles. Los combos que lo incluyen descuentan de este stock.",
            "is_active": "Si lo desactivás, deja de venderse suelto. Los combos que lo incluyen siguen a la venta mientras haya stock.",
            "image": f"Opcional. Peso máximo: {MAX_MOVIE_IMAGE_SIZE_MB} MB.",
        }
        widgets = {
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }


class CandyComboForm(CandyFormMixin, forms.ModelForm):
    MAX_COMPONENT_QUANTITY = 20

    class Meta:
        model = CandyCombo
        fields = ("name", "price", "is_active", "image")
        labels = {
            "name": "Nombre",
            "price": "Precio del combo",
            "is_active": "A la venta",
            "image": "Imagen",
        }
        help_texts = {
            "image": f"Opcional. Peso máximo: {MAX_MOVIE_IMAGE_SIZE_MB} MB.",
        }
        widgets = {
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.combo_fields = [self[name] for name in self._meta.fields]
        current = (
            {item.product_id: item.quantity for item in self.instance.items.all()}
            if self.instance.pk
            else {}
        )
        self.products = CandyProduct.in_menu_order(CandyProduct.objects.all())
        self.product_rows = []
        for product in self.products:
            name = f"product_{product.pk}"
            self.fields[name] = forms.IntegerField(
                label=product.name,
                min_value=0,
                max_value=self.MAX_COMPONENT_QUANTITY,
                required=False,
                initial=current.get(product.pk, 0),
                widget=forms.NumberInput(attrs={"min": 0, "max": self.MAX_COMPONENT_QUANTITY}),
            )
            self.product_rows.append({"product": product, "field": self[name]})

    def clean(self):
        cleaned_data = super().clean()
        self.combo_items = {
            product.pk: cleaned_data.get(f"product_{product.pk}") or 0 for product in self.products
        }
        self.combo_items = {pk: quantity for pk, quantity in self.combo_items.items() if quantity}
        if sum(self.combo_items.values()) < 2:
            raise forms.ValidationError(
                "Un combo tiene que incluir al menos dos unidades de productos."
            )
        return cleaned_data

    def save(self, commit=True):
        combo = super().save(commit=commit)
        if commit:
            combo.items.exclude(product_id__in=self.combo_items).delete()
            for product_id, quantity in self.combo_items.items():
                CandyComboItem.objects.update_or_create(
                    combo=combo,
                    product_id=product_id,
                    defaults={"quantity": quantity},
                )
        return combo
