"""Optional size-description endpoints.

Include this module to mount them. They stay unregistered until a project
does so, including when ``django_fashion_size`` is in ``INSTALLED_APPS``::

    path("", include("django_fashion_size.urls"))

That serves ``/size-description-decode/`` and ``/size-description-encode/``.
"""

from django.urls import path

from django_fashion_size.description_api import (
    decode_size_descriptions,
    encode_size_descriptions,
)

app_name = "django_fashion_size"

urlpatterns = [
    path(
        "size-description-decode/",
        decode_size_descriptions,
        name="size-description-decode",
    ),
    path(
        "size-description-encode/",
        encode_size_descriptions,
        name="size-description-encode",
    ),
]
