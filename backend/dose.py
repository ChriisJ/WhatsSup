"""Dose calculation + optimal-timing helpers.

Pure functions that operate on duck-typed objects (anything with the
attributes they read). This keeps the module importable without
SQLAlchemy/Pydantic installed - useful for lightweight unit tests.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from typing import Optional, Protocol


class _HasDose(Protocol):
    default_dose_per_kg: Optional[float]
    default_unit: str
    category: str
    best_taken_with_food: bool
    best_taken_empty_stomach: bool


class _HasUserDose(Protocol):
    custom_dose_per_kg: Optional[float]
    custom_unit: Optional[str]
    custom_fixed_dose: Optional[float]
    schedule_json: str


def compute_recommended_dose(
    user_supplement: _HasUserDose,
    supplement: _HasDose,
    profile: Optional[object],
) -> tuple[Optional[float], Optional[str]]:
    """Return (dose, unit). None if no body weight + no fixed override."""
    if user_supplement.custom_fixed_dose is not None:
        return user_supplement.custom_fixed_dose, user_supplement.custom_unit or supplement.default_unit

    body_weight = getattr(profile, "body_weight_kg", None) if profile else None

    if body_weight and user_supplement.custom_dose_per_kg:
        return round(body_weight * user_supplement.custom_dose_per_kg, 2), (
            user_supplement.custom_unit or supplement.default_unit
        )

    if body_weight and supplement.default_dose_per_kg:
        return round(body_weight * supplement.default_dose_per_kg, 2), (
            user_supplement.custom_unit or supplement.default_unit
        )

    return None, user_supplement.custom_unit or supplement.default_unit


def get_schedule(user_supplement: _HasUserDose) -> list[time]:
    try:
        raw = json.loads(user_supplement.schedule_json)
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
    if not schedule:
        return None
    today = now.date()
    candidates = [datetime.combine(today, t) for t in schedule]
    candidates += [datetime.combine(today + timedelta(days=1), t) for t in schedule]
    for c in candidates:
        if c > now:
            return c
    return None


def optimal_window(supplement: _HasDose) -> str:
    if supplement.best_taken_empty_stomach:
        return "30 min vor einer Mahlzeit (nüchtern)"
    if supplement.best_taken_with_food:
        return "Mit einer fettreichen Mahlzeit"
    cat = (getattr(supplement, "category", "") or "").lower()
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


def compute_recommended_dose(
    user_supplement: UserSupplement,
    supplement: Supplement,
    profile: Optional[UserProfile],
) -> tuple[Optional[float], Optional[str]]:
    """Return (dose, unit) for the user. None if no body weight + no fixed override."""
    # 1. Fixed override wins
    if user_supplement.custom_fixed_dose is not None:
        return user_supplement.custom_fixed_dose, user_supplement.custom_unit or supplement.default_unit

    # 2. Per-kg override
    if profile and profile.body_weight_kg and user_supplement.custom_dose_per_kg:
        return round(profile.body_weight_kg * user_supplement.custom_dose_per_kg, 2), (
            user_supplement.custom_unit or supplement.default_unit
        )

    # 3. Catalog default per-kg
    if profile and profile.body_weight_kg and supplement.default_dose_per_kg:
        return round(profile.body_weight_kg * supplement.default_dose_per_kg, 2), (
            user_supplement.custom_unit or supplement.default_unit
        )

    # 4. Cannot compute without weight
    return None, user_supplement.custom_unit or supplement.default_unit


def get_schedule(user_supplement: UserSupplement) -> list[time]:
    """Parse the stored JSON schedule into a list of time objects."""
    try:
        raw = json.loads(user_supplement.schedule_json)
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
    """Given a daily schedule, find the next datetime (today or tomorrow) >= now."""
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
    """Heuristic: best time-of-day recommendation based on category + flags."""
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
