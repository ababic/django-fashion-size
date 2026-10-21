"""Batch encode and decode endpoints for size description strings."""

import json
import sys
import types

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        DATABASES={
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
        },
        INSTALLED_APPS=["django_fashion_size"],
        SECRET_KEY="test",
        USE_I18N=True,
        LANGUAGE_CODE="en-gb",
    )
    django.setup()

import pytest
from django.test import RequestFactory
from django.test.utils import override_settings
from django.urls import Resolver404, include, path, resolve, reverse

from django_fashion_size.description_api import (
    BATCH_LIMIT,
    decode_size_descriptions,
    encode_size_descriptions,
)


class _User:
    def __init__(self, *, authenticated: bool, active: bool = True) -> None:
        self.is_authenticated = authenticated
        self.is_active = active


def _post(view, payload, *, user=None, csrf: bool = False):
    request = RequestFactory().post(
        "/size-description-decode/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    request.user = user if user is not None else _User(authenticated=True)
    if not csrf:
        request._dont_enforce_csrf_checks = True
    return view(request)


def _body(response) -> dict:
    return json.loads(response.content)


def test_anonymous_and_inactive_users_are_rejected() -> None:
    payload = {"source_region": "uk", "items": [{"value": "UK 10"}]}
    anonymous = _post(decode_size_descriptions, payload, user=_User(authenticated=False))
    inactive = _post(
        decode_size_descriptions,
        payload,
        user=_User(authenticated=True, active=False),
    )
    assert anonymous.status_code == 403
    assert inactive.status_code == 403
    assert _body(anonymous)["error"] == "Authentication required."


def test_post_without_a_csrf_token_is_rejected() -> None:
    response = _post(
        decode_size_descriptions,
        {"source_region": "uk", "items": [{"value": "UK 10"}]},
        csrf=True,
    )
    assert response.status_code == 403


def test_source_region_is_read_once_for_the_batch() -> None:
    response = _post(
        decode_size_descriptions,
        {
            "source_region": "UK",
            "items": [
                {"value": "10", "product_type": "dresses", "source_region": "eu"},
                {"value": "12", "product_type": "dresses"},
            ],
        },
    )
    assert response.status_code == 200, response.content
    results = _body(response)["results"]
    assert [size["size_unit"] for size in results[0]["sizes"]] == ["uk-dress-size"]
    assert results[0]["sizes"][0]["raw"] == "10"
    assert results[1]["sizes"][0]["raw"] == "12"
    assert results[1]["sizes"][0]["size_unit"] == "uk-dress-size"
    assert "regions" not in results[0]["sizes"][0]


def test_preferred_regions_convert_chart_and_length_sizes() -> None:
    response = _post(
        decode_size_descriptions,
        {
            "source_region": "uk",
            "preferred_regions": ["eu", "us"],
            "age_group": "adult",
            "gender": "female",
            "items": [
                {"value": "UK 10", "product_type": "dresses"},
                {"value": "10in", "product_type": "shorts"},
            ],
        },
    )
    assert response.status_code == 200, response.content
    dress, length = _body(response)["results"]
    assert dress["sizes"][0]["raw"] == "10"
    assert dress["sizes"][0]["size_unit"] == "uk-dress-size"
    regions = {item["region"]: item for item in dress["sizes"][0]["regions"]}
    assert regions["eu"]["raw"] == "38"
    assert regions["eu"]["size_unit"] == "eu-dress-size"
    assert regions["us"]["raw"] == "6"
    assert regions["us"]["size_unit"] == "us-dress-size"
    converted = {item["region"]: item for item in length["sizes"][0]["regions"]}
    assert converted["eu"]["size_unit"] == "cm-inside-leg"
    assert converted["eu"]["raw"] == "25.4"
    assert converted["us"]["size_unit"] == "in-inside-leg"
    assert converted["us"]["raw"] == "10"


def test_chart_conversion_without_a_demographic_reports_the_gap() -> None:
    response = _post(
        decode_size_descriptions,
        {
            "source_region": "uk",
            "preferred_regions": ["eu"],
            "items": [{"value": "UK 10", "product_type": "dresses"}],
        },
    )
    assert response.status_code == 200, response.content
    region = _body(response)["results"][0]["sizes"][0]["regions"][0]
    assert region["region"] == "eu"
    assert "age_group and gender" in region["error"]


def test_encode_converts_to_the_first_preferred_region() -> None:
    response = _post(
        encode_size_descriptions,
        {
            "source_region": "uk",
            "preferred_regions": ["eu", "us"],
            "age_group": "adult",
            "gender": "female",
            "items": [
                {
                    "product_type": "dresses",
                    "sizes": [{"raw": "10", "size_unit": "uk-dress-size"}],
                },
                {
                    "product_type": "shorts",
                    "sizes": [{"raw": "10", "size_unit": "in-shorts-inseam"}],
                },
            ],
        },
    )
    assert response.status_code == 200, response.content
    dress, shorts = _body(response)["results"]
    assert dress["text"] == "EU 38"
    assert dress["used"][0]["size_unit"] == "eu-dress-size"
    regions = {item["region"]: item for item in dress["used"][0]["regions"]}
    assert regions["eu"]["raw"] == "38"
    assert regions["us"]["raw"] == "6"
    assert shorts["text"] == "25cm"
    assert shorts["used"][0]["size_unit"] == "cm-shorts-inseam"
    assert shorts["used"][0]["raw"] == "25.4"


def test_one_bad_item_does_not_reject_the_batch() -> None:
    response = _post(
        decode_size_descriptions,
        {
            "source_region": "uk",
            "items": [
                {"value": "UK 10", "product_type": "not-a-product"},
                {"value": "M"},
                "nope",
            ],
        },
    )
    assert response.status_code == 200, response.content
    first, second, third = _body(response)["results"]
    assert "product_type" in first["error"]
    assert second["sizes"][0]["size_unit"] == "letter"
    assert second["sizes"][0]["raw"] == "M"
    assert third["error"] == "Each item must be an object."


def test_request_level_errors_reject_the_batch() -> None:
    missing = _post(decode_size_descriptions, {"items": []})
    assert missing.status_code == 400
    assert "source_region" in _body(missing)["error"]
    too_many = _post(
        encode_size_descriptions,
        {
            "source_region": "uk",
            "items": [{"sizes": [{"raw": "10", "size_unit": "uk-dress-size"}]}] * (BATCH_LIMIT + 1),
        },
    )
    assert too_many.status_code == 400
    assert "500" in _body(too_many)["error"]
    empty_items = _post(
        decode_size_descriptions,
        {"source_region": "fr", "items": []},
    )
    assert empty_items.status_code == 200
    assert _body(empty_items)["results"] == []
    not_json = RequestFactory().post(
        "/size-description-decode/",
        data="nope",
        content_type="application/json",
    )
    not_json.user = _User(authenticated=True)
    not_json._dont_enforce_csrf_checks = True
    response = decode_size_descriptions(not_json)
    assert response.status_code == 400


def _urlconf(name: str, patterns: list) -> str:
    module = types.ModuleType(name)
    module.urlpatterns = patterns
    sys.modules[name] = module
    return name


def test_urls_stay_unregistered_until_included() -> None:
    empty = _urlconf("empty_description_urls", [])
    mounted = _urlconf(
        "mounted_description_urls",
        [path("", include("django_fashion_size.urls"))],
    )
    with override_settings(ROOT_URLCONF=empty), pytest.raises(Resolver404):
        resolve("/size-description-decode/")
    with override_settings(ROOT_URLCONF=mounted):
        match = resolve("/size-description-decode/")
        assert match.func is decode_size_descriptions
        assert resolve("/size-description-encode/").func is encode_size_descriptions
        assert (
            reverse("django_fashion_size:size-description-decode")
            == "/size-description-decode/"
        )
        assert (
            reverse("django_fashion_size:size-description-encode")
            == "/size-description-encode/"
        )


def test_get_is_not_allowed() -> None:
    request = RequestFactory().get("/size-description-decode/")
    request.user = _User(authenticated=True)
    request._dont_enforce_csrf_checks = True
    response = decode_size_descriptions(request)
    assert response.status_code == 405
