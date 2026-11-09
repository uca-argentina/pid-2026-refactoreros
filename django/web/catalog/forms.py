from django import forms
from domain.movies.models import Review

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ("stars", "comment")
        labels = {"stars": "Estrellas (1 a 5)", "comment": "Comentario"}
