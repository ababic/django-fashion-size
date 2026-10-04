"""Django fields for fashion measurements.

``MeasurementField`` stores a size-unit slug and returns a ``SizeUnit``.
``MeasurementValueField`` stores a size token and returns a ``Size``.
The measurements themselves live in ``fashion-size``.
"""

from django_fashion_size.kinds import MeasurementKindSlug
from django_fashion_size.model_fields import MeasurementField, MeasurementFormField, MeasurementValueField

__all__ = [
    "MeasurementField",
    "MeasurementFormField",
    "MeasurementKindSlug",
    "MeasurementValueField",
]
