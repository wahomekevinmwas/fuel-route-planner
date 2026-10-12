import requests
from django.conf import settings

METERS_PER_MILE = 1609.344


class RoutingError(Exception):
    pass


def get_route(start, finish):
    """ONE call to the routing API. start/finish are (lat, lng).

    Returns {"coords": [[lon, lat], ...], "distance_miles": float, "duration_hours": float}.
    """
    url = (
        f"{settings.ROUTING_BASE_URL}/route/v1/driving/"
        f"{start[1]:.6f},{start[0]:.6f};{finish[1]:.6f},{finish[0]:.6f}"
    )
    try:
        resp = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson", "steps": "false"},
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutingError(f"Routing service failed: {exc}") from exc

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"No drivable route found ({data.get('code', 'unknown error')}).")
    route = data["routes"][0]
    return {
        "coords": route["geometry"]["coordinates"],
        "distance_miles": route["distance"] / METERS_PER_MILE,
        "duration_hours": route["duration"] / 3600,
    }
