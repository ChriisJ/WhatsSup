"""Compliance statistics."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_session
from ..models import IntakeLog, IntakeStatus, Supplement, User, UserSupplement
from ..schemas import ComplianceStats
from ..security import get_current_user

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/compliance", response_model=ComplianceStats)
async def compliance(
    days: int = Query(default=30, ge=1, le=365),
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    cutoff = datetime.now() - timedelta(days=days)
    stmt = (
        select(IntakeLog)
        .options(selectinload(IntakeLog.user_supplement).selectinload(UserSupplement.supplement))
        .where(IntakeLog.user_id == current.id, IntakeLog.scheduled_for >= cutoff)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    total = len(rows)
    taken = sum(1 for r in rows if r.status == IntakeStatus.TAKEN)
    skipped = sum(1 for r in rows if r.status == IntakeStatus.SKIPPED)
    missed = sum(1 for r in rows if r.status == IntakeStatus.MISSED)

    per_supp: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [done, scheduled]
    for r in rows:
        name = r.user_supplement.supplement.name if r.user_supplement and r.user_supplement.supplement else "?"
        per_supp[name][1] += 1
        if r.status == IntakeStatus.TAKEN:
            per_supp[name][0] += 1

    per_supp_pct = {
        name: round((v[0] / v[1] * 100) if v[1] else 0, 1)
        for name, v in per_supp.items()
    }

    pct = round((taken / total * 100) if total else 0, 1)
    return ComplianceStats(
        days=days,
        total_scheduled=total,
        total_taken=taken,
        total_skipped=skipped,
        total_missed=missed,
        compliance_pct=pct,
        per_supplement=per_supp_pct,
    )
