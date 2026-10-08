"""Waist size stays a regional chart, and display renders it as inches or centimetres."""

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
    AU_WAIST_SIZE,
    EU_WAIST_SIZE,
    UK_CHEST_SIZE,
    UK_DRESS_SIZE,
    UK_WAIST_SIZE,
    US_WAIST_SIZE,
    Size,
)

import django_fashion_size  # noqa: F401


def test_uk_us_and_au_waist_sizes_display_as_inches() -> None:
    uk = Size.from_raw(30, UK_WAIST_SIZE)
    us = Size.from_raw(30, US_WAIST_SIZE)
    au = Size.from_raw(30, AU_WAIST_SIZE)
    assert uk.display() == '30"'
    assert uk.localised_display("en-gb") == '30"'
    assert uk.localised_display("fr") == "30 in"
    assert us.localised_display("de") == "30 in"
    assert au.display() == '30"'
    assert uk.raw == 30


def test_eu_waist_size_displays_as_centimetres() -> None:
    eu = Size.from_raw(46, EU_WAIST_SIZE)
    assert eu.display() == "46cm"
    assert eu.localised_display("en-gb") == "46cm"
    assert eu.localised_display("de") == "46 cm"
    assert eu.raw == 46


def test_waist_conversion_stays_on_the_regional_chart() -> None:
    uk = Size.from_raw(30, UK_WAIST_SIZE)
    converted = uk.convert_to_locale(
        "eu",
        demographic=Demographic(age_group="adult", gender="male"),
    )
    assert converted.raw == 46
    assert converted.size.size_unit.slug == "eu-waist-size"
    assert converted.display() == "46cm"


def test_other_size_types_keep_their_display() -> None:
    assert Size.from_raw(10, UK_DRESS_SIZE).display() == "UK 10"
    assert Size.from_raw(38, UK_CHEST_SIZE).display() == "UK 38"
