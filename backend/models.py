"""SQLAlchemy models for WhatsSup."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IntakeStatus(str, enum.Enum):
    PENDING = "pending"          # scheduled, not yet confirmed
    TAKEN = "taken"              # confirmed
    SKIPPED = "skipped"          # user said skip
    MISSED = "missed"            # passed without confirmation
    SNOOZED = "snoozed"          # temporarily postponed


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    profile: Mapped["UserProfile"] = relationship(
        "UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    supplements: Mapped[list["UserSupplement"]] = relationship(
        "UserSupplement", back_populates="user", cascade="all, delete-orphan"
    )
    intakes: Mapped[list["IntakeLog"]] = relationship(
        "IntakeLog", back_populates="user", cascade="all, delete-orphan"
    )
    bp_readings: Mapped[list["BloodPressureReading"]] = relationship(
        "BloodPressureReading", back_populates="user", cascade="all, delete-orphan"
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    body_weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Berlin")
    notify_discord: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_telegram: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_whatsapp: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_web: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship("User", back_populates="profile")


class Supplement(Base):
    """Catalog of known supplements - shared across users."""

    __tablename__ = "supplements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="other")  # vitamin, mineral, amino, nootropic, ...
    default_dose_per_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    default_unit: Mapped[str] = mapped_column(String(16), default="mg")
    half_life_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    best_taken_with_food: Mapped[bool] = mapped_column(Boolean, default=False)
    best_taken_empty_stomach: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user_links: Mapped[list["UserSupplement"]] = relationship(
        "UserSupplement", back_populates="supplement"
    )


class UserSupplement(Base):
    """A specific supplement tracked by a specific user, with their dose + schedule."""

    __tablename__ = "user_supplements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    supplement_id: Mapped[int] = mapped_column(
        ForeignKey("supplements.id", ondelete="CASCADE"), nullable=False
    )
    # If non-null overrides supplement.default_dose_per_kg
    custom_dose_per_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    custom_unit: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    custom_fixed_dose: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Schedule stored as JSON string list of HH:MM times, e.g. '["08:00","20:00"]'
    schedule_json: Mapped[str] = mapped_column(String(255), default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    user: Mapped[User] = relationship("User", back_populates="supplements")
    supplement: Mapped[Supplement] = relationship("Supplement", back_populates="user_links")
    intakes: Mapped[list["IntakeLog"]] = relationship(
        "IntakeLog", back_populates="user_supplement", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "supplement_id", name="uq_user_supplement"),
    )


class IntakeLog(Base):
    """Record of a (scheduled or ad-hoc) intake event."""

    __tablename__ = "intake_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user_supplement_id: Mapped[int] = mapped_column(
        ForeignKey("user_supplements.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[IntakeStatus] = mapped_column(
        Enum(IntakeStatus), default=IntakeStatus.PENDING
    )
    actual_taken_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dose_taken: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    confirmed_via: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Number of reminder pushes sent so far (for 30-min loop)
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)
    # Timestamp of the most recent reminder push. Drives the scheduler's
    # throttle: a new reminder is sent only if ``now - last_reminded_at``
    # exceeds the configured interval, regardless of how many pushes were
    # skipped (e.g. quiet hours, bot downtime). Nullable until first push.
    last_reminded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    user: Mapped[User] = relationship("User", back_populates="intakes")
    user_supplement: Mapped[UserSupplement] = relationship(
        "UserSupplement", back_populates="intakes"
    )


class BloodPressureReading(Base):
    __tablename__ = "blood_pressure_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    systolic: Mapped[int] = mapped_column(Integer, nullable=False)
    diastolic: Mapped[int] = mapped_column(Integer, nullable=False)
    pulse: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship("User", back_populates="bp_readings")


class InteractionRule(Base):
    """Predefined (or user-flagged) interaction between two supplements."""

    __tablename__ = "interaction_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplement_a_slug: Mapped[str] = mapped_column(String(128), nullable=False)
    supplement_b_slug: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="warning")  # info, warning, danger
    description: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
