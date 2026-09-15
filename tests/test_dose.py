"""Smoke tests using only Python stdlib (no FastAPI/SQLAlchemy deps).

These tests verify the pure-logic helpers. Run with:
    python tests/test_dose.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

# Make backend importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.dose import (  # noqa: E402
    compute_recommended_dose,
    get_schedule,
    next_occurrence,
    optimal_window,
)


@dataclass
class FakeSupp:
    default_dose_per_kg: float = 0.1
    default_unit: str = "g"
    category: str = "amino"
    best_taken_with_food: bool = False
    best_taken_empty_stomach: bool = False


@dataclass
class FakeUS:
    custom_dose_per_kg: float = None
    custom_unit: str = None
    custom_fixed_dose: float = None
    schedule_json: str = "[]"


@dataclass
class FakeProfile:
    body_weight_kg: float = 80.0


def _supp(**kw) -> FakeSupp:
    return FakeSupp(**kw)


def _profile(weight=80.0) -> FakeProfile:
    return FakeProfile(body_weight_kg=weight)


def _us(schedule, **kw) -> FakeUS:
    return FakeUS(schedule_json=json.dumps(schedule), **kw)


def assert_eq(actual, expected, name):
    status = "✓" if actual == expected else "✗"
    print(f"  {status} {name}: expected={expected!r}, got={actual!r}")
    if actual != expected:
        sys.exit(1)


# ---- compute_recommended_dose ----
print("compute_recommended_dose")
us = _us([])
supp = _supp(default_dose_per_kg=0.1, default_unit="g")
prof = _profile(weight=80)
dose, unit = compute_recommended_dose(us, supp, prof)
assert_eq(dose, 8.0, "per-kg default: 80kg * 0.1 g/kg")
assert_eq(unit, "g", "unit g")

us = _us([], custom_dose_per_kg=0.15)
dose, unit = compute_recommended_dose(us, supp, prof)
assert_eq(dose, 12.0, "custom per-kg: 80 * 0.15")

us = _us([], custom_fixed_dose=5.0)
dose, unit = compute_recommended_dose(us, supp, prof)
assert_eq(dose, 5.0, "fixed dose wins")

us = _us([])
prof = _profile(weight=None)
dose, _ = compute_recommended_dose(us, supp, prof)
assert_eq(dose, None, "no body weight -> None")

# ---- get_schedule ----
print("get_schedule")
us = _us(["08:00", "20:30"])
sched = get_schedule(us)
assert_eq([t.strftime("%H:%M") for t in sched], ["08:00", "20:30"], "schedule parsed")

us = _us(["bad", "20:30"])
sched = get_schedule(us)
assert_eq([t.strftime("%H:%M") for t in sched], ["20:30"], "invalid entry dropped")

# ---- next_occurrence ----
print("next_occurrence")
now = datetime(2026, 9, 15, 10, 15)
sched = [time(8, 0), time(20, 0)]
nxt = next_occurrence(sched, now)
assert_eq(nxt, datetime(2026, 9, 15, 20, 0), "next is today 20:00")

now = datetime(2026, 9, 15, 21, 0)
nxt = next_occurrence(sched, now)
assert_eq(nxt, datetime(2026, 9, 16, 8, 0), "next is tomorrow 08:00")

# ---- optimal_window ----
print("optimal_window")
assert_eq(optimal_window(_supp(category="magnesium")), "30–60 min vor dem Schlafen", "magnesium")
assert_eq(optimal_window(_supp(category="vitamin-d")), "Mit einer fettreichen Mahlzeit (Mittag/Abend)", "vit D")
assert_eq(optimal_window(_supp(best_taken_empty_stomach=True)), "30 min vor einer Mahlzeit (nüchtern)", "empty stomach flag")
assert_eq(optimal_window(_supp(best_taken_with_food=True)), "Mit einer fettreichen Mahlzeit", "with food flag")

print("\nAll dose/schedule/timing logic tests passed ✓")
