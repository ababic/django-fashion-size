"""Django choice field for measurement kinds.

Values match ``fashion_size.kinds.KindSlug``.
"""

from django.db import models


class MeasurementKindSlug(models.TextChoices):
    """Fine-grained measurement kinds that can be bound to catalog attributes."""

    DRESS = "dress", "Dress size"
    ADULT_SHOE = "adult-shoe", "Adult shoe size"
    KIDS_SHOE = "kids-shoe", "Kids shoe size"
    BABY_SHOE = "baby-shoe", "Baby shoe size"
    CUP_SIZE = "cup-size", "Cup size"
    BAND_SIZE = "band-size", "Band size"
    WAIST_SIZE = "waist-size", "Waist size"
    CHEST_SIZE = "chest-size", "Chest size"
    CHEST = "chest", "Chest"
    WAIST = "waist", "Waist"
    INSIDE_LEG = "inside-leg", "Inside leg"
    COLLAR = "collar", "Collar"
