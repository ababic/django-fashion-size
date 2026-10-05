# django-fashion-size

Django fields for [`fashion-size`](https://github.com/ababic/fashion-size).

`SizeUnitField` stores which size unit a column is (`uk-dress-size`). Reading it returns a `SizeUnit`.

`SizeField` stores the size token (`10`, `7.5`, `DD`). Pass `size_unit_field` pointing at a `SizeUnitField` on this model or a related one (`"size_unit"`, `"attribute.size_unit"`). Reading it returns a `Size`; call `.convert()` on that value.

The source repository is [github.com/ababic/django-fashion-size](https://github.com/ababic/django-fashion-size). It depends on [`fashion-size`](https://github.com/ababic/fashion-size). PyPI packaging comes later.

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

`SizeField`'s form control is an autocomplete. You type a size and the list shows chart values that start with that text. A short select beside the field chooses the region or unit you are typing (`UK`, `EU`, `in`, `cm`). A "View conversion chart" link to the right of the field opens the conversion chart. The value saved on the model is the token in `size_unit_field` (`10` when the field stores UK dress sizes, even if you typed EU `38`). Add `django_fashion_size` to `INSTALLED_APPS` so the widget's CSS and script are found. Age group and gender come from the form or the instance (`age_group`, `gender`); a brand name and product type (`brand`, `product_type`) pick a brand chart when one exists.
