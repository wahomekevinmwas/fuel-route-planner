"""Core tests: run with `python -m unittest planner.tests.test_core` (no Django needed)."""
import random
import unittest

import numpy as np

from planner.core.geo import haversine_miles, resample, stations_near_route
from planner.core.optimizer import Candidate, NoFeasiblePlan, plan_fuel_stops


def oracle_cost(cands, total, rng, mpg):
    """Exhaustive DP over integer miles/fuel: the true minimum cost."""
    nodes = [(0, None)] + [(int(c.mile), c.price) for c in sorted(cands, key=lambda c: c.mile)] + [(total, None)]
    INF = float("inf")
    dp = [[INF] * (rng + 1) for _ in nodes]
    dp[0][rng] = 0.0  # start with a full tank, free
    for i, (m, price) in enumerate(nodes[:-1]):
        for f in range(rng + 1):
            base = dp[i][f]
            if base == INF:
                continue
            max_buy = rng - f if price is not None else 0
            for x in range(max_buy + 1):
                cost = base + (x / mpg) * (price or 0)
                have = f + x
                for j in range(i + 1, len(nodes)):
                    d = nodes[j][0] - m
                    if d > have:
                        break
                    dp[j][have - d] = min(dp[j][have - d], cost)
    return min(dp[-1])


class OptimizerTests(unittest.TestCase):
    def test_short_trip_needs_no_stops(self):
        self.assertEqual(plan_fuel_stops([Candidate(1, 100, 3.0)], 400), [])

    def test_buys_only_what_is_needed_to_reach_cheaper_station(self):
        cands = [Candidate(1, 300, 4.0), Candidate(2, 600, 3.0), Candidate(3, 900, 5.0)]
        plan = plan_fuel_stops(cands, 1200, range_miles=500, mpg=10)
        # Mile 600 is out of reach from the start (full tank = 500 miles), so stop at mile 300
        # and buy just the 100 miles (10 gal) needed to reach the cheaper station.
        self.assertEqual(plan[0].key, 1)
        self.assertAlmostEqual(plan[0].gallons, 10.0)
        self.assertEqual(plan[1].key, 2)  # then fill up where fuel is cheapest

    def test_stop_penalty_removes_pointless_stops(self):
        # A (mile 100) is the cheapest start; B (590, $3.00) is the cheapest in A's reach;
        # C (610, $2.96) saves only 4 cents/gal over B. Pure-cost mode adds a stop at C;
        # with a $5 per-stop penalty the plan simply finishes from B.
        cands = [Candidate("A", 100, 2.50), Candidate("B", 590, 3.00), Candidate("C", 610, 2.96)]
        exact = plan_fuel_stops(cands, 1000, range_miles=500, mpg=10)
        realistic = plan_fuel_stops(cands, 1000, range_miles=500, mpg=10, stop_penalty=5.0)
        self.assertEqual([p.key for p in exact], ["A", "B", "C"])
        self.assertEqual([p.key for p in realistic], ["A", "B"])

    def test_stop_penalty_matches_bruteforce_over_station_subsets(self):
        """For small problems, try EVERY subset of stations: the penalty plan must be the best."""
        rnd = random.Random(11)
        checked = 0
        for _ in range(250):
            rng = rnd.choice([30, 50])
            total = rnd.randint(rng + 5, rng * 3)
            n = rnd.randint(1, 7)
            cands = [Candidate(i, rnd.randint(1, total - 1), round(rnd.uniform(2.5, 5.0), 2)) for i in range(n)]
            pen = rnd.choice([0.5, 2.0, 5.0])
            try:
                got = plan_fuel_stops(cands, total, range_miles=rng, mpg=10, stop_penalty=pen, unit_miles=1.0)
            except NoFeasiblePlan:
                with self.assertRaises(NoFeasiblePlan):
                    plan_fuel_stops(cands, total, range_miles=rng, mpg=10)
                continue
            best = float("inf")
            for mask in range(1 << n):
                subset = [c for i, c in enumerate(cands) if mask >> i & 1]
                try:
                    plan = plan_fuel_stops(subset, total, range_miles=rng, mpg=10)
                except NoFeasiblePlan:
                    continue
                best = min(best, sum(p.cost for p in plan) + pen * len(plan))
            self.assertAlmostEqual(sum(p.cost for p in got) + pen * len(got), best, places=6)
            checked += 1
        self.assertGreater(checked, 100)

    def test_infeasible_gap(self):
        with self.assertRaises(NoFeasiblePlan):
            plan_fuel_stops([Candidate(1, 100, 3.0)], 1200, range_miles=500)

    def test_matches_bruteforce_oracle(self):
        rnd = random.Random(7)
        for _ in range(400):
            rng = rnd.choice([30, 50, 80])
            total = rnd.randint(rng + 5, rng * 4)
            n = rnd.randint(1, 9)
            cands = [Candidate(i, rnd.randint(1, total - 1), round(rnd.uniform(2.5, 5.0), 2)) for i in range(n)]
            try:
                plan = plan_fuel_stops(cands, total, range_miles=rng, mpg=10)
            except NoFeasiblePlan:
                self.assertEqual(oracle_cost(cands, total, rng, 10), float("inf"))
                continue
            greedy = sum(p.cost for p in plan)
            self.assertAlmostEqual(greedy, oracle_cost(cands, total, rng, 10), places=6)
            # never buy a negative/absurd amount and never exceed a full tank in one stop
            for p in plan:
                self.assertGreater(p.gallons, 0)
                self.assertLessEqual(p.gallons * 10, rng + 1e-6)


class GeoTests(unittest.TestCase):
    def test_haversine_known_distance(self):
        # Los Angeles -> New York is about 2,445 miles.
        d = float(haversine_miles(34.0522, -118.2437, 40.7128, -74.0060))
        self.assertAlmostEqual(d, 2445, delta=15)

    def test_resample_gives_uniform_spacing(self):
        pts, cum = resample([[-100.0, 40.0], [-90.0, 40.0]], step_miles=1.0)
        self.assertLess(np.max(np.diff(cum)), 1.01)
        # thinning: a dense polyline is reduced to ~1 mile spacing
        dense = [[-100.0 + i * 0.0001, 40.0] for i in range(20000)]
        thin, _ = resample(dense, step_miles=1.0)
        self.assertLess(len(thin), 200)

    def test_stations_near_route(self):
        pts, cum = resample([[-100.0, 40.0], [-90.0, 40.0]], step_miles=1.0)
        lat = np.array([40.02, 41.5, 39.99])
        lng = np.array([-95.0, -95.0, -91.0])
        idx, miles, off = stations_near_route(pts, cum, lat, lng, corridor_miles=5)
        self.assertEqual(sorted(idx.tolist()), [0, 2])  # the 41.5N one is ~100 miles away
        mile_of = dict(zip(idx.tolist(), miles.tolist()))
        self.assertLess(mile_of[0], mile_of[2])


if __name__ == "__main__":
    unittest.main()
