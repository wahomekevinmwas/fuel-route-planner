"""In-memory, numpy-backed view of the fuel stations so each request is one vectorised query."""
from dataclasses import dataclass, field

import numpy as np

from ..models import FuelStation

_store = None


@dataclass
class StationStore:
    lat: np.ndarray = field(default_factory=lambda: np.array([]))
    lng: np.ndarray = field(default_factory=lambda: np.array([]))
    price: np.ndarray = field(default_factory=lambda: np.array([]))
    info: list = field(default_factory=list)


def get_station_store():
    global _store
    if _store is None:
        rows = list(
            FuelStation.objects.exclude(lat__isnull=True).exclude(lng__isnull=True)
            .values("id", "name", "address", "city", "state", "price", "lat", "lng")
        )
        _store = StationStore(
            lat=np.array([r["lat"] for r in rows], dtype=float),
            lng=np.array([r["lng"] for r in rows], dtype=float),
            price=np.array([float(r["price"]) for r in rows], dtype=float),
            info=rows,
        )
    return _store


def reset_store():
    global _store
    _store = None
