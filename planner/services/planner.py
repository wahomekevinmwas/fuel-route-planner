from time import perf_counter
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse

from ..core.geo import resample, stations_near_route
from ..core.optimizer import Candidate, NoFeasiblePlan, plan_fuel_stops
from .geocoding import geocode
from .routing import get_route
from .stations import get_station_store

MAX_GEOMETRY_POINTS = 2000  # keep the JSON response small; the map does not need every vertex


class PlanError(Exception):
    pass


def _downsample(coords, limit=MAX_GEOMETRY_POINTS):
    if len(coords) <= limit:
        return coords
    step = len(coords) / limit
    picked = [coords[int(i * step)] for i in range(limit)]
    picked[-1] = coords[-1]
    return picked


def build_plan(start_query, finish_query):
    cache_key = (
        f"plan:{start_query.strip().lower()}|{finish_query.strip().lower()}"
        f"|{settings.STOP_PENALTY_DOLLARS}|{settings.VEHICLE_RANGE_MILES}|{settings.VEHICLE_MPG}"
        f"|{settings.START_WITH_FULL_TANK}|{settings.CORRIDOR_MILES}"
    )
    t0 = perf_counter()
    cached = cache.get(cache_key)
    if cached:
        # Report how long THIS request took, not the original computation.
        return {**cached, "cached": True, "timing_ms": {"total": round((perf_counter() - t0) * 1000, 1)}}

    s_lat, s_lng, s_label = geocode(start_query)
    f_lat, f_lng, f_label = geocode(finish_query)
    t_geocoded = perf_counter()
    route = get_route((s_lat, s_lng), (f_lat, f_lng))  # the single routing-API call
    t_routed = perf_counter()

    pts, cum = resample(route["coords"], step_miles=1.0)
    total_miles = route["distance_miles"]
    if cum[-1] > 0:
        cum = cum * (total_miles / cum[-1])  # align our polyline distance with the API's own total

    store = get_station_store()
    if len(store.lat) == 0:
        raise PlanError("No fuel stations loaded. Run: python manage.py import_fuel_prices <csv>")

    # Try the normal corridor first; in sparse regions widen it rather than fail outright.
    purchases, last_error = None, None
    for corridor in (settings.CORRIDOR_MILES, settings.CORRIDOR_MILES * 2.5, settings.CORRIDOR_MILES * 5):
        idx, miles, offsets = stations_near_route(pts, cum, store.lat, store.lng, corridor)
        candidates = [Candidate(int(i), float(m), float(store.price[i])) for i, m in zip(idx, miles)]
        try:
            purchases = plan_fuel_stops(
                candidates,
                total_miles,
                range_miles=settings.VEHICLE_RANGE_MILES,
                mpg=settings.VEHICLE_MPG,
                initial_fuel_miles=None if settings.START_WITH_FULL_TANK else 0.0,
                stop_penalty=settings.STOP_PENALTY_DOLLARS,
            )
            break
        except NoFeasiblePlan as exc:
            last_error = exc
    if purchases is None:
        raise PlanError(str(last_error))

    offset_of = dict(zip(idx.tolist(), offsets.tolist()))
    stops = []
    for p in purchases:
        info = store.info[p.key]
        stops.append({
            "name": info["name"],
            "address": info["address"],
            "city": info["city"],
            "state": info["state"],
            "lat": info["lat"],
            "lng": info["lng"],
            "mile_marker": round(p.mile, 1),
            "miles_off_route": round(offset_of.get(p.key, 0.0), 1),
            "price_per_gallon": round(p.price, 3),
            "gallons_purchased": round(p.gallons, 2),
            "cost": round(p.cost, 2),
        })

    total_cost = round(sum(p.cost for p in purchases), 2)
    gallons_used = total_miles / settings.VEHICLE_MPG
    # The vehicle leaves with a full tank. Those gallons are real trip fuel, so price them at
    # the mean price of corridor stations in the first 50 miles (else of all corridor stations).
    start_gallons = max(0.0, gallons_used - sum(p.gallons for p in purchases)) if settings.START_WITH_FULL_TANK else 0.0
    near_start = [c.price for c in candidates if c.mile <= 50.0] or [c.price for c in candidates]
    start_price = sum(near_start) / len(near_start) if near_start else float(store.price.mean())
    start_cost = start_gallons * start_price
    qs = urlencode({"start": start_query, "finish": finish_query})
    result = {
        "start": {"query": start_query, "label": s_label, "lat": s_lat, "lng": s_lng},
        "finish": {"query": finish_query, "label": f_label, "lat": f_lat, "lng": f_lng},
        "distance_miles": round(total_miles, 1),
        "duration_hours": round(route["duration_hours"], 1),
        "fuel_stops": stops,
        "total_fuel_cost": round(total_cost + start_cost, 2),
        "fuel_purchased_cost": total_cost,
        "starting_tank_gallons": round(start_gallons, 2),
        "starting_tank_price_per_gallon": round(start_price, 3),
        "starting_tank_cost": round(start_cost, 2),
        "total_gallons_purchased": round(sum(p.gallons for p in purchases), 2),
        "total_gallons_used": round(gallons_used, 2),
        "route": {
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "LineString", "coordinates": _downsample(route["coords"])},
        },
        "map_url": f"{reverse('route-map')}?{qs}",
        "assumptions": {
            "vehicle_range_miles": settings.VEHICLE_RANGE_MILES,
            "mpg": settings.VEHICLE_MPG,
            "start_with_full_tank": settings.START_WITH_FULL_TANK,
            "stop_penalty_dollars": settings.STOP_PENALTY_DOLLARS,
            "note": "total_fuel_cost = fuel_purchased_cost (bought at the stops) + starting_tank_cost (the full tank the vehicle leaves with).",
        },
        "timing_ms": {
            "geocoding": round((t_geocoded - t0) * 1000),
            "routing_api": round((t_routed - t_geocoded) * 1000),
            "our_code": round((perf_counter() - t_routed) * 1000),
            "total": round((perf_counter() - t0) * 1000),
        },
        "corridor_miles_used": corridor,
        "cached": False,
    }
    result["assumptions"]["starting_tank"] = (
        "Vehicle starts with a full tank; those gallons are priced at the mean price of corridor "
        "stations within 50 miles of the origin and included in total_fuel_cost."
    )
    cache.set(cache_key, result, 60 * 60)
    return result
