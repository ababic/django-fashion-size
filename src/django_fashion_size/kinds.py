"""Django choices for size types and product types.

Values stay aligned with ``fashion_size``. Product-type labels are
``gettext_lazy`` strings so ``makemessages`` can collect them.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from fashion_size.product_types import ProductType as FashionSizeProductType
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


class FashionProductType(models.TextChoices):
    """Product ranges that can have their own brand conversion chart.

    Values match ``fashion_size.product_types.ProductType``. Labels are
    marked for translation so forms can show them in the active language.
    """

    JEANS = FashionSizeProductType.JEANS, _("Jeans")
    TROUSERS = FashionSizeProductType.TROUSERS, _("Trousers")
    SHIRTS = FashionSizeProductType.SHIRTS, _("Shirts")
    DRESS_SHIRTS = FashionSizeProductType.DRESS_SHIRTS, _("Dress Shirts")
    SUITS = FashionSizeProductType.SUITS, _("Suits")
    SUIT_JACKETS = FashionSizeProductType.SUIT_JACKETS, _("Suit Jackets")
    DRESSES = FashionSizeProductType.DRESSES, _("Dresses")
    UNDERWEAR = FashionSizeProductType.UNDERWEAR, _("Underwear")
    CASUAL_TOPS = FashionSizeProductType.CASUAL_TOPS, _("Casual Tops")
    KNITWEAR = FashionSizeProductType.KNITWEAR, _("Knitwear")
    SHOES = FashionSizeProductType.SHOES, _("Shoes")
    BOOTS = FashionSizeProductType.BOOTS, _("Boots")
    TRAINERS = FashionSizeProductType.TRAINERS, _("Trainers")
    ACTIVEWEAR_TOPS = FashionSizeProductType.ACTIVEWEAR_TOPS, _("Activewear Tops")
    ACTIVEWEAR_BOTTOMS = FashionSizeProductType.ACTIVEWEAR_BOTTOMS, _("Activewear Bottoms")
