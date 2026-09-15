"""Blood pressure tracking."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import BloodPressureReading, User
from ..schemas import BloodPressureIn, BloodPressureOut
from ..security import get_current_user

router = APIRouter(prefix="/api/blood-pressure", tags=["blood-pressure"])


@router.get("", response_model=list[BloodPressureOut])
async def list_readings(
    days: int = Query(default=30, ge=1, le=365),
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    cutoff = datetime.now() - timedelta(days=days)
    stmt = (
        select(BloodPressureReading)
        .where(
            BloodPressureReading.user_id == current.id,
            BloodPressureReading.recorded_at >= cutoff,
        )
        .order_by(BloodPressureReading.recorded_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=BloodPressureOut)
async def add_reading(
    body: BloodPressureIn,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rec = BloodPressureReading(
        user_id=current.id,
        systolic=body.systolic,
        diastolic=body.diastolic,
        pulse=body.pulse,
        recorded_at=body.recorded_at or datetime.now(),
        notes=body.notes,
    )
    session.add(rec)
    await session.commit()
    await session.refresh(rec)
    return rec


@router.delete("/{reading_id}")
async def delete_reading(
    reading_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rec = await session.get(BloodPressureReading, reading_id)
    if not rec or rec.user_id != current.id:
        raise HTTPException(status_code=404, detail="Not found")
    await session.delete(rec)
    await session.commit()
    return {"deleted": True}
