"""Django fields for fashion sizes.

``SizeUnitField`` stores a size-unit slug and returns a ``SizeUnit``.
``SizeField`` stores a size token and returns a ``Size``.
``FashionProductTypeField`` stores a product-type slug and returns a
``ProductType``, or ``None`` when the value is blank or unknown; its form
control always offers ``FashionProductType`` options.
The size types and charts live in ``fashion-size``.

Importing this package registers Django's active language with
``fashion-size`` and points ``Size.display`` at that language. Lengths then
render as ``32"`` / ``81cm`` in English and ``32 in`` / ``81 cm`` otherwise.
"""

from django.utils.translation import get_language
from fashion_size import register_display_language
from fashion_size.types import Size

from django_fashion_size.kinds import FashionProductType, SizeTypeSlug
from django_fashion_size.model_fields import (
    FashionProductTypeField,
    FashionProductTypeFormField,
    SizeField,
    SizeUnitField,
    SizeUnitFormField,
)
from django_fashion_size.widgets import SizeFormField, SizeValueWidget


def _display_for_active_language(size: Size) -> str:
    """Format with Django's active language, falling back to ``en-gb``."""
    return size.localised_display()


Size.display = _display_for_active_language
register_display_language(get_language)

__all__ = [
    "FashionProductType",
    "FashionProductTypeField",
    "FashionProductTypeFormField",
    "SizeField",
    "SizeFormField",
    "SizeTypeSlug",
    "SizeUnitField",
    "SizeUnitFormField",
    "SizeValueWidget",
]
