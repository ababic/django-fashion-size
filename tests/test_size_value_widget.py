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

from django.db import models

from fashion_size.types import CM_CHEST_SIZE, Size, UK_ADULT_SHOE_SIZE

from django_fashion_size import SizeField, SizeFormField, SizeValueWidget
from django_fashion_size.model_fields import stored_size_token


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


def _config(form: forms.Form, name: str = "size") -> dict:
    html = str(form[name])
    match = re.search(
        rf'<script id="id_{name}-config" type="application/json">(.*?)</script>',
        html,
    )
    assert match, html
    return json.loads(match.group(1))


class StoredValueForm(forms.Form):
    """A char column, with the size unit and names supplied to the field."""

    value = SizeFormField(
        size_unit=UK_ADULT_SHOE_SIZE,
        brand_name="Dune London",
        product_type_name="Shoes",
        age_group="adult",
        gender="female",
    )


class LinkedNameForm(forms.Form):
    """The same char column, reading the unit and names from sibling fields."""

    value = SizeFormField(
        size_unit_field="size_unit",
        brand_name_field="brand_name",
        product_type_name_field="product_type_name",
    )
    size_unit = forms.CharField(required=False)
    brand_name = forms.CharField(required=False)
    product_type_name = forms.CharField(required=False)
    age_group = forms.CharField(required=False)
    gender = forms.CharField(required=False)


def test_waist_size_keeps_the_region_select() -> None:
    form = ItemForm(
        initial={
            "size_unit": "uk-waist-size",
            "age_group": "adult",
            "gender": "male",
            "size": "30",
        }
    )
    measurement = _config(form)["units"]["uk-waist-size"]["measurement"]
    assert measurement["length"] is False
    assert measurement["storage_format"] == "uk"
    assert measurement["format_side"] == "left"
    assert [item["value"] for item in measurement["formats"]] == ["uk", "eu", "us", "au"]


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
    assert config["brandField"] == "brand"
    assert config["productTypeField"] == "product_type"


def test_charfield_accepts_a_size_unit_brand_name_and_product_type_name() -> None:
    form = StoredValueForm(initial={"value": "5"})
    config = _config(form, "value")
    assert config["initialUnit"] == "uk-adult-shoe-size"
    assert config["brand"] == "Dune London"
    assert config["productType"] == "shoes"
    assert config["sizeUnitField"] == ""
    assert config["brandField"] == ""
    assert config["productTypeField"] == ""
    chart = config["charts"]["adult-shoe"]
    assert chart["origin"] == "brand"
    assert "dunelondon.com" in chart["source"]
    assert config["units"]["uk-adult-shoe-size"]["context"]["product_type_name"] == "Shoes"
    posted = StoredValueForm(
        data={
            "value__active": "1",
            "value__entry": "38",
            "value__format": "eu",
            "value__unit": "uk-adult-shoe-size",
            "value__age_group": "adult",
            "value__gender": "female",
            "value__brand": "Dune London",
            "value__product_type": "Shoes",
        }
    )
    assert posted.is_valid(), posted.errors
    assert posted.cleaned_data["value"] == "5"


def test_charfield_reads_brand_and_product_type_from_linked_fields() -> None:
    form = LinkedNameForm(
        initial={
            "size_unit": "uk-adult-shoe-size",
            "age_group": "adult",
            "gender": "female",
            "brand_name": "Dune London",
            "product_type_name": "Shoes",
        }
    )
    config = _config(form, "value")
    assert config["initialUnit"] == "uk-adult-shoe-size"
    assert config["brand"] == "Dune London"
    assert config["productType"] == "shoes"
    assert config["sizeUnitField"] == "size_unit"
    assert config["brandField"] == "brand_name"
    assert config["productTypeField"] == "product_type_name"
    assert config["charts"]["adult-shoe"]["origin"] == "brand"


def _cup_form(**data: str) -> ItemForm:
    payload = {
        "size_unit": "uk-cup-size",
        "age_group": "adult",
        "gender": "female",
        "size__active": "1",
        "size__format": "uk",
        "size__unit": "uk-cup-size",
        "size__age_group": "adult",
        "size__gender": "female",
    }
    payload.update(data)
    return ItemForm(data=payload)


def test_cup_suggestions_append_alpha_labels_after_the_letter_chart() -> None:
    form = ItemForm(
        initial={
            "size_unit": "uk-cup-size",
            "age_group": "adult",
            "gender": "female",
        }
    )
    config = _config(form)
    uk = config["units"]["uk-cup-size"]["values"]["uk"]
    labels = [item["input"] for item in uk]
    assert labels.index("K") < labels.index("XXS")
    assert labels[-7:] == ["XXS", "XS", "S", "MD", "LG", "XL", "XXL"]
    medium = next(item for item in uk if item["input"] == "MD")
    assert medium["stored"] == "MD"
    assert "M" not in labels
    assert "L" not in labels
    chart_tokens = {cell for row in config["charts"]["cup-size"]["rows"] for cell in row.values()}
    assert "XXS" not in chart_tokens
    assert "MD" not in chart_tokens
    eu = config["units"]["uk-cup-size"]["values"]["eu"]
    eu_medium = next(item for item in eu if item["input"] == "M")
    assert eu_medium["stored"] == "J"
    alpha = next(item for item in eu if item["input"] == "MD")
    assert alpha["stored"] == "MD"


def test_alpha_cup_alias_posts_the_canonical_token() -> None:
    form = _cup_form(size__entry="medium")
    assert form.is_valid(), form.errors
    assert form.cleaned_data["size"] == "MD"
    large = _cup_form(size__entry="large", size__format="eu")
    assert large.is_valid(), large.errors
    assert large.cleaned_data["size"] == "LG"


def test_single_letter_m_stays_a_cup_letter() -> None:
    uk = _cup_form(size__entry="M")
    assert not uk.is_valid()
    assert "not on the chart" in uk.errors["size"][0]
    eu = _cup_form(size__entry="M", size__format="eu")
    assert eu.is_valid(), eu.errors
    assert eu.cleaned_data["size"] == "J"


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
    test_charfield_accepts_a_size_unit_brand_name_and_product_type_name()
    test_charfield_reads_brand_and_product_type_from_linked_fields()
    test_cup_suggestions_append_alpha_labels_after_the_letter_chart()
    test_alpha_cup_alias_posts_the_canonical_token()
    test_single_letter_m_stays_a_cup_letter()
    test_model_field_uses_the_autocomplete_widget()
    print("ok")
