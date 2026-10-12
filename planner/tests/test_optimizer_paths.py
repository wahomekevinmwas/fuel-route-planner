from unittest import mock

from django.test import SimpleTestCase

from planner.core import optimizer
from planner.core.optimizer import Candidate, plan_fuel_stops

RANGE, MPG, UNIT = 50, 10, 1.0


def max_gap(plan, total):
    marks = [0.0] + [p.mile for p in plan] + [total]
    return max(b - a for a, b in zip(marks, marks[1:]))


class DpRetryPathTests(SimpleTestCase):
    """Inputs found by search: the DP's first attempt is rejected by the exact check."""

    def _plan(self, cands, total, pen):
        with mock.patch.object(optimizer, "_select_stops", wraps=optimizer._select_stops) as spy:
            plan = plan_fuel_stops(cands, total, range_miles=RANGE, mpg=MPG, stop_penalty=pen, unit_miles=UNIT)
        return plan, spy

    def test_retry_with_one_unit_reserve_gives_a_drivable_plan(self):
        total = 148.93
        cands = [Candidate(0, 98.16, 3.37), Candidate(1, 63.74, 3.25), Candidate(2, 138.32, 4.8),
                 Candidate(3, 48.5, 3.65), Candidate(4, 29.15, 4.13)]
        plan, spy = self._plan(cands, total, 0.5)
        self.assertEqual(spy.call_count, 2)
        self.assertEqual(spy.call_args_list[0].args[-1], 0)  # first attempt: no reserve
        self.assertEqual(spy.call_args_list[1].args[-1], 1)  # retry: one-unit reserve
        self.assertLessEqual(max_gap(plan, total), RANGE + 1e-6)

    def test_falls_back_to_pure_cost_plan_when_both_attempts_fail(self):
        total = 107.64
        cands = [Candidate(0, 85.07, 3.48), Candidate(1, 57.19, 3.92), Candidate(2, 7.3, 4.12)]
        plan, spy = self._plan(cands, total, 2.0)
        self.assertEqual(spy.call_count, 2)
        exact = plan_fuel_stops(cands, total, range_miles=RANGE, mpg=MPG)  # penalty 0
        self.assertEqual([p.key for p in plan], [p.key for p in exact])
        self.assertLessEqual(max_gap(plan, total), RANGE + 1e-6)
