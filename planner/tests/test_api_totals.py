from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase

from planner.models import FuelStation
from planner.services.stations import reset_store

from .test_api import POINTS, ROUTE

# About 53 miles along 40N: well under one tank, and far from both fixture stations.
SHORT_ROUTE = {
    "coords": [[-100.0, 40.0], [-99.0, 40.0]],
    "distance_miles": 53.0,
    "duration_hours": 1.0,
}
SHORT_POINTS = {"A": (40.0, -100.0, "A"), "B": (40.0, -99.0, "B")}


class TripCostTests(TestCase):
    def setUp(self):
        cache.clear()
        reset_store()
        FuelStation.objects.create(name="Cheap", city="X", state="IA", price="3.100", lat=40.01, lng=-95.0)
        FuelStation.objects.create(name="Pricey", city="Y", state="OH", price="3.900", lat=40.01, lng=-88.0)

    def _get(self, route, points):
        with mock.patch("planner.services.planner.get_route", return_value=route), \
             mock.patch("planner.services.planner.geocode", side_effect=lambda q: points[q]):
            resp = self.client.get("/api/route/", {"start": "A", "finish": "B"})
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_totals_add_up_on_a_long_route(self):
        d = self._get(ROUTE, POINTS)
        self.assertGreaterEqual(len(d["fuel_stops"]), 1)
        self.assertAlmostEqual(d["fuel_purchased_cost"], sum(s["cost"] for s in d["fuel_stops"]),
                               delta=0.011 * len(d["fuel_stops"]))
        self.assertAlmostEqual(d["total_fuel_cost"], d["fuel_purchased_cost"] + d["starting_tank_cost"], delta=0.011)
        self.assertAlmostEqual(d["total_gallons_used"],
                               d["total_gallons_purchased"] + d["starting_tank_gallons"], delta=0.02)
        self.assertGreater(d["starting_tank_gallons"], 0)
        self.assertLessEqual(d["starting_tank_gallons"],
                             settings.VEHICLE_RANGE_MILES / settings.VEHICLE_MPG + 0.01)

    def test_short_trip_without_stops_still_reports_a_cost(self):
        d = self._get(SHORT_ROUTE, SHORT_POINTS)
        self.assertEqual(d["fuel_stops"], [])
        self.assertEqual(d["fuel_purchased_cost"], 0)
        self.assertAlmostEqual(d["starting_tank_gallons"], 53.0 / settings.VEHICLE_MPG, places=2)
        # No corridor stations, so the price falls back to the mean of all stations: (3.10 + 3.90) / 2
        self.assertAlmostEqual(d["starting_tank_price_per_gallon"], 3.5, places=3)
        self.assertGreater(d["total_fuel_cost"], 0)
        self.assertAlmostEqual(d["total_fuel_cost"], d["starting_tank_cost"], delta=0.011)

    def test_assumptions_state_how_the_starting_tank_is_priced(self):
        d = self._get(ROUTE, POINTS)
        self.assertIn("starting_tank", d["assumptions"])
