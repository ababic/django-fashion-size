"""Django fields for a size unit and a stored size."""

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


class SizeUnitFormField(forms.TypedChoiceField):
    """Choice field whose submitted value is a size-unit slug."""

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


class SizeUnitField(models.CharField):
    """Concrete size unit for an attribute (UK dress size, chest in centimetres, …).

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
        size_unit = self.to_python(value)
        if size_unit is None:
            return ""
        return size_unit.slug

    def pre_save(self, model_instance: models.Model, add: bool) -> str:
        size_unit = self.to_python(getattr(model_instance, self.attname))
        setattr(model_instance, self.attname, size_unit)
        return "" if size_unit is None else size_unit.slug

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
        kwargs["choices_form_class"] = SizeUnitFormField
        return super().formfield(**kwargs)


def _size_unit_field_path(path: str) -> str:
    """Normalise ``size_unit`` / ``attribute.size_unit`` / ``attribute__size_unit``."""
    normalized = str(path or "").strip().replace("__", ".")
    parts = normalized.split(".")
    if not parts or any(not part.isidentifier() for part in parts):
        raise ValueError(
            "size_unit_field must name a SizeUnitField on this model or a related model, "
            "for example 'size_unit' or 'attribute.size_unit'."
        )
    return ".".join(parts)


def resolve_size_unit(instance: models.Model, size_unit_field: str) -> SizeUnit | None:
    """Follow ``size_unit_field`` from ``instance``, including relations.

    Each step is an attribute lookup (``host.size_unit``). An empty step, a
    missing relation, or a blank size unit returns ``None``.
    """
    current: Any = instance
    for part in size_unit_field.split("."):
        if current is None:
            return None
        current = getattr(current, part)
    if isinstance(current, SizeUnit):
        return current
    if current is None or current == "":
        return None
    return parse_size_unit_slug(str(current))


def _format_length_token(raw: Any) -> str:
    """Exact length token. ``81.28`` stays ``81.28``; whole numbers drop the decimal."""
    text = format(raw, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def stored_size_token(value: Any) -> str:
    """Column text for a size: ``10``, ``7.5``, ``DD``, ``81.28``, or blank."""
    if isinstance(value, Size):
        raw = value.raw
        if isinstance(raw, str):
            return raw
        if value.size_unit.length_unit:
            return _format_length_token(raw)
        return format_raw(raw)
    if value is None:
        return ""
    return str(value).strip()


class SizeDescriptor(DeferredAttribute):
    """Read a stored token as a ``Size`` bound to ``size_unit_field``."""

    def __get__(self, instance: models.Model | None, cls: type | None = None) -> Any:
        if instance is None:
            return self
        raw = super().__get__(instance, cls)
        if isinstance(raw, Size):
            return raw
        if raw is None or raw == "":
            return None
        size_unit = resolve_size_unit(instance, self.field.size_unit_field)
        if size_unit is None:
            raise ValueError(f"Cannot read {self.field.name!r}: {self.field.size_unit_field!r} is empty.")
        return Size.from_raw(raw, size_unit)

    def __set__(self, instance: models.Model, value: Any) -> None:
        if isinstance(value, Size):
            size_unit = resolve_size_unit(instance, self.field.size_unit_field)
            if size_unit is not None and size_unit != value.size_unit:
                raise ValidationError(
                    f"{self.field.name} is {value.size_unit.label}, "
                    f"but {self.field.size_unit_field} is {size_unit.label}."
                )
            instance.__dict__[self.field.attname] = stored_size_token(value)
            return
        if value is None:
            instance.__dict__[self.field.attname] = ""
            return
        instance.__dict__[self.field.attname] = str(value).strip()


class SizeField(models.CharField):
    """Store a size token and expose a ``Size`` that can convert.

    ``size_unit_field`` names the ``SizeUnitField`` that says what the token
    means. It may live on this model (``size_unit``) or across relations
    (``attribute.size_unit``, or ``attribute__size_unit``). Reading the field
    returns a ``Size``; call ``.convert()`` on that value. Writing a
    ``Size``, a number, or a size token stores the raw token
    (``10``, ``7.5``, ``DD``).
    """

    def __init__(self, *args: Any, size_unit_field: str, **kwargs: Any) -> None:
        self.size_unit_field = _size_unit_field_path(size_unit_field)
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
        kwargs["size_unit_field"] = self.size_unit_field
        return name, path, args, kwargs

    def contribute_to_class(self, cls: type[models.Model], name: str, private_only: bool = False) -> None:
        super().contribute_to_class(cls, name, private_only=private_only)
        setattr(cls, name, SizeDescriptor(self))

    def from_db_value(self, value: str | None, expression: object, connection: object) -> str:
        if value is None:
            return ""
        return value

    def to_python(self, value: Any) -> str:
        if isinstance(value, Size):
            return stored_size_token(value)
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
        size_unit = resolve_size_unit(model_instance, self.size_unit_field)
        if size_unit is None:
            raise ValidationError(f"Set {self.size_unit_field} before storing a size.")
        try:
            token = stored_size_token(Size.from_raw(raw, size_unit))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValidationError(f"Invalid size {raw!r}.") from exc
        model_instance.__dict__[self.attname] = token
        return token

    def clean(self, value: Any, model_instance: models.Model) -> str:
        token = super().clean(value, model_instance)
        if not token:
            return ""
        size_unit = resolve_size_unit(model_instance, self.size_unit_field)
        if size_unit is None:
            raise ValidationError(f"Set {self.size_unit_field} before storing a size.")
        try:
            Size.from_raw(token, size_unit)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValidationError(f"Invalid size {token!r}.") from exc
        return token

    def formfield(self, **kwargs: Any) -> forms.Field:
        from django_fashion_size.widgets import SizeFormField, SizeValueWidget

        kwargs.setdefault("form_class", SizeFormField)
        kwargs.setdefault("widget", SizeValueWidget())
        form_class = kwargs["form_class"]
        if isinstance(form_class, type) and issubclass(form_class, SizeFormField):
            kwargs["size_unit_field"] = self.size_unit_field
        return super().formfield(**kwargs)
