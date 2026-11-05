from django import forms
from .models import Question, WheelConfig, WheelSlot


class GameSettingsForm(forms.ModelForm):
    class Meta:
        model = WheelConfig
        fields = ["question_seconds"]
        help_texts = {"question_seconds": "Entre 1 y 300 segundos. Se aplica a partidas nuevas; el servidor controla el vencimiento."}


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["text", "options", "correct", "difficulty", "active"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3}), "options": forms.Textarea(attrs={"rows": 3})}
        help_texts = {"options": 'JSON: ["Respuesta A", "Respuesta B", "Respuesta C"]'}


class SlotForm(forms.ModelForm):
    class Meta:
        model = WheelSlot
        fields = ["kind", "label", "count", "position", "product", "active"]


class ImportForm(forms.Form):
    payload = forms.CharField(label="Preguntas en JSON", max_length=1_000_000, widget=forms.Textarea(attrs={"rows": 10}), required=False)
    file = forms.FileField(label="O archivo JSON", required=False)

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get("file")
        if upload and upload.size > 1_000_000:
            raise forms.ValidationError("El archivo no debe superar 1 MB.")
        if bool(upload) == bool(cleaned.get("payload")):
            raise forms.ValidationError("Pegá JSON o elegí un archivo, solo una opción.")
        return cleaned


class GrantForm(forms.Form):
    key = forms.UUIDField(widget=forms.HiddenInput)
    reward = forms.ChoiceField(label="Qué otorgar", choices=[("spin", "Tiradas adicionales"), ("attempt", "Trivias adicionales · una pregunta cada una")], initial="spin", required=False)
    amount = forms.IntegerField(label="Tiradas adicionales", min_value=1, max_value=100,
        widget=forms.NumberInput(attrs={"step": 1, "inputmode": "numeric"}))
    reason = forms.CharField(label="Motivo", max_length=500, widget=forms.Textarea(attrs={"rows": 2}))
