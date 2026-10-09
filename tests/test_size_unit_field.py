"""SizeUnitField stores a slug, returns a SizeUnit, and lists translated units."""

import django
from django import forms
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

from django.core.exceptions import ValidationError
from django.db import connection, models
from django.utils.functional import Promise
from fashion_size.types import SIZE_UNIT_BY_SLUG, Size, SizeUnit, size_unit_choices

from django_fashion_size import (
    CUSTOM_SIZE_UNIT,
    CustomSizeUnit,
    SizeUnitField,
    SizeUnitFormField,
    SizeUnitSlug,
)


class Garment(models.Model):
    size_unit = SizeUnitField()

    class Meta:
        app_label = "django_fashion_size"


class GarmentForm(forms.ModelForm):
    class Meta:
        model = Garment
        fields = ["size_unit"]


def test_labels_match_fashion_size_and_are_translatable() -> None:
    assert [member.value for member in SizeUnitSlug] == [
        slug for slug, _label in size_unit_choices()
    ]
    assert [str(member.label) for member in SizeUnitSlug] == [
        label for _slug, label in size_unit_choices()
    ]
    assert all(isinstance(member.label, Promise) for member in SizeUnitSlug)
    assert SizeUnitSlug.UK_DRESS_SIZE == "uk-dress-size"
    assert str(SizeUnitSlug.UK_DRESS_SIZE.label) == "UK Dress size"
    assert str(SizeUnitSlug.CM_CHEST_SIZE.label) == "Chest (centimetres)"


def test_field_ignores_supplied_choices() -> None:
    field = SizeUnitField(choices=[("nope", "Nope")])
    assert isinstance(field, SizeUnitField)
    assert [value for value, _label in field.choices] == list(SizeUnitSlug.values)
    form_field = field.formfield()
    assert isinstance(form_field, SizeUnitFormField)
    shown = [value for value, _label in form_field.choices if value]
    assert shown == list(SizeUnitSlug.values)
    assert "nope" not in shown
    assert (
        form_field.prepare_value(SIZE_UNIT_BY_SLUG["eu-dress-size"]) == "eu-dress-size"
    )
    _name, path, _args, kwargs = SizeUnitField().deconstruct()
    assert path.endswith("SizeUnitField")
    assert "choices" not in kwargs


def test_clean_returns_a_size_unit() -> None:
    field = Garment._meta.get_field("size_unit")
    garment = Garment()
    assert field.clean("uk-dress-size", garment) is SIZE_UNIT_BY_SLUG["uk-dress-size"]
    assert (
        field.clean(SIZE_UNIT_BY_SLUG["cm-chest-size"], garment)
        is SIZE_UNIT_BY_SLUG["cm-chest-size"]
    )
    assert field.clean("", garment) is None
    assert isinstance(field.to_python("in-collar-size"), SizeUnit)
    try:
        field.clean("dress", garment)
    except ValidationError as exc:
        assert "dress" in str(exc)
    else:
        raise AssertionError("expected ValidationError")


def test_custom_is_off_unless_the_field_opts_in() -> None:
    field = SizeUnitField()
    assert field.allow_custom is False
    garment = Garment()
    try:
        field.clean("custom", garment)
    except ValidationError as exc:
        assert "custom" in str(exc)
    else:
        raise AssertionError("expected ValidationError")
    form_field = field.formfield()
    assert form_field.allow_custom is False
    assert "custom" not in [value for value, _label in form_field.choices if value]
    _name, path, _args, kwargs = field.deconstruct()
    assert path.endswith("SizeUnitField")
    assert "allow_custom" not in kwargs
    assert "choices" not in kwargs


class CustomGarment(models.Model):
    size_unit = SizeUnitField(allow_custom=True)

    class Meta:
        app_label = "django_fashion_size"


def test_allow_custom_stores_custom_and_returns_custom_size_unit() -> None:
    field = CustomGarment._meta.get_field("size_unit")
    assert field.allow_custom is True
    garment = CustomGarment()
    cleaned = field.clean("custom", garment)
    assert cleaned is CUSTOM_SIZE_UNIT
    assert isinstance(cleaned, CustomSizeUnit)
    assert cleaned.slug == "custom"
    assert field.clean("CUSTOM", garment) is CUSTOM_SIZE_UNIT
    assert field.get_prep_value(cleaned) == "custom"
    assert field.to_python("custom") is CUSTOM_SIZE_UNIT
    form_field = field.formfield()
    assert form_field.allow_custom is True
    assert form_field.clean("custom") is CUSTOM_SIZE_UNIT
    assert form_field.prepare_value(CUSTOM_SIZE_UNIT) == "custom"
    labels = [(value, str(label)) for value, label in form_field.choices if value]
    assert ("custom", "Custom") in labels
    html = str(form_field.widget.render("size_unit", "custom"))
    assert 'value="custom"' in html
    assert cleaned.can_convert_to(SIZE_UNIT_BY_SLUG["uk-dress-size"]) is False
    try:
        Size.from_raw("10", cleaned)
    except TypeError as exc:
        assert "cannot be converted" in str(exc)
    else:
        raise AssertionError("expected TypeError")
    _name, _path, _args, kwargs = field.deconstruct()
    assert kwargs.get("allow_custom") is True
    assert "choices" not in kwargs
    with connection.schema_editor() as editor:
        editor.create_model(CustomGarment)
    saved = CustomGarment.objects.create(size_unit="custom")
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT size_unit FROM {CustomGarment._meta.db_table} WHERE id = %s",
            [saved.pk],
        )
        stored = cursor.fetchone()[0]
    assert stored == "custom"
    assert CustomGarment.objects.get(pk=saved.pk).size_unit is CUSTOM_SIZE_UNIT


def test_model_form_saves_the_posted_slug() -> None:
    with connection.schema_editor() as editor:
        editor.create_model(Garment)
    garment = Garment.objects.create(size_unit="uk-dress-size")
    form = GarmentForm(data={"size_unit": "eu-dress-size"}, instance=garment)
    assert form.is_valid(), form.errors
    assert form.cleaned_data["size_unit"] is SIZE_UNIT_BY_SLUG["eu-dress-size"]
    form.save()
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT size_unit FROM {Garment._meta.db_table} WHERE id = %s",
            [garment.pk],
        )
        stored = cursor.fetchone()[0]
    assert stored == "eu-dress-size"
    assert (
        Garment.objects.get(pk=garment.pk).size_unit
        is SIZE_UNIT_BY_SLUG["eu-dress-size"]
    )
