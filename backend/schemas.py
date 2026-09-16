"""Pydantic schemas for API I/O."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import IntakeStatus


# ---- Auth ----
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    is_admin: bool


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=4, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    is_admin: bool
    created_at: datetime


# ---- Profile ----
class ProfileIn(BaseModel):
    body_weight_kg: Optional[float] = Field(default=None, gt=0, lt=500)
    timezone: str = "Europe/Berlin"
    notify_discord: bool = True
    notify_telegram: bool = True
    notify_whatsapp: bool = True
    notify_web: bool = True


class ProfileOut(ProfileIn):
    model_config = ConfigDict(from_attributes=True)


# ---- Supplement catalog ----
class SupplementBase(BaseModel):
    name: str
    category: str = "other"
    default_dose_per_kg: Optional[float] = None
    default_unit: str = "mg"
    half_life_hours: Optional[float] = None
    best_taken_with_food: bool = False
    best_taken_empty_stomach: bool = False
    notes: Optional[str] = None


class SupplementCreate(SupplementBase):
    slug: str


class SupplementOut(SupplementBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str


# ---- User supplement link ----
class UserSupplementIn(BaseModel):
    supplement_id: int
    custom_dose_per_kg: Optional[float] = None
    custom_unit: Optional[str] = None
    custom_fixed_dose: Optional[float] = None
    schedule: list[str] = Field(
        default_factory=list,
        description="List of HH:MM times, e.g. ['08:00','20:00']",
    )
    active: bool = True
    notes: Optional[str] = None


class UserSupplementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    supplement_id: int
    supplement: SupplementOut
    custom_dose_per_kg: Optional[float]
    custom_unit: Optional[str]
    custom_fixed_dose: Optional[float]
    schedule: list[str]
    active: bool
    notes: Optional[str]
    # Computed fields (filled by route)
    recommended_dose: Optional[float] = None
    recommended_unit: Optional[str] = None
    next_due_at: Optional[datetime] = None


# ---- Intake ----
class IntakeConfirmIn(BaseModel):
    dose_taken: Optional[float] = None
    unit: Optional[str] = None
    notes: Optional[str] = None


class IntakeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_supplement_id: int
    # Nested so the frontend can render the supplement name + dose without
    # an extra round-trip per intake. The route eagerly loads it via
    # selectinload(IntakeLog.user_supplement).selectinload(UserSupplement.supplement).
    user_supplement: "UserSupplementSlim"
    scheduled_for: datetime
    status: IntakeStatus
    actual_taken_at: Optional[datetime]
    dose_taken: Optional[float]
    unit: Optional[str]
    confirmed_via: Optional[str]
    reminder_count: int


class UserSupplementSlim(BaseModel):
    """Subset of UserSupplementOut returned inside IntakeOut - no need for
    the heavy nested Supplement just for display."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    supplement_id: int
    schedule: list[str] = []
    custom_dose_per_kg: Optional[float] = None
    custom_unit: Optional[str] = None
    custom_fixed_dose: Optional[float] = None
    supplement_name: Optional[str] = None
    supplement_category: Optional[str] = None


# ---- Blood pressure ----
class BloodPressureIn(BaseModel):
    systolic: int = Field(ge=50, le=300)
    diastolic: int = Field(ge=30, le=200)
    pulse: Optional[int] = Field(default=None, ge=20, le=250)
    recorded_at: Optional[datetime] = None
    notes: Optional[str] = None


class BloodPressureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    systolic: int
    diastolic: int
    pulse: Optional[int]
    recorded_at: datetime
    notes: Optional[str]


# ---- Stats ----
class ComplianceStats(BaseModel):
    days: int
    total_scheduled: int
    total_taken: int
    total_skipped: int
    total_missed: int
    compliance_pct: float
    per_supplement: dict[str, float] = Field(default_factory=dict)


# ---- Interactions ----
class InteractionOut(BaseModel):
    supplement_a: str
    supplement_b: str
    severity: str
    description: str
    recommendation: str
