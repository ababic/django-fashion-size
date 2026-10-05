"""Django choices for size types.

Values and labels come from ``fashion_size`` so they stay aligned with
``fashion_size.size_types.SizeTypeSlug``.
"""

from django.db import models

from fashion_size.size_types import SizeTypeSlug as FashionSizeTypeSlug
from fashion_size.types import SIZE_TYPE_BY_SLUG


def _size_type_label(slug: FashionSizeTypeSlug) -> str:
    return SIZE_TYPE_BY_SLUG[slug].label


class SizeTypeSlug(models.TextChoices):
    """Fine-grained size types that can be bound to catalog attributes."""

    DRESS = FashionSizeTypeSlug.DRESS, _size_type_label(FashionSizeTypeSlug.DRESS)
    ADULT_SHOE = FashionSizeTypeSlug.ADULT_SHOE, _size_type_label(FashionSizeTypeSlug.ADULT_SHOE)
    KIDS_SHOE = FashionSizeTypeSlug.KIDS_SHOE, _size_type_label(FashionSizeTypeSlug.KIDS_SHOE)
    BABY_SHOE = FashionSizeTypeSlug.BABY_SHOE, _size_type_label(FashionSizeTypeSlug.BABY_SHOE)
    CUP_SIZE = FashionSizeTypeSlug.CUP_SIZE, _size_type_label(FashionSizeTypeSlug.CUP_SIZE)
    BAND_SIZE = FashionSizeTypeSlug.BAND_SIZE, _size_type_label(FashionSizeTypeSlug.BAND_SIZE)
    WAIST_SIZE = FashionSizeTypeSlug.WAIST_SIZE, _size_type_label(FashionSizeTypeSlug.WAIST_SIZE)
    CHEST_SIZE = FashionSizeTypeSlug.CHEST_SIZE, _size_type_label(FashionSizeTypeSlug.CHEST_SIZE)
    CHEST = FashionSizeTypeSlug.CHEST, _size_type_label(FashionSizeTypeSlug.CHEST)
    WAIST = FashionSizeTypeSlug.WAIST, _size_type_label(FashionSizeTypeSlug.WAIST)
    INSIDE_LEG = FashionSizeTypeSlug.INSIDE_LEG, _size_type_label(FashionSizeTypeSlug.INSIDE_LEG)
    COLLAR = FashionSizeTypeSlug.COLLAR, _size_type_label(FashionSizeTypeSlug.COLLAR)
