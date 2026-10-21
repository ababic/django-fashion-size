# django-fashion-size

[![PyPI](https://img.shields.io/pypi/v/django-fashion-size?label=PyPI)](https://pypi.org/project/django-fashion-size/)
[![Python](https://img.shields.io/pypi/pyversions/django-fashion-size?label=Python)](https://pypi.org/project/django-fashion-size/)
[![Django](https://img.shields.io/badge/Django-6.0%20%7C%206.1-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Release](https://github.com/ababic/django-fashion-size/actions/workflows/release.yml/badge.svg)](https://github.com/ababic/django-fashion-size/actions/workflows/release.yml)

Django fields for [`fashion-size`](https://github.com/ababic/fashion-size).

`SizeTypeField` stores which size type a column is (`dress`, `adult-shoe`). Reading it returns a `SizeType`.

`SizeUnitField` stores which size unit a column is (`uk-dress-size`). Reading it returns a `SizeUnit`.

`SizeField` stores the size token (`10`, `7.5`, `DD`, `MD`). Pass `size_unit_field` pointing at a `SizeUnitField` on this model or a related one (`"size_unit"`, `"attribute.size_unit"`). Reading it returns a `Size`; call `.convert()` on that value.

The source repository is [github.com/ababic/django-fashion-size](https://github.com/ababic/django-fashion-size). It depends on [`fashion-size`](https://github.com/ababic/fashion-size) (CalVer releases on PyPI).

```bash
pip install django-fashion-size
```

Supported Django versions are **6.0** and **6.1** (see `django>=6.0,<7` in `pyproject.toml`). CI runs the test suite against each of those releases and against [Django's `main` branch](https://github.com/django/django/tree/main).

```bash
pip install tox
tox
```

To run a single environment, for example Django 6.0: `tox -e py312-django60`.

Frontend sources live under `frontend/`. Lint and build with `cd frontend && npm ci && npm run lint && npm run build` (then commit any changes under `src/django_fashion_size/static/django_fashion_size/`). CI runs Ruff in `lint.yml` and lint/build checks in `frontend.yml`.

A release is a `vX.Y.Z` tag matching the version in `pyproject.toml`. The release workflow publishes that tag only when the tagged commit is on `main` or a `release-*` branch. Building the package compiles the size field's CSS and JavaScript from `frontend/` into the static files the widget serves. That compile step runs in the release workflow, and it needs Node.js when you build from this repository. An install from PyPI uses the compiled files and does not need Node.

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
from fashion_size.demographics import Demographic

value.convert_to_locale(
    "eu",
    demographic=Demographic(age_group="adult", gender="female"),
)
```

`FashionProductType` is a Django `TextChoices` enum with the same values as `fashion_size.product_types.ProductType`. Its labels are marked for translation (`gettext_lazy`), so `makemessages` can collect them.

`FashionProductTypeField` stores a product-type slug (`shoes`). Reading it returns a `fashion_size.product_types.ProductType`, or `None` when the value is blank or not a known product type. `full_clean` rejects values that are not in `FashionProductType.values`. Its default form field is `FashionProductTypeFormField`, a select whose options always come from `FashionProductType`. Passed `choices` are ignored so the list cannot go stale against `fashion-size`.

`SizeTypeSlug` and `SizeUnitSlug` are Django `TextChoices` enums. Their values match `fashion-size` (`dress`, `uk-dress-size`). Their labels are `gettext_lazy` strings (`Dress size`, `UK Dress size`), so `makemessages` can collect them. `SizeTypeField` and `SizeUnitField` selects always use those labels, in the active language. Passed `choices` are ignored so a stale list cannot replace them. `SizeTypeField` stores one of the size-type slugs and returns the `SizeType`. A blank column reads as `None`. Use it when the attribute is the size type, and each value keeps its own source unit and raw token:

```python
class Attribute(models.Model):
    size_type = SizeTypeField()


class AttributeValue(models.Model):
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE)
    size_unit = SizeUnitField()
    size = SizeField(size_unit_field="size_unit")
```

`attribute.size_type` is a `SizeType` (`dress`). `attribute_value.size` is a `Size` in whatever unit was supplied (`eu-dress-size` / `38`). Convert from that pair when a UK token is needed; the stored columns stay the source unit and the raw token.

Importing this package registers Django's `get_language` as the `fashion-size` display language and makes `Size.display()` use it. English lengths render as `32"` and `81cm`; other languages render as `32 in` and `81 cm`. `fashion-size` uses that same formatting for UK, US, and AU waist and chest sizes, and for UK, US, and EU band sizes. EU waist and chest labels, AU bands, and French bands keep their region prefix (`EU 46`). `UK 10` and `DD` stay the same in every language. Cup size also accepts sports-bra alpha labels (`XXS`, `XS`, `S`, `MD`, `LG`, `XL`, `XXL`). They convert as the same token in every region, and the autocomplete lists them after the letter chart. `Size.display()` shows `MD` and `LG` as `M` and `L`; the stored token stays `MD` and `LG`. Brand charts ship with `fashion-size`; pass `brand_name` and `product_type` on `Size.convert` / `Size.convert_to_locale`. The model fields do not need this package in `INSTALLED_APPS`.

`SizeField`'s form control is an autocomplete. You type a size and the list shows chart values that start with that text. A short select beside the field chooses the region or unit you are typing (`UK`, `EU`, `in`, `cm`). A "View conversion chart" link to the right of the field opens the conversion chart. The value saved on the model is the token in `size_unit_field` (`10` when the field stores UK dress sizes, even if you typed EU `38`). Add `django_fashion_size` to `INSTALLED_APPS` so the widget's CSS and script are found.

Length size types (`chest`, `waist`, `inside-leg`, `shorts-inseam`, `trousers-inseam`, `collar`, `sleeve`) convert between inches and centimetres inside that type's own bounds. Shorts inseam is 2–22 inches, trousers inseam is 24–42, and sleeve is 28–40. The autocomplete uses those bounds.

Label size types (`trouser-length`, `top-length`, `shoe-width`, `proportion`, `age-months`, `age-years`, `letter`) have one universal unit and no conversion chart. The autocomplete lists the vocabulary (`Regular`, `One size`). Age bands have no fixed list: type `6 months` or `2-3 years` and the stored token is the canonical band (`6`, `2-3`). Aliases such as `R` and `small` are stored as `regular` and `S`.

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

## Size description API

`fashion_size.descriptions` can read a feed string and join sizes back into one. Two POST endpoints expose that to JavaScript and other non-Python clients. They are not mounted until you include them:

```python
path("", include("django_fashion_size.urls"))
```

`POST /size-description-decode/` and `POST /size-description-encode/` each accept a JSON object. The caller must have an active authenticated session, and the request must include the CSRF token. `source_region` is read once for the whole request (`uk`, `eu`, `us`, `au`, or `fr`; `eur` is accepted as `eu`). `items` is a list of at most 500 objects. A bad item is reported in `results` and does not reject the rest of the batch. A bad `source_region`, a bad `preferred_regions` list, or more than 500 items rejects the request.

`preferred_regions` is also request-level. On decode, each size gains a `regions` list with that size converted into each preferred region. On encode, chart sizes are converted to the first preferred region before the string is built, and each used size includes the same `regions` list. Lengths move between inches and centimetres (EU and FR use centimetres). Label sizes keep their token and change wording. Chart conversion needs `age_group` and `gender` (`adult` / `child` / `baby`, and `female` / `male` / `unisex`), on the request or on the item. Pass `brand_name` as well when a brand chart should be used; a product type on its own stays on the default chart, because fashion-size requires a brand name alongside a product type.

```json
{
  "source_region": "uk",
  "preferred_regions": ["eu", "us"],
  "age_group": "adult",
  "gender": "female",
  "items": [
    {"value": "UK 10", "product_type": "dresses"}
  ]
}
```

Encode items send `sizes` instead of `value`:

```json
{
  "source_region": "uk",
  "preferred_regions": ["eu"],
  "age_group": "adult",
  "gender": "female",
  "items": [
    {
      "product_type": "dresses",
      "sizes": [{"raw": "10", "size_unit": "uk-dress-size"}]
    }
  ]
}
```

The encoded `text` for that item is `EU 38`.
