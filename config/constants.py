"""Application-wide constants and enums."""

from enum import Enum


class CEFRLevel(str, Enum):
    """Common European Framework of Reference levels."""

    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class GoalType(str, Enum):
    """Student learning goals."""

    GENERAL = "general"
    BUSINESS = "business"
    IELTS = "ielts"
    TOEFL = "toefl"
    OGE_EGE = "oge_ege"


class SubscriptionTier(str, Enum):
    """Monetization tiers."""

    START = "START"
    PRO = "PRO"


class BookingStatus(str, Enum):
    """Lesson booking status."""

    PLANNED = "planned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class ConfirmationStatus(str, Enum):
    """Booking confirmation status."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    RESCHEDULED = "rescheduled"


class PaymentStatus(str, Enum):
    """Payment status."""

    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"
    OVERDUE = "overdue"


class PaymentType(str, Enum):
    """Payment type."""

    LESSON = "lesson"
    SUBSCRIPTION = "subscription"
    PACKAGE = "package"


class FileType(str, Enum):
    """Material file type."""

    DOCUMENT = "document"
    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"


class EngagementEventType(str, Enum):
    """Types of daily engagement activities."""

    WORD_OF_DAY = "word_of_day"
    SPEAKING_PROMPT = "speaking"
    GRAMMAR_DRILL = "grammar_drill"


class AIUsageType(str, Enum):
    """Types of AI API calls for tracking."""

    HOMEWORK_CHECK = "homework_check"
    QUIZ_GENERATION = "quiz_generation"
    CONTENT_GENERATION = "content_generation"


# Placement test configuration
PLACEMENT_QUESTIONS_COUNT = 12
PLACEMENT_START_LEVEL = CEFRLevel.B1

# CEFR level weights for scoring
CEFR_WEIGHTS: dict[CEFRLevel, int] = {
    CEFRLevel.A1: 1,
    CEFRLevel.A2: 2,
    CEFRLevel.B1: 3,
    CEFRLevel.B2: 4,
    CEFRLevel.C1: 5,
    CEFRLevel.C2: 6,
}

# Reminder timing (minutes before lesson)
REMINDER_TIMINGS = [1440, 120]  # T-24h, T-2h

# Post-lesson follow-up (minutes after lesson end)
POST_LESSON_FOLLOWUP_MINUTES = 30

# Default lesson duration
DEFAULT_LESSON_DURATION_MIN = 60
