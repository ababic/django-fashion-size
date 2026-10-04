# django-fashion-size

Django fields for [`fashion-size`](https://github.com/ababic/fashion-size).

`MeasurementField` stores which measurement a column is (`uk-dress-size`). Reading it returns a `Measurement`.

`MeasurementValueField` stores the size token (`10`, `7.5`, `DD`). Pass `measurement_field` pointing at a `MeasurementField` on this model or a related one (`"measurement"`, `"attribute.measurement"`). Reading it returns a `MeasurementValue`; call `.convert()` on that value.

The source repository is [github.com/ababic/django-fashion-size](https://github.com/ababic/django-fashion-size). It depends on [`fashion-size`](https://github.com/ababic/fashion-size). PyPI packaging comes later.

```python
from django.db import models

from django_fashion_size.model_fields import MeasurementField, MeasurementValueField


class Attribute(models.Model):
    measurement = MeasurementField()


class AttributeValue(models.Model):
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE)
    size = MeasurementValueField(measurement_field="attribute.measurement")
```

```python
value = attribute_value.size
value.convert("eu", age_group="adult", gender="female")
```

`MeasurementKindSlug` is a Django choices enum with the same values as `fashion_size.kinds.KindSlug`.

Brand-specific conversion and display language are registered on `fashion-size` (`register_brand_converter`, `register_display_language`). This package does not need to be in `INSTALLED_APPS` when the host app registers those hooks.
