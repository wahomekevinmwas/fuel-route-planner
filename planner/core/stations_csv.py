"""Parse and clean the fuel-price CSV. Pure Python (no Django) so it is testable on its own.

Cleaning rules, all driven by what the real file contains:
  * Canadian provinces (AB, BC, ON, QC, ...) are dropped: the planner is USA-only.
  * The same station (same OPIS id) appears on several rows with different prices; we keep
    ONE record per station, at its lowest listed price.
  * Prices are rounded to 5 decimals (the file has values like 3.00733333).
"""
import csv

US_STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
    "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)

ALIASES = {
    "opis_id": ["opis truckstop id", "opis id", "id", "truckstop id"],
    "name": ["truckstop name", "name", "station name"],
    "address": ["address", "street address"],
    "city": ["city"],
    "state": ["state", "state code", "st"],
    "price": ["retail price", "price", "price per gallon", "diesel price"],
    "lat": ["latitude", "lat"],
    "lng": ["longitude", "lng", "lon", "long"],
}


class CsvFormatError(Exception):
    pass


def find_columns(header):
    lowered = {h.strip().lower(): h for h in header}
    cols = {f: next((lowered[n] for n in names if n in lowered), None) for f, names in ALIASES.items()}
    missing = [f for f in ("name", "city", "state", "price") if not cols[f]]
    if missing:
        raise CsvFormatError(f"CSV is missing columns for: {', '.join(missing)}. Found: {list(header)}")
    return cols


def load_stations(path):
    """Return (records, stats). Each record is a dict ready for FuelStation(**record)."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        cols = find_columns(reader.fieldnames or [])
        rows = list(reader)

    def get(row, field):
        col = cols[field]
        return (row.get(col) or "").strip() if col else ""

    stats = {"rows": len(rows), "non_us": 0, "bad_price": 0}
    best = {}
    for row in rows:
        state = get(row, "state").upper()
        if state not in US_STATES:
            stats["non_us"] += 1
            continue
        try:
            price = round(float(get(row, "price").replace("$", "")), 5)
        except ValueError:
            stats["bad_price"] += 1
            continue
        if price <= 0:
            stats["bad_price"] += 1
            continue
        name, city, address = get(row, "name"), get(row, "city"), get(row, "address")
        opis = get(row, "opis_id")
        key = ("id", opis) if opis else ("addr", name.lower(), address.lower(), city.lower(), state)
        lat, lng = get(row, "lat"), get(row, "lng")
        rec = {
            "opis_id": opis, "name": name, "address": address, "city": city, "state": state,
            "price": price,
            "lat": float(lat) if lat else None, "lng": float(lng) if lng else None,
        }
        if key not in best or price < best[key]["price"]:
            best[key] = rec
    records = list(best.values())
    stats["stations"] = len(records)
    stats["cities"] = len({(r["city"].lower(), r["state"]) for r in records})
    return records, stats
