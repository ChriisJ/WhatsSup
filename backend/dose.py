"""Dose calculation + optimal-timing helpers for WhatsSup.

Pure functions that compute the user's recommended dose from a body-weight
profile and the supplement catalog entry, plus timing heuristics used by the
UI to explain *when* a supplement is best taken.

Operates on the SQLAlchemy ORM models (`UserSupplement`, `Supplement`,
`UserProfile`). Kept in its own module so it can be unit-tested without
spinning up the FastAPI app.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from typing import Optional

from .models import Supplement, UserProfile, UserSupplement


def compute_recommended_dose(
    user_supplement: UserSupplement,
    supplement: Supplement,
    profile: Optional[UserProfile],
) -> tuple[Optional[float], Optional[str]]:
    """Return (dose, unit) for the user. None if no body weight + no fixed override.

    Precedence (highest first):
      1. ``custom_fixed_dose`` on the user's link (explicit override).
      2. ``custom_dose_per_kg`` * body weight (per-link override).
      3. Catalog ``default_dose_per_kg`` * body weight.
      4. Falls back to ``(None, custom_unit or default_unit)`` - caller decides
         whether to surface "set your body weight" to the user.
    """
    # 1. Fixed override wins
    if user_supplement.custom_fixed_dose is not None:
        return user_supplement.custom_fixed_dose, user_supplement.custom_unit or supplement.default_unit

    body_weight = profile.body_weight_kg if profile and profile.body_weight_kg else None

    # 2. Per-kg override
    if body_weight and user_supplement.custom_dose_per_kg:
        return round(body_weight * user_supplement.custom_dose_per_kg, 2), (
            user_supplement.custom_unit or supplement.default_unit
        )

    # 3. Catalog default per-kg
    if body_weight and supplement.default_dose_per_kg:
        return round(body_weight * supplement.default_dose_per_kg, 2), (
            user_supplement.custom_unit or supplement.default_unit
        )

    # 4. Cannot compute without weight
    return None, user_supplement.custom_unit or supplement.default_unit


def get_schedule(user_supplement: UserSupplement) -> list[time]:
    """Parse the stored JSON schedule (e.g. ``'["08:00","20:00"]'``) into a list of ``time`` objects, sorted ascending."""
    try:
        raw = json.loads(user_supplement.schedule_json or "[]")
    except Exception:
        return []
    out: list[time] = []
    for item in raw:
        try:
            h, m = item.split(":")
            out.append(time(int(h), int(m)))
        except Exception:
            continue
    return sorted(out)


def next_occurrence(schedule: list[time], now: datetime) -> Optional[datetime]:
    """Given a daily schedule, find the next datetime (today or tomorrow) that is strictly after ``now``."""
    if not schedule:
        return None
    today = now.date()
    candidates = [datetime.combine(today, t) for t in schedule]
    candidates += [datetime.combine(today + timedelta(days=1), t) for t in schedule]
    for c in candidates:
        if c > now:
            return c
    return None


def optimal_window(supplement: Supplement) -> str:
    """Heuristic: best time-of-day recommendation based on category + flags. German UI strings."""
    if supplement.best_taken_empty_stomach:
        return "30 min vor einer Mahlzeit (nüchtern)"
    if supplement.best_taken_with_food:
        return "Mit einer fettreichen Mahlzeit"
    cat = (supplement.category or "").lower()
    if cat in ("vitamin-d", "omega"):
        return "Mit einer fettreichen Mahlzeit (Mittag/Abend)"
    if cat in ("magnesium", "melatonin", "zma"):
        return "30–60 min vor dem Schlafen"
    if cat in ("vitamin-b", "vitamin-c", "iron", "eisen", "zinc", "zink"):
        return "Morgens nüchtern (mit Abstand zu Kaffee/Calcium)"
    if cat in ("creatine",):
        return "Täglich gleicher Zeitpunkt - Morgen empfohlen"
    if cat in ("caffeine", "koffein"):
        return "Vormittags (vor 14 Uhr)"
    return "Feste Tageszeit beibehalten"
