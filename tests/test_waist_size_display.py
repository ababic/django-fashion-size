"""Measurement display comes from fashion-size; Django supplies the language."""

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

from fashion_size.demographics import Demographic
from fashion_size.types import (
    AU_BAND_SIZE,
    EU_BAND_SIZE,
    EU_WAIST_SIZE,
    UK_BAND_SIZE,
    UK_CHEST_SIZE,
    UK_DRESS_SIZE,
    UK_WAIST_SIZE,
    Size,
)

import django_fashion_size  # noqa: F401


def test_uk_waist_and_chest_display_like_inches() -> None:
    waist = Size.from_raw(30, UK_WAIST_SIZE)
    chest = Size.from_raw(38, UK_CHEST_SIZE)
    assert waist.display() == '30"'
    assert waist.localised_display("de") == "30 in"
    assert chest.display() == '38"'
    assert chest.localised_display("fr") == "38 in"
    assert waist.raw == 30


def test_eu_waist_keeps_its_region_prefix() -> None:
    eu = Size.from_raw(46, EU_WAIST_SIZE)
    assert eu.display() == "EU 46"
    assert eu.localised_display("de") == "EU 46"


def test_band_display_follows_fashion_size() -> None:
    assert Size.from_raw(34, UK_BAND_SIZE).display() == '34"'
    assert Size.from_raw(75, EU_BAND_SIZE).display() == "75cm"
    assert Size.from_raw(75, EU_BAND_SIZE).localised_display("de") == "75 cm"
    assert Size.from_raw(34, AU_BAND_SIZE).display() == "AU 34"


def test_waist_conversion_stays_on_the_regional_chart() -> None:
    converted = Size.from_raw(30, UK_WAIST_SIZE).convert_to_locale(
        "eu",
        demographic=Demographic(age_group="adult", gender="male"),
    )
    assert converted.raw == 46
    assert converted.size.size_unit.slug == "eu-waist-size"
    assert converted.display() == "EU 46"


def test_dress_size_keeps_its_region_prefix() -> None:
    assert Size.from_raw(10, UK_DRESS_SIZE).display() == "UK 10"
