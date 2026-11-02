"""Autocomplete form control for ``SizeField``.

The size is a text field. Suggestions appear as you type and come from the
fashion-size chart for the field's size unit, plus any valid labels that are
not rows on that chart (shoe and cup alpha sizes). A short select chooses the
region or length unit you are typing. ``selection="select"`` replaces the
autocomplete with a dropdown of the same values. ``unavailable`` keeps named
sizes in that list with an `` (n/a)`` suffix and refuses them. A "View
conversion chart" link to the right of the field opens that chart;
``show_chart_link=False`` leaves it out. The posted value is the token stored
by ``SizeField``. ``build_size_value_config`` returns the same JSON without a
bound form, for an API or another React tree.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import InvalidOperation
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import format_html, json_script
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from fashion_size.brands import BrandName, resolve_brand_name
from fashion_size.charts import chart_for
from fashion_size.demographics import AgeGroup, Demographic, Gender
from fashion_size.product_types import ProductType, resolve_product_type
from fashion_size.scales import cup_sort_key, default_scale
from fashion_size.types import (
    CUP_ALPHA_ORDER,
    FRENCH_BAND_OFFSET,
    SHOE_ALPHA_ORDER,
    SIZE_UNITS,
    ConversionScale,
    IncompatibleSizeError,
    LengthOutOfRangeError,
    LetterSizeRow,
    Locale,
    LocaleSizeRow,
    MissingScaleError,
    Size,
    SizeFamily,
    SizeType,
    SizeUnit,
    UnknownSizeError,
    format_age_gender,
    format_raw,
    is_cup_alpha_token,
    length_entry_bounds,
    length_value_in_range,
    normalize_raw,
    parse_size_unit_slug,
    shoe_alpha_token,
    size_from_attribute_option,
    size_unit_for_length_unit,
    size_unit_for_locale,
)

from django_fashion_size.model_fields import (
    CUSTOM_SIZE_UNIT_SLUG,
    length_bounds_message,
    resolve_size_unit,
    stored_size_token,
)

_CHART_FORMATS = (("uk", "UK"), ("eu", "EU"), ("us", "US"), ("au", "AU"))
_LENGTH_FORMATS = (("in", "in"), ("cm", "cm"))
_REGION_LABELS = dict((*_CHART_FORMATS, ("fr", "FR")))
_SELECTIONS = frozenset({"autocomplete", "select"})
_NOT_ON_CHART = "That size is not on the chart."
_UNRECOGNISED_LABEL = "That size is not recognised."
_UNAVAILABLE = _("That size is not available.")
_UNAVAILABLE_SUFFIX = _(" (n/a)")
_CUSTOM_SIZE = "Choose a custom size."
_CUSTOM_LABEL = _("Custom")
# Valid sizes that are not rows on the conversion chart. Each entry region
# lists the same tokens, and the stored value is that token.
_OFF_CHART_TOKENS = {
    SizeFamily.CUP_SIZE: CUP_ALPHA_ORDER,
    SizeFamily.SHOE_SIZE: SHOE_ALPHA_ORDER,
}
_SHOE_ALPHA_RANK = {token: index for index, token in enumerate(SHOE_ALPHA_ORDER)}


class _InvalidEntry:
    def __init__(self, message: str, text: str = "") -> None:
        self.message = message
        self.text = text


def _normalize_custom_values(values: list[str] | None) -> tuple[str, ...]:
    """Strip, drop blanks, and keep the first spelling of each custom size."""
    if not values:
        return ()
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        text = str(value).strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return tuple(cleaned)


def _match_custom(text: str, custom_values: tuple[str, ...]) -> str | None:
    """Canonical custom size, ``""`` when ``text`` is blank, or ``None`` when unknown."""
    needle = text.strip()
    if not needle:
        return ""
    folded = needle.casefold()
    for value in custom_values:
        if value.casefold() == folded:
            return value
    return None


def _entry_formats(size_type: SizeType) -> tuple[tuple[str, str], ...]:
    if size_type.family == SizeFamily.LABEL:
        # One universal unit. The select stays hidden; the value is the type slug.
        return ((str(size_type.slug), size_type.label),)
    if size_type.family == SizeFamily.LENGTH:
        return _LENGTH_FORMATS
    if size_type.family.french_matches_eu or size_type.family == SizeFamily.BAND_SIZE:
        return (*_CHART_FORMATS, ("fr", "FR"))
    return _CHART_FORMATS


def _normalize_entry_region(value: Any) -> str:
    """Region slug for a locked entry select. Blank leaves the select open."""
    if isinstance(value, Locale):
        slug = value.value
    else:
        slug = str(value or "").strip().lower().replace("_", "-")
    if not slug:
        return ""
    if slug == "eur":
        slug = "eu"
    if slug not in _REGION_LABELS:
        raise ValueError("entry_region must be a region (uk, eu, us, au, or fr).")
    return slug


def _select_formats(
    size_type: SizeType, entry_region: str
) -> tuple[tuple[tuple[str, str], ...], bool]:
    """Formats shown in the region select, and whether that select is locked.

    Lengths and labels have no region. A lock on a chart size leaves one
    region; the frontend adds Custom beside it when custom values are in play,
    and disables the select when they are not.
    """
    formats = _entry_formats(size_type)
    if not entry_region or size_type.family in {SizeFamily.LABEL, SizeFamily.LENGTH}:
        return formats, False
    locked = tuple(item for item in formats if item[0] == entry_region)
    if locked:
        return locked, True
    return ((entry_region, _REGION_LABELS[entry_region]),), True


def _check_entry_region(size_unit: SizeUnit | None, entry_region: str) -> None:
    """Reject a lock the fixed size unit cannot honour."""
    if not entry_region or size_unit is None:
        return
    family = size_unit.size_type.family
    if family in {SizeFamily.LABEL, SizeFamily.LENGTH}:
        raise ValueError("entry_region applies to chart sizes, which have a region select.")
    allowed = {value for value, _label in _entry_formats(size_unit.size_type)}
    if entry_region not in allowed:
        region = _REGION_LABELS[entry_region]
        raise ValueError(f"{size_unit.size_type.label} has no {region} sizes.")


def _label_suggestions(size_type: SizeType) -> list[dict[str, str]]:
    """Display word and canonical token for a label size type.

    Age bands have no fixed list; the field accepts a typed age and
    ``fashion-size`` canonicalises it. ``ONE`` is a stored letter token
    whose alias is ``one size``, so the suggestion shows that word.
    """
    vocabulary = size_type.vocabulary
    if vocabulary is None:
        return []
    return [{"input": label, "stored": token} for token, label in vocabulary.display]


def _canonical_label(size_unit: SizeUnit, text: str) -> str:
    """Stored token for a label size, including a token that is already canonical.

    ``Size.from_raw`` folds aliases (``small``, ``one size``, ``6 months``).
    A saved letter token such as ``ONE`` is not itself an alias, so a value
    already in the vocabulary is kept.
    """
    try:
        return stored_size_token(Size.from_raw(text, size_unit))
    except (ValueError, InvalidOperation, TypeError):
        vocabulary = size_unit.size_type.vocabulary
        token = text.strip()
        if vocabulary is not None and token in dict(vocabulary.display):
            return token
        raise ValidationError(_UNRECOGNISED_LABEL) from None


def _is_length_size(size_unit: SizeUnit) -> bool:
    """True for centimetre and inch size types.

    Waist, chest, and band units can carry ``length_unit`` so ``fashion-size``
    can display them like a length. The form still chooses a region, because
    those charts do not convert like inches and centimetres.
    """
    return size_unit.size_type.family == SizeFamily.LENGTH


def _storage_format(size_unit: SizeUnit) -> str:
    if size_unit.size_type.family == SizeFamily.LABEL:
        return str(size_unit.size_type.slug)
    if _is_length_size(size_unit) and size_unit.length_unit:
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


def _brand_name(value: Any) -> BrandName | str:
    if isinstance(value, BrandName):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        known = resolve_brand_name(text)
        return known if known is not None else text
    name = getattr(value, "name", None)
    if isinstance(name, BrandName):
        return name
    if isinstance(name, str):
        text = name.strip()
        if not text:
            return ""
        known = resolve_brand_name(text)
        return known if known is not None else text
    return ""


def _product_type_slug(value: Any) -> str:
    """Chart slug for a product type name (``Shoes``), slug (``shoes``), or object."""
    if isinstance(value, ProductType):
        return value.value
    if isinstance(value, str):
        return _slug_from_product_type_text(value)
    for attr in ("slug", "value", "name"):
        raw = getattr(value, attr, None)
        if isinstance(raw, str) and raw.strip():
            return _slug_from_product_type_text(raw)
    return ""


def _slug_from_product_type_text(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    try:
        return resolve_product_type(cleaned).value
    except ValueError:
        pass
    for product_type in ProductType:
        if product_type.label.casefold() == cleaned.casefold():
            return product_type.value
    return cleaned.lower()


def _demographic_label(age_group: str, gender: str) -> str:
    if not age_group or not gender:
        return ""
    try:
        return format_age_gender(age_group, gender)
    except ValueError:
        return " ".join(part for part in (age_group, gender) if part)


def _product_label(value: ProductType | str) -> str:
    if isinstance(value, ProductType):
        return value.label
    try:
        return resolve_product_type(value).label
    except ValueError:
        return str(value)


def _scale_from_chart(size_type: SizeType, chart: Any) -> ConversionScale:
    if size_type.family == SizeFamily.CUP_SIZE:
        rows = tuple(
            LetterSizeRow.from_tokens(row["uk"], row["eu"], row["us"], row["au"]) for row in chart.rows
        )
    else:
        rows = tuple(
            LocaleSizeRow.from_numbers(row["uk"], row["eu"], row["us"], row["au"]) for row in chart.rows
        )
    base = {
        "size_type": size_type,
        "age_group": chart.age_group,
        "gender": chart.gender,
        "rows": rows,
    }
    effective_from = getattr(chart, "effective_from", None) or getattr(chart, "updated_at", None)
    effective_until = getattr(chart, "effective_until", None)
    if effective_from is not None:
        try:
            return ConversionScale(
                **base,
                effective_from=effective_from,
                effective_until=effective_until,
            )
        except TypeError:
            # Older fashion-size releases did not include effective date fields.
            pass
    try:
        return ConversionScale(**base)
    except TypeError:
        # Newer fashion-size releases require ``effective_from``. If the chart
        # does not carry one, treat it as "latest now" instead of requiring an
        # explicit lookup date from callers.
        return ConversionScale(
            **base,
            effective_from=datetime.now(UTC),
            effective_until=effective_until,
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
        # Alpha labels are valid sizes and are not rows on the chart.
        # The stored token is the label itself in every region.
        pairs.extend((token, token) for token in _OFF_CHART_TOKENS.get(scale.size_type.family, ()))
    cup = scale.size_type.family == SizeFamily.CUP_SIZE
    for entry_raw, stored_raw in pairs:
        label = _token(entry_raw)
        if label in seen:
            continue
        seen.add(label)
        values.append({"input": label, "stored": _token(stored_raw)})
    values.sort(key=lambda item: _suggestion_sort(item, cup=cup))
    return values


def _suggestion_sort(item: dict[str, str], *, cup: bool = False) -> tuple[int, int] | tuple[int, float, str]:
    if cup:
        return cup_sort_key(item["input"])
    text = item["input"]
    if _is_number(text):
        return (0, float(text), text)
    rank = _SHOE_ALPHA_RANK.get(text)
    if rank is not None:
        return (1, float(rank), text)
    return (2, 0.0, text.lower())


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _normalize_selection(value: str | None) -> str:
    """``autocomplete`` (typed list) or ``select`` (dropdown of the same values)."""
    text = "autocomplete" if value in (None, "") else str(value).strip().lower()
    if text not in _SELECTIONS:
        raise ValueError("selection must be 'autocomplete' or 'select'.")
    return text


def _normalize_unavailable(values: list[str] | None) -> tuple[str, ...]:
    """Stored tokens, or aliases of them, that this context must not offer."""
    if not values:
        return ()
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return tuple(cleaned)


def _stored_token_for_unit(size_unit: SizeUnit, text: str) -> str | None:
    """Canonical stored token for ``text`` in ``size_unit``, or ``None``."""
    try:
        return stored_size_token(Size.from_raw(text, size_unit))
    except (ValueError, InvalidOperation, TypeError, ValidationError):
        return None


def _banned_tokens(size_unit: SizeUnit | None, unavailable: tuple[str, ...]) -> tuple[str, ...]:
    """Caller tokens plus the stored token each one resolves to for this unit."""
    banned: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        if token and token not in seen:
            seen.add(token)
            banned.append(token)

    for text in unavailable:
        add(text)
        if size_unit is not None:
            add(_stored_token_for_unit(size_unit, text) or "")
    return tuple(banned)


def _token_unavailable(size_unit: SizeUnit | None, token: str, unavailable: tuple[str, ...]) -> bool:
    if not token or not unavailable:
        return False
    if size_unit is None:
        folded = token.casefold()
        return any(item.casefold() == folded for item in unavailable)
    banned = set(_banned_tokens(size_unit, unavailable))
    if token in banned:
        return True
    resolved = _stored_token_for_unit(size_unit, token)
    return bool(resolved and resolved in banned)


def _mark_unavailable(
    values: list[dict[str, str]],
    banned: tuple[str, ...],
    *,
    casefold: bool = False,
) -> list[dict[str, Any]]:
    """Copy ``values``, flagging any whose label or stored token is banned."""
    if not banned:
        return [dict(item) for item in values]
    exact = set(banned)
    folded = {item.casefold() for item in banned} if casefold else set()
    marked: list[dict[str, Any]] = []
    for item in values:
        hit = item["stored"] in exact or item["input"] in exact
        if not hit and folded:
            hit = item["stored"].casefold() in folded or item["input"].casefold() in folded
        if hit:
            marked.append({**item, "unavailable": True})
        else:
            marked.append(dict(item))
    return marked


def _closed_list(size_unit: SizeUnit) -> bool:
    """True when the size unit has a fixed set of values a dropdown can list.

    Lengths are any number inside a range. Age bands are typed (``6 months``)
    and have no fixed vocabulary to put in a menu.
    """
    family = size_unit.size_type.family
    if family == SizeFamily.LENGTH:
        return False
    if family == SizeFamily.LABEL:
        vocabulary = size_unit.size_type.vocabulary
        return bool(vocabulary and vocabulary.display)
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
        groups = [_product_label(product_type) for product_type in brand_chart.product_types]
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
    if not name:
        return None
    posted = _form_value(form, name)
    if posted not in (None, ""):
        return posted
    for obj in objects:
        value = getattr(obj, name, None)
        if value not in (None, ""):
            return value
    return None


def _current_unit_slug(form: forms.BaseForm, size_unit_field: str, explicit: SizeUnit | None) -> str:
    if explicit is not None:
        return explicit.slug
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


def _conversion_demographic(age_group: str, gender: str, *, length: bool) -> Demographic:
    age = str(age_group or "").strip().lower()
    sex = str(gender or "").strip().lower()
    if length and (not age or not sex):
        return Demographic(age_group=AgeGroup.ADULT, gender=Gender.UNISEX)
    return Demographic(age_group=age, gender=sex)


def _convert_entry(
    *,
    unit_slug: str,
    format_name: str,
    text: str,
    age_group: str,
    gender: str,
    brand_name: BrandName | str,
    product_type: str,
    entry_region: str = "",
) -> str:
    try:
        storage = next(unit for unit in SIZE_UNITS if unit.slug == unit_slug)
    except StopIteration as exc:
        raise ValidationError(_NOT_ON_CHART) from exc
    size_type = storage.size_type
    if size_type.family == SizeFamily.LABEL:
        if format_name != str(size_type.slug):
            raise ValidationError(_UNRECOGNISED_LABEL)
        return _canonical_label(storage, text)
    length_message = (
        length_bounds_message(size_type) if size_type.family == SizeFamily.LENGTH else None
    )
    allowed = {value for value, _label in _entry_formats(size_type)}
    regional = size_type.family not in {SizeFamily.LABEL, SizeFamily.LENGTH}
    if entry_region and regional and format_name != entry_region:
        region = _REGION_LABELS[entry_region]
        raise ValidationError(_("Enter the size in %(region)s.") % {"region": region})
    if format_name not in allowed:
        raise ValidationError(length_message or _NOT_ON_CHART)
    try:
        entered = Size.from_raw(text, _entry_unit(size_type, format_name))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(length_message or _NOT_ON_CHART) from exc
    if length_message is not None and not length_value_in_range(entered.raw, entered.size_unit):
        raise ValidationError(length_message)
    is_length = size_type.family == SizeFamily.LENGTH
    if not is_length and (not str(age_group or "").strip() or not str(gender or "").strip()):
        if format_name == _storage_format(storage):
            return stored_size_token(entered)
        raise ValidationError(_NOT_ON_CHART)
    demographic = _conversion_demographic(age_group, gender, length=is_length)
    resolved_product_type = _product_type_slug(product_type) or None
    if not is_length:
        scale, _brand_chart = _resolve_scale(
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
        # Alpha labels (sports-bra cups, shoe S/M/L) convert identically and are not chart rows.
        alpha_label = (size_type.family == SizeFamily.CUP_SIZE and is_cup_alpha_token(str(entered.raw))) or (
            size_type.family == SizeFamily.SHOE_SIZE and shoe_alpha_token(entered.raw) is not None
        )
        if not alpha_label:
            try:
                scale.row_for(entered.raw, entered.size_unit)
            except UnknownSizeError as exc:
                raise ValidationError(_NOT_ON_CHART) from exc
    try:
        converted = entered.convert(
            storage,
            demographic=demographic,
            brand_name=brand_name or None,
            product_type=resolved_product_type,
        )
    except (UnknownSizeError, MissingScaleError, IncompatibleSizeError, LengthOutOfRangeError, ValueError) as exc:
        raise ValidationError(length_message or _NOT_ON_CHART) from exc
    return stored_size_token(converted.size)


def _is_custom_submission(data: Any, name: str) -> bool:
    unit_slug = str(data.get(f"{name}__unit") or "").strip().lower()
    format_name = str(data.get(f"{name}__format") or "").strip().lower()
    return unit_slug == CUSTOM_SIZE_UNIT_SLUG or format_name == CUSTOM_SIZE_UNIT_SLUG


def posted_size_token(
    data: Any,
    name: str,
    custom_values: tuple[str, ...] = (),
    entry_region: str = "",
    unavailable: tuple[str, ...] = (),
    size_unit: SizeUnit | None = None,
) -> str | _InvalidEntry:
    """Storage token from the control, or the plain input when script is off."""
    if str(data.get(f"{name}__active") or "") != "1":
        value = data.get(name)
        token = "" if value is None else str(value).strip()
        if _token_unavailable(size_unit, token, unavailable):
            return _InvalidEntry(str(_UNAVAILABLE), token)
        return "" if value is None else str(value)
    entry = data.get(f"{name}__entry")
    text = "" if entry is None else str(entry).strip()
    if text == "":
        return ""
    if _is_custom_submission(data, name):
        if not custom_values:
            return _InvalidEntry(_CUSTOM_SIZE, text)
        matched = _match_custom(text, custom_values)
        if matched is None:
            return _InvalidEntry(_CUSTOM_SIZE, text)
        if _token_unavailable(None, matched, unavailable):
            return _InvalidEntry(str(_UNAVAILABLE), text)
        return matched
    unit_slug = str(data.get(f"{name}__unit") or "").strip().lower()
    try:
        token = _convert_entry(
            unit_slug=unit_slug,
            format_name=str(data.get(f"{name}__format") or "").strip().lower(),
            text=text,
            age_group=str(data.get(f"{name}__age_group") or "").strip().lower(),
            gender=str(data.get(f"{name}__gender") or "").strip().lower(),
            brand_name=str(data.get(f"{name}__brand") or "").strip(),
            product_type=_product_type_slug(data.get(f"{name}__product_type")),
            entry_region=entry_region,
        )
    except ValidationError as exc:
        message = exc.messages[0] if exc.messages else _NOT_ON_CHART
        return _InvalidEntry(message, text)
    posted_unit = size_unit
    if unit_slug:
        try:
            posted_unit = parse_size_unit_slug(unit_slug)
        except ValueError:
            posted_unit = size_unit
    if _token_unavailable(posted_unit, token, unavailable):
        return _InvalidEntry(str(_UNAVAILABLE), text)
    return token


def _posted_size_unit(data: Any, name: str, fallback: SizeUnit | None) -> SizeUnit | None:
    """Unit the posted token is stored in. Custom sizes have no unit."""
    if str(data.get(f"{name}__active") or "") != "1":
        return fallback
    if _is_custom_submission(data, name):
        return None
    unit_slug = str(data.get(f"{name}__unit") or "").strip().lower()
    if not unit_slug:
        return fallback
    try:
        return parse_size_unit_slug(unit_slug)
    except ValueError:
        return fallback


def _linked_field_name(form: forms.BaseForm, name: str) -> str:
    """HTML name of a sibling field, or blank when this form does not include it."""
    if name and "." not in name and name in form.fields:
        return form.add_prefix(name)
    return ""


def build_size_value_config(
    *,
    size_unit: SizeUnit | str | None = None,
    brand_name: Any = None,
    product_type_name: Any = None,
    age_group: str | None = None,
    gender: str | None = None,
    custom_values: list[str] | None = None,
    choices: list[str] | None = None,
    entry_region: Locale | str | None = None,
    label: Any = "",
    units: Sequence[SizeUnit] | None = None,
    show_chart_link: bool = True,
    selection: str | None = None,
    unavailable: list[str] | None = None,
) -> dict[str, Any]:
    """JSON for one size control, with no form and no hidden input names.

    ``size_unit`` is the stored unit (a ``SizeUnit`` or a slug). ``units``
    embeds every unit a caller can switch to; omit it to embed ``size_unit``
    only. ``entry_region`` locks the region select the same way
    ``SizeFormField`` does. ``show_chart_link`` hides the conversion chart
    when false. ``selection`` is ``autocomplete`` or ``select``. ``unavailable``
    lists stored tokens (or aliases) that stay visible with an `` (n/a)``
    suffix and cannot be chosen. The result has no ``sizeUnitField``,
    ``brandField``, or ``productTypeField`` — those belong to a Django form post.
    """
    region = _normalize_entry_region(entry_region)
    mode = _normalize_selection(selection)
    blocked = _normalize_unavailable(unavailable)
    pinned: SizeUnit | None = None
    initial = ""
    if isinstance(size_unit, SizeUnit):
        pinned = size_unit
        initial = size_unit.slug
    elif size_unit not in (None, ""):
        text = str(size_unit).strip()
        if text.lower() == CUSTOM_SIZE_UNIT_SLUG:
            initial = CUSTOM_SIZE_UNIT_SLUG
        elif text:
            try:
                pinned = parse_size_unit_slug(text)
            except ValueError:
                # A bound form can post a slug that is not a size unit yet.
                # Callers who pass ``size_unit`` on its own still get the error.
                if units is None:
                    raise
                initial = text.lower()
            else:
                initial = pinned.slug
    if units is None:
        _check_entry_region(pinned, region)
        selected = [pinned] if pinned is not None else []
    else:
        selected = []
        seen: set[str] = set()
        for unit in units:
            if unit.slug in seen:
                continue
            seen.add(unit.slug)
            selected.append(unit)
        if pinned is not None and pinned.slug not in seen:
            selected.append(pinned)
    age = _plain(age_group)
    sex = _plain(gender)
    brand = _brand_name(brand_name)
    product_type = _product_type_slug(product_type_name)
    cleaned_custom = _normalize_custom_values(custom_values)
    choice_list = list(choices) if choices is not None else None
    charts: dict[str, Any] = {}
    payload: dict[str, Any] = {}
    scales: dict[str, tuple[ConversionScale | None, Any]] = {}
    for unit in selected:
        key = unit.size_type.slug
        is_label = unit.size_type.family == SizeFamily.LABEL
        if not is_label and key not in scales:
            scales[key] = _resolve_scale(
                unit.size_type,
                age_group=age,
                gender=sex,
                brand_name=brand,
                product_type=product_type,
            )
        scale, brand_chart = (None, None) if is_label else scales[key]
        formats = _entry_formats(unit.size_type)
        select_formats, format_locked = _select_formats(unit.size_type, region)
        chart_key = ""
        if scale is not None:
            chart_key = key
            if chart_key not in charts:
                charts[chart_key] = _chart_payload(scale, unit.size_type, formats, brand_chart, sex)
        values: dict[str, list[dict[str, Any]]] = {}
        unit_choices = choice_list if unit.slug == initial else None
        banned = _banned_tokens(unit, blocked)
        if is_label:
            values[str(unit.size_type.slug)] = _mark_unavailable(
                _label_suggestions(unit.size_type),
                banned,
            )
        elif scale is not None:
            for format_name, _format_label in formats:
                values[format_name] = _mark_unavailable(
                    _suggestion_values(
                        scale,
                        unit,
                        _entry_unit(unit.size_type, format_name),
                        unit_choices,
                    ),
                    banned,
                )
        measurement: dict[str, Any] = {
            "kind": unit.size_type.slug,
            "label": unit.size_type.label,
            "storage_format": _storage_format(unit),
            "storage_measurement": unit.slug,
            "format_side": "right" if _is_length_size(unit) else "left",
            "formats": [{"value": value, "label": format_label} for value, format_label in select_formats],
            "format_locked": format_locked,
            "length": _is_length_size(unit),
            "closed": _closed_list(unit),
        }
        if measurement["length"]:
            bounds = length_entry_bounds(unit.size_type)
            measurement["length_min"] = format_raw(bounds.min_inches)
            measurement["length_max"] = format_raw(bounds.max_inches)
            measurement["length_error"] = length_bounds_message(unit.size_type)
        payload[unit.slug] = {
            "measurement": measurement,
            "context": {
                "demographic_label": _demographic_label(age, sex),
                "product_type_name": _product_label(product_type) if product_type else "",
                "product_type_group_name": "",
            },
            "chartKey": chart_key,
            "values": values,
            "choices": unit_choices or [],
            "unavailable": list(banned),
        }
    if cleaned_custom:
        # A synthetic unit. Nothing converts; the list is the whole vocabulary.
        payload[CUSTOM_SIZE_UNIT_SLUG] = {
            "measurement": {
                "kind": CUSTOM_SIZE_UNIT_SLUG,
                "label": _CUSTOM_LABEL,
                "storage_format": CUSTOM_SIZE_UNIT_SLUG,
                "storage_measurement": CUSTOM_SIZE_UNIT_SLUG,
                "format_side": "left",
                "formats": [{"value": CUSTOM_SIZE_UNIT_SLUG, "label": _CUSTOM_LABEL}],
                "length": False,
                "closed": True,
                "custom": True,
            },
            "context": {
                "demographic_label": _demographic_label(age, sex),
                "product_type_name": _product_label(product_type) if product_type else "",
                "product_type_group_name": "",
            },
            "chartKey": "",
            "values": {
                CUSTOM_SIZE_UNIT_SLUG: _mark_unavailable(
                    [{"input": value, "stored": value} for value in cleaned_custom],
                    blocked,
                    casefold=True,
                )
            },
            "choices": list(cleaned_custom),
            "unavailable": list(blocked),
        }
    return {
        "initialUnit": initial,
        "entryRegion": region,
        "ageGroup": age,
        "gender": sex,
        "brand": brand,
        "productType": product_type,
        "label": "" if label is None else label,
        "showChartLink": bool(show_chart_link),
        "selection": mode,
        "unavailable": list(blocked),
        "unavailableSuffix": _UNAVAILABLE_SUFFIX,
        "unavailableMessage": _UNAVAILABLE,
        "customValues": list(cleaned_custom),
        "customLabel": _CUSTOM_LABEL,
        "units": payload,
        "charts": charts,
    }


def size_value_config(
    form: forms.BaseForm,
    *,
    size_unit_field: str,
    brand_name_field: str,
    product_type_name_field: str,
    widget: SizeValueWidget,
    label: str,
) -> dict[str, Any]:
    """Form JSON: ``build_size_value_config`` plus the sibling field names."""
    objects = _context_objects(form, size_unit_field)
    age_group = _plain(_first(widget, form, objects, "age_group", widget.age_group))
    gender = _plain(_first(widget, form, objects, "gender", widget.gender))
    brand = _brand_name(_first(widget, form, objects, brand_name_field, widget.brand_name))
    product_type = _product_type_slug(
        _first(widget, form, objects, product_type_name_field, widget.product_type_name)
    )
    current = _current_unit_slug(form, size_unit_field, widget.size_unit)
    on_form = widget.size_unit is None and "." not in size_unit_field and size_unit_field in form.fields
    included = [unit for unit in SIZE_UNITS if on_form or unit.slug == current]
    config = build_size_value_config(
        size_unit=current,
        brand_name=brand,
        product_type_name=product_type,
        age_group=age_group,
        gender=gender,
        custom_values=list(widget.custom_values),
        choices=list(widget.choices) if widget.choices is not None else None,
        entry_region=widget.entry_region,
        label=label,
        units=included,
        show_chart_link=widget.show_chart_link,
        selection=widget.selection,
        unavailable=list(widget.unavailable),
    )
    config["sizeUnitField"] = form.add_prefix(size_unit_field) if on_form else ""
    config["brandField"] = _linked_field_name(form, brand_name_field)
    config["productTypeField"] = _linked_field_name(form, product_type_name_field)
    return config


class SizeValueWidget(forms.Widget):
    """Size token control, with a region or unit select.

    ``selection`` is ``autocomplete`` or ``select``. ``unavailable`` lists
    stored tokens that stay in the list with an `` (n/a)`` suffix and cannot
    be chosen.
    """

    def __init__(
        self,
        attrs: dict[str, Any] | None = None,
        *,
        age_group: str | None = None,
        gender: str | None = None,
        size_unit: SizeUnit | str | None = None,
        brand_name: str | None = None,
        product_type_name: str | None = None,
        choices: list[str] | None = None,
        custom_values: list[str] | None = None,
        entry_region: Locale | str | None = None,
        show_chart_link: bool = True,
        selection: str | None = None,
        unavailable: list[str] | None = None,
    ) -> None:
        self.age_group = age_group
        self.gender = gender
        self.size_unit = None if size_unit in (None, "") else (
            size_unit if isinstance(size_unit, SizeUnit) else parse_size_unit_slug(str(size_unit))
        )
        self.brand_name = brand_name
        self.product_type_name = product_type_name
        self.choices = choices
        self.custom_values = _normalize_custom_values(custom_values)
        self.entry_region = _normalize_entry_region(entry_region)
        self.show_chart_link = bool(show_chart_link)
        self.selection = _normalize_selection(selection)
        self.unavailable = _normalize_unavailable(unavailable)
        _check_entry_region(self.size_unit, self.entry_region)
        self.config: dict[str, Any] = {}
        super().__init__(attrs)

    class Media:
        css = {"all": ["django_fashion_size/size_value_field.css"]}
        js = ["django_fashion_size/size_value_field.js"]

    def value_from_datadict(
        self, data: Any, files: Any, name: str
    ) -> tuple[str, SizeUnit | None] | _InvalidEntry:
        parsed = posted_size_token(
            data,
            name,
            self.custom_values,
            self.entry_region,
            self.unavailable,
            self.size_unit,
        )
        if isinstance(parsed, _InvalidEntry):
            return parsed
        if str(data.get(f"{name}__active") or "") != "1":
            matched = _match_custom(parsed, self.custom_values) if parsed else ""
            if parsed and matched:
                return (matched, None)
            return (parsed, self.size_unit)
        return (parsed, _posted_size_unit(data, name, self.size_unit))

    def render(self, name: str, value: Any, attrs: dict[str, Any] | None = None, renderer: Any = None) -> str:
        attrs = self.build_attrs(self.attrs, attrs)
        input_id = str(attrs.get("id") or f"id_{name}")
        config = dict(self.config)
        config["disabled"] = bool(attrs.get("disabled"))
        config.setdefault("label", "")
        if isinstance(value, tuple) and value:
            value = value[0]
        if isinstance(value, _InvalidEntry):
            token = value.text
        else:
            token = "" if value in (None, "") else str(value)
        input_attrs = {key: item for key, item in attrs.items() if key != "required"}
        input_attrs["id"] = input_id
        input_attrs["autocomplete"] = "off"
        input_attrs["data-size-value-input"] = "true"
        rendered_input = forms.TextInput().render(name, token, input_attrs, renderer)
        initial_unit = str(config.get("initialUnit") or "")
        measurement = (config.get("units") or {}).get(initial_unit, {}).get("measurement") or {}
        shown = measurement.get("formats") or []
        if measurement.get("format_locked") and shown:
            initial_format = shown[0]["value"]
        else:
            initial_format = measurement.get("storage_format", "")
        hidden_values = {
            "entry": token,
            "format": initial_format,
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
    """Char field whose widget is the size autocomplete.

    ``clean`` returns ``(token, size_unit)``. ``size_unit`` is the unit that
    token is stored in. It is ``None`` when the token is one of
    ``custom_values`` — those values are not sizes and do not convert.
    Pass ``custom_values`` to add a Custom option to the linked size-unit
    select (or to the region select when the unit is fixed on this field).

    ``entry_region`` locks the region the user types in (``uk``, ``eu``,
    ``us``, ``au``, or ``fr``). The stored token is still this field's size
    unit. Suggestions stay on that region even when the control cannot be
    changed. With custom values on the region select, that select stays
    editable and lists only the locked region and Custom; choosing Custom
    limits suggestions to those values. Without them, the region is shown
    and cannot be changed. Length and label units have no region list, so
    the lock does not apply to them.

    ``show_chart_link`` defaults to true. Set it false to omit the
    conversion-chart link.

    ``selection`` is ``autocomplete`` (the default) or ``select``. ``select``
    lists the same values in a dropdown. Lengths and age bands stay a text
    field, because they have no fixed list. ``unavailable`` is a list of
    stored tokens, or aliases such as ``medium``. Those sizes stay in the
    list with an `` (n/a)`` suffix, cannot be chosen, and are rejected on
    submit.
    """

    def __init__(
        self,
        *args: Any,
        size_unit_field: str = "",
        size_unit: SizeUnit | str | None = None,
        brand_name: str | None = None,
        product_type_name: str | None = None,
        brand_name_field: str = "brand",
        product_type_name_field: str = "product_type",
        age_group: str | None = None,
        gender: str | None = None,
        custom_values: list[str] | None = None,
        entry_region: Locale | str | None = None,
        show_chart_link: bool | None = None,
        selection: str | None = None,
        unavailable: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        self.size_unit_field = size_unit_field
        self.brand_name_field = brand_name_field
        self.product_type_name_field = product_type_name_field
        widget = kwargs.setdefault("widget", SizeValueWidget())
        if isinstance(widget, SizeValueWidget):
            if size_unit not in (None, ""):
                widget.size_unit = size_unit if isinstance(size_unit, SizeUnit) else parse_size_unit_slug(str(size_unit))
            if brand_name is not None:
                widget.brand_name = brand_name
            if product_type_name is not None:
                widget.product_type_name = product_type_name
            if age_group is not None:
                widget.age_group = age_group
            if gender is not None:
                widget.gender = gender
            if custom_values is not None:
                widget.custom_values = _normalize_custom_values(custom_values)
            if entry_region is not None:
                widget.entry_region = _normalize_entry_region(entry_region)
            if show_chart_link is not None:
                widget.show_chart_link = bool(show_chart_link)
            if selection is not None:
                widget.selection = _normalize_selection(selection)
            if unavailable is not None:
                widget.unavailable = _normalize_unavailable(unavailable)
            _check_entry_region(widget.size_unit, widget.entry_region)
        super().__init__(*args, **kwargs)

    def _token_and_unit(self, value: Any) -> tuple[str, SizeUnit | None]:
        if isinstance(value, _InvalidEntry):
            raise ValidationError(value.message)
        if isinstance(value, tuple) and len(value) == 2:
            token, unit = value
            if isinstance(token, _InvalidEntry):
                raise ValidationError(token.message)
            if unit is not None and not isinstance(unit, SizeUnit):
                unit = None
            return super().to_python(token), unit
        return super().to_python(value), None

    def to_python(self, value: Any) -> tuple[str, SizeUnit | None]:
        return self._token_and_unit(value)

    def validate(self, value: Any) -> None:
        token = value[0] if isinstance(value, tuple) else value
        super().validate(token)

    def run_validators(self, value: Any) -> None:
        token = value[0] if isinstance(value, tuple) else value
        super().run_validators(token)

    def has_changed(self, initial: Any, data: Any) -> bool:
        if self.disabled:
            return False
        try:
            cleaned = self.to_python(data)
        except ValidationError:
            return True
        token = cleaned[0] if isinstance(cleaned, tuple) else cleaned
        if isinstance(initial, tuple):
            initial = initial[0]
        initial_value = "" if initial is None else initial
        return initial_value != token

    def get_bound_field(self, form: forms.BaseForm, field_name: str) -> forms.BoundField:
        return SizeBoundField(form, self, field_name)


class SizeBoundField(forms.BoundField):
    def as_widget(self, widget: forms.Widget | None = None, attrs: dict[str, Any] | None = None, only_initial: bool = False) -> str:
        widget = widget or self.field.widget
        if isinstance(widget, SizeValueWidget) and isinstance(self.field, SizeFormField):
            widget.config = size_value_config(
                self.form,
                size_unit_field=self.field.size_unit_field,
                brand_name_field=self.field.brand_name_field,
                product_type_name_field=self.field.product_type_name_field,
                widget=widget,
                label=self.label,
            )
        return super().as_widget(widget, attrs, only_initial)
