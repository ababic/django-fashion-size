"""Django choices for size types, size units, and product types.

Values stay aligned with ``fashion_size``. Labels are ``gettext_lazy``
strings so ``makemessages`` can collect them and forms can show them in
the active language.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from fashion_size.product_types import ProductType as FashionSizeProductType
from fashion_size.size_types import SizeTypeSlug as FashionSizeTypeSlug


class SizeTypeSlug(models.TextChoices):
    """Fine-grained size types that can be bound to catalog attributes.

    Values match ``fashion_size.size_types.SizeTypeSlug``. Labels are
    marked for translation so a ``SizeTypeField`` select can show them
    in the active language.
    """

    DRESS = FashionSizeTypeSlug.DRESS, _("Dress size")
    ADULT_SHOE = FashionSizeTypeSlug.ADULT_SHOE, _("Adult shoe size")
    KIDS_SHOE = FashionSizeTypeSlug.KIDS_SHOE, _("Kids shoe size")
    BABY_SHOE = FashionSizeTypeSlug.BABY_SHOE, _("Baby shoe size")
    CUP_SIZE = FashionSizeTypeSlug.CUP_SIZE, _("Cup size")
    BAND_SIZE = FashionSizeTypeSlug.BAND_SIZE, _("Band size")
    WAIST_SIZE = FashionSizeTypeSlug.WAIST_SIZE, _("Waist size")
    CHEST_SIZE = FashionSizeTypeSlug.CHEST_SIZE, _("Chest size")
    CHEST = FashionSizeTypeSlug.CHEST, _("Chest")
    WAIST = FashionSizeTypeSlug.WAIST, _("Waist")
    INSIDE_LEG = FashionSizeTypeSlug.INSIDE_LEG, _("Inside leg")
    COLLAR = FashionSizeTypeSlug.COLLAR, _("Collar")


class SizeUnitSlug(models.TextChoices):
    """Concrete size units (UK dress size, chest in centimetres, …).

    Values match ``fashion_size`` size-unit slugs. Labels are marked for
    translation so a ``SizeUnitField`` select can show them in the active
    language.
    """

    UK_DRESS_SIZE = "uk-dress-size", _("UK Dress size")
    EU_DRESS_SIZE = "eu-dress-size", _("EU Dress size")
    US_DRESS_SIZE = "us-dress-size", _("US Dress size")
    AU_DRESS_SIZE = "au-dress-size", _("AU Dress size")
    UK_ADULT_SHOE_SIZE = "uk-adult-shoe-size", _("UK Adult shoe size")
    EU_ADULT_SHOE_SIZE = "eu-adult-shoe-size", _("EU Adult shoe size")
    US_ADULT_SHOE_SIZE = "us-adult-shoe-size", _("US Adult shoe size")
    AU_ADULT_SHOE_SIZE = "au-adult-shoe-size", _("AU Adult shoe size")
    UK_KIDS_SHOE_SIZE = "uk-kids-shoe-size", _("UK Kids shoe size")
    EU_KIDS_SHOE_SIZE = "eu-kids-shoe-size", _("EU Kids shoe size")
    US_KIDS_SHOE_SIZE = "us-kids-shoe-size", _("US Kids shoe size")
    AU_KIDS_SHOE_SIZE = "au-kids-shoe-size", _("AU Kids shoe size")
    UK_BABY_SHOE_SIZE = "uk-baby-shoe-size", _("UK Baby shoe size")
    EU_BABY_SHOE_SIZE = "eu-baby-shoe-size", _("EU Baby shoe size")
    US_BABY_SHOE_SIZE = "us-baby-shoe-size", _("US Baby shoe size")
    AU_BABY_SHOE_SIZE = "au-baby-shoe-size", _("AU Baby shoe size")
    UK_CUP_SIZE = "uk-cup-size", _("UK Cup size")
    EU_CUP_SIZE = "eu-cup-size", _("EU Cup size")
    US_CUP_SIZE = "us-cup-size", _("US Cup size")
    AU_CUP_SIZE = "au-cup-size", _("AU Cup size")
    UK_BAND_SIZE = "uk-band-size", _("UK Band size")
    EU_BAND_SIZE = "eu-band-size", _("EU Band size")
    US_BAND_SIZE = "us-band-size", _("US Band size")
    AU_BAND_SIZE = "au-band-size", _("AU Band size")
    FR_BAND_SIZE = "fr-band-size", _("FR Band size")
    UK_WAIST_SIZE = "uk-waist-size", _("UK Waist size")
    EU_WAIST_SIZE = "eu-waist-size", _("EU Waist size")
    US_WAIST_SIZE = "us-waist-size", _("US Waist size")
    AU_WAIST_SIZE = "au-waist-size", _("AU Waist size")
    UK_CHEST_SIZE = "uk-chest-size", _("UK Chest size")
    EU_CHEST_SIZE = "eu-chest-size", _("EU Chest size")
    US_CHEST_SIZE = "us-chest-size", _("US Chest size")
    AU_CHEST_SIZE = "au-chest-size", _("AU Chest size")
    IN_CHEST_SIZE = "in-chest-size", _("Chest (inches)")
    CM_CHEST_SIZE = "cm-chest-size", _("Chest (centimetres)")
    IN_WAIST_SIZE = "in-waist-size", _("Waist (inches)")
    CM_WAIST_SIZE = "cm-waist-size", _("Waist (centimetres)")
    IN_INSIDE_LEG = "in-inside-leg", _("Inside leg (inches)")
    CM_INSIDE_LEG = "cm-inside-leg", _("Inside leg (centimetres)")
    IN_COLLAR_SIZE = "in-collar-size", _("Collar (inches)")
    CM_COLLAR_SIZE = "cm-collar-size", _("Collar (centimetres)")


class FashionProductType(models.TextChoices):
    """Product ranges that can have their own brand conversion chart.

    Values match ``fashion_size.product_types.ProductType``. Labels are
    marked for translation so forms can show them in the active language.
    """

    JEANS = FashionSizeProductType.JEANS, _("Jeans")
    TROUSERS = FashionSizeProductType.TROUSERS, _("Trousers")
    SHORTS = FashionSizeProductType.SHORTS, _("Shorts")
    SHIRTS = FashionSizeProductType.SHIRTS, _("Shirts")
    DRESS_SHIRTS = FashionSizeProductType.DRESS_SHIRTS, _("Dress Shirts")
    SUITS = FashionSizeProductType.SUITS, _("Suits & Tailoring")
    DRESSES = FashionSizeProductType.DRESSES, _("Dresses")
    SKIRTS = FashionSizeProductType.SKIRTS, _("Skirts")
    UNDERWEAR = FashionSizeProductType.UNDERWEAR, _("Underwear")
    BRAS = FashionSizeProductType.BRAS, _("Bras")
    SWIMWEAR = FashionSizeProductType.SWIMWEAR, _("Swimwear")
    NIGHTWEAR = FashionSizeProductType.NIGHTWEAR, _("Nightwear")
    HOSIERY = FashionSizeProductType.HOSIERY, _("Hosiery")
    CASUAL_TOPS = FashionSizeProductType.CASUAL_TOPS, _("Casual Tops")
    CASUAL_BOTTOMS = FashionSizeProductType.CASUAL_BOTTOMS, _("Casual Bottoms")
    KNITWEAR = FashionSizeProductType.KNITWEAR, _("Knitwear")
    OUTERWEAR = FashionSizeProductType.OUTERWEAR, _("Outerwear")
    SHOES = FashionSizeProductType.SHOES, _("Shoes")
    BOOTS = FashionSizeProductType.BOOTS, _("Boots")
    TRAINERS = FashionSizeProductType.TRAINERS, _("Trainers")
    ACTIVEWEAR_TOPS = FashionSizeProductType.ACTIVEWEAR_TOPS, _("Activewear Tops")
    ACTIVEWEAR_BOTTOMS = (
        FashionSizeProductType.ACTIVEWEAR_BOTTOMS,
        _("Activewear Bottoms"),
    )
