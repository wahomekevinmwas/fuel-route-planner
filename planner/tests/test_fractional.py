import random

from django.test import SimpleTestCase

from planner.core.optimizer import Candidate, NoFeasiblePlan, plan_fuel_stops


class FractionalMileTests(SimpleTestCase):
    """Real routes have fractional miles; the DP rounds them to a grid, so guard the invariants."""

    def test_penalty_plan_is_drivable_and_never_beats_exact_subsets(self):
        rnd = random.Random(23)
        checked = 0
        for _ in range(250):
            rng = rnd.choice([30, 50])
            total = round(rnd.uniform(rng + 5, rng * 3), 2)
            n = rnd.randint(1, 7)
            cands = [Candidate(i, round(rnd.uniform(1, total - 1), 2), round(rnd.uniform(2.5, 5.0), 2))
                     for i in range(n)]
            pen = rnd.choice([0.5, 2.0, 5.0])
            try:
                plan_fuel_stops(cands, total, range_miles=rng, mpg=10)
            except NoFeasiblePlan:
                continue  # genuinely infeasible; covered elsewhere

            got = plan_fuel_stops(cands, total, range_miles=rng, mpg=10, stop_penalty=pen, unit_miles=1.0)

            marks = [0.0] + [p.mile for p in got] + [total]
            for a, b in zip(marks, marks[1:]):
                self.assertLessEqual(b - a, rng + 1e-6, f"gap {b - a:.2f} > range {rng}")

            best = float("inf")
            for mask in range(1 << n):
                subset = [c for i, c in enumerate(cands) if mask >> i & 1]
                try:
                    plan = plan_fuel_stops(subset, total, range_miles=rng, mpg=10)
                except NoFeasiblePlan:
                    continue
                best = min(best, sum(p.cost for p in plan) + pen * len(plan))
            self.assertGreaterEqual(sum(p.cost for p in got) + pen * len(got), best - 1e-6)
            checked += 1
        self.assertGreater(checked, 100)
