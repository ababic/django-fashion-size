"""SizeTypeField stores a slug and returns a SizeType."""

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
from django.db import models
from fashion_size.types import SIZE_TYPE_BY_SLUG, SIZE_TYPES, SizeType

from django_fashion_size import SizeTypeField, SizeTypeFormField, SizeTypeSlug


class Attribute(models.Model):
    size_type = SizeTypeField()

    class Meta:
        app_label = "django_fashion_size"


class AttributeForm(forms.ModelForm):
    class Meta:
        model = Attribute
        fields = ["size_type"]


def test_to_python_returns_the_size_type() -> None:
    field = Attribute._meta.get_field("size_type")
    assert isinstance(field, SizeTypeField)
    dress = field.to_python("dress")
    assert dress is SIZE_TYPE_BY_SLUG["dress"]
    assert isinstance(dress, SizeType)
    assert dress.slug == "dress"
    assert dress.label == "Dress size"
    assert field.to_python(dress) is dress
    assert field.to_python(SizeTypeSlug.ADULT_SHOE) is SIZE_TYPE_BY_SLUG["adult-shoe"]
    assert field.to_python("  CHEST  ") is SIZE_TYPE_BY_SLUG["chest"]
    assert field.to_python("") is None
    assert field.to_python(None) is None
    assert (
        field.from_db_value("kids-shoe", None, None) is SIZE_TYPE_BY_SLUG["kids-shoe"]
    )
    assert field.from_db_value("", None, None) is None


def test_unknown_slug_is_rejected() -> None:
    field = Attribute._meta.get_field("size_type")
    try:
        field.to_python("not-a-size-type")
    except ValidationError as exc:
        assert "not-a-size-type" in str(exc)
    else:
        raise AssertionError("expected ValidationError")
    item = Attribute()
    try:
        field.clean("not-a-size-type", item)
    except ValidationError:
        pass
    else:
        raise AssertionError("expected ValidationError")


def test_prep_value_and_pre_save_store_the_slug() -> None:
    field = Attribute._meta.get_field("size_type")
    dress = SIZE_TYPE_BY_SLUG["dress"]
    assert field.get_prep_value(dress) == "dress"
    assert field.get_prep_value("adult-shoe") == "adult-shoe"
    assert field.get_prep_value("") == ""
    assert field.get_prep_value(None) == ""
    item = Attribute(size_type="eu-dress-size")
    try:
        field.pre_save(item, add=True)
    except ValidationError:
        pass
    else:
        raise AssertionError("expected ValidationError")
    item.size_type = "waist-size"
    assert field.pre_save(item, add=True) == "waist-size"
    assert item.size_type is SIZE_TYPE_BY_SLUG["waist-size"]
    item.size_type = None
    assert field.pre_save(item, add=False) == ""
    assert item.size_type is None


def test_clean_accepts_a_size_type_or_slug() -> None:
    field = Attribute._meta.get_field("size_type")
    item = Attribute()
    assert field.clean("dress", item) is SIZE_TYPE_BY_SLUG["dress"]
    assert field.clean(SIZE_TYPE_BY_SLUG["collar"], item) is SIZE_TYPE_BY_SLUG["collar"]
    assert field.clean("", item) is None
    item.size_type = "inside-leg"
    item.full_clean()
    assert item.size_type is SIZE_TYPE_BY_SLUG["inside-leg"]


def test_form_field_posts_a_slug_and_cleans_to_a_size_type() -> None:
    field = Attribute._meta.get_field("size_type")
    form_field = field.formfield()
    assert isinstance(form_field, SizeTypeFormField)
    assert form_field.prepare_value(SIZE_TYPE_BY_SLUG["dress"]) == "dress"
    values = [value for value, _label in form_field.choices if value]
    assert values == [str(size_type.slug) for size_type in SIZE_TYPES]
    form = AttributeForm(data={"size_type": "cup-size"})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["size_type"] is SIZE_TYPE_BY_SLUG["cup-size"]
    blank = AttributeForm(data={"size_type": ""})
    assert blank.is_valid(), blank.errors
    assert blank.cleaned_data["size_type"] in ("", None)
    invalid = AttributeForm(data={"size_type": "dress-size"})
    assert not invalid.is_valid()
    assert "size_type" in invalid.errors


def test_deconstruct_drops_defaults() -> None:
    _name, path, _args, kwargs = SizeTypeField().deconstruct()
    assert path.endswith("SizeTypeField")
    assert kwargs == {}
    _name, _path, _args, custom = SizeTypeField(
        blank=False, max_length=32
    ).deconstruct()
    assert custom["blank"] is False
    assert custom["max_length"] == 32
    assert "choices" not in custom
    assert max(len(str(size_type.slug)) for size_type in SIZE_TYPES) <= 40
