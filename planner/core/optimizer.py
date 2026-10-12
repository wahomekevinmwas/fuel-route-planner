"""Cheapest-fuel planning along a route. Pure Python + numpy, no Django.

Problem: a vehicle drives `total_miles` along a line. It can hold at most `range_miles`
of fuel and burns it at 1 mile per mile. Fuel stations sit at known mile markers with
known prices. Minimise the money spent buying fuel.

Two layers:

1. `_greedy` is the classic "gas station problem" solution, provably optimal for a GIVEN set
   of stations. At a station, look ahead one full tank:
     - if a cheaper station is in reach, buy only enough to get there;
     - else if the destination is in reach, buy only enough to finish;
     - else fill the tank and drive to the cheapest station in reach.

2. `_select_stops` decides WHICH stations are worth stopping at. Pure cost-minimising makes
   silly extra stops to save a few cents, so a small per-stop penalty (time and hassle) is
   included in the decision, solved exactly with dynamic programming. The penalty only
   steers the choice of stops; reported costs are real fuel costs.

The tests check both layers against brute-force oracles.
"""
import math
from dataclasses import dataclass

import numpy as np

EPS = 1e-9
SAME_SPOT_MILES = 0.05


class NoFeasiblePlan(Exception):
    """Raised when two consecutive usable stations are further apart than the vehicle's range."""


@dataclass(frozen=True)
class Candidate:
    key: int
    mile: float
    price: float  # dollars per gallon


@dataclass(frozen=True)
class Purchase:
    key: int
    mile: float
    price: float
    gallons: float

    @property
    def cost(self):
        return self.gallons * self.price


def _collapse_same_spot(cands):
    """Stations sharing (almost) the same mile marker are interchangeable: keep the cheapest."""
    out = []
    for c in sorted(cands, key=lambda c: (c.mile, c.price)):
        if out and abs(c.mile - out[-1].mile) < SAME_SPOT_MILES:
            if c.price < out[-1].price:
                out[-1] = c
            continue
        out.append(c)
    return out


def _greedy(candidates, total_miles, range_miles, mpg, initial_fuel_miles):
    """Exact cheapest purchases using only the given candidate stations."""
    cands = _collapse_same_spot(c for c in candidates if 0 < c.mile < total_miles)
    fuel = range_miles if initial_fuel_miles is None else min(initial_fuel_miles, range_miles)
    pos = 0.0
    here = None  # Candidate we are standing at; None means the start point (no pump).
    purchases = []

    def buy(miles_of_fuel):
        if miles_of_fuel > EPS:
            purchases.append(Purchase(here.key, here.mile, here.price, miles_of_fuel / mpg))

    while True:
        remaining = total_miles - pos
        if remaining <= fuel + EPS:
            return purchases

        if here is None:
            # Start point: we cannot buy here, so we must reach a station on what we have.
            window = [c for c in cands if pos < c.mile <= pos + fuel + EPS]
            if not window:
                raise NoFeasiblePlan("No fuel station within reach of the start.")
            target = min(window, key=lambda c: (c.price, c.mile))
            fuel -= target.mile - pos
        else:
            window = [c for c in cands if pos < c.mile <= pos + range_miles + EPS]
            cheaper = next((c for c in window if c.price < here.price - EPS), None)
            if cheaper is not None:
                buy(max(0.0, (cheaper.mile - pos) - fuel))
                fuel = max(0.0, fuel - (cheaper.mile - pos))
                target = cheaper
            elif remaining <= range_miles + EPS:
                buy(remaining - fuel)
                return purchases
            else:
                if not window:
                    raise NoFeasiblePlan(
                        f"No fuel station within {range_miles:.0f} miles after mile {pos:.0f}."
                    )
                buy(range_miles - fuel)
                best_price = min(c.price for c in window)
                target = [c for c in window if c.price <= best_price + EPS][-1]  # farthest of the cheapest
                fuel = range_miles - (target.mile - pos)

        pos = target.mile
        here = target


def _select_stops(cands, total_miles, range_miles, mpg, fuel0, penalty, unit, reserve=0):
    """Choose WHICH stations to stop at, minimising fuel cost + penalty per stop.

    Dynamic programme over (station, fuel level). Fuel is counted in `unit`-mile steps and
    distances are rounded up, so every plan it returns is genuinely drivable. Buying fuel at a
    station is an "unbounded knapsack" step, done in O(levels) with a running minimum.
    """
    n = len(cands)
    miles = [0.0] + [c.mile for c in cands] + [total_miles]
    # Round each station's absolute position up, then take differences, so rounding error
    # stays under one unit overall instead of accumulating on every leg. The caller checks
    # the chosen stops against exact miles and retries with `reserve=1` if needed.
    levels = int(range_miles // unit) - reserve
    start_level = min(int(min(fuel0, range_miles) // unit), levels)
    pos = [math.ceil((x - EPS) / unit) for x in miles]
    legs = [max(0, pos[k + 1] - pos[k]) for k in range(n + 1)]
    inf = 1e18
    idx = np.arange(levels + 1)

    arrive = np.full(levels + 1, inf)
    arrive[start_level] = 0.0
    source = [None] * (n + 1)  # source[k][f] = fuel level before buying at station k (or -1)

    for k in range(n + 1):
        if k == 0:
            depart = arrive  # the start is not a pump
        else:
            per_unit = cands[k - 1].price * unit / mpg
            shifted = arrive - idx * per_unit
            running_min = np.minimum.accumulate(shifted)
            record = np.where(shifted <= running_min, idx, 0)
            argmin = np.maximum.accumulate(record)
            prev_min = np.concatenate([[inf], running_min[:-1]])
            prev_arg = np.concatenate([[0], argmin[:-1]])
            buy = prev_min + idx * per_unit + penalty
            bought = buy < arrive - 1e-12
            depart = np.where(bought, buy, arrive)
            source[k] = np.where(bought, prev_arg, -1)
        leg = legs[k]
        nxt = np.full(levels + 1, inf)
        if leg <= levels:
            nxt[: levels + 1 - leg] = depart[leg:]
        arrive = nxt

    if arrive.min() >= inf / 2:
        raise NoFeasiblePlan(f"No fuel stations close enough together for a {range_miles:.0f}-mile range.")

    level = int(arrive.argmin())
    chosen = []
    for k in range(n, -1, -1):
        level += legs[k]  # fuel on departing node k
        if k >= 1 and source[k][level] >= 0:
            chosen.append(cands[k - 1])
            level = int(source[k][level])
    return chosen[::-1]


def plan_fuel_stops(candidates, total_miles, range_miles=500.0, mpg=10.0, initial_fuel_miles=None,
                    stop_penalty=0.0, unit_miles=5.0):
    """Return the Purchase list (only stops where fuel is actually bought).

    stop_penalty: dollars of "inconvenience" charged per fuel stop when deciding WHERE to stop
    (it is never added to the reported fuel cost). 0 gives the pure cheapest-fuel plan, which
    happily makes extra stops to save a few cents; a few dollars gives realistic plans.
    """
    cands = _collapse_same_spot(c for c in candidates if 0 < c.mile < total_miles)
    fuel0 = range_miles if initial_fuel_miles is None else min(initial_fuel_miles, range_miles)
    if stop_penalty > 0 and cands and total_miles > fuel0 + EPS:
        for reserve in (0, 1):
            try:
                picked = _select_stops(cands, total_miles, range_miles, mpg, fuel0, stop_penalty,
                                       unit_miles, reserve)
                _greedy(picked, total_miles, range_miles, mpg, initial_fuel_miles)  # exact check
            except NoFeasiblePlan:
                continue
            cands = picked
            break
        # else: keep every candidate; _greedy below gives the pure-cost plan (or raises if truly infeasible)
    return _greedy(cands, total_miles, range_miles, mpg, initial_fuel_miles)
