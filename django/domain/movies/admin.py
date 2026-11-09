from django.contrib import admin

from .models import Movie
from .models import Review

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
        "trailer_url",
    )
    
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("movie", "user", "stars", "created_at")
    list_filter = ("stars",)
    search_fields = ("comment",)