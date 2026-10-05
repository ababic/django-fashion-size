"""FashionProductTypeField stores a slug; its form field lists ProductType options."""

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
from fashion_size.product_types import ProductType

from django_fashion_size import FashionProductTypeField, FashionProductTypeFormField
from django_fashion_size.model_fields import product_type_choices


class CatalogItem(models.Model):
    product_type = FashionProductTypeField(blank=True)

    class Meta:
        app_label = "django_fashion_size"


class CatalogItemForm(forms.ModelForm):
    class Meta:
        model = CatalogItem
        fields = ["product_type"]


def _choice_values(field: forms.ChoiceField) -> list[str]:
    return [value for value, _label in field.choices]


def test_model_field_is_a_charfield_and_stores_the_slug() -> None:
    field = CatalogItem._meta.get_field("product_type")
    assert isinstance(field, FashionProductTypeField)
    assert field.choices is None
    assert field.to_python("shoes") == "shoes"
    assert field.to_python(ProductType.SHOES) == ProductType.SHOES
    assert field.get_prep_value("shoes") == "shoes"


def test_form_field_options_match_product_type() -> None:
    field = FashionProductTypeFormField()
    expected = product_type_choices()
    assert list(field.choices) == expected
    assert ("shoes", "Shoes") in field.choices
    assert len(field.choices) == len(list(ProductType))


def test_form_field_ignores_supplied_and_assigned_choices() -> None:
    field = FashionProductTypeFormField(choices=[("nope", "Nope")])
    assert "nope" not in _choice_values(field)
    assert "shoes" in _choice_values(field)
    field.choices = [("still-nope", "Still nope")]
    assert "still-nope" not in _choice_values(field)
    assert list(field.choices) == product_type_choices()


def test_optional_form_field_includes_a_blank_option() -> None:
    field = FashionProductTypeFormField(required=False)
    values = _choice_values(field)
    assert values[0] == ""
    assert values[1:] == [product_type.value for product_type in ProductType]


def test_model_formfield_uses_the_product_type_form_field() -> None:
    form_field = CatalogItem._meta.get_field("product_type").formfield()
    assert isinstance(form_field, FashionProductTypeFormField)
    assert "shoes" in _choice_values(form_field)
    assert _choice_values(form_field)[0] == ""


def test_model_field_ignores_constructor_choices() -> None:
    field = FashionProductTypeField(choices=[("nope", "Nope")])
    assert field.choices is None
    form_field = field.formfield()
    assert isinstance(form_field, FashionProductTypeFormField)
    assert "nope" not in _choice_values(form_field)
    assert "jeans" in _choice_values(form_field)


def test_deconstruct_omits_default_max_length_and_choices() -> None:
    field = FashionProductTypeField()
    _name, path, _args, kwargs = field.deconstruct()
    assert path.endswith("FashionProductTypeField")
    assert "max_length" not in kwargs
    assert "choices" not in kwargs


def test_model_form_validates_posted_slug() -> None:
    valid = CatalogItemForm(data={"product_type": "shoes"})
    assert valid.is_valid(), valid.errors
    assert valid.cleaned_data["product_type"] == "shoes"
    invalid = CatalogItemForm(data={"product_type": "not-a-product"})
    assert not invalid.is_valid()
    assert "product_type" in invalid.errors


if __name__ == "__main__":
    test_model_field_is_a_charfield_and_stores_the_slug()
    test_form_field_options_match_product_type()
    test_form_field_ignores_supplied_and_assigned_choices()
    test_optional_form_field_includes_a_blank_option()
    test_model_formfield_uses_the_product_type_form_field()
    test_model_field_ignores_constructor_choices()
    test_deconstruct_omits_default_max_length_and_choices()
    test_model_form_validates_posted_slug()
    print("ok")
