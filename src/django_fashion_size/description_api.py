"""JSON endpoints for fashion-size description encode and decode.

The views are mounted only when a project includes
``django_fashion_size.urls``. Each request takes ``source_region`` once and
may take ``preferred_regions``. A batch holds at most 500 items. The caller
must be an active, authenticated user.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import InvalidOperation
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from fashion_size.demographics import AgeGroup, Demographic, Gender
from fashion_size.descriptions import decode_size_description, encode_size_description
from fashion_size.product_types import ProductType, resolve_product_type
from fashion_size.types import (
    LengthOutOfRangeError,
    Locale,
    Size,
    SizeFamily,
    format_raw,
    parse_size_unit_slug,
    size_unit_for_length_unit,
    size_unit_for_locale,
)

BATCH_LIMIT = 500

_REGION_ALIASES = {
    "uk": Locale.UK,
    "eu": Locale.EU,
    "eur": Locale.EU,
    "us": Locale.US,
    "au": Locale.AU,
    "fr": Locale.FR,
}
_REGION_HELP = "uk, eu, us, au, or fr"
_LENGTH_DEMOGRAPHIC = Demographic(AgeGroup.ADULT, Gender.UNISEX)


def _error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _active_user(request: HttpRequest) -> bool:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_active", True))


def _region(value: object, *, field: str) -> Locale:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a region ({_REGION_HELP}).")
    locale = _REGION_ALIASES.get(value.strip().lower())
    if locale is None:
        raise ValueError(f"{field} must be a region ({_REGION_HELP}).")
    return locale


def _preferred_regions(value: object) -> tuple[Locale, ...]:
    if value in (None, "", []):
        return ()
    if isinstance(value, str) or not isinstance(value, list):
        raise TypeError("preferred_regions must be a list of regions.")
    return tuple(_region(item, field="preferred_regions") for item in value)


def _text(value: object, field: str) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string.")
    return value.strip()


def _product_type(value: object) -> ProductType | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise TypeError("product_type must be a product type.")
    try:
        return resolve_product_type(value)
    except ValueError as exc:
        raise ValueError("product_type must be a product type.") from exc


def _demographic(age_group: str, gender: str) -> Demographic | None:
    if not age_group and not gender:
        return None
    if not age_group or not gender:
        raise ValueError("age_group and gender are both required to convert a size.")
    try:
        return Demographic(AgeGroup(age_group), Gender(gender))
    except ValueError as exc:
        raise ValueError("age_group and gender are not a known demographic.") from exc


def _request_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse the arguments that apply to every item in the batch."""
    age_group = _text(payload.get("age_group", ""), "age_group").lower()
    gender = _text(payload.get("gender", ""), "gender").lower()
    return {
        "source_region": _region(payload.get("source_region"), field="source_region"),
        "preferred_regions": _preferred_regions(payload.get("preferred_regions")),
        "age_group": age_group,
        "gender": gender,
        "demographic": _demographic(age_group, gender),
        "brand_name": _text(payload.get("brand_name", ""), "brand_name"),
        "product_type": _product_type(payload.get("product_type")),
    }


def _item_text(item: dict[str, Any], context: dict[str, Any], field: str) -> str:
    if field in item and item[field] not in (None, ""):
        return _text(item[field], field)
    return str(context[field])


def _item_context(item: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Per-item product, brand, and demographic, falling back to the request."""
    if "product_type" in item and item["product_type"] not in (None, ""):
        product_type = _product_type(item["product_type"])
    else:
        product_type = context["product_type"]
    brand_name = _item_text(item, context, "brand_name")
    age_group = _item_text(item, context, "age_group").lower()
    gender = _item_text(item, context, "gender").lower()
    if age_group == context["age_group"] and gender == context["gender"]:
        demographic = context["demographic"]
    else:
        demographic = _demographic(age_group, gender)
    return {
        "product_type": product_type,
        "brand_name": brand_name,
        "demographic": demographic,
    }


def _bare_size(size: Size) -> dict[str, str]:
    raw = size.raw
    return {
        "raw": raw if isinstance(raw, str) else format_raw(raw),
        "size_type": str(size.size_type.slug),
        "size_unit": size.size_unit.slug,
        "display": size.display(),
    }


def _convert_to_region(
    size: Size,
    region: Locale,
    *,
    demographic: Demographic | None,
    brand_name: str,
    product_type: ProductType | None,
) -> tuple[Size | None, str]:
    """Express ``size`` in ``region``.

    Label sizes keep their token and only change wording. Lengths move
    between inches and centimetres. Chart sizes use ``convert_to_locale``
    when a demographic is available. A chart conversion is not given a
    product type unless a brand name is too: fashion-size rejects a product
    type on its own.
    """
    family = size.size_type.family
    if family is SizeFamily.LABEL:
        return size, ""
    if family is SizeFamily.LENGTH and size.size_unit.length_unit:
        wanted = "cm" if region in {Locale.EU, Locale.FR} else "in"
        if size.size_unit.length_unit == wanted:
            return size, ""
        try:
            converted = size.convert(
                size_unit_for_length_unit(size.size_type, wanted),
                demographic=demographic or _LENGTH_DEMOGRAPHIC,
            ).size
        except LengthOutOfRangeError:
            return None, "That length is outside the range for this region."
        except (ValueError, TypeError):
            return None, "This size could not be converted."
        return converted, ""
    try:
        target = size_unit_for_locale(size.size_type, region)
    except (ValueError, TypeError):
        return None, "This size has no value in that region."
    if target.slug == size.size_unit.slug:
        return size, ""
    if demographic is None:
        return None, "age_group and gender are required to convert this size."
    try:
        converted = size.convert_to_locale(
            region,
            demographic=demographic,
            brand_name=brand_name or None,
            product_type=product_type if brand_name else None,
        ).size
    except (ValueError, TypeError):
        return None, "This size could not be converted."
    return converted, ""


def _size_payload(
    size: Size,
    *,
    preferred: tuple[Locale, ...],
    demographic: Demographic | None,
    brand_name: str,
    product_type: ProductType | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = _bare_size(size)
    if not preferred:
        return payload
    regions: list[dict[str, Any]] = []
    for region in preferred:
        converted, message = _convert_to_region(
            size,
            region,
            demographic=demographic,
            brand_name=brand_name,
            product_type=product_type,
        )
        if converted is None:
            regions.append({"region": region.value, "error": message})
            continue
        region_payload: dict[str, Any] = _bare_size(converted)
        region_payload["region"] = region.value
        if converted.size_type.family is SizeFamily.LABEL:
            region_payload["display"] = converted.size_type.label_text(
                str(converted.raw), region
            )
        regions.append(region_payload)
    payload["regions"] = regions
    return payload


def _parse_sizes(value: object) -> tuple[Size, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("sizes must be a non-empty list.")
    sizes: list[Size] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise TypeError("Each size needs a raw value and a size_unit.")
        unit_slug = entry.get("size_unit")
        raw = entry.get("raw")
        if not isinstance(unit_slug, str) or not unit_slug.strip():
            raise TypeError("Each size needs a raw value and a size_unit.")
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
            raise TypeError("Each size needs a raw value and a size_unit.")
        slug = unit_slug.strip()
        try:
            unit = parse_size_unit_slug(slug)
            token: str | int | float = raw.strip() if isinstance(raw, str) else raw
            sizes.append(Size.from_raw(token, unit))
        except (ValueError, TypeError, InvalidOperation) as exc:
            raise ValueError(f"Unrecognised size {raw!r} for {slug}.") from exc
    return tuple(sizes)


def _prepare_chart_sizes(
    sizes: tuple[Size, ...],
    preferred: tuple[Locale, ...],
    *,
    demographic: Demographic | None,
    brand_name: str,
    product_type: ProductType | None,
) -> tuple[Size, ...]:
    """Move chart sizes to the first preferred region before they are encoded.

    Lengths and label sizes stay as they are. ``encode_size_description``
    already chooses a length unit and label wording from ``preferred_regions``.
    """
    if not preferred:
        return sizes
    region = preferred[0]
    prepared: list[Size] = []
    for size in sizes:
        if size.size_type.family in {SizeFamily.LENGTH, SizeFamily.LABEL}:
            prepared.append(size)
            continue
        converted, _message = _convert_to_region(
            size,
            region,
            demographic=demographic,
            brand_name=brand_name,
            product_type=product_type,
        )
        prepared.append(size if converted is None else converted)
    return tuple(prepared)


def _decode_item(item: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if "value" not in item or not isinstance(item["value"], str):
        raise TypeError("value must be a string.")
    item_context = _item_context(item, context)
    decoded = decode_size_description(
        item["value"],
        context["source_region"],
        product_type=item_context["product_type"],
    )
    return {
        "sizes": [
            _size_payload(
                size,
                preferred=context["preferred_regions"],
                demographic=item_context["demographic"],
                brand_name=item_context["brand_name"],
                product_type=item_context["product_type"],
            )
            for size in decoded.sizes
        ],
        "format_id": decoded.format_id,
        "confidence": decoded.confidence,
        "discarded": [
            {"text": token.text, "reason": token.reason} for token in decoded.discarded
        ],
        "alternatives": list(decoded.alternatives),
    }


def _encode_item(item: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    item_context = _item_context(item, context)
    sizes = _prepare_chart_sizes(
        _parse_sizes(item.get("sizes")),
        context["preferred_regions"],
        demographic=item_context["demographic"],
        brand_name=item_context["brand_name"],
        product_type=item_context["product_type"],
    )
    description_format = item.get("format")
    if description_format == "":
        description_format = None
    if description_format is not None and not isinstance(description_format, str):
        raise TypeError("format must be a string.")
    encoded = encode_size_description(
        sizes,
        context["source_region"],
        preferred_regions=context["preferred_regions"] or None,
        product_type=item_context["product_type"],
        format=description_format,
    )
    return {
        "text": encoded.text,
        "format_id": encoded.format_id,
        "confidence": encoded.confidence,
        "used": [
            _size_payload(
                size,
                preferred=context["preferred_regions"],
                demographic=item_context["demographic"],
                brand_name=item_context["brand_name"],
                product_type=item_context["product_type"],
            )
            for size in encoded.used
        ],
        "discarded": [
            {"text": token.text, "reason": token.reason} for token in encoded.discarded
        ],
    }


def _batch(
    request: HttpRequest,
    handle: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
) -> JsonResponse:
    if not _active_user(request):
        return _error("Authentication required.", status=403)
    try:
        payload = json.loads(request.body or b"")
    except json.JSONDecodeError:
        return _error("Expected a JSON object.")
    if not isinstance(payload, dict):
        return _error("Expected a JSON object.")
    items = payload.get("items")
    if not isinstance(items, list):
        return _error("items must be a list.")
    if len(items) > BATCH_LIMIT:
        return _error(f"A batch can contain at most {BATCH_LIMIT} items.")
    try:
        context = _request_context(payload)
    except (TypeError, ValueError) as exc:
        return _error(str(exc))
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            results.append({"error": "Each item must be an object."})
            continue
        try:
            results.append(handle(item, context))
        except (TypeError, ValueError) as exc:
            results.append({"error": str(exc)})
    return JsonResponse({"results": results})


@csrf_protect
@require_POST
def decode_size_descriptions(request: HttpRequest) -> JsonResponse:
    """Read up to 500 feed size strings.

    ``source_region`` and ``preferred_regions`` are request-level.
    ``preferred_regions`` adds a ``regions`` list on each size, converted
    into those regions. Chart conversion uses the request's ``age_group``
    and ``gender`` unless the item sets its own.
    """
    return _batch(request, _decode_item)


@csrf_protect
@require_POST
def encode_size_descriptions(request: HttpRequest) -> JsonResponse:
    """Join up to 500 groups of sizes into feed strings.

    Chart sizes are converted to the first ``preferred_regions`` entry before
    encoding, when a demographic is available. The same list is returned on
    each used size.
    """
    return _batch(request, _encode_item)
