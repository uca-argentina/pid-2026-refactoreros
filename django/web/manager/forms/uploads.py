from django import forms

MAX_MOVIE_IMAGE_SIZE_MB = 2
MAX_MOVIE_IMAGE_SIZE_BYTES = MAX_MOVIE_IMAGE_SIZE_MB * 1024 * 1024


def validate_image_size(image, label="La imagen"):
    if image and getattr(image, "size", 0) > MAX_MOVIE_IMAGE_SIZE_BYTES:
        raise forms.ValidationError(f"{label} no puede superar los {MAX_MOVIE_IMAGE_SIZE_MB} MB.")
    return image
