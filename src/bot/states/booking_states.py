"""FSM states for booking flow."""

from aiogram.fsm.state import State, StatesGroup


class BookingStates(StatesGroup):
    """Booking flow states."""

    selecting_day = State()
    selecting_slot = State()
    entering_manual_time = State()
    confirming = State()
