"""Supplement-supplement interactions.

Curated, conservative list. Severity: info | warning | danger.
NOT a substitute for medical advice.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .models import InteractionRule


# Built-in seed data — applied on first startup.
SEED_RULES: list[dict] = [
    {
        "supplement_a_slug": "calcium",
        "supplement_b_slug": "iron",
        "severity": "warning",
        "description": "Calcium verringert die Eisenaufnahme.",
        "recommendation": "Mindestens 2 Stunden Abstand zwischen den Einnahmen.",
    },
    {
        "supplement_a_slug": "calcium",
        "supplement_b_slug": "zinc",
        "severity": "warning",
        "description": "Calcium und Zink konkurrieren um dieselben Aufnahmewege.",
        "recommendation": "Zeitlich versetzt einnehmen (2+ Stunden).",
    },
    {
        "supplement_a_slug": "calcium",
        "supplement_b_slug": "magnesium",
        "severity": "info",
        "description": "Hohe Dosen können sich gegenseitig behindern.",
        "recommendation": "Unter 500 mg Calcium pro Einzeldosis bleiben oder zeitlich trennen.",
    },
    {
        "supplement_a_slug": "iron",
        "supplement_b_slug": "zinc",
        "severity": "warning",
        "description": "Gegenseitige Aufnahmebehinderung.",
        "recommendation": "2+ Stunden Abstand.",
    },
    {
        "supplement_a_slug": "iron",
        "supplement_b_slug": "coffee",
        "severity": "warning",
        "description": "Koffein/Tannine hemmen die Eisenaufnahme.",
        "recommendation": "Eisen mindestens 1 Stunde vor/nach Kaffee einnehmen.",
    },
    {
        "supplement_a_slug": "zinc",
        "supplement_b_slug": "copper",
        "severity": "warning",
        "description": "Langfristig hohe Zinkdosen können Kupfermangel verursachen.",
        "recommendation": "Bei regelmäßiger Zinkeinnahme Kupfer supplementieren (1 mg Cu pro 15 mg Zn).",
    },
    {
        "supplement_a_slug": "magnesium",
        "supplement_b_slug": "calcium",
        "severity": "info",
        "description": "Hohe Magnesiumdosen können Calcium-Aufnahme reduzieren.",
        "recommendation": "Idealerweise 2 Stunden zeitversetzt.",
    },
    {
        "supplement_a_slug": "vitamin-c",
        "supplement_b_slug": "vitamin-b12",
        "severity": "info",
        "description": "Hohe Vitamin-C-Dosen können B12 inaktivieren.",
        "recommendation": "Zeitlich trennen, besonders bei Hochdosis-C.",
    },
    {
        "supplement_a_slug": "melatonin",
        "supplement_b_slug": "caffeine",
        "severity": "danger",
        "description": "Koffein untergräbt die Melatonin-Wirkung.",
        "recommendation": "Kein Koffein ab 6 Stunden vor Melatonin.",
    },
    {
        "supplement_a_slug": "vitamin-k",
        "supplement_b_slug": "vitamin-e",
        "severity": "warning",
        "description": "Hohe Vitamin-E-Dosen können die Vitamin-K-Wirkung stören.",
        "recommendation": "Wenn Blutverdünner: ärztlich abklären.",
    },
    {
        "supplement_a_slug": "ashwagandha",
        "supplement_b_slug": "l-theanine",
        "severity": "info",
        "description": "Kombinierte sedative Wirkung möglich.",
        "recommendation": "Niedrig starten, Wirkung beobachten.",
    },
    {
        "supplement_a_slug": "creatine",
        "supplement_b_slug": "caffeine",
        "severity": "info",
        "description": "Frühe Studien zeigten Behinderung - neuere Daten zeigen keinen Effekt.",
        "recommendation": "Kann gemeinsam eingenommen werden, wenn keine Magenprobleme auftreten.",
    },
]


async def ensure_seed_rules(session: AsyncSession) -> None:
    """Insert SEED_RULES if missing (matched by slug pair)."""
    existing = await session.execute(select(InteractionRule))
    have = {(r.supplement_a_slug, r.supplement_b_slug) for r in existing.scalars().all()}
    for rule in SEED_RULES:
        a, b = sorted([rule["supplement_a_slug"], rule["supplement_b_slug"]])
        if (a, b) in have or (b, a) in have:
            continue
        session.add(InteractionRule(
            supplement_a_slug=a,
            supplement_b_slug=b,
            severity=rule["severity"],
            description=rule["description"],
            recommendation=rule["recommendation"],
        ))
    await session.commit()


async def find_interactions_for(
    session: AsyncSession,
    slugs: Iterable[str],
) -> list[InteractionRule]:
    """Return all interaction rules where any of the given slugs appears on either side."""
    slugs = set(slugs)
    if len(slugs) < 2:
        return []
    result = await session.execute(select(InteractionRule))
    matches: list[InteractionRule] = []
    for rule in result.scalars().all():
        if rule.supplement_a_slug in slugs or rule.supplement_b_slug in slugs:
            # require both sides are in the set
            if rule.supplement_a_slug in slugs and rule.supplement_b_slug in slugs:
                matches.append(rule)
    return matches
