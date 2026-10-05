"""SizeField's form control is an autocomplete backed by fashion-size charts."""

import json
import re

import django
from django import forms
from django.conf import settings

if not settings.configured:
    settings.configure(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        INSTALLED_APPS=["django_fashion_size"],
        SECRET_KEY="test",
        USE_I18N=True,
        LANGUAGE_CODE="en-gb",
    )
    django.setup()

from django.db import models  # noqa: E402

from fashion_size.types import CM_CHEST_SIZE, Size  # noqa: E402

from django_fashion_size import SizeField, SizeFormField, SizeValueWidget  # noqa: E402
from django_fashion_size.model_fields import stored_size_token  # noqa: E402


class Item(models.Model):
    size_unit = models.CharField(max_length=40, blank=True)
    age_group = models.CharField(max_length=20, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    brand = models.CharField(max_length=80, blank=True)
    product_type = models.CharField(max_length=40, blank=True)
    size = SizeField(size_unit_field="size_unit")

    class Meta:
        app_label = "django_fashion_size"


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ["size_unit", "age_group", "gender", "brand", "product_type", "size"]


def _config(form: forms.Form) -> dict:
    html = str(form["size"])
    match = re.search(r'<script id="id_size-config" type="application/json">(.*?)</script>', html)
    assert match, html
    return json.loads(match.group(1))


def test_widget_is_an_autocomplete_not_a_size_select() -> None:
    form = ItemForm(
        initial={
            "size_unit": "uk-dress-size",
            "age_group": "adult",
            "gender": "female",
            "size": "10",
        }
    )
    html = str(form["size"])
    assert 'data-size-value-input="true"' in html
    assert "<select" not in html
    assert 'aria-autocomplete' not in html
    config = _config(form)
    eu = config["units"]["uk-dress-size"]["values"]["eu"]
    ten = next(item for item in eu if item["stored"] == "10")
    assert ten["input"] == "38"
    assert config["charts"]["dress"]["rows"]
    assert form["size"].field.widget.media._js == ["django_fashion_size/size_value_field.js"]


def test_typed_eu_size_posts_the_uk_token() -> None:
    form = ItemForm(
        data={
            "size_unit": "uk-dress-size",
            "age_group": "adult",
            "gender": "female",
            "size": "10",
            "size__active": "1",
            "size__entry": "38",
            "size__format": "eu",
            "size__unit": "uk-dress-size",
            "size__age_group": "adult",
            "size__gender": "female",
        }
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["size"] == "10"


def test_off_chart_size_is_rejected() -> None:
    form = ItemForm(
        data={
            "size_unit": "uk-dress-size",
            "age_group": "adult",
            "gender": "female",
            "size__active": "1",
            "size__entry": "99",
            "size__format": "uk",
            "size__unit": "uk-dress-size",
            "size__age_group": "adult",
            "size__gender": "female",
        }
    )
    assert not form.is_valid()
    assert "not on the chart" in form.errors["size"][0]


def test_inches_posted_into_a_centimetre_field() -> None:
    form = ItemForm(
        data={
            "size_unit": "cm-chest-size",
            "size__active": "1",
            "size__entry": "32",
            "size__format": "in",
            "size__unit": "cm-chest-size",
        }
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["size"] == "81.28"
    assert stored_size_token(Size.from_raw("81.28", CM_CHEST_SIZE)) == "81.28"


def test_brand_chart_is_embedded() -> None:
    form = ItemForm(
        initial={
            "size_unit": "uk-adult-shoe-size",
            "age_group": "adult",
            "gender": "female",
            "brand": "Dune London",
            "product_type": "shoes",
        }
    )
    config = _config(form)
    chart = config["charts"]["adult-shoe"]
    assert "dunelondon.com" in chart["source"]
    assert chart["origin"] == "brand"


def test_model_field_uses_the_autocomplete_widget() -> None:
    field = Item._meta.get_field("size").formfield()
    assert isinstance(field, SizeFormField)
    assert isinstance(field.widget, SizeValueWidget)


if __name__ == "__main__":
    test_widget_is_an_autocomplete_not_a_size_select()
    test_typed_eu_size_posts_the_uk_token()
    test_off_chart_size_is_rejected()
    test_inches_posted_into_a_centimetre_field()
    test_brand_chart_is_embedded()
    test_model_field_uses_the_autocomplete_widget()
    print("ok")
