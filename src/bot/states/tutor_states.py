"""FSM states for tutor panel."""

from aiogram.fsm.state import State, StatesGroup


class TutorStates(StatesGroup):
    """States for tutor panel interactions."""

    adding_student = State()
    editing_note = State()
    editing_lesson_note = State()
    entering_payment = State()
    selecting_duration = State()
    # Package
    entering_package_price = State()
    entering_stars_price = State()
    # Student individual price
    entering_student_price = State()
    # Lesson summary + parent
    entering_lesson_summary = State()
    entering_parent_id = State()
    entering_parent_name = State()
    # Student goal
    editing_goal = State()
    # Student progress
    entering_progress = State()
    # Student rename
    renaming_student = State()
    # AI functions (premium only)
    creating_lesson_plan = State()
    checking_homework = State()


class TutorRegistrationStates(StatesGroup):
    """States for tutor self-registration flow."""

    entering_name = State()
    entering_subjects = State()
    entering_price = State()
