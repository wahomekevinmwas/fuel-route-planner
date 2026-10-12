# Fuel Route Planner (Django)

Given a start and finish inside the USA, the API returns the driving route, the cheapest
places to refuel along it (vehicle range 500 miles, 10 mpg), and the total fuel cost.

No API keys are needed: routing uses the public OSRM server and geocoding uses Nominatim.

## Setup

Requires Python 3.12+ (Django 6.1). Developed on Python 3.14.

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt                        # pinned: Django 6.1.2, numpy, requests
python manage.py migrate
python manage.py loaddata stations                     # 6,626 pre-geocoded US stations, takes seconds
python manage.py runserver
```

Try it:

```bash
curl "http://127.0.0.1:8000/api/route/?start=Los%20Angeles,CA&finish=New%20York,NY"
```

Optional environment variables (defaults are development settings: `DEBUG` on, placeholder
secret key): `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `ROUTING_BASE_URL`,
`GEOCODING_URL`, `HTTP_USER_AGENT`.

### Loading fuel prices from the CSV (optional)

The committed fixture (`planner/fixtures/stations.json`) is the result of importing the supplied
file, so this is only needed to rebuild it:

```bash
python manage.py import_fuel_prices data/fuel-prices-for-be-assessment.csv
```

What the importer does with the supplied file (8,151 rows):

* drops the 620 **Canadian** rows (AB, BC, ON, QC, ...): the planner is USA-only;
* merges repeated rows for the same station (same OPIS id, differing prices) into one
  station at its **lowest listed price**, giving **6,626 US stations**;
* locates each station by **city** (3,808 unique cities). Street addresses such as
  "I-44, EXIT 283 & US-69" geocode poorly, so city + state is used, once, at import time.

Geocoding uses Nominatim at its allowed 1 request/second (about 70 minutes from a cold start).
Results are cached in `geocode_cache.json`, which is committed with all 3,808 cities, so a
re-import should not need Nominatim again. An offline city list can also be used:
`--gazetteer us_cities.csv` (columns `city`, `state` or `state_id`, `lat`, `lng`).

## API

`GET /api/route/?start=Chicago,IL&finish=Dallas,TX` or
`POST /api/route/` with `{"start": "Chicago, IL", "finish": "Dallas, TX"}`.
Locations can be place names or `lat,lng`.

Response (abridged; Los Angeles to New York):

```json
{
  "distance_miles": 2793.7,
  "fuel_stops": [
    {"name": "...", "city": "...", "state": "..", "lat": 0, "lng": 0, "mile_marker": 271.0,
     "price_per_gallon": 3.282, "gallons_purchased": 27.1, "cost": 88.94}
  ],
  "total_fuel_cost": 877.92,
  "fuel_purchased_cost": 703.56,
  "starting_tank_gallons": 50.0,
  "starting_tank_price_per_gallon": 3.487,
  "starting_tank_cost": 174.36,
  "total_gallons_purchased": 229.37,
  "total_gallons_used": 279.37,
  "route": {"type": "Feature", "geometry": {"type": "LineString", "coordinates": []}},
  "map_url": "/api/route/map/?start=...&finish=...",
  "timing_ms": {"geocoding": 16, "routing_api": 2745, "our_code": 124, "total": 2885}
}
```

* `total_fuel_cost`: money spent on fuel for the whole trip = `fuel_purchased_cost` + `starting_tank_cost`.
* `fuel_purchased_cost`: what is bought at the listed stops.
* `starting_tank_*`: the fuel the vehicle leaves with, and how it was priced (see Assumptions).
* `route.geometry`: the route as a GeoJSON LineString; `fuel_stops` carries each stop's coordinates.
* A repeated request is served from cache: `"cached": true` and `timing_ms.total` is under a millisecond.

`GET /api/route/map/` is a browser page (Leaflet + OpenStreetMap) that draws the route and
the fuel stops from the same API.

Errors: `400` bad input or unknown place, `422` no feasible fuel plan (gap larger than the
vehicle range), `502` routing/geocoding service unavailable.

## How it works

1. **Resolve** start/finish (Nominatim geocoding, cached; skipped when `lat,lng` is given).
2. **Route**: exactly ONE call to the routing API (OSRM public server) for the full geometry.
3. **Match stations**: resample the route to 1-mile spacing, then a numpy coarse-then-fine
   search finds stations within 10 miles of the route and each one's mile marker (about 100 ms
   for a cross-country route against 8,000 stations).
4. **Optimise** (`planner/core/optimizer.py`):
   * *Buying*: greedy "gas station problem". At each stop, if a cheaper station is within one
     tank, buy only enough to reach it; otherwise if the destination is reachable, buy only
     enough to finish; otherwise fill up and drive to the cheapest station in reach. For a
     given set of stations this is provably optimal (checked against a brute-force oracle on
     400 random scenarios).
   * *Choosing stations*: a dynamic programme over (station, fuel level) with a small
     per-stop penalty (`STOP_PENALTY_DOLLARS`, default $8, never added to the reported cost).
     Without it the cheapest plan makes a dozen pointless stops to save pennies. On Los
     Angeles to New York: penalty 0 gives 17 stops and $695.21 of fuel at stops; the default
     gives 6 stops and $703.56. It is also checked against brute force over every subset of
     stations.
   * *Rounding*: fuel is counted in 5-mile steps and each station's mile marker is rounded up
     once, cumulatively, so rounding error stays under one step. Rounding per leg instead
     would inflate a 2,800-mile route by over 600 miles and force extra stops. The chosen
     stops are then verified by the exact planner; if rounding made a plan infeasible, the
     DP is retried with one step of range reserved, and as a last resort every station is used.
5. Results are cached, so a repeated request makes zero external calls. The cache key includes
   the settings that change the answer (penalty, range, mpg, start tank, corridor).

## Assumptions (change in `config/settings.py`)

* The vehicle leaves the start with a **full 500-mile tank**. Those gallons are real trip fuel,
  so `total_fuel_cost` includes them, priced at the mean price of the corridor stations within
  50 miles of the origin (all corridor stations if there are none that close). Short trips that
  need no stop therefore still report a cost. `START_WITH_FULL_TANK = False` makes it start empty.
* Stations are located at **city level** (the CSV's street addresses like "I-40, EXIT 85"
  geocode poorly), so `CORRIDOR_MILES` is a generous 10.
* Station detours are not costed; a station inside the corridor is treated as on the route.
* One price per station: the lowest listed (the file repeats stations with different prices).
* If no plan exists with stations within 10 miles of the route, the corridor is widened
  automatically (25, then 50 miles) before returning an error; `corridor_miles_used` reports it.

## Notes on performance

An uncached cross-country request takes about 2.9 s, of which about 2.7 s is the single call to
the public OSRM server; our own code takes about 0.1 to 0.3 s. The plan cache is in-process
(`LocMemCache`), so it resets when the server restarts.

## Tests

```bash
python -m unittest planner.tests.test_core planner.tests.test_csv   # algorithm, geometry, CSV cleaning (no Django needed)
python manage.py test                          # all 21 tests, including the API tests (external calls mocked)
```