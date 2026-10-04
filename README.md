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

Brand-specific conversion and display language are registered on `fashion-size` (`register_brand_converter`, `register_display_language`). This package does not need to be in `INSTALLED_APPS` when the host app registers those hooks.
