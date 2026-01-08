# Taiga backend settings
from __future__ import annotations

import os

from .common import *

DEBUG = os.getenv("DEBUG", "False").lower() == "true"
SECRET_KEY = os.getenv("TAIGA_SECRET_KEY", "insecure-change-me")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("PGDATABASE", "taiga"),
        "USER": os.getenv("PGUSER", "taiga"),
        "PASSWORD": os.getenv("PGPASSWORD", ""),
        "HOST": os.getenv("PGHOST", "localhost"),
        "PORT": os.getenv("PGPORT", "5432"),
    }
}

# URLs
SITES = {
    "api": {"domain": os.getenv("TAIGA_SITES_DOMAIN", "localhost"), "scheme": "https", "name": "api"},
    "front": {"domain": os.getenv("TAIGA_SITES_DOMAIN", "localhost"), "scheme": "https", "name": "front"},
}

SITE_ID = "api"

# Media and static files
MEDIA_URL = "/media/"
STATIC_URL = "/static/"
MEDIA_ROOT = "/taiga-back/media"
STATIC_ROOT = "/taiga-back/static"

# Email (disabled for demo)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Registration
PUBLIC_REGISTER_ENABLED = True

# Disable async features for simplicity
CELERY_ENABLED = False

# Security
ALLOWED_HOSTS = ["*"]
