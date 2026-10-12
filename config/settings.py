import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "planner",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

# Plans and geocoding results are cached so repeat requests make zero external calls.
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    # Geocoding results survive server restarts (a place only needs looking up once).
    "geocode": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": BASE_DIR / ".geocode_cache",
    },
}

# ---- Fuel planner settings -------------------------------------------------
VEHICLE_RANGE_MILES = 500.0
VEHICLE_MPG = 10.0
# Assumption: the vehicle leaves the start point with a full tank (not billed).
START_WITH_FULL_TANK = True
# Stations further than this from the route are ignored. Stations are located at
# city level (see README), so keep this a little generous.
CORRIDOR_MILES = 10.0
# Dollars of "time and hassle" charged per fuel stop when deciding WHERE to stop. It steers
# the choice of stops only; it is never added to the reported fuel cost. 0.0 gives the pure
# cheapest-fuel plan, which makes many extra stops to save a few cents.
STOP_PENALTY_DOLLARS = 8.0

# Routing: OSRM-compatible API (free public demo server by default).
ROUTING_BASE_URL = os.environ.get("ROUTING_BASE_URL", "https://router.project-osrm.org")
# Geocoding: Nominatim (OpenStreetMap). Their policy requires an identifying User-Agent.
GEOCODING_URL = os.environ.get("GEOCODING_URL", "https://nominatim.openstreetmap.org/search")
HTTP_USER_AGENT = os.environ.get("HTTP_USER_AGENT", "fuel-route-planner/1.0 (assessment)")
HTTP_TIMEOUT_SECONDS = 15

# Let OpenStreetMap's tile servers see where requests come from (Django's default of
# "same-origin" strips the Referer header and the tiles come back as 403 Access blocked).
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
