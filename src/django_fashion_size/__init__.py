"""Django fields for fashion sizes.

``SizeTypeField`` stores a size-type slug and returns a ``SizeType``.
``SizeUnitField`` stores a size-unit slug and returns a ``SizeUnit``.
``SizeField`` stores a size token and returns a ``Size``.
``FashionProductTypeField`` stores a product-type slug and returns a
``ProductType``, or ``None`` when the value is blank or unknown; its form
control always offers ``FashionProductType`` options.
The size types and charts live in ``fashion-size``.

Importing this package registers Django's active language with
``fashion-size`` and points ``Size.display`` at that language. Lengths then
render as ``32"`` / ``81cm`` in English and ``32 in`` / ``81 cm`` otherwise.
Waist sizes stay a separate size type (regional charts do not convert like a
length). Display still shows each region's number as a measurement: UK, US,
and AU as inches (``30"``), EU as centimetres (``46cm``).
"""

from decimal import Decimal

from django.utils.translation import get_language
from fashion_size import register_display_language
from fashion_size.types import Size, SizeFamily, format_length_for_language

from django_fashion_size.kinds import FashionProductType, SizeTypeSlug, SizeUnitSlug
from django_fashion_size.model_fields import (
    FashionProductTypeField,
    FashionProductTypeFormField,
    SizeField,
    SizeTypeField,
    SizeTypeFormField,
    SizeUnitField,
    SizeUnitFormField,
)
from django_fashion_size.widgets import SizeFormField, SizeValueWidget

# Waist-size charts convert by region, but each region's number is a measurement.
# UK, US, and AU are inches on every waist chart. EU is centimetres.
_WAIST_SIZE_DISPLAY_UNIT = {"uk": "in", "us": "in", "au": "in", "eu": "cm"}

_fashion_localised_display = Size.localised_display


def _waist_size_display_unit(size: Size) -> str | None:
    """``in`` or ``cm`` when this waist size should render as a length."""
    if size.size_unit.size_type.family != SizeFamily.WAIST_SIZE:
        return None
    if not isinstance(size.raw, Decimal):
        return None
    return _WAIST_SIZE_DISPLAY_UNIT.get(size.size_unit.locale.value)


def _localised_display(size: Size, locale: str | None = None) -> str:
    """Length-style waist display, otherwise fashion-size's own formatter."""
    length_unit = _waist_size_display_unit(size)
    if length_unit is not None:
        return format_length_for_language(size.raw, length_unit, locale)
    return _fashion_localised_display(size, locale)


def _display_for_active_language(size: Size) -> str:
    """Format with Django's active language, falling back to ``en-gb``."""
    return _localised_display(size)


Size.localised_display = _localised_display
Size.display = _display_for_active_language
register_display_language(get_language)

__all__ = [
    "FashionProductType",
    "FashionProductTypeField",
    "FashionProductTypeFormField",
    "SizeField",
    "SizeFormField",
    "SizeTypeField",
    "SizeTypeFormField",
    "SizeTypeSlug",
    "SizeUnitField",
    "SizeUnitFormField",
    "SizeUnitSlug",
    "SizeValueWidget",
]
