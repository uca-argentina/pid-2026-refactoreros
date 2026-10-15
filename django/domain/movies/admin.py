from django.contrib import admin

from .models import Movie

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ("title", "genre", "rating", "duration_minutes")
    list_filter = ("genre", "rating")
    search_fields = ("title", "synopsis")
    ordering = ("title",)
    fields = (
        "title",
        "synopsis",
        "genre",
        "rating",
        "duration_minutes",
        "image",
    )