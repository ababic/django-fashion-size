"""Django fields for fashion measurements.

``MeasurementField`` stores a measurement slug and returns a ``Measurement``.
``MeasurementValueField`` stores a size token and returns a ``MeasurementValue``.
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
