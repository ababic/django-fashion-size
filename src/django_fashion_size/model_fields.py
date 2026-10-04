"""Django fields for a measurement identity and a stored measurement value."""

from __future__ import annotations

from decimal import InvalidOperation
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.query_utils import DeferredAttribute

from fashion_size.types import (
    SIZE_UNIT_BY_SLUG,
    Size,
    SizeUnit,
    format_raw,
    parse_size_unit_slug,
    size_unit_choices,
)

# One list so ``deconstruct`` can drop the default choices by identity.
SIZE_UNIT_CHOICES = size_unit_choices()


class MeasurementFormField(forms.TypedChoiceField):
    """Choice field whose submitted value is a measurement slug."""

    def prepare_value(self, value: Any) -> Any:
        # The widget matches option values (slugs). ``coerce`` is ``to_python``,
        # which returns a ``SizeUnit``; its string form is the label, so a
        # saved value would render as an unselected blank.
        if isinstance(value, SizeUnit):
            return value.slug
        prepared = super().prepare_value(value)
        if isinstance(prepared, SizeUnit):
            return prepared.slug
        return prepared


class MeasurementField(models.CharField):
    """Concrete measurement for an attribute (UK dress size, chest in centimetres, …).

    The column stores the size-unit slug. Reading the field returns the
    ``SizeUnit`` instance, or ``None`` when the attribute is not a convertible
    size. Assign a ``SizeUnit`` or its slug.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("max_length", 40)
        kwargs.setdefault("blank", True)
        kwargs.setdefault("default", "")
        kwargs.setdefault("choices", SIZE_UNIT_CHOICES)
        super().__init__(*args, **kwargs)

    def deconstruct(self) -> tuple[str, str, list[Any], dict[str, Any]]:
        name, path, args, kwargs = super().deconstruct()
        if kwargs.get("max_length") == 40:
            del kwargs["max_length"]
        if kwargs.get("blank") is True:
            del kwargs["blank"]
        if kwargs.get("default") == "":
            del kwargs["default"]
        if kwargs.get("choices") is SIZE_UNIT_CHOICES:
            del kwargs["choices"]
        return name, path, args, kwargs

    def from_db_value(self, value: str | None, expression: object, connection: object) -> SizeUnit | None:
        return self.to_python(value)

    def to_python(self, value: Any) -> SizeUnit | None:
        if isinstance(value, SizeUnit) or value is None or value == "":
            return value or None
        slug = str(value).strip().lower()
        try:
            return SIZE_UNIT_BY_SLUG[slug]
        except KeyError as exc:
            raise ValidationError(f"Unknown size unit {value!r}.") from exc

    def get_prep_value(self, value: Any) -> str:
        measurement = self.to_python(value)
        if measurement is None:
            return ""
        return measurement.slug

    def pre_save(self, model_instance: models.Model, add: bool) -> str:
        measurement = self.to_python(getattr(model_instance, self.attname))
        setattr(model_instance, self.attname, measurement)
        return "" if measurement is None else measurement.slug

    def _slug_for_validation(self, value: Any) -> str:
        if isinstance(value, SizeUnit):
            return value.slug
        if value is None:
            return ""
        return str(value)

    def validate(self, value: Any, model_instance: models.Model) -> None:
        super().validate(self._slug_for_validation(value), model_instance)

    def run_validators(self, value: Any) -> None:
        super().run_validators(self._slug_for_validation(value))

    def formfield(self, **kwargs: Any) -> forms.Field:
        # Choice fields ignore ``form_class`` and fall back to TypedChoiceField
        # unless ``choices_form_class`` is set.
        kwargs["choices_form_class"] = MeasurementFormField
        return super().formfield(**kwargs)


def _measurement_field_path(path: str) -> str:
    """Normalise ``measurement`` / ``attribute.measurement`` / ``attribute__measurement``."""
    normalized = str(path or "").strip().replace("__", ".")
    parts = normalized.split(".")
    if not parts or any(not part.isidentifier() for part in parts):
        raise ValueError(
            "measurement_field must name a MeasurementField on this model or a related model, "
            "for example 'measurement' or 'attribute.measurement'."
        )
    return ".".join(parts)


def resolve_measurement(instance: models.Model, measurement_field: str) -> SizeUnit | None:
    """Follow ``measurement_field`` from ``instance``, including relations.

    Each step is an attribute lookup (``host.measurement``). An empty step, a
    missing relation, or a blank measurement returns ``None``.
    """
    current: Any = instance
    for part in measurement_field.split("."):
        if current is None:
            return None
        current = getattr(current, part)
    if isinstance(current, SizeUnit):
        return current
    if current is None or current == "":
        return None
    return parse_size_unit_slug(str(current))


def stored_measurement_token(value: Any) -> str:
    """Column text for a measurement value: ``10``, ``7.5``, ``DD``, or blank."""
    if isinstance(value, Size):
        raw = value.raw
        if isinstance(raw, str):
            return raw
        return format_raw(raw)
    if value is None:
        return ""
    return str(value).strip()


class MeasurementValueDescriptor(DeferredAttribute):
    """Read a stored token as a ``Size`` bound to ``measurement_field``."""

    def __get__(self, instance: models.Model | None, cls: type | None = None) -> Any:
        if instance is None:
            return self
        raw = super().__get__(instance, cls)
        if isinstance(raw, Size):
            return raw
        if raw is None or raw == "":
            return None
        measurement = resolve_measurement(instance, self.field.measurement_field)
        if measurement is None:
            raise ValueError(f"Cannot read {self.field.name!r}: {self.field.measurement_field!r} is empty.")
        return Size.from_raw(raw, measurement)

    def __set__(self, instance: models.Model, value: Any) -> None:
        if isinstance(value, Size):
            measurement = resolve_measurement(instance, self.field.measurement_field)
            if measurement is not None and measurement != value.size_unit:
                raise ValidationError(
                    f"{self.field.name} is {value.size_unit.label}, "
                    f"but {self.field.measurement_field} is {measurement.label}."
                )
            instance.__dict__[self.field.attname] = stored_measurement_token(value)
            return
        if value is None:
            instance.__dict__[self.field.attname] = ""
            return
        instance.__dict__[self.field.attname] = str(value).strip()


class MeasurementValueField(models.CharField):
    """Store a size token and expose a ``Size`` that can convert.

    ``measurement_field`` names the ``MeasurementField`` that says what the token
    means. It may live on this model (``measurement``) or across relations
    (``attribute.measurement``, or ``attribute__measurement``). Reading the field
    returns a ``Size``; call ``.convert()`` on that value. Writing a
    ``Size``, a number, or a size token stores the raw token
    (``10``, ``7.5``, ``DD``).
    """

    def __init__(self, *args: Any, measurement_field: str, **kwargs: Any) -> None:
        self.measurement_field = _measurement_field_path(measurement_field)
        kwargs.setdefault("max_length", 32)
        kwargs.setdefault("blank", True)
        kwargs.setdefault("default", "")
        super().__init__(*args, **kwargs)

    def deconstruct(self) -> tuple[str, str, list[Any], dict[str, Any]]:
        name, path, args, kwargs = super().deconstruct()
        if kwargs.get("max_length") == 32:
            del kwargs["max_length"]
        if kwargs.get("blank") is True:
            del kwargs["blank"]
        if kwargs.get("default") == "":
            del kwargs["default"]
        kwargs["measurement_field"] = self.measurement_field
        return name, path, args, kwargs

    def contribute_to_class(self, cls: type[models.Model], name: str, private_only: bool = False) -> None:
        super().contribute_to_class(cls, name, private_only=private_only)
        setattr(cls, name, MeasurementValueDescriptor(self))

    def from_db_value(self, value: str | None, expression: object, connection: object) -> str:
        if value is None:
            return ""
        return value

    def to_python(self, value: Any) -> str:
        if isinstance(value, Size):
            return stored_measurement_token(value)
        if value is None:
            return ""
        return str(value).strip()

    def get_prep_value(self, value: Any) -> str:
        return self.to_python(value)

    def value_from_object(self, obj: models.Model) -> str:
        """Form widgets need the stored token, not the converted ``Size``."""
        raw = obj.__dict__.get(self.attname, "")
        return "" if raw is None else self.to_python(raw)

    def pre_save(self, model_instance: models.Model, add: bool) -> str:
        raw = model_instance.__dict__.get(self.attname, "")
        if raw in (None, ""):
            model_instance.__dict__[self.attname] = ""
            return ""
        measurement = resolve_measurement(model_instance, self.measurement_field)
        if measurement is None:
            raise ValidationError(f"Set {self.measurement_field} before storing a measurement value.")
        try:
            token = stored_measurement_token(Size.from_raw(raw, measurement))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValidationError(f"Invalid measurement value {raw!r}.") from exc
        model_instance.__dict__[self.attname] = token
        return token

    def clean(self, value: Any, model_instance: models.Model) -> str:
        token = super().clean(value, model_instance)
        if not token:
            return ""
        measurement = resolve_measurement(model_instance, self.measurement_field)
        if measurement is None:
            raise ValidationError(f"Set {self.measurement_field} before storing a measurement value.")
        try:
            Size.from_raw(token, measurement)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValidationError(f"Invalid measurement value {token!r}.") from exc
        return token
