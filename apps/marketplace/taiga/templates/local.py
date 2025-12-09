import os
from .common import *

HOP3_APP_URL = "https://" + os.environ["HOP3_APP_DOMAIN"]

MEDIA_URL = HOP3_APP_URL + "/media/"
STATIC_URL = HOP3_APP_URL + "/static/"
ADMIN_MEDIA_PREFIX = HOP3_APP_URL + "/static/admin/"
SITES["front"]["scheme"] = "https"
SITES["front"]["domain"] =  os.environ["HOP3_APP_DOMAIN"]
SITES["api"]["domain"] =  os.environ["HOP3_APP_DOMAIN"]
SITES["api"]["scheme"] = "https"

SECRET_KEY = "theveryultratopsecretkey"

DEBUG = False
TEMPLATE_DEBUG = False
PUBLIC_REGISTER_ENABLED = True

DEFAULT_FROM_EMAIL =  os.environ.get("MAIL_FROM", "noreply@localhost")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Setup email
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_USE_TLS = False
EMAIL_HOST = os.environ.get("SMTP_HOST", "localhost")
EMAIL_PORT = os.environ.get("SMTP_PORT", "25")
EMAIL_HOST_USER = os.environ.get("SMTP_USERNAME", "")
EMAIL_HOST_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# Database config
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DATABASE", "taiga"),
        "USER": os.environ.get("POSTGRES_USERNAME", "taiga"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

WEBHOOKS_ENABLED = True

# LDAP overrides if enabled
if "LDAP_HOST" in os.environ:
    print("  Using LDAP")
    PUBLIC_REGISTER_ENABLED = False

    INSTALLED_APPS += ["taiga_contrib_ldap_auth"]

    LDAP_SERVER = "ldap://" + os.environ["LDAP_HOST"]
    LDAP_PORT = int(os.environ.get("LDAP_PORT", "389"))

    # Full DN of the service account use to connect to LDAP server and search for login user's account entry
    # If LDAP_BIND_DN is not specified, or is blank, then an anonymous bind is attempated
    LDAP_BIND_DN = ""
    LDAP_BIND_PASSWORD = ""
    # Starting point within LDAP structure to search for login user
    LDAP_SEARCH_BASE = os.environ.get("LDAP_USERS_BASE_DN", "")
    # LDAP property used for searching, ie. login username needs to match value in sAMAccountName property in LDAP
    LDAP_SEARCH_PROPERTY = "sAMAccountName"
    # LDAP_SEARCH_SUFFIX = None # '@example.com'

    # Names of LDAP properties on user account to get email and full name
    LDAP_EMAIL_PROPERTY = "mail"
    LDAP_FULL_NAME_PROPERTY = "displayname"

# Allows custom overrides, keep in sync with start.sh
if os.path.exists("/app/data/customlocal.py"):
    print("  Importing /app/data/customlocal.py")
    exec(compile(source=open("/app/data/customlocal.py").read(), filename="/app/data/customlocal.py", mode="exec"))
