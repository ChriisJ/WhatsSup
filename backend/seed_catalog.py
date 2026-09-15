"""Built-in supplement catalog. Inserted on first start if missing."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .models import Supplement


SEED_CATALOG: list[dict] = [
    {
        "slug": "creatine",
        "name": "Creatine Monohydrate",
        "category": "amino",
        "default_dose_per_kg": 0.1,
        "default_unit": "g",
        "half_life_hours": 3.0,
        "best_taken_with_food": False,
        "best_taken_empty_stomach": False,
        "notes": "Tägliche Erhaltungsdosis. Optional: 3-5g fix.",
    },
    {
        "slug": "vitamin-d3",
        "name": "Vitamin D3",
        "category": "vitamin-d",
        "default_dose_per_kg": None,
        "default_unit": "IU",
        "half_life_hours": 720.0,  # ~30 days in tissue
        "best_taken_with_food": True,
        "best_taken_empty_stomach": False,
        "notes": "Empfohlene Dosis 1000-4000 IU täglich. Mit Fett für Aufnahme.",
    },
    {
        "slug": "magnesium",
        "name": "Magnesium (Bisglycinat / Citrat)",
        "category": "magnesium",
        "default_dose_per_kg": 6.0,
        "default_unit": "mg",
        "half_life_hours": 24.0,
        "best_taken_with_food": False,
        "best_taken_empty_stomach": True,
        "notes": "Abends fördert Schlaf. Bisglycinat = magenfreundlich.",
    },
    {
        "slug": "zinc",
        "name": "Zink",
        "category": "zinc",
        "default_dose_per_kg": 0.5,
        "default_unit": "mg",
        "half_life_hours": 24.0,
        "best_taken_with_food": False,
        "best_taken_empty_stomach": True,
        "notes": "Nüchtern für beste Aufnahme. Mit Kupfer balancieren.",
    },
    {
        "slug": "omega-3",
        "name": "Omega-3 (EPA/DHA)",
        "category": "omega",
        "default_dose_per_kg": 20.0,  # mg/kg EPA+DHA
        "default_unit": "mg",
        "half_life_hours": 48.0,
        "best_taken_with_food": True,
        "best_taken_empty_stomach": False,
        "notes": "Mit fettreicher Mahlzeit. Wirkt entzündungshemmend.",
    },
    {
        "slug": "vitamin-c",
        "name": "Vitamin C",
        "category": "vitamin-c",
        "default_dose_per_kg": 8.0,
        "default_unit": "mg",
        "half_life_hours": 12.0,
        "best_taken_with_food": False,
        "best_taken_empty_stomach": True,
        "notes": "Tagesdosis splitten bei >500 mg.",
    },
    {
        "slug": "iron",
        "name": "Eisen",
        "category": "iron",
        "default_dose_per_kg": None,
        "default_unit": "mg",
        "half_life_hours": 72.0,
        "best_taken_with_food": False,
        "best_taken_empty_stomach": True,
        "notes": "Mit Vitamin C für Aufnahme. Abstand zu Calcium/Kaffee/Tee.",
    },
    {
        "slug": "melatonin",
        "name": "Melatonin",
        "category": "melatonin",
        "default_dose_per_kg": None,
        "default_unit": "mg",
        "half_life_hours": 1.0,
        "best_taken_with_food": False,
        "best_taken_empty_stomach": True,
        "notes": "0.3-1 mg 30 min vor Schlafen. Niedrig dosieren.",
    },
    {
        "slug": "caffeine",
        "name": "Koffein",
        "category": "caffeine",
        "default_dose_per_kg": 3.0,
        "default_unit": "mg",
        "half_life_hours": 5.0,
        "best_taken_with_food": False,
        "best_taken_empty_stomach": True,
        "notes": "Vor 14 Uhr. Toleranz steigt schnell.",
    },
    {
        "slug": "l-theanine",
        "name": "L-Theanin",
        "category": "nootropic",
        "default_dose_per_kg": 4.0,
        "default_unit": "mg",
        "half_life_hours": 2.5,
        "best_taken_with_food": False,
        "best_taken_empty_stomach": True,
        "notes": "Gut mit Koffein kombinierbar (Fokus ohne Crash).",
    },
    {
        "slug": "ashwagandha",
        "name": "Ashwagandha (KSM-66)",
        "category": "adaptogen",
        "default_dose_per_kg": 5.0,
        "default_unit": "mg",
        "half_life_hours": 6.0,
        "best_taken_with_food": True,
        "best_taken_empty_stomach": False,
        "notes": "Mit Mahlzeit. Stressreduktion, Cortisol.",
    },
    {
        "slug": "vitamin-b12",
        "name": "Vitamin B12",
        "category": "vitamin-b",
        "default_dose_per_kg": None,
        "default_unit": "mcg",
        "half_life_hours": 6.0,
        "best_taken_with_food": False,
        "best_taken_empty_stomach": True,
        "notes": "Sublingual oder morgens nüchtern.",
    },
    {
        "slug": "vitamin-k2",
        "name": "Vitamin K2 (MK-7)",
        "category": "vitamin-k",
        "default_dose_per_kg": None,
        "default_unit": "mcg",
        "half_life_hours": 72.0,
        "best_taken_with_food": True,
        "best_taken_empty_stomach": False,
        "notes": "Mit Fett. Synergie mit Vitamin D.",
    },
    {
        "slug": "zma",
        "name": "ZMA (Zink/Magnesium/B6)",
        "category": "mineral-complex",
        "default_dose_per_kg": None,
        "default_unit": "mg",
        "half_life_hours": 24.0,
        "best_taken_with_food": False,
        "best_taken_empty_stomach": True,
        "notes": "Auf nüchternen Magen vor dem Schlafen.",
    },
    {
        "slug": "calcium",
        "name": "Calcium",
        "category": "mineral",
        "default_dose_per_kg": 15.0,
        "default_unit": "mg",
        "half_life_hours": 24.0,
        "best_taken_with_food": True,
        "best_taken_empty_stomach": False,
        "notes": "Mit Mahlzeit. Auf Splitting achten (<500 mg pro Dosis).",
    },
    {
        "slug": "coffee",
        "name": "Kaffee",
        "category": "caffeine",
        "default_dose_per_kg": None,
        "default_unit": "cup",
        "half_life_hours": 5.0,
        "best_taken_with_food": False,
        "best_taken_empty_stomach": False,
        "notes": "Vor 14 Uhr wegen Melatonin-Unterdrückung.",
    },
]


async def ensure_seed_catalog(session: AsyncSession) -> None:
    """Insert SEED_CATALOG entries if missing (matched by slug)."""
    existing = await session.execute(select(Supplement))
    have = {s.slug for s in existing.scalars().all()}
    for entry in SEED_CATALOG:
        if entry["slug"] in have:
            continue
        session.add(Supplement(**entry))
    await session.commit()
