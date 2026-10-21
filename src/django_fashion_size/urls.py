"""Optional size-description endpoints.

Include this module to mount them. They stay unregistered until a project
does so, including when ``django_fashion_size`` is in ``INSTALLED_APPS``::

    path("fashion-size/", include("django_fashion_size.urls"))
"""

from django.urls import path

from django_fashion_size.description_api import (
    decode_size_descriptions,
    encode_size_descriptions,
)

app_name = "django_fashion_size"

urlpatterns = [
    path(
        "descriptions/decode/",
        decode_size_descriptions,
        name="decode-size-descriptions",
    ),
    path(
        "descriptions/encode/",
        encode_size_descriptions,
        name="encode-size-descriptions",
    ),
]
