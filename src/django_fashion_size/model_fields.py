"""Django fields for a size type, a size unit, and a stored size."""

from __future__ import annotations

from decimal import InvalidOperation
from typing import Any, Self

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.fields import BLANK_CHOICE_DASH
from django.db.models.query_utils import DeferredAttribute
from django.utils.translation import gettext_lazy as _
from fashion_size.product_types import ProductType, resolve_product_type
from fashion_size.types import (
    SIZE_TYPE_BY_SLUG,
    SIZE_UNIT_BY_SLUG,
    Size,
    SizeType,
    SizeUnit,
    format_raw,
    parse_size_unit_slug,
)

from django_fashion_size.kinds import FashionProductType, SizeTypeSlug, SizeUnitSlug

# Stored slug for an opted-in Custom size unit. Not a fashion-size chart unit.
CUSTOM_SIZE_UNIT_SLUG = "custom"


class CustomSizeUnit:
    """The ``custom`` size unit. It is stored as a slug and cannot convert.

    ``SizeUnitField(allow_custom=True)`` reads that slug as this object.
    The default field does not accept it. There is one shared instance, so
    ``CustomSizeUnit() is CustomSizeUnit()``.
    """

    slug = CUSTOM_SIZE_UNIT_SLUG

    def __new__(cls) -> Self:
        instance = getattr(cls, "_instance", None)
        if instance is None:
            instance = super().__new__(cls)
            cls._instance = instance
        return instance

    @property
    def label(self) -> str:
        return str(_("Custom"))

    def can_convert_to(self, other: object) -> bool:
        return False

    def __getattr__(self, name: str) -> Any:
        if name in {
            "size_type",
            "locale",
            "length_unit",
            "display_prefix",
            "display_suffix",
            "supports_brand_overrides",
        }:
            raise TypeError("Custom sizes cannot be converted.")
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CustomSizeUnit)

    def __hash__(self) -> int:
        return hash(self.slug)

    def __str__(self) -> str:
        return self.label

    def __repr__(self) -> str:
        return "CustomSizeUnit()"


CUSTOM_SIZE_UNIT = CustomSizeUnit()


def _translated_choices(
    kind: type[models.TextChoices], *, include_blank: bool
) -> list[tuple[str, str]]:
    """Slug/label pairs from a ``TextChoices`` enum. Labels stay lazy."""
    choices = list(kind.choices)
    if include_blank:
        return [*BLANK_CHOICE_DASH, *choices]
    return choices


class SizeUnitFormField(forms.TypedChoiceField):
    """Choice field whose submitted value is a size-unit slug.

    Options come from ``SizeUnitSlug``. Their labels are ``gettext_lazy``
    strings. ``allow_custom`` adds a Custom option; ``SizeUnitField`` passes
    its own ``allow_custom`` through, and that defaults to false. ``coerce``
    is the model field's ``to_python``, so a posted slug becomes a
    ``SizeUnit`` or ``CustomSizeUnit`` and the column still stores the slug.
    """

    def __init__(self, *, allow_custom: bool = False, **kwargs: Any) -> None:
        # Set before ``choices`` is assigned. The setter reads this flag.
        self.allow_custom = allow_custom
        super().__init__(**kwargs)

    def prepare_value(self, value: Any) -> Any:
        # The widget matches option values (slugs). ``coerce`` is ``to_python``,
        # which returns a ``SizeUnit``; its string form is the label, so a
        # saved value would render as an unselected blank.
        if isinstance(value, CustomSizeUnit):
            return value.slug
        if isinstance(value, SizeUnit):
            return value.slug
        prepared = super().prepare_value(value)
        if isinstance(prepared, CustomSizeUnit):
            return prepared.slug
        if isinstance(prepared, SizeUnit):
            return prepared.slug
        return prepared

    @forms.ChoiceField.choices.setter
    def choices(self, _value: Any) -> None:
        include_blank = not getattr(self, "required", True)
        choices = _translated_choices(SizeUnitSlug, include_blank=include_blank)
        if getattr(self, "allow_custom", False):
            choices = [*choices, (CUSTOM_SIZE_UNIT_SLUG, _("Custom"))]
        self._choices = self.widget.choices = choices


def _size_unit_form_field(allow_custom: bool) -> type[SizeUnitFormField]:
    """``SizeUnitFormField`` that is constructed with this ``allow_custom``."""

    class _Field(SizeUnitFormField):
        def __init__(self, **kwargs: Any) -> None:
            kwargs["allow_custom"] = allow_custom
            super().__init__(**kwargs)

    _Field.__name__ = SizeUnitFormField.__name__
    _Field.__qualname__ = SizeUnitFormField.__qualname__
    return _Field


class SizeUnitField(models.CharField):
    """Concrete size unit for an attribute (UK dress size, chest in centimetres, …).

    The column stores the size-unit slug. Reading the field returns the
    ``SizeUnit`` instance, or ``None`` when the attribute is not a convertible
    size. Assign a ``SizeUnit`` or its slug. The select uses ``SizeUnitSlug``
    labels.

    ``allow_custom`` defaults to false. Set it to add a Custom option. That
    option is stored as the slug ``custom`` and reads back as a
    ``CustomSizeUnit``, which cannot be used in conversion.
    """

    # Changing the flag does not change the column.
    non_db_attrs = (*models.CharField.non_db_attrs, "allow_custom")

    def __init__(self, *args: Any, allow_custom: bool = False, **kwargs: Any) -> None:
        self.allow_custom = allow_custom
        kwargs.pop("choices", None)
        kwargs.setdefault("max_length", 40)
        kwargs.setdefault("blank", True)
        kwargs.setdefault("default", "")
        choices = list(SizeUnitSlug.choices)
        if allow_custom:
            choices.append((CUSTOM_SIZE_UNIT_SLUG, _("Custom")))
        kwargs["choices"] = choices
        super().__init__(*args, **kwargs)

    def deconstruct(self) -> tuple[str, str, list[Any], dict[str, Any]]:
        name, path, args, kwargs = super().deconstruct()
        if kwargs.get("max_length") == 40:
            del kwargs["max_length"]
        if kwargs.get("blank") is True:
            del kwargs["blank"]
        if kwargs.get("default") == "":
            del kwargs["default"]
        # Labels are translated at render time. Migrations do not store them.
        expected = list(SizeUnitSlug.choices)
        if self.allow_custom:
            expected.append((CUSTOM_SIZE_UNIT_SLUG, _("Custom")))
            kwargs["allow_custom"] = True
        if kwargs.get("choices") == expected:
            del kwargs["choices"]
        return name, path, args, kwargs

    def from_db_value(
        self, value: str | None, expression: object, connection: object
    ) -> SizeUnit | None:
        return self.to_python(value)

    def to_python(self, value: Any) -> SizeUnit | CustomSizeUnit | None:
        if isinstance(value, CustomSizeUnit):
            if not self.allow_custom:
                raise ValidationError(f"Unknown size unit {CUSTOM_SIZE_UNIT_SLUG!r}.")
            return CUSTOM_SIZE_UNIT
        if isinstance(value, SizeUnit) or value is None or value == "":
            return value or None
        slug = str(value).strip().lower()
        if slug == CUSTOM_SIZE_UNIT_SLUG:
            if not self.allow_custom:
                raise ValidationError(f"Unknown size unit {value!r}.")
            return CUSTOM_SIZE_UNIT
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
        if isinstance(value, (SizeUnit, CustomSizeUnit)):
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
        # unless ``choices_form_class`` is set. Django also drops kwargs it does
        # not know, so ``allow_custom`` is given to the form field's constructor
        # rather than left in ``kwargs``.
        allow_custom = kwargs.pop("allow_custom", self.allow_custom)
        kwargs["choices_form_class"] = _size_unit_form_field(allow_custom)
        return super().formfield(**kwargs)


class SizeTypeFormField(forms.TypedChoiceField):
    """Choice field whose submitted value is a size-type slug.

    Options always come from ``SizeTypeSlug``. Their labels are
    ``gettext_lazy`` strings. ``coerce`` is the model field's
    ``to_python``, so a posted slug becomes a ``SizeType`` and the column
    still stores the slug.
    """

    def prepare_value(self, value: Any) -> Any:
        # The widget matches option values (slugs). ``coerce`` is ``to_python``,
        # which returns a ``SizeType``; its string form is the label, so a
        # saved value would render as an unselected blank.
        if isinstance(value, SizeType):
            return str(value.slug)
        prepared = super().prepare_value(value)
        if isinstance(prepared, SizeType):
            return str(prepared.slug)
        return prepared

    @forms.ChoiceField.choices.setter
    def choices(self, _value: Any) -> None:
        include_blank = not getattr(self, "required", True)
        choices = _translated_choices(SizeTypeSlug, include_blank=include_blank)
        self._choices = self.widget.choices = choices


class SizeTypeField(models.CharField):
    """Size type for an attribute (dress size, adult shoe size, chest, …).

    The column stores the size-type slug (``dress``, ``adult-shoe``). Reading
    the field returns the ``SizeType`` instance, or ``None`` when the column
    is blank. Assign a ``SizeType`` or its slug. The select uses
    ``SizeTypeSlug`` labels. Each stored size still uses ``SizeUnitField``
    and ``SizeField`` for the unit and raw token.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("choices", None)
        kwargs.setdefault("max_length", 40)
        kwargs.setdefault("blank", True)
        kwargs.setdefault("default", "")
        kwargs["choices"] = list(SizeTypeSlug.choices)
        super().__init__(*args, **kwargs)

    def deconstruct(self) -> tuple[str, str, list[Any], dict[str, Any]]:
        name, path, args, kwargs = super().deconstruct()
        if kwargs.get("max_length") == 40:
            del kwargs["max_length"]
        if kwargs.get("blank") is True:
            del kwargs["blank"]
        elif self.blank is False:
            # CharField omits blank=False. This field defaults to blank=True,
            # so a required field has to say so in the migration.
            kwargs["blank"] = False
        if kwargs.get("default") == "":
            del kwargs["default"]
        # Labels are translated at render time. Migrations do not store them.
        if kwargs.get("choices") == list(SizeTypeSlug.choices):
            del kwargs["choices"]
        return name, path, args, kwargs

    def from_db_value(
        self, value: str | None, expression: object, connection: object
    ) -> SizeType | None:
        return self.to_python(value)

    def to_python(self, value: Any) -> SizeType | None:
        if isinstance(value, SizeType) or value is None or value == "":
            return value or None
        slug = str(value).strip().lower()
        try:
            return SIZE_TYPE_BY_SLUG[slug]
        except KeyError as exc:
            raise ValidationError(f"Unknown size type {value!r}.") from exc

    def get_prep_value(self, value: Any) -> str:
        size_type = self.to_python(value)
        if size_type is None:
            return ""
        return str(size_type.slug)

    def pre_save(self, model_instance: models.Model, add: bool) -> str:
        size_type = self.to_python(getattr(model_instance, self.attname))
        setattr(model_instance, self.attname, size_type)
        return "" if size_type is None else str(size_type.slug)

    def _slug_for_validation(self, value: Any) -> str:
        if isinstance(value, SizeType):
            return str(value.slug)
        if value is None:
            return ""
        return str(value).strip().lower()

    def validate(self, value: Any, model_instance: models.Model) -> None:
        super().validate(self._slug_for_validation(value), model_instance)

    def run_validators(self, value: Any) -> None:
        super().run_validators(self._slug_for_validation(value))

    def formfield(self, **kwargs: Any) -> forms.Field:
        kwargs["choices_form_class"] = SizeTypeFormField
        return super().formfield(**kwargs)


def product_type_choices(*, include_blank: bool = False) -> list[tuple[str, str]]:
    """``(slug, label)`` pairs from ``FashionProductType`` — usable as form ``choices``."""
    choices = list(FashionProductType.choices)
    if include_blank:
        return [*BLANK_CHOICE_DASH, *choices]
    return choices


class FashionProductTypeFormField(forms.ChoiceField):
    """Select whose options always follow ``FashionProductType``.

    Callers cannot replace the option list: ``choices`` is rebuilt from
    ``FashionProductType`` whenever it is set. Labels are translatable.
    A blank option is included when the field is not required. The posted
    value is the product-type slug.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("choices", None)
        kwargs.pop("coerce", None)
        kwargs.pop("empty_value", None)
        kwargs.pop("max_length", None)
        super().__init__(*args, **kwargs)

    def prepare_value(self, value: Any) -> Any:
        if isinstance(value, ProductType):
            return value.value
        prepared = super().prepare_value(value)
        if isinstance(prepared, ProductType):
            return prepared.value
        return prepared

    @forms.ChoiceField.choices.setter
    def choices(self, _value: Any) -> None:
        include_blank = not getattr(self, "required", True)
        choices = product_type_choices(include_blank=include_blank)
        self._choices = self.widget.choices = choices


# Longer than any current ``ProductType`` slug (``activewear-bottoms`` is 19).
# Kept in ``deconstruct`` so the VARCHAR constraint is explicit in migrations.
PRODUCT_TYPE_MAX_LENGTH = 64


class FashionProductTypeField(models.CharField):
    """Product-type slug stored as text.

    The column stores the slug. Reading the field returns a
    ``fashion_size.product_types.ProductType``, or ``None`` when the value
    is blank or not a known product type. ``clean`` / ``full_clean`` reject
    values that ``fashion_size`` cannot resolve. Forms use
    ``FashionProductTypeFormField``, whose options always come from
    ``FashionProductType``. Passed ``choices`` are ignored so a stale list
    cannot replace the current product types. ``max_length`` defaults to 64
    and is always deconstructed, because it is a database column constraint.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("choices", None)
        kwargs.setdefault("max_length", PRODUCT_TYPE_MAX_LENGTH)
        super().__init__(*args, **kwargs)

    def deconstruct(self) -> tuple[str, str, list[Any], dict[str, Any]]:
        name, path, args, kwargs = super().deconstruct()
        kwargs.pop("choices", None)
        return name, path, args, kwargs

    def from_db_value(
        self, value: str | None, expression: object, connection: object
    ) -> ProductType | None:
        return self.to_python(value)

    def to_python(self, value: Any) -> ProductType | None:
        if isinstance(value, ProductType) or value is None or value == "":
            return value or None
        try:
            return resolve_product_type(value)
        except ValueError:
            return None

    def get_prep_value(self, value: Any) -> str:
        product_type = self.to_python(value)
        return "" if product_type is None else product_type.value

    def pre_save(self, model_instance: models.Model, add: bool) -> str:
        product_type = self.to_python(getattr(model_instance, self.attname))
        setattr(model_instance, self.attname, product_type)
        return "" if product_type is None else product_type.value

    def _slug_for_validation(self, value: Any) -> str:
        if isinstance(value, ProductType):
            return value.value
        if value is None:
            return ""
        return str(value).strip().lower()

    def _validate_known_product_type(self, value: Any) -> None:
        slug = self._slug_for_validation(value)
        if not slug:
            return
        try:
            resolve_product_type(slug)
        except ValueError:
            raise ValidationError(
                self.error_messages["invalid_choice"],
                code="invalid_choice",
                params={"value": value},
            ) from None

    def validate(self, value: Any, model_instance: models.Model) -> None:
        self._validate_known_product_type(value)
        super().validate(self._slug_for_validation(value), model_instance)

    def clean(self, value: Any, model_instance: models.Model) -> ProductType | None:
        # ``to_python`` maps unknown slugs to ``None``; check first so
        # ``full_clean`` fails instead of treating them as blank.
        self._validate_known_product_type(value)
        return super().clean(value, model_instance)

    def formfield(self, **kwargs: Any) -> forms.Field:
        kwargs.setdefault("form_class", FashionProductTypeFormField)
        # Django admin walks the field MRO and applies CharField's
        # AdminTextInputWidget. That would replace the select, so drop
        # text inputs and keep an explicit choice widget.
        widget = kwargs.get("widget")
        if widget is not None:
            widget_class = widget if isinstance(widget, type) else type(widget)
            if issubclass(widget_class, forms.TextInput):
                kwargs.pop("widget")
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


def resolve_size_unit(
    instance: models.Model, size_unit_field: str
) -> SizeUnit | CustomSizeUnit | None:
    """Follow ``size_unit_field`` from ``instance``, including relations.

    Each step is an attribute lookup (``host.size_unit``). An empty step, a
    missing relation, or a blank size unit returns ``None``. The slug
    ``custom`` is a ``CustomSizeUnit``.
    """
    current: Any = instance
    for part in size_unit_field.split("."):
        if current is None:
            return None
        current = getattr(current, part)
    if isinstance(current, (SizeUnit, CustomSizeUnit)):
        return current
    if current is None or current == "":
        return None
    slug = str(current).strip().lower()
    if slug == CUSTOM_SIZE_UNIT_SLUG:
        return CUSTOM_SIZE_UNIT
    return parse_size_unit_slug(slug)


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
            raise ValueError(
                f"Cannot read {self.field.name!r}: {self.field.size_unit_field!r} is empty."
            )
        return Size.from_raw(raw, size_unit)

    def __set__(self, instance: models.Model, value: Any) -> None:
        # ``SizeFormField`` cleans to ``(token, size_unit)``. The column stores the token.
        if (
            isinstance(value, tuple)
            and len(value) == 2
            and (value[1] is None or isinstance(value[1], SizeUnit))
        ):
            value = value[0]
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
    returns a ``Size``; call ``.convert()`` or ``.convert_to_locale()`` on that
    value (with a ``Demographic`` from ``fashion_size``). Writing a
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

    def contribute_to_class(
        self, cls: type[models.Model], name: str, private_only: bool = False
    ) -> None:
        super().contribute_to_class(cls, name, private_only=private_only)
        setattr(cls, name, SizeDescriptor(self))

    def from_db_value(
        self, value: str | None, expression: object, connection: object
    ) -> str:
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
        if isinstance(size_unit, CustomSizeUnit):
            raise ValidationError("Custom sizes cannot be converted.")
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
        if isinstance(size_unit, CustomSizeUnit):
            raise ValidationError("Custom sizes cannot be converted.")
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
