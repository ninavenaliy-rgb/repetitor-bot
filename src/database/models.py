"""SQLAlchemy ORM models for all database tables."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import Index, JSON, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Tutor(Base):
    """Tutor (bot operator) account."""

    __tablename__ = "tutors"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    subjects: Mapped[str] = mapped_column(String(500), default="English")
    calendar_id: Mapped[str] = mapped_column(String(500), default="primary")
    subscription_plan: Mapped[str] = mapped_column(String(20), default="BASIC")
    default_lesson_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("2000"))
    default_duration_min: Mapped[int] = mapped_column(Integer, default=60)
    invite_token: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True, index=True)
    registration_state: Mapped[str] = mapped_column(String(20), default="active")
    referral_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True, index=True)
    referred_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("tutors.id", ondelete="SET NULL"), nullable=True
    )
    referral_balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    users: Mapped[list[User]] = relationship(back_populates="tutor")
    bookings: Mapped[list[Booking]] = relationship(back_populates="tutor")
    materials: Mapped[list[Material]] = relationship(back_populates="tutor")
    quizzes: Mapped[list[Quiz]] = relationship(back_populates="tutor")
    referrals: Mapped[list[Tutor]] = relationship(
        "Tutor",
        foreign_keys="[Tutor.referred_by_id]",
        back_populates="referrer",
    )
    referrer: Mapped[Optional[Tutor]] = relationship(
        "Tutor",
        foreign_keys="[Tutor.referred_by_id]",
        back_populates="referrals",
        remote_side="[Tutor.id]",
    )


class LessonPackage(Base):
    """Prepaid lesson package purchased by a student."""

    __tablename__ = "lesson_packages"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tutor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tutors.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    package_type: Mapped[str] = mapped_column(String(10))  # "4", "8", "12"
    total_lessons: Mapped[int] = mapped_column(Integer)
    lessons_remaining: Mapped[int] = mapped_column(Integer)
    price_total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/exhausted/cancelled
    payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    tutor: Mapped[Tutor] = relationship(foreign_keys="[LessonPackage.tutor_id]")
    user: Mapped[User] = relationship(foreign_keys="[LessonPackage.user_id]")


class User(Base):
    """Student / lead user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tutor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("tutors.id", ondelete="SET NULL"), nullable=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    parent_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    parent_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    parent_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notify_parent: Mapped[bool] = mapped_column(Boolean, default=False)
    active_package_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("lesson_packages.id", ondelete="SET NULL"), nullable=True
    )
    cefr_level: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    goal: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    subscription_tier: Mapped[str] = mapped_column(String(20), default="BASIC")
    price_per_lesson: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    language: Mapped[str] = mapped_column(String(5), default="ru")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Progress bar: tutor sets 0-100 manually
    progress_level: Mapped[int] = mapped_column(Integer, default=0)
    # Student referral system
    student_referral_code: Mapped[Optional[str]] = mapped_column(
        String(12), unique=True, nullable=True
    )
    referred_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    bonus_lessons: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    tutor: Mapped[Optional[Tutor]] = relationship(back_populates="users")
    bookings: Mapped[list[Booking]] = relationship(back_populates="user")
    engagement_events: Mapped[list[EngagementEvent]] = relationship(
        back_populates="user"
    )
    ai_usages: Mapped[list[AIUsage]] = relationship(back_populates="user")
    quiz_attempts: Mapped[list[QuizAttempt]] = relationship(back_populates="user")


class Booking(Base):
    """Lesson booking / appointment."""

    __tablename__ = "bookings"
    __table_args__ = (
        # Composite index for the most common query: tutor's future bookings
        Index("ix_bookings_tutor_scheduled", "tutor_id", "scheduled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tutor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tutors.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    scheduled_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    duration_min: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    confirmation_status: Mapped[str] = mapped_column(String(20), default="pending")
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_rule: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    topic: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    homework: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lesson_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_lesson_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    voice_homework_file_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    parent_notified_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    google_event_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    reminders_sent: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    tutor: Mapped[Tutor] = relationship(back_populates="bookings")
    user: Mapped[User] = relationship(back_populates="bookings")


class Material(Base):
    """Teaching material (file, document, media)."""

    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tutor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tutors.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_id: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(100), default="English")
    cefr_level: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    tutor: Mapped[Tutor] = relationship(back_populates="materials")
    assignments: Mapped[list[MaterialAssignment]] = relationship(
        back_populates="material"
    )


class MaterialAssignment(Base):
    """Track which materials were sent to which students."""

    __tablename__ = "material_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("materials.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    sent_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    material: Mapped[Material] = relationship(back_populates="assignments")
    user: Mapped[User] = relationship()


class Payment(Base):
    """Payment record for lesson or subscription."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tutor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tutors.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    payment_type: Mapped[str] = mapped_column(String(20), default="lesson")
    provider_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    paid_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    tutor: Mapped[Tutor] = relationship()
    user: Mapped[User] = relationship()


class Quiz(Base):
    """Quiz / test created by tutor or auto-generated."""

    __tablename__ = "quizzes"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tutor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("tutors.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(100), default="English")
    cefr_level: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    questions: Mapped[dict] = mapped_column(JSON, default=list)
    time_limit_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_placement: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    tutor: Mapped[Optional[Tutor]] = relationship(back_populates="quizzes")
    attempts: Mapped[list[QuizAttempt]] = relationship(back_populates="quiz")


class QuizAttempt(Base):
    """Student's attempt at a quiz."""

    __tablename__ = "quiz_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("quizzes.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    answers: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    score: Mapped[int] = mapped_column(Integer, default=0)
    max_score: Mapped[int] = mapped_column(Integer, default=0)
    cefr_result: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    quiz: Mapped[Quiz] = relationship(back_populates="attempts")
    user: Mapped[User] = relationship(back_populates="quiz_attempts")


class EngagementEvent(Base):
    """Daily engagement activity tracking."""

    __tablename__ = "engagement_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(30))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    streak_day: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="engagement_events")


class AIUsage(Base):
    """AI API usage tracking for rate limiting and cost monitoring."""

    __tablename__ = "ai_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    usage_type: Mapped[str] = mapped_column(String(30))
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="ai_usages")


class AISession(Base):
    """Short-term operational memory for AI administrator (per tutor session)."""

    __tablename__ = "ai_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tutor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tutors.id", ondelete="CASCADE"), index=True
    )
    # JSON: {last_student_referenced, last_datetime_referenced, pending_action, history}
    context_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_interaction_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tutor: Mapped[Tutor] = relationship(foreign_keys=[tutor_id])


class AIMetric(Base):
    """Analytics: every AI admin command logged here for quality tracking."""

    __tablename__ = "ai_metrics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tutor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tutors.id", ondelete="CASCADE"), index=True
    )
    intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    was_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    error_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    raw_input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tutor: Mapped[Tutor] = relationship(foreign_keys=[tutor_id])


class StudentMetrics(Base):
    """Current academic score snapshot — one row per student, upserted on each event."""

    __tablename__ = "student_metrics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    academic_score: Mapped[int] = mapped_column(Integer, default=0)
    cefr_level: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    attendance_rate: Mapped[float] = mapped_column(Float, default=0.0)
    engagement_rate: Mapped[float] = mapped_column(Float, default=0.0)
    hw_count_30d: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])


class ScoreHistory(Base):
    """Event-driven academic score change log."""

    __tablename__ = "score_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[int] = mapped_column(Integer)
    delta: Mapped[int] = mapped_column(Integer, default=0)
    source_event: Mapped[str] = mapped_column(String(50))  # homework / lesson / engagement / placement
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])


class ReferralCommission(Base):
    """Referral commission record — 15% from referred tutor's student payments."""

    __tablename__ = "referral_commissions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    referrer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tutors.id", ondelete="CASCADE"), index=True
    )
    referred_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tutors.id", ondelete="CASCADE")
    )
    payment_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    commission: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    referrer: Mapped[Tutor] = relationship(foreign_keys=[referrer_id])
    referred: Mapped[Tutor] = relationship(foreign_keys=[referred_id])
