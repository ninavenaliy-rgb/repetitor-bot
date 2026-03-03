"""FSM states for user registration flow."""

from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Registration flow states."""

    waiting_language = State()
    waiting_goal = State()
    waiting_level = State()
