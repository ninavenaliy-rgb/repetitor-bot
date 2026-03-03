"""FSM states for placement test flow."""

from aiogram.fsm.state import State, StatesGroup


class PlacementStates(StatesGroup):
    """Placement test states."""

    answering = State()
