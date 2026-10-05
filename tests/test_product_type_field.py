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

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import Promise
from fashion_size.product_types import ProductType

from django_fashion_size import FashionProductType, FashionProductTypeField, FashionProductTypeFormField
from django_fashion_size.model_fields import PRODUCT_TYPE_MAX_LENGTH, product_type_choices


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


def test_fashion_product_type_mirrors_product_type_with_translatable_labels() -> None:
    assert [member.value for member in FashionProductType] == [member.value for member in ProductType]
    assert [str(member.label) for member in FashionProductType] == [member.label for member in ProductType]
    assert all(isinstance(member.label, Promise) for member in FashionProductType)
    assert FashionProductType.SHOES == "shoes"
    assert str(FashionProductType.SHOES.label) == "Shoes"


def test_model_field_returns_product_type_or_none() -> None:
    field = CatalogItem._meta.get_field("product_type")
    assert isinstance(field, FashionProductTypeField)
    assert field.choices is None
    assert field.to_python("shoes") is ProductType.SHOES
    assert field.to_python(ProductType.SHOES) is ProductType.SHOES
    assert field.to_python(FashionProductType.SHOES) is ProductType.SHOES
    assert field.to_python("") is None
    assert field.to_python(None) is None
    assert field.to_python("not-a-product") is None
    assert field.from_db_value("shoes", None, None) is ProductType.SHOES
    assert field.from_db_value("", None, None) is None
    assert field.from_db_value("not-a-product", None, None) is None
    assert field.get_prep_value("shoes") == "shoes"
    assert field.get_prep_value(ProductType.SHOES) == "shoes"
    assert field.get_prep_value("") == ""
    assert field.get_prep_value("not-a-product") == ""


def test_form_field_prepares_a_product_type_as_its_slug() -> None:
    field = FashionProductTypeFormField()
    assert field.prepare_value(ProductType.SHOES) == "shoes"
    assert field.prepare_value("shoes") == "shoes"
    assert field.prepare_value("") == ""


def test_form_field_options_match_product_type() -> None:
    field = FashionProductTypeFormField()
    expected = product_type_choices()
    assert list(field.choices) == expected
    assert ("shoes", "Shoes") in [(value, str(label)) for value, label in field.choices]
    assert len(field.choices) == len(FashionProductType)


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
    assert values[1:] == [product_type.value for product_type in FashionProductType]


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


def test_deconstruct_keeps_max_length_and_omits_choices() -> None:
    field = FashionProductTypeField()
    _name, path, _args, kwargs = field.deconstruct()
    assert path.endswith("FashionProductTypeField")
    assert kwargs["max_length"] == PRODUCT_TYPE_MAX_LENGTH
    assert "choices" not in kwargs
    assert max(len(member.value) for member in FashionProductType) < PRODUCT_TYPE_MAX_LENGTH


def test_model_field_rejects_unknown_product_type() -> None:
    field = CatalogItem._meta.get_field("product_type")
    item = CatalogItem()
    assert field.clean("shoes", item) is ProductType.SHOES
    assert field.clean(ProductType.SHOES, item) is ProductType.SHOES
    assert field.clean(FashionProductType.SHOES, item) is ProductType.SHOES
    assert field.clean("", item) is None
    try:
        field.clean("not-a-product", item)
    except ValidationError as exc:
        assert exc.code == "invalid_choice"
        assert "not-a-product" in str(exc)
    else:
        raise AssertionError("expected ValidationError")
    item.product_type = "not-a-product"
    try:
        item.full_clean()
    except ValidationError as exc:
        assert "product_type" in exc.message_dict
        assert exc.message_dict["product_type"][0]
    else:
        raise AssertionError("expected ValidationError")


def test_model_form_validates_posted_slug() -> None:
    valid = CatalogItemForm(data={"product_type": "shoes"})
    assert valid.is_valid(), valid.errors
    assert valid.cleaned_data["product_type"] == "shoes"
    invalid = CatalogItemForm(data={"product_type": "not-a-product"})
    assert not invalid.is_valid()
    assert "product_type" in invalid.errors


if __name__ == "__main__":
    test_fashion_product_type_mirrors_product_type_with_translatable_labels()
    test_model_field_returns_product_type_or_none()
    test_form_field_prepares_a_product_type_as_its_slug()
    test_form_field_options_match_product_type()
    test_form_field_ignores_supplied_and_assigned_choices()
    test_optional_form_field_includes_a_blank_option()
    test_model_formfield_uses_the_product_type_form_field()
    test_model_field_ignores_constructor_choices()
    test_deconstruct_keeps_max_length_and_omits_choices()
    test_model_field_rejects_unknown_product_type()
    test_model_form_validates_posted_slug()
    print("ok")
