"""Optional size-description endpoints.

Include this module to mount them. They stay unregistered until a project
does so, including when ``django_fashion_size`` is in ``INSTALLED_APPS``::

    path("api/size-descriptions/", include("django_fashion_size.urls"))

That serves ``decode/`` and ``encode/`` at ``/api/size-descriptions/decode/``
and ``/api/size-descriptions/encode/``.
"""

from django.urls import path

from django_fashion_size.description_api import (
    decode_size_descriptions,
    encode_size_descriptions,
)

app_name = "django_fashion_size"

urlpatterns = [
    path("decode/", decode_size_descriptions, name="decode"),
    path("encode/", encode_size_descriptions, name="encode"),
]
