"""Autocomplete form control for ``SizeField``.

The size is a text field. Suggestions appear as you type and come from the
fashion-size chart for the field's size unit. A short select chooses the region
or length unit you are typing. A "View conversion chart" link to the
right of the field opens that chart. The posted value is the token stored
by ``SizeField``.
"""

from __future__ import annotations

from decimal import InvalidOperation
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import format_html, json_script
from django.utils.safestring import mark_safe

from fashion_size.charts import chart_for
from fashion_size.demographics import Gender
from fashion_size.product_types import ProductType
from fashion_size.scales import default_scale
from fashion_size.types import (
    FRENCH_BAND_OFFSET,
    SIZE_UNITS,
    ConversionScale,
    IncompatibleSizeError,
    LengthOutOfRangeError,
    LetterSizeRow,
    LocaleSizeRow,
    MissingScaleError,
    Size,
    SizeFamily,
    SizeType,
    SizeUnit,
    UnknownSizeError,
    format_age_gender,
    format_raw,
    normalize_raw,
    size_from_attribute_option,
    size_unit_for_length_unit,
    size_unit_for_locale,
)

from django_fashion_size.model_fields import resolve_size_unit, stored_size_token

_CHART_FORMATS = (("uk", "UK"), ("eu", "EU"), ("us", "US"), ("au", "AU"))
_LENGTH_FORMATS = (("in", "in"), ("cm", "cm"))
_NOT_ON_CHART = "That size is not on the chart."
_LENGTH_RANGE = "Enter a length from 5 to 150 inches."


class _InvalidEntry:
    def __init__(self, message: str) -> None:
        self.message = message


def _entry_formats(size_type: SizeType) -> tuple[tuple[str, str], ...]:
    if size_type.family == SizeFamily.LENGTH:
        return _LENGTH_FORMATS
    if size_type.family.french_matches_eu or size_type.family == SizeFamily.BAND_SIZE:
        return (*_CHART_FORMATS, ("fr", "FR"))
    return _CHART_FORMATS


def _storage_format(size_unit: SizeUnit) -> str:
    if size_unit.length_unit:
        return size_unit.length_unit
    return size_unit.locale.value


def _entry_unit(size_type: SizeType, format_name: str) -> SizeUnit:
    if size_type.family == SizeFamily.LENGTH:
        return size_unit_for_length_unit(size_type, format_name)
    return size_unit_for_locale(size_type, format_name)


def _token(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    return format_raw(raw)


def _plain(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    raw = getattr(value, "value", None)
    if isinstance(raw, str):
        return raw.strip()
    return str(value).strip()


def _brand_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name.strip()
    return ""


def _product_type_slug(value: Any) -> str:
    if isinstance(value, ProductType):
        return value.value
    if isinstance(value, str):
        return value.strip().lower()
    slug = getattr(value, "slug", None) or getattr(value, "value", None)
    if isinstance(slug, str):
        return slug.strip().lower()
    return ""


def _demographic_label(age_group: str, gender: str) -> str:
    if not age_group or not gender:
        return ""
    try:
        return format_age_gender(age_group, gender)
    except ValueError:
        return " ".join(part for part in (age_group, gender) if part)


def _product_label(slug: str) -> str:
    try:
        return ProductType(slug).label
    except ValueError:
        return slug


def _scale_from_chart(size_type: SizeType, chart: Any) -> ConversionScale:
    if size_type.family == SizeFamily.CUP_SIZE:
        rows = tuple(
            LetterSizeRow.from_tokens(row["uk"], row["eu"], row["us"], row["au"]) for row in chart.rows
        )
    else:
        rows = tuple(
            LocaleSizeRow.from_numbers(row["uk"], row["eu"], row["us"], row["au"]) for row in chart.rows
        )
    return ConversionScale(
        size_type=size_type,
        age_group=chart.age_group,
        gender=chart.gender,
        rows=rows,
    )


def _resolve_scale(
    size_type: SizeType,
    *,
    age_group: str,
    gender: str,
    brand_name: str,
    product_type: str,
) -> tuple[ConversionScale | None, Any]:
    """Default or brand chart for this size type. Lengths have no chart."""
    if size_type.family == SizeFamily.LENGTH or not age_group or not gender:
        return None, None
    brand_chart = None
    if brand_name and size_type.supports_brand_overrides:
        lookup_gender = Gender.MALE if gender == Gender.UNISEX else gender
        brand_chart = chart_for(
            brand_name,
            size_type.slug,
            age_group,
            lookup_gender,
            product_type or None,
        )
    if brand_chart is not None:
        return _scale_from_chart(size_type, brand_chart), brand_chart
    try:
        return default_scale(size_type, age_group, gender), None
    except (MissingScaleError, ValueError):
        return None, None


def _suggestion_values(
    scale: ConversionScale,
    storage: SizeUnit,
    entry: SizeUnit,
    choices: list[str] | None,
) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    seen: set[str] = set()
    if choices:
        pairs: list[tuple[Any, Any]] = []
        for choice in choices:
            parsed = size_from_attribute_option(storage.slug, choice)
            if parsed is None:
                continue
            try:
                converted = scale.convert_raw(parsed.raw, storage, entry)
            except (UnknownSizeError, IncompatibleSizeError, ValueError, ArithmeticError):
                continue
            pairs.append((converted, parsed.raw))
    else:
        pairs = list(zip(scale.raw_values(entry), scale.raw_values(storage), strict=True))
    for entry_raw, stored_raw in pairs:
        label = _token(entry_raw)
        if label in seen:
            continue
        seen.add(label)
        values.append({"input": label, "stored": _token(stored_raw)})
    values.sort(key=_suggestion_sort)
    return values


def _suggestion_sort(item: dict[str, str]) -> tuple[int, float, str]:
    text = item["input"]
    if _is_number(text):
        return (0, float(text), text)
    return (1, 0.0, text.lower())


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _chart_rows(scale: ConversionScale, size_type: SizeType, formats: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    include_french = any(value == "fr" for value, _label in formats)
    rows: list[dict[str, str]] = []
    for row in scale.rows:
        raw = row.as_dict()
        item = {key: _token(raw[key]) for key in ("uk", "eu", "us", "au")}
        if include_french:
            if size_type.family == SizeFamily.BAND_SIZE:
                item["fr"] = format_raw(normalize_raw(raw["eu"]) + FRENCH_BAND_OFFSET)
            else:
                item["fr"] = item["eu"]
        rows.append(item)
    return rows


def _chart_payload(
    scale: ConversionScale,
    size_type: SizeType,
    formats: tuple[tuple[str, str], ...],
    brand_chart: Any,
    gender: str,
) -> dict[str, Any]:
    demographic = format_age_gender(scale.age_group, scale.gender)
    if brand_chart is not None:
        name = f"{brand_chart.brand_name} {demographic} {size_type.label.lower()} chart"
        source = brand_chart.source_url or "Brand chart"
        notes = brand_chart.source_notes
        origin = "brand"
        groups = [_product_label(slug) for slug in brand_chart.product_types]
    else:
        name = f"Default {demographic} {size_type.label.lower()} chart"
        source = "Default chart"
        notes = ""
        origin = "default"
        groups = []
    if gender == Gender.UNISEX and scale.gender == Gender.MALE:
        fallback = "Unisex uses the men's chart."
    elif gender and gender != scale.gender and not scale.gender:
        fallback = "This age group uses one shared chart."
    else:
        fallback = ""
    return {
        "name": name,
        "source": source,
        "notes": notes,
        "origin": origin,
        "demographic": demographic,
        "groups": groups,
        "fallback_note": fallback,
        "columns": [{"key": value, "label": label} for value, label in formats],
        "rows": _chart_rows(scale, size_type, formats),
    }


def _form_value(form: forms.BaseForm, name: str) -> Any:
    if name not in form.fields:
        return None
    if form.is_bound:
        posted = form.data.get(form.add_prefix(name))
        if posted not in (None, ""):
            return posted
    initial = form.initial.get(name, form.fields[name].initial)
    if initial not in (None, ""):
        return initial
    return None


def _context_objects(form: forms.BaseForm, size_unit_field: str) -> list[Any]:
    instance = getattr(form, "instance", None)
    if instance is None:
        return []
    objects = [instance]
    current = instance
    for part in size_unit_field.split(".")[:-1]:
        if not part:
            continue
        current = getattr(current, part, None)
        if current is None:
            break
        objects.append(current)
    return objects


def _first(widget: SizeValueWidget, form: forms.BaseForm, objects: list[Any], name: str, explicit: Any) -> Any:
    if explicit not in (None, ""):
        return explicit
    posted = _form_value(form, name)
    if posted not in (None, ""):
        return posted
    for obj in objects:
        value = getattr(obj, name, None)
        if value not in (None, ""):
            return value
    return None


def _current_unit_slug(form: forms.BaseForm, size_unit_field: str) -> str:
    if "." not in size_unit_field:
        posted = _form_value(form, size_unit_field)
        if isinstance(posted, SizeUnit):
            return posted.slug
        if posted not in (None, ""):
            return str(posted).strip().lower()
    instance = getattr(form, "instance", None)
    if instance is not None:
        try:
            unit = resolve_size_unit(instance, size_unit_field)
        except (AttributeError, ValueError):
            unit = None
        if unit is not None:
            return unit.slug
    return ""


def _convert_entry(
    *,
    unit_slug: str,
    format_name: str,
    text: str,
    age_group: str,
    gender: str,
    brand_name: str,
    product_type: str,
) -> str:
    try:
        storage = next(unit for unit in SIZE_UNITS if unit.slug == unit_slug)
    except StopIteration as exc:
        raise ValidationError(_NOT_ON_CHART) from exc
    size_type = storage.size_type
    allowed = {value for value, _label in _entry_formats(size_type)}
    if format_name not in allowed:
        raise ValidationError(_NOT_ON_CHART)
    try:
        entered = Size.from_raw(text, _entry_unit(size_type, format_name))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(_LENGTH_RANGE if size_type.family == SizeFamily.LENGTH else _NOT_ON_CHART) from exc
    if size_type.family == SizeFamily.LENGTH:
        try:
            converted = entered.convert(storage)
        except (LengthOutOfRangeError, IncompatibleSizeError, ValueError) as exc:
            raise ValidationError(_LENGTH_RANGE) from exc
        return stored_size_token(converted)
    scale, brand_chart = _resolve_scale(
        size_type,
        age_group=age_group,
        gender=gender,
        brand_name=brand_name,
        product_type=product_type,
    )
    if scale is None:
        if format_name == _storage_format(storage):
            return stored_size_token(entered)
        raise ValidationError(_NOT_ON_CHART)
    try:
        scale.row_for(entered.raw, entered.size_unit)
        converted = entered.convert(
            storage,
            age_group=age_group or None,
            gender=gender or None,
            brand_scale=scale if brand_chart is not None else None,
        )
    except (UnknownSizeError, MissingScaleError, IncompatibleSizeError, ValueError) as exc:
        raise ValidationError(_NOT_ON_CHART) from exc
    return stored_size_token(converted)


def posted_size_token(data: Any, name: str) -> str | _InvalidEntry:
    """Storage token from the autocomplete, or the plain input when script is off."""
    if str(data.get(f"{name}__active") or "") != "1":
        value = data.get(name)
        return "" if value is None else str(value)
    entry = data.get(f"{name}__entry")
    if entry is None or str(entry).strip() == "":
        return ""
    try:
        return _convert_entry(
            unit_slug=str(data.get(f"{name}__unit") or "").strip().lower(),
            format_name=str(data.get(f"{name}__format") or "").strip().lower(),
            text=str(entry).strip(),
            age_group=str(data.get(f"{name}__age_group") or "").strip().lower(),
            gender=str(data.get(f"{name}__gender") or "").strip().lower(),
            brand_name=str(data.get(f"{name}__brand") or "").strip(),
            product_type=str(data.get(f"{name}__product_type") or "").strip().lower(),
        )
    except ValidationError as exc:
        message = exc.messages[0] if exc.messages else _NOT_ON_CHART
        return _InvalidEntry(message)


def size_value_config(
    form: forms.BaseForm,
    *,
    size_unit_field: str,
    widget: SizeValueWidget,
    label: str,
) -> dict[str, Any]:
    """JSON for one autocomplete: charts, suggestion lists, and the active size unit."""
    objects = _context_objects(form, size_unit_field)
    age_group = _plain(_first(widget, form, objects, "age_group", widget.age_group))
    gender = _plain(_first(widget, form, objects, "gender", widget.gender))
    brand = _brand_name(_first(widget, form, objects, "brand", widget.brand_name))
    product_type = _product_type_slug(_first(widget, form, objects, "product_type", widget.product_type))
    current = _current_unit_slug(form, size_unit_field)
    on_form = "." not in size_unit_field and size_unit_field in form.fields
    units = [unit for unit in SIZE_UNITS if on_form or unit.slug == current]
    charts: dict[str, Any] = {}
    payload: dict[str, Any] = {}
    choices = list(widget.choices) if widget.choices is not None else None
    scales: dict[str, tuple[ConversionScale | None, Any]] = {}
    for size_unit in units:
        key = size_unit.size_type.slug
        if key not in scales:
            scales[key] = _resolve_scale(
                size_unit.size_type,
                age_group=age_group,
                gender=gender,
                brand_name=brand,
                product_type=product_type,
            )
        scale, brand_chart = scales[key]
        formats = _entry_formats(size_unit.size_type)
        chart_key = ""
        if scale is not None:
            chart_key = key
            if chart_key not in charts:
                charts[chart_key] = _chart_payload(scale, size_unit.size_type, formats, brand_chart, gender)
        values: dict[str, list[dict[str, str]]] = {}
        unit_choices = choices if size_unit.slug == current else None
        if scale is not None:
            for format_name, _format_label in formats:
                values[format_name] = _suggestion_values(
                    scale,
                    size_unit,
                    _entry_unit(size_unit.size_type, format_name),
                    unit_choices,
                )
        payload[size_unit.slug] = {
            "measurement": {
                "kind": size_unit.size_type.slug,
                "label": size_unit.size_type.label,
                "storage_format": _storage_format(size_unit),
                "storage_measurement": size_unit.slug,
                "format_side": "right" if size_unit.length_unit else "left",
                "formats": [{"value": value, "label": format_label} for value, format_label in formats],
                "length": bool(size_unit.length_unit),
            },
            "context": {
                "demographic_label": _demographic_label(age_group, gender),
                "product_type_name": _product_label(product_type) if product_type else "",
                "product_type_group_name": "",
            },
            "chartKey": chart_key,
            "values": values,
            "choices": unit_choices or [],
        }
    return {
        "initialUnit": current,
        "sizeUnitField": form.add_prefix(size_unit_field) if on_form else "",
        "ageGroup": age_group,
        "gender": gender,
        "brand": brand,
        "productType": product_type,
        "label": label,
        "units": payload,
        "charts": charts,
    }


class SizeValueWidget(forms.Widget):
    """Autocomplete for a stored size token, with a region or unit select."""

    def __init__(
        self,
        attrs: dict[str, Any] | None = None,
        *,
        age_group: str | None = None,
        gender: str | None = None,
        brand_name: str | None = None,
        product_type: str | None = None,
        choices: list[str] | None = None,
    ) -> None:
        self.age_group = age_group
        self.gender = gender
        self.brand_name = brand_name
        self.product_type = product_type
        self.choices = choices
        self.config: dict[str, Any] = {}
        super().__init__(attrs)

    class Media:
        css = {"all": ["django_fashion_size/size_value_field.css"]}
        js = ["django_fashion_size/size_value_field.js"]

    def value_from_datadict(self, data: Any, files: Any, name: str) -> str | _InvalidEntry:
        return posted_size_token(data, name)

    def render(self, name: str, value: Any, attrs: dict[str, Any] | None = None, renderer: Any = None) -> str:
        attrs = self.build_attrs(self.attrs, attrs)
        input_id = str(attrs.get("id") or f"id_{name}")
        config = dict(self.config)
        config["disabled"] = bool(attrs.get("disabled"))
        config.setdefault("label", "")
        token = "" if value in (None, "") else str(value)
        input_attrs = {key: item for key, item in attrs.items() if key != "required"}
        input_attrs["id"] = input_id
        input_attrs["autocomplete"] = "off"
        input_attrs["data-size-value-input"] = "true"
        rendered_input = forms.TextInput().render(name, token, input_attrs, renderer)
        initial_unit = str(config.get("initialUnit") or "")
        measurement = (config.get("units") or {}).get(initial_unit, {}).get("measurement") or {}
        hidden_values = {
            "entry": token,
            "format": measurement.get("storage_format", ""),
            "unit": initial_unit,
            "age_group": config.get("ageGroup", ""),
            "gender": config.get("gender", ""),
            "brand": config.get("brand", ""),
            "product_type": config.get("productType", ""),
            "active": "",
        }
        hidden = mark_safe(
            "".join(
                format_html(
                    '<input type="hidden" name="{}" value="{}" data-size-value-{}="true">',
                    f"{name}__{suffix}",
                    hidden_values[suffix],
                    suffix.replace("_", "-"),
                )
                for suffix in hidden_values
            )
        )
        return format_html(
            '{}<div class="size-value-field" data-size-value-field data-config="{}">{}<div data-size-value-root></div>{}</div>',
            json_script(config, f"{input_id}-config"),
            f"{input_id}-config",
            rendered_input,
            hidden,
        )


class SizeFormField(forms.CharField):
    """Char field whose widget is the size autocomplete."""

    def __init__(self, *args: Any, size_unit_field: str = "", **kwargs: Any) -> None:
        self.size_unit_field = size_unit_field
        kwargs.setdefault("widget", SizeValueWidget())
        super().__init__(*args, **kwargs)

    def to_python(self, value: Any) -> str:
        if isinstance(value, _InvalidEntry):
            raise ValidationError(value.message)
        return super().to_python(value)

    def get_bound_field(self, form: forms.BaseForm, field_name: str) -> forms.BoundField:
        return SizeBoundField(form, self, field_name)


class SizeBoundField(forms.BoundField):
    def as_widget(self, widget: forms.Widget | None = None, attrs: dict[str, Any] | None = None, only_initial: bool = False) -> str:
        widget = widget or self.field.widget
        if isinstance(widget, SizeValueWidget) and isinstance(self.field, SizeFormField):
            widget.config = size_value_config(
                self.form,
                size_unit_field=self.field.size_unit_field,
                widget=widget,
                label=self.label,
            )
        return super().as_widget(widget, attrs, only_initial)
