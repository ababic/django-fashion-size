# django-fashion-size

Django fields for [`fashion-size`](https://github.com/ababic/fashion-size).

`SizeUnitField` stores which size unit a column is (`uk-dress-size`). Reading it returns a `SizeUnit`.

`SizeField` stores the size token (`10`, `7.5`, `DD`). Pass `size_unit_field` pointing at a `SizeUnitField` on this model or a related one (`"size_unit"`, `"attribute.size_unit"`). Reading it returns a `Size`; call `.convert()` on that value.

The source repository is [github.com/ababic/django-fashion-size](https://github.com/ababic/django-fashion-size). It depends on [`fashion-size`](https://github.com/ababic/fashion-size) 0.1 or newer.

```bash
pip install django-fashion-size
```

A release is a `vX.Y.Z` tag matching the version in `pyproject.toml`. Building the package compiles the size field's CSS and JavaScript from `frontend/` into the static files the widget serves. That compile step runs in the release workflow, and it needs Node.js when you build from this repository. An install from PyPI uses the compiled files and does not need Node.

```python
from django.db import models

from django_fashion_size.model_fields import SizeField, SizeUnitField


class Attribute(models.Model):
    size_unit = SizeUnitField()


class AttributeValue(models.Model):
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE)
    size = SizeField(size_unit_field="attribute.size_unit")
```

```python
value = attribute_value.size
value.convert("eu", age_group="adult", gender="female")
```

`SizeTypeSlug` is a Django choices enum with the same values as `fashion_size.size_types.SizeTypeSlug`.

Importing this package registers Django's `get_language` as the `fashion-size` display language and makes `Size.display()` use it. English lengths render as `32"` and `81cm`; other languages render as `32 in` and `81 cm`. `UK 10` and `DD` stay the same in every language. Brand-specific conversion is still registered on `fashion-size` (`register_brand_converter`). The model fields do not need this package in `INSTALLED_APPS`.

`SizeField`'s form control is an autocomplete. You type a size and the list shows chart values that start with that text. A short select beside the field chooses the region or unit you are typing (`UK`, `EU`, `in`, `cm`). A "View conversion chart" link to the right of the field opens the conversion chart. The value saved on the model is the token in `size_unit_field` (`10` when the field stores UK dress sizes, even if you typed EU `38`). Add `django_fashion_size` to `INSTALLED_APPS` so the widget's CSS and script are found.

The same control is `SizeFormField`, so a `CharField` such as `AttributeValue.value` can use it without becoming a `SizeField`. Pass the attribute's `SizeUnit` and the brand and product type you already have. `brand_name` is the brand's name. `product_type_name` is the product type's name (`Shoes`) or slug (`shoes`). Age group and gender select the chart.

```python
self.fields["value"] = SizeFormField(
    size_unit=attribute.size_unit,
    brand_name=brand_name,
    product_type_name=product_type_name,
    age_group="adult",
    gender="female",
)
```

Leave those values unset to read them from other fields. A `SizeField` still passes its `size_unit_field`. `brand_name_field` defaults to `brand`, and `product_type_name_field` defaults to `product_type`. Point them at other names when the form uses those:

```python
value = SizeFormField(
    size_unit_field="size_unit",
    brand_name_field="brand_name",
    product_type_name_field="product_type_name",
)
```
