"""Load the fuel-price CSV into the database and attach coordinates to every station.

The CSV gives street addresses such as "I-40, EXIT 85", which geocoders handle poorly, so
stations are located at CITY level (city + state). That keeps geocoding to a few thousand
unique cities, done ONCE here, so request time never touches a geocoder for stations.

Coordinates come from, in order: lat/lng columns in the CSV, an optional offline gazetteer
CSV (--gazetteer, columns city,state,lat,lng), then Nominatim (cached in a JSON file so
the command can be re-run or resumed).
"""
import csv
import json
import time
from decimal import Decimal
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from planner.core.stations_csv import CsvFormatError, load_stations
from planner.models import FuelStation
from planner.services.stations import reset_store


class Command(BaseCommand):
    help = "Import fuel prices from a CSV and geocode stations by city."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--gazetteer", help="Optional offline city CSV: columns city, state (or state_id), lat, lng")
        parser.add_argument("--cache", default="geocode_cache.json", help="Geocode cache file")
        parser.add_argument("--no-geocode", action="store_true", help="Skip network geocoding")

    def handle(self, *args, **opts):
        path = Path(opts["csv_path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        try:
            records, stats = load_stations(path)
        except CsvFormatError as exc:
            raise CommandError(str(exc))
        self.stdout.write(
            f"{stats['rows']} rows -> {stats['stations']} unique US stations in {stats['cities']} cities "
            f"(skipped {stats['non_us']} non-US rows, {stats['bad_price']} bad prices)"
        )

        self._geocode(records, opts)

        with transaction.atomic():
            FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(
                [FuelStation(**{**r, "price": Decimal(str(r["price"]))}) for r in records], batch_size=1000
            )
        reset_store()
        located = sum(1 for r in records if r["lat"] is not None)
        self.stdout.write(self.style.SUCCESS(f"Imported {len(records)} stations ({located} with coordinates)."))
        missing = sorted({(r["city"], r["state"]) for r in records if r["lat"] is None})
        if missing:
            self.stdout.write(self.style.WARNING(
                f"{len(missing)} cities could not be located; their stations are ignored by the planner: "
                + ", ".join(f"{c}, {st}" for c, st in missing[:15]) + (" ..." if len(missing) > 15 else "")
            ))

    # ------------------------------------------------------------------
    def _geocode(self, records, opts):
        gaz = {}
        if opts["gazetteer"]:
            with open(opts["gazetteer"], newline="", encoding="utf-8-sig") as fh:
                for g in csv.DictReader(fh):
                    g = {k.strip().lower(): v for k, v in g.items()}
                    state = g.get("state") or g.get("state_id") or ""
                    lng = g.get("lng") or g.get("lon") or g.get("long")
                    if not (g.get("city") and state and g.get("lat") and lng):
                        raise CommandError("Gazetteer needs columns city, state (or state_id), lat, lng.")
                    gaz[(g["city"].strip().lower(), state.strip().upper())] = (float(g["lat"]), float(lng))

        cache_path = Path(opts["cache"])
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

        todo = sorted({(r["city"], r["state"]) for r in records if r["lat"] is None})
        self.stdout.write(f"{len(todo)} unique cities need coordinates")
        session = requests.Session()
        session.headers["User-Agent"] = settings.HTTP_USER_AGENT
        looked_up = 0
        try:
            for city, state in todo:
                key = f"{city.lower()}|{state}"
                if (city.lower(), state) in gaz:
                    cache[key] = list(gaz[(city.lower(), state)])
                    continue
                if key in cache or opts["no_geocode"]:
                    continue
                try:
                    resp = session.get(
                        settings.GEOCODING_URL,
                        params={"q": f"{city}, {state}, USA", "countrycodes": "us", "format": "jsonv2", "limit": 1},
                        timeout=settings.HTTP_TIMEOUT_SECONDS,
                    )
                    resp.raise_for_status()
                    found = resp.json()
                    cache[key] = [float(found[0]["lat"]), float(found[0]["lon"])] if found else None
                except (requests.RequestException, ValueError, KeyError) as exc:
                    self.stderr.write(f"  geocode failed for {city}, {state}: {exc} (will retry on next run)")
                    time.sleep(2)
                    continue
                looked_up += 1
                if looked_up % 50 == 0:
                    cache_path.write_text(json.dumps(cache))
                    self.stdout.write(f"  ...{looked_up} of ~{len(todo)} looked up")
                time.sleep(1.1)  # Nominatim usage policy: max 1 request per second
        finally:
            cache_path.write_text(json.dumps(cache))  # progress survives Ctrl+C; just re-run to resume

        for r in records:
            if r["lat"] is None:
                hit = cache.get(f"{r['city'].lower()}|{r['state']}")
                if hit:
                    r["lat"], r["lng"] = hit
