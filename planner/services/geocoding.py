import re

import requests
from django.conf import settings
from django.core.cache import caches

from ..models import FuelStation
from .us_cities import CITIES

LATLNG_RE = re.compile(r"^\s*(-?\d+(\.\d+)?)\s*,\s*(-?\d+(\.\d+)?)\s*$")
CITY_STATE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z .'\-]*?)\s*,\s*([A-Za-z]{2})\s*$")
# Rough bounding box of the contiguous United States (the area a road route can cover).
US_BOUNDS = {"lat": (24.0, 49.6), "lng": (-125.5, -66.5)}


class GeocodeError(Exception):
    pass


def _check_in_us(lat, lng, label):
    (lat_min, lat_max), (lng_min, lng_max) = US_BOUNDS["lat"], US_BOUNDS["lng"]
    if not (lat_min <= lat <= lat_max and lng_min <= lng <= lng_max):
        raise GeocodeError(f"'{label}' is outside the contiguous USA.")


def _known_city(query):
    """'Dallas, TX' -> coordinates already stored with the imported stations (no network)."""
    m = CITY_STATE_RE.match(query)
    if not m:
        return None
    city, state = m.group(1).strip(), m.group(2).upper()
    row = (
        FuelStation.objects.filter(city__iexact=city, state=state, lat__isnull=False, lng__isnull=False)
        .values("lat", "lng")
        .first()
    )
    if row:
        return row["lat"], row["lng"], f"{city.title()}, {state}"
    if (city.lower(), state) in CITIES:  # major cities that have no fuel station in the data
        lat, lng = CITIES[(city.lower(), state)]
        return lat, lng, f"{city.title()}, {state}"
    return None


def geocode(query):
    """Turn 'Chicago, IL' or '41.88,-87.63' into (lat, lng, label). Results are cached."""
    query = (query or "").strip()
    if not query:
        raise GeocodeError("Location is empty.")

    m = LATLNG_RE.match(query)
    if m:
        lat, lng = float(m.group(1)), float(m.group(3))
        _check_in_us(lat, lng, query)
        return lat, lng, f"{lat:.5f},{lng:.5f}"

    known = _known_city(query)  # instant: cities we already located during the import
    if known:
        return known

    key = "geo:" + query.lower()
    hit = caches["geocode"].get(key)
    if hit:
        return hit

    try:
        resp = requests.get(
            settings.GEOCODING_URL,
            params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        results = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise GeocodeError(f"Geocoding service failed for '{query}': {exc}") from exc

    if not results:
        raise GeocodeError(f"Could not find '{query}' in the USA.")
    lat, lng = float(results[0]["lat"]), float(results[0]["lon"])
    _check_in_us(lat, lng, query)
    value = (lat, lng, results[0].get("display_name", query))
    caches["geocode"].set(key, value, 60 * 60 * 24 * 30)
    return value
