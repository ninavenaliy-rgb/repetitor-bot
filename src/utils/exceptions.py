"""Custom exception hierarchy."""


class RepetitorBotError(Exception):
    """Base exception for all application errors."""

    pass


class SlotConflictError(RepetitorBotError):
    """Raised when attempting to book an already-taken slot."""

    pass


class RateLimitExceededError(RepetitorBotError):
    """Raised when user exceeds AI usage rate limit."""

    pass


class CalendarAPIError(RepetitorBotError):
    """Raised when Google Calendar API fails."""

    pass


class PlacementTestError(RepetitorBotError):
    """Raised on placement test flow errors."""

    pass


class PaymentError(RepetitorBotError):
    """Raised on payment processing errors."""

    pass
