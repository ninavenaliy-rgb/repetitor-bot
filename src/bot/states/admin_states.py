"""FSM states для админ-панели."""

from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    """States для работы с админ-панелью."""

    # Редактирование данных
    editing_payment_amount = State()
    editing_student_price = State()
    editing_tutor_price = State()
    editing_booking_duration = State()

    # Добавление данных
    adding_student_name = State()
    adding_student_contact = State()

    # Редактирование расписания
    editing_booking_time = State()

    # Редактирование заметок
    editing_note = State()

    # Корректировка доходов
    entering_income_correction = State()
