"""API tests. Run with `python manage.py test` (needs Django installed). External APIs are mocked."""
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from planner.models import FuelStation
from planner.services.stations import reset_store

# A straight west->east route along 40N, roughly 1,060 miles.
ROUTE = {
    "coords": [[-100.0, 40.0], [-90.0, 40.0], [-80.0, 40.0]],
    "distance_miles": 1060.0,
    "duration_hours": 16.0,
}
POINTS = {"A": (40.0, -100.0, "A"), "B": (40.0, -80.0, "B")}


class RouteApiTests(TestCase):
    def setUp(self):
        cache.clear()
        reset_store()
        FuelStation.objects.create(name="Cheap", city="X", state="IA", price="3.100", lat=40.01, lng=-95.0)
        FuelStation.objects.create(name="Pricey", city="Y", state="OH", price="3.900", lat=40.01, lng=-88.0)

    @mock.patch("planner.services.planner.get_route", return_value=ROUTE)
    @mock.patch("planner.services.planner.geocode", side_effect=lambda q: POINTS[q])
    def test_plan_has_stops_cost_and_one_routing_call(self, _geo, get_route):
        resp = self.client.get("/api/route/", {"start": "A", "finish": "B"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(len(data["fuel_stops"]), 1)
        self.assertGreater(data["total_fuel_cost"], 0)
        self.assertEqual(data["route"]["geometry"]["type"], "LineString")
        get_route.assert_called_once()

        # second identical request is served from cache: no further routing call
        self.client.get("/api/route/", {"start": "A", "finish": "B"})
        get_route.assert_called_once()

    def test_missing_params_is_400(self):
        resp = self.client.get("/api/route/", {"start": "A"})
        self.assertEqual(resp.status_code, 400)


class GeocodeTests(TestCase):
    def test_known_city_resolves_without_network(self):
        from planner.services.geocoding import geocode

        FuelStation.objects.create(name="S", city="Dallas", state="TX", price="3.000", lat=32.78, lng=-96.8)
        with mock.patch("planner.services.geocoding.requests.get") as http:
            lat, lng, label = geocode("dallas, tx")
        self.assertEqual((lat, lng, label), (32.78, -96.8, "Dallas, TX"))
        http.assert_not_called()

    def test_major_city_without_stations_resolves_without_network(self):
        from planner.services.geocoding import geocode

        with mock.patch("planner.services.geocoding.requests.get") as http:
            lat, lng, label = geocode("Los Angeles, CA")
        self.assertAlmostEqual(lat, 34.05, places=1)
        self.assertEqual(label, "Los Angeles, CA")
        http.assert_not_called()
