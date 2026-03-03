"""AI Administrator Handler — natural language commands from tutors.

ADDENDUM v1.1 + v1.2 implementation:
- §17 Context Memory (load/save ai_sessions)
- §18 Multi-Intent / Compound Actions
- §19 Recurring Lesson Support
- §21 Voice Message Support (registered handler with normalization)
- §22 Intelligent Confirmation System
- §25 Escalation Handling (confidence < 0.7)
- §26 Conflict Resolution v2 (3 nearest free slots)
- §32 Slash Commands (/create, /reschedule, /cancel, /paid, /schedule, /summary)
- §34 Voice Processing Pipeline with text normalization
- §35 Context Continuation (last_student_referenced)
- §36 lesson_summary intent
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger

from src.database.engine import get_session
from src.database.models import Tutor
from src.services.ai_admin_service import AIAdminService, AIAdminResult

router = Router(name="ai_admin")
_ai_admin = AIAdminService()

# Trigger phrase that activates AI mode for the tutor
_AI_TRIGGER = "ИИ"


class AIAdminStates(StatesGroup):
    waiting_confirmation = State()   # §22: waiting for user to confirm action
    waiting_clarification = State()  # §25: waiting for user to answer clarification question


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _confirm_keyboard() -> InlineKeyboardMarkup:
    """§22: Yes/No confirmation keyboard. Payload is stored in FSM state."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, всё верно", callback_data="ai_confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="ai_cancel"),
            ]
        ]
    )


def _free_slots_keyboard(slots: list[str], intent: str, student_id: str) -> InlineKeyboardMarkup:
    """§26: Show 3 nearest free slots when requested slot is busy."""
    buttons = []
    for slot in slots[:3]:
        payload = json.dumps({"intent": intent, "datetime": slot, "student_id": student_id})
        buttons.append([
            InlineKeyboardButton(text=_fmt_slot(slot), callback_data=f"ai_slot:{payload[:64]}")
        ])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="ai_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _fmt_slot(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")) + timedelta(hours=3)
        days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        return f"{dt.strftime('%d.%m')} ({days[dt.weekday()]}) {dt.strftime('%H:%M')}"
    except Exception:
        return iso


# ── Main text handler ─────────────────────────────────────────────────────────

@router.message(
    F.text.regexp(r"(?i)^ии\b"),
)
async def on_ai_command(
    message: Message,
    state: FSMContext,
    db_tutor: Optional[Tutor] = None,
) -> None:
    """§17: Load context, interpret command, handle result.

    Activated when tutor starts message with 'ИИ' (case-insensitive).
    Example: 'ИИ перенеси Игоря на завтра в 18'
    """
    if not db_tutor:
        return  # only tutors use AI admin

    # Strip "ии" prefix (case-insensitive)
    raw_text = message.text.strip()
    command_text = raw_text[2:].strip()  # len("ии") == 2
    if not command_text:
        await message.answer(
            "Напишите команду после «ИИ». Например:\n"
            "<i>ИИ перенеси Игоря на завтра в 18:00</i>"
        )
        return

    # §17: Load session context
    session_context = await _load_context(db_tutor.id)

    # Load student list and existing lessons for V2 time resolution
    students = await _load_students(db_tutor.id)
    existing_lessons = await _load_existing_lessons(db_tutor.id)

    thinking = await message.answer("Обрабатываю...")

    result = await _ai_admin.interpret(
        text=command_text,
        tutor_id=db_tutor.id,
        students=students,
        session_context=session_context,
        existing_lessons=existing_lessons,
        mode="text",
    )

    await thinking.delete()

    # §25: Escalation — ask clarifying question
    if result.needs_escalation:
        question = result.clarification_question or "Не удалось понять команду. Уточните, пожалуйста."
        await message.answer(f"❓ {question}")
        # Set FSM state so the user's next message is handled as clarification
        await state.set_state(AIAdminStates.waiting_clarification)
        await state.update_data(original_command=command_text)
        # Save partial context for follow-up
        await _save_context(db_tutor.id, session_context, command_text, question)
        return

    # §22: Build confirmation message
    confirm_text = _ai_admin.build_confirmation_text(result)
    action_payload = _serialize_result(result)

    # Store payload in FSM state (callback_data has 64-byte Telegram limit)
    await state.set_state(AIAdminStates.waiting_confirmation)
    await state.update_data(pending_payload=action_payload)

    await message.answer(
        confirm_text,
        reply_markup=_confirm_keyboard(),
    )

    # Save pending action to context (§17/§35)
    await _save_context(
        db_tutor.id,
        session_context,
        user_msg=command_text,
        assistant_msg=confirm_text,
        pending_action=result.intent,
        pending_payload=action_payload,
        last_student=result.entities.get("student_name"),
    )


# ── §21/§34 Voice Message Support ────────────────────────────────────────────

_FILLER_WORDS = re.compile(
    r"\b(эээ+|ммм+|ааа+|ну+|короче|вот|типа|значит|собственно|в общем)\b",
    flags=re.IGNORECASE,
)
_TIME_WORDS = {
    "один": "13:00", "одного": "13:00",
    "два": "14:00", "двух": "14:00",
    "три": "15:00", "трёх": "15:00", "трех": "15:00",
    "четыре": "16:00", "четырёх": "16:00", "четырех": "16:00",
    "пять": "17:00", "пяти": "17:00",
    "шесть": "18:00", "шести": "18:00",
    "семь": "19:00", "семи": "19:00",
    "восемь": "20:00", "восьми": "20:00",
    "девять": "21:00", "девяти": "21:00",
    "десять": "10:00", "десяти": "10:00",
    "одиннадцать": "11:00", "одиннадцати": "11:00",
    "двенадцать": "12:00", "двенадцати": "12:00",
}


def _normalize_voice_text(text: str) -> str:
    """§34.3: Remove filler words, normalize time expressions."""
    # Remove filler words
    text = _FILLER_WORDS.sub("", text)
    # Normalize "в шесть" → "в 18:00"
    def _replace_time(m: re.Match) -> str:
        word = m.group(2).lower()
        return f"{m.group(1)}{_TIME_WORDS.get(word, m.group(2))}"
    text = re.sub(r"(в\s+)(\w+)", _replace_time, text, flags=re.IGNORECASE)
    # Collapse multiple spaces
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


@router.message(StateFilter(None), F.voice)
async def on_tutor_voice_command(
    message: Message,
    state: FSMContext,
    db_tutor: Optional[Tutor] = None,
) -> None:
    """§34: Registered voice handler — only processes tutor voice messages."""
    if not db_tutor:
        return  # Students: voice goes to homework handler (different router priority)

    # §38/39: Duration limit ≤ 60 seconds
    if message.voice.duration > 60:
        await message.answer("Голосовое сообщение не должно превышать 60 секунд. Запишите покороче или напишите текстом.")
        return

    await handle_tutor_voice(message, db_tutor, state)


async def handle_tutor_voice(message: Message, db_tutor: Tutor, state: FSMContext) -> None:
    """§21: Process voice command from tutor. Call from tutor_panel.py if needed."""
    thinking = await message.answer("Распознаю голосовое сообщение...")

    try:
        from src.services.ai_service import AIService
        ai_service = AIService()

        voice = message.voice
        file = await message.bot.get_file(voice.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        audio_data = file_bytes.read()

        transcript = await ai_service.transcribe_voice(audio_data, filename="voice.ogg")
        if not transcript:
            await thinking.edit_text("Не удалось распознать. Попробуйте текстом: <i>ИИ [команда]</i>")
            return

        # §34.3: Normalize transcript before sending to AI
        normalized = _normalize_voice_text(transcript)
        await thinking.edit_text(f"Понял: <i>{normalized}</i>\n\nОбрабатываю...")

        session_context = await _load_context(db_tutor.id)
        students = await _load_students(db_tutor.id)
        existing_lessons = await _load_existing_lessons(db_tutor.id)
        result = await _ai_admin.interpret(
            text=normalized,
            tutor_id=db_tutor.id,
            students=students,
            session_context=session_context,
            existing_lessons=existing_lessons,
            mode="voice",
        )
        await thinking.delete()

        if result.needs_escalation:
            question = result.clarification_question or "Уточните команду."
            await message.answer(f"Голосовое: <i>{normalized}</i>\n\n❓ {question}")
            await state.set_state(AIAdminStates.waiting_clarification)
            await state.update_data(original_command=normalized)
            await _save_context(db_tutor.id, session_context, normalized, question)
            return

        confirm_text = _ai_admin.build_confirmation_text(result)
        action_payload = _serialize_result(result)

        await state.set_state(AIAdminStates.waiting_confirmation)
        await state.update_data(pending_payload=action_payload)

        await message.answer(
            f"Голосовое: <i>{normalized}</i>\n\n{confirm_text}",
            reply_markup=_confirm_keyboard(),
        )
        await _save_context(
            db_tutor.id, session_context,
            user_msg=normalized, assistant_msg=confirm_text,
            pending_action=result.intent, pending_payload=action_payload,
            last_student=result.entities.get("student_name"),
        )
    except Exception as e:
        logger.error(f"Voice command processing error: {e}")
        await thinking.edit_text("Ошибка. Попробуйте текстом: <i>ИИ [команда]</i>")


# ── Confirmation handlers ─────────────────────────────────────────────────────

@router.callback_query(F.data == "ai_confirm")
async def on_ai_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    db_tutor: Optional[Tutor] = None,
) -> None:
    """§22: Execute confirmed action. Payload is read from FSM state."""
    if not db_tutor:
        await callback.answer()
        return

    fsm_data = await state.get_data()
    action_data = fsm_data.get("pending_payload", "")

    try:
        result_dict = json.loads(action_data)
        result = AIAdminResult(result_dict)
    except Exception:
        await callback.answer("Ошибка данных. Повторите команду.")
        return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    # §17: Clear FSM state and DB context
    await state.clear()
    await _clear_context(db_tutor.id)

    # Dispatch to intent executor
    response_text = await _execute_intent(result, db_tutor, callback.bot)

    await callback.message.answer(response_text)


@router.callback_query(F.data == "ai_cancel")
async def on_ai_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    db_tutor: Optional[Tutor] = None,
) -> None:
    """Cancel pending AI action."""
    await callback.answer("Отменено")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Действие отменено.")
    await state.clear()
    if db_tutor:
        await _clear_context(db_tutor.id)


# ── Clarification reply handler (§25) ─────────────────────────────────────────

@router.message(StateFilter(AIAdminStates.waiting_clarification), F.text)
async def on_clarification_reply(
    message: Message,
    state: FSMContext,
    db_tutor: Optional[Tutor] = None,
) -> None:
    """Handle user's reply to a clarification question.

    Combines the original command with the clarification and re-interprets.
    Example: bot asked "Какое время?", user answers "в 18:00" →
    we send "перенеси S в 18:00" back to AI.
    """
    if not db_tutor:
        await state.clear()
        return

    fsm_data = await state.get_data()
    original_command = fsm_data.get("original_command", "")
    clarification = message.text.strip()

    # Merge original command with clarification answer
    combined_text = f"{original_command} {clarification}" if original_command else clarification

    await state.clear()

    session_context = await _load_context(db_tutor.id)
    students = await _load_students(db_tutor.id)
    existing_lessons = await _load_existing_lessons(db_tutor.id)

    thinking = await message.answer("Обрабатываю...")

    result = await _ai_admin.interpret(
        text=combined_text,
        tutor_id=db_tutor.id,
        students=students,
        session_context=session_context,
        existing_lessons=existing_lessons,
        mode="text",
    )

    await thinking.delete()

    if result.needs_escalation:
        question = result.clarification_question or "Не удалось понять. Попробуйте написать полную команду: ИИ [действие]"
        await message.answer(f"❓ {question}")
        await state.set_state(AIAdminStates.waiting_clarification)
        await state.update_data(original_command=combined_text)
        return

    confirm_text = _ai_admin.build_confirmation_text(result)
    action_payload = _serialize_result(result)

    await state.set_state(AIAdminStates.waiting_confirmation)
    await state.update_data(pending_payload=action_payload)

    await message.answer(confirm_text, reply_markup=_confirm_keyboard())
    await _save_context(
        db_tutor.id, session_context,
        user_msg=combined_text, assistant_msg=confirm_text,
        pending_action=result.intent, pending_payload=action_payload,
        last_student=result.entities.get("student_name"),
    )


# ── §32 Slash Commands ────────────────────────────────────────────────────────

async def _slash_clarify(
    message: Message,
    state: FSMContext,
    db_tutor: Optional[Tutor],
    prompt: str,
    original_command: str,
    tutor_only: bool = False,
) -> None:
    """Helper: tutor gets clarification flow, students get a redirect message."""
    if db_tutor:
        await message.answer(prompt)
        await state.set_state(AIAdminStates.waiting_clarification)
        await state.update_data(original_command=original_command)
    elif not tutor_only:
        await message.answer("Воспользуйтесь меню или обратитесь к репетитору.")
    else:
        await message.answer("Эта команда доступна только репетиторам.")


@router.message(Command("create"))
async def cmd_create(message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None) -> None:
    """§32: /create — schedule a new lesson."""
    await _slash_clarify(
        message, state, db_tutor,
        prompt="📅 Укажите ученика и время урока:\n<i>Например: Маша завтра в 18:00</i>",
        original_command="запиши",
    )


@router.message(Command("reschedule"))
async def cmd_reschedule(message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None) -> None:
    """§32: /reschedule — move a lesson to another time."""
    await _slash_clarify(
        message, state, db_tutor,
        prompt="🔄 Кого перенести и на когда?\n<i>Например: Маша с пятницы на субботу в 15:00</i>",
        original_command="перенеси урок",
        tutor_only=True,
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None) -> None:
    """§32: /cancel — cancel a lesson."""
    await _slash_clarify(
        message, state, db_tutor,
        prompt="❌ Чей урок отменить и когда?\n<i>Например: Маша в пятницу</i>",
        original_command="отмени урок",
        tutor_only=True,
    )


@router.message(Command("paid"))
async def cmd_paid(message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None) -> None:
    """§32: /paid — mark payment received."""
    await _slash_clarify(
        message, state, db_tutor,
        prompt="💰 Кто заплатил и сколько?\n<i>Например: Маша 1500 рублей наличными</i>",
        original_command="отметь оплату",
        tutor_only=True,
    )


@router.message(Command("schedule"))
async def cmd_schedule(
    message: Message,
    db_tutor: Optional[Tutor] = None,
    db_user=None,
) -> None:
    """§32: /schedule — show upcoming schedule. Tutors see all lessons, students see their own."""
    if db_tutor:
        text = await _exec_show_schedule({}, db_tutor)
        await message.answer(text)
    else:
        # Students: show their own upcoming bookings
        if not db_user:
            await message.answer("Нет данных о пользователе.")
            return
        from src.database.repositories.booking_repo import BookingRepository
        async with get_session() as session:
            repo = BookingRepository(session)
            now = datetime.now(timezone.utc)
            bookings = await repo.get_upcoming_by_tutor(
                tutor_id=db_user.tutor_id,
                from_dt=now,
                to_dt=now + timedelta(days=14),
            ) if hasattr(db_user, "tutor_id") and db_user.tutor_id else []
        if not bookings:
            await message.answer("Ближайших уроков нет.")
            return
        lines = ["<b>Ваши ближайшие уроки:</b>"]
        for b in bookings[:5]:
            lines.append(f"  • {_fmt_slot(b.scheduled_at.isoformat())} ({b.duration_min} мин)")
        await message.answer("\n".join(lines))


@router.message(Command("summary"))
async def cmd_summary(message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None) -> None:
    """§32/§36: /summary — record lesson summary (tutors only)."""
    await _slash_clarify(
        message, state, db_tutor,
        prompt=(
            "📝 Напишите итог урока:\n"
            "<i>Например: Маша — прошли passive voice, путает was done и did</i>\n\n"
            "Или надиктуйте голосовым сообщением."
        ),
        original_command="итог урока",
        tutor_only=True,
    )


# ── Intent Executor ───────────────────────────────────────────────────────────

async def _execute_intent(result: AIAdminResult, db_tutor: Tutor, bot) -> str:
    """Execute the confirmed intent and return result message."""

    if result.intent == "compound_action":
        # §18: Execute actions sequentially
        responses = []
        for action in result.actions:
            sub = AIAdminResult({**action, "confidence": 1.0, "needs_confirmation": False})
            resp = await _execute_single(sub, db_tutor, bot)
            responses.append(resp)
        return "\n".join(responses)

    return await _execute_single(result, db_tutor, bot)


async def _execute_single(result: AIAdminResult, db_tutor: Tutor, bot) -> str:
    """Execute a single intent."""
    e = result.entities
    intent = result.intent

    try:
        if intent == "book_lesson":
            return await _exec_book_lesson(e, db_tutor, bot)

        if intent == "reschedule_lesson":
            return await _exec_reschedule(e, db_tutor)

        if intent == "cancel_lesson":
            return await _exec_cancel_lesson(e, db_tutor, bot)

        if intent == "mark_paid":
            return await _exec_mark_paid(e, db_tutor)

        if intent == "set_recurring_schedule":
            return await _exec_recurring(e, db_tutor, bot)  # §19

        if intent == "show_schedule":
            return await _exec_show_schedule(e, db_tutor)

        if intent == "show_student":
            return await _exec_show_student(e, db_tutor)

        if intent == "add_homework":
            return await _exec_add_homework(e, db_tutor, bot)

        if intent == "lesson_summary":
            return await _exec_lesson_summary(e, db_tutor)

        if intent == "update_student_profile":
            return await _exec_update_student_profile(e, db_tutor)

        # V2 intent name aliases (map to V1 executors)
        if intent == "create_lesson":
            return await _exec_book_lesson(e, db_tutor, bot)

        if intent == "create_recurring":
            return await _exec_recurring(e, db_tutor, bot)

        return f"Действие «{intent}» пока не реализовано."

    except Exception as exc:
        logger.error(f"Intent execution error ({intent}): {exc}")
        return f"Произошла ошибка при выполнении. Попробуйте ещё раз."


async def _exec_book_lesson(e: dict, db_tutor: Tutor, bot) -> str:
    student_name = e.get("student_name")
    dt_str = e.get("datetime")
    duration = e.get("duration_min") or db_tutor.default_duration_min or 60

    if not student_name or not dt_str:
        return "Не хватает данных: укажите имя ученика и время урока."

    student = await _find_student(student_name, db_tutor.id)
    if not student:
        return f"Ученик «{student_name}» не найден."

    dt = _parse_dt(dt_str)
    if not dt:
        return "Не удалось распознать дату/время."

    from src.services.booking_service import BookingService
    from src.utils.exceptions import SlotConflictError
    booking_service = BookingService()

    try:
        booking = await booking_service.create_booking(
            tutor_id=db_tutor.id,
            user_id=student["id"],
            calendar_id="primary",
            scheduled_at=dt,
            duration_min=int(duration),
        )
        # Notify student
        if student.get("telegram_id") and bot:
            try:
                from datetime import timedelta
                moscow_dt = dt + timedelta(hours=3)
                await bot.send_message(
                    chat_id=student["telegram_id"],
                    text=f"Урок запланирован на <b>{moscow_dt.strftime('%d.%m %H:%M')}</b> (МСК)",
                )
            except Exception:
                pass
        from src.services.ai_admin_service import _fmt_dt
        return f"Урок с <b>{student_name}</b> записан на <b>{_fmt_dt(dt_str)}</b>."

    except SlotConflictError:
        # §26: Generate 3 nearest free slots
        free_slots = await _find_free_slots(db_tutor.id, dt, int(duration))
        if free_slots:
            slots_text = "\n".join(f"  • {_fmt_slot(s)}" for s in free_slots)
            return (
                f"Время {_fmt_slot(dt_str)} занято.\n\n"
                f"Ближайшие свободные слоты:\n{slots_text}\n\n"
                "Напишите: ИИ запиши {ученик} на {время}"
            )
        return f"Время {_fmt_slot(dt_str)} занято. Свободных слотов рядом нет."


async def _exec_reschedule(e: dict, db_tutor: Tutor) -> str:
    student_name = e.get("student_name")
    new_dt_str = e.get("new_datetime")

    if not student_name or not new_dt_str:
        return "Не хватает данных для переноса."

    student = await _find_student(student_name, db_tutor.id)
    if not student:
        return f"Ученик «{student_name}» не найден."

    new_dt = _parse_dt(new_dt_str)
    if not new_dt:
        return "Не удалось распознать новую дату."

    # Find nearest upcoming lesson for this student
    from src.database.repositories.booking_repo import BookingRepository
    async with get_session() as session:
        repo = BookingRepository(session)
        now = datetime.now(timezone.utc)
        bookings = await repo.get_upcoming_by_tutor(
            tutor_id=db_tutor.id,
            from_dt=now,
            to_dt=now + timedelta(days=90),
        )
        student_bookings = [b for b in bookings if str(b.user_id) == str(student["id"])]
        if not student_bookings:
            return f"У ученика «{student_name}» нет запланированных уроков."

        booking = student_bookings[0]
        booking.scheduled_at = new_dt
        await session.commit()

    from src.services.ai_admin_service import _fmt_dt
    return f"Урок с <b>{student_name}</b> перенесён на <b>{_fmt_dt(new_dt_str)}</b>."


async def _exec_cancel_lesson(e: dict, db_tutor: Tutor, bot) -> str:
    student_name = e.get("student_name")
    if not student_name:
        return "Укажите имя ученика."

    student = await _find_student(student_name, db_tutor.id)
    if not student:
        return f"Ученик «{student_name}» не найден."

    from src.database.repositories.booking_repo import BookingRepository
    async with get_session() as session:
        repo = BookingRepository(session)
        now = datetime.now(timezone.utc)
        bookings = await repo.get_upcoming_by_tutor(
            tutor_id=db_tutor.id,
            from_dt=now,
            to_dt=now + timedelta(days=90),
        )
        student_bookings = [b for b in bookings if str(b.user_id) == str(student["id"])]
        if not student_bookings:
            return f"У ученика «{student_name}» нет запланированных уроков."

        booking = student_bookings[0]
        booking.status = "cancelled"
        await session.commit()

    if student.get("telegram_id") and bot:
        try:
            from src.services.ai_admin_service import _fmt_dt
            await bot.send_message(
                chat_id=student["telegram_id"],
                text=f"Урок отменён репетитором.",
            )
        except Exception:
            pass

    return f"Урок с <b>{student_name}</b> отменён."


async def _exec_mark_paid(e: dict, db_tutor: Tutor) -> str:
    student_name = e.get("student_name")
    amount = e.get("amount")
    method = e.get("payment_method", "наличные")

    if not student_name:
        return "Укажите имя ученика."

    student = await _find_student(student_name, db_tutor.id)
    if not student:
        return f"Ученик «{student_name}» не найден."

    from src.database.repositories.booking_repo import BookingRepository
    async with get_session() as session:
        repo = BookingRepository(session)
        now = datetime.now(timezone.utc)
        # Find latest lesson for this student
        bookings = await repo.get_upcoming_by_tutor(
            tutor_id=db_tutor.id,
            from_dt=now - timedelta(days=30),
            to_dt=now + timedelta(days=90),
        )
        student_id_str = str(student["id"])
        recent = [b for b in bookings if str(b.user_id) == student_id_str]
        if not recent:
            return f"Нет уроков для отметки оплаты у «{student_name}»."

        latest = sorted(recent, key=lambda b: b.scheduled_at, reverse=True)[0]
        latest.status = "paid"
        await session.commit()

    amount_text = f" {int(amount)}₽" if amount else ""
    method_text = f" ({method})" if method else ""
    return f"Оплата{amount_text}{method_text} от <b>{student_name}</b> отмечена."


async def _exec_recurring(e: dict, db_tutor: Tutor, bot) -> str:
    """§19: Create recurring weekly schedule."""
    student_name = e.get("student_name")
    weekday = e.get("weekday")
    time_str = e.get("time")
    duration = e.get("duration_min") or db_tutor.default_duration_min or 60
    start_date_str = e.get("start_date")
    end_date_str = e.get("end_date")

    if not all([student_name, weekday, time_str, start_date_str]):
        return "Не хватает данных: укажите ученика, день недели, время и дату начала."

    student = await _find_student(student_name, db_tutor.id)
    if not student:
        return f"Ученик «{student_name}» не найден."

    # Map Russian weekday names to integers
    weekday_map = {
        "Пн": 0, "Вт": 1, "Ср": 2, "Чт": 3, "Пт": 4, "Сб": 5, "Вс": 6,
        "Понедельник": 0, "Вторник": 1, "Среда": 2, "Четверг": 3,
        "Пятница": 4, "Суббота": 5, "Воскресенье": 6,
        "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6,
    }
    target_weekday = weekday_map.get(weekday)
    if target_weekday is None:
        return f"Не распознан день недели: «{weekday}»."

    try:
        start_dt = _parse_dt(start_date_str)
        end_dt = _parse_dt(end_date_str) if end_date_str else start_dt + timedelta(weeks=12)
        h, m = map(int, time_str.split(":"))
    except Exception:
        return "Ошибка в формате даты или времени."

    from src.services.booking_service import BookingService
    from src.utils.exceptions import SlotConflictError
    booking_service = BookingService()

    # Generate all lesson dates
    lessons_created = 0
    conflicts = 0
    current = start_dt
    # Advance to first occurrence of target weekday
    while current.weekday() != target_weekday:
        current += timedelta(days=1)

    while current <= end_dt:
        lesson_dt = current.replace(hour=h, minute=m, second=0, microsecond=0)
        try:
            await booking_service.create_booking(
                tutor_id=db_tutor.id,
                user_id=student["id"],
                calendar_id="primary",
                scheduled_at=lesson_dt,
                duration_min=int(duration),
            )
            lessons_created += 1
        except SlotConflictError:
            conflicts += 1
        current += timedelta(weeks=1)

    result_text = f"Создано <b>{lessons_created}</b> уроков для <b>{student_name}</b>"
    result_text += f" (каждый {weekday} в {time_str})"
    if conflicts:
        result_text += f"\n⚠️ Пропущено конфликтов: {conflicts}"
    return result_text


async def _exec_show_schedule(e: dict, db_tutor: Tutor) -> str:
    from src.database.repositories.booking_repo import BookingRepository
    async with get_session() as session:
        repo = BookingRepository(session)
        now = datetime.now(timezone.utc)
        bookings = await repo.get_upcoming_by_tutor(
            tutor_id=db_tutor.id,
            from_dt=now,
            to_dt=now + timedelta(days=7),
        )

    if not bookings:
        return "На ближайшую неделю уроков нет."

    lines = ["<b>Ближайшие уроки:</b>"]
    from src.database.repositories.user_repo import UserRepository
    async with get_session() as session:
        user_repo = UserRepository(session)
        for b in bookings[:10]:
            user = await user_repo.get_by_id(b.user_id)
            name = user.name if user else "?"
            lines.append(f"  {_fmt_slot(b.scheduled_at.isoformat())} — {name} ({b.duration_min} мин)")

    return "\n".join(lines)


async def _exec_show_student(e: dict, db_tutor: Tutor) -> str:
    student_name = e.get("student_name")
    if not student_name:
        return "Укажите имя ученика."

    student = await _find_student(student_name, db_tutor.id)
    if not student:
        return f"Ученик «{student_name}» не найден."

    return (
        f"<b>{student['name']}</b>\n"
        f"Уровень: {student.get('level') or '—'}\n"
        f"Цель: {student.get('goal') or '—'}"
    )


async def _exec_add_homework(e: dict, db_tutor: Tutor, bot) -> str:
    student_name = e.get("student_name")
    hw_text = e.get("text", "")

    if not student_name or not hw_text:
        return "Укажите имя ученика и текст домашнего задания."

    student = await _find_student(student_name, db_tutor.id)
    if not student:
        return f"Ученик «{student_name}» не найден."

    if student.get("telegram_id") and bot:
        try:
            await bot.send_message(
                chat_id=student["telegram_id"],
                text=f"Домашнее задание от репетитора:\n\n{hw_text}",
            )
        except Exception:
            pass

    return f"Домашнее задание отправлено <b>{student_name}</b>."


async def _exec_lesson_summary(e: dict, db_tutor: Tutor) -> str:
    """§36: Save lesson summary to last booking for this student."""
    student_name = e.get("student_name")
    topics = e.get("topics_covered") or []
    weak_areas = e.get("weak_areas") or []
    notes = e.get("notes", "")

    if not student_name:
        return "Укажите имя ученика."

    student = await _find_student(student_name, db_tutor.id)
    if not student:
        return f"Ученик «{student_name}» не найден."

    from src.database.repositories.booking_repo import BookingRepository
    async with get_session() as session:
        repo = BookingRepository(session)
        now = datetime.now(timezone.utc)
        bookings = await repo.get_upcoming_by_tutor(
            tutor_id=db_tutor.id,
            from_dt=now - timedelta(days=30),
            to_dt=now + timedelta(hours=2),
        )
        student_bookings = [b for b in bookings if str(b.user_id) == str(student["id"])]
        if not student_bookings:
            return f"Нет уроков для сохранения итога у «{student_name}» за последние 30 дней."

        # Find the most recent booking
        latest = sorted(student_bookings, key=lambda b: b.scheduled_at, reverse=True)[0]

        # Build summary text
        summary_parts = []
        if topics:
            summary_parts.append(f"Темы: {', '.join(topics)}")
        if weak_areas:
            summary_parts.append(f"Трудности: {', '.join(weak_areas)}")
        if notes:
            summary_parts.append(f"Заметки: {notes}")

        latest.lesson_summary = "\n".join(summary_parts)
        if weak_areas:
            latest.notes = f"Ошибки/трудности: {', '.join(weak_areas)}"
        await session.commit()

    topics_text = ", ".join(topics) if topics else "не указаны"
    weak_text = ", ".join(weak_areas) if weak_areas else "нет"
    return (
        f"✅ Итог урока с <b>{student_name}</b> сохранён.\n"
        f"Темы: {topics_text}\n"
        f"Трудности: {weak_text}"
    )


async def _exec_update_student_profile(e: dict, db_tutor: Tutor) -> str:
    """Update student profile fields: level, goal, weak areas, grammar/vocabulary gaps."""
    student_name = e.get("student_name")
    if not student_name:
        return "Укажите имя ученика."

    student = await _find_student(student_name, db_tutor.id)
    if not student:
        return f"Ученик «{student_name}» не найден."

    updated_fields: list[str] = []
    from src.database.repositories.user_repo import UserRepository
    async with get_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(uuid.UUID(student["id"]))
        if not user:
            return f"Ученик «{student_name}» не найден в базе."

        if e.get("level"):
            user.cefr_level = str(e["level"])[:5]
            updated_fields.append(f"уровень: {e['level']}")

        if e.get("goal"):
            user.goal = str(e["goal"])[:50]
            updated_fields.append(f"цель: {e['goal']}")

        # Build notes from weak areas / gaps
        notes_parts: list[str] = []
        for key, label in [
            ("weak_areas", "Слабые места"),
            ("grammar_gaps", "Грамматика"),
            ("vocabulary_gaps", "Лексика"),
        ]:
            val = e.get(key)
            if val:
                items = val if isinstance(val, list) else [val]
                notes_parts.append(f"{label}: {', '.join(str(i) for i in items)}")
        if e.get("notes"):
            notes_parts.append(str(e["notes"]))

        if notes_parts:
            new_notes = "\n".join(notes_parts)
            user.notes = (user.notes + "\n\n" + new_notes) if user.notes else new_notes
            updated_fields.append("заметки обновлены")

        await session.commit()

    if not updated_fields:
        return f"Нечего обновлять для «{student_name}». Укажите уровень, цель или заметки."

    return (
        f"✅ Профиль <b>{student_name}</b> обновлён:\n"
        + "\n".join(f"  • {f}" for f in updated_fields)
    )


# ── Context Helpers (§17) ─────────────────────────────────────────────────────

async def _load_context(tutor_id: uuid.UUID) -> Optional[dict]:
    try:
        async with get_session() as session:
            from src.database.repositories.ai_session_repo import AISessionRepository
            repo = AISessionRepository(session)
            ai_session = await repo.get_active(tutor_id)
            return ai_session.context_state if ai_session else None
    except Exception as e:
        logger.warning(f"Failed to load AI context: {e}")
        return None


async def _save_context(
    tutor_id: uuid.UUID,
    existing_context: Optional[dict],
    user_msg: str,
    assistant_msg: str,
    pending_action: Optional[str] = None,
    pending_payload: Optional[str] = None,
    last_student: Optional[str] = None,
) -> None:
    """§17/§35: Persist updated context to ai_sessions."""
    try:
        history = (existing_context or {}).get("history", [])
        # Keep last _MAX_HISTORY pairs (§24)
        history = history[-(6):]  # 3 pairs = 6 entries max
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})

        new_context: dict = {
            "history": history,
        }
        if pending_action:
            new_context["pending_action"] = pending_action
        if pending_payload:
            new_context["pending_payload"] = pending_payload
        # §35: Persist last referenced student for contextual short replies
        prev_student = (existing_context or {}).get("last_student_referenced")
        new_context["last_student_referenced"] = last_student or prev_student

        async with get_session() as session:
            from src.database.repositories.ai_session_repo import AISessionRepository
            repo = AISessionRepository(session)
            await repo.upsert(tutor_id, new_context)
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to save AI context: {e}")


async def _clear_context(tutor_id: uuid.UUID) -> None:
    try:
        async with get_session() as session:
            from src.database.repositories.ai_session_repo import AISessionRepository
            repo = AISessionRepository(session)
            await repo.clear(tutor_id)
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to clear AI context: {e}")


# ── DB Helpers ────────────────────────────────────────────────────────────────

async def _load_students(tutor_id: uuid.UUID) -> list[dict]:
    """Load student list for entity resolution (§24: only relevant data)."""
    try:
        from src.database.repositories.user_repo import UserRepository
        async with get_session() as session:
            repo = UserRepository(session)
            users = await repo.get_active_by_tutor(tutor_id)
            return [
                {
                    "id": str(u.id),
                    "name": u.name,
                    "telegram_id": u.telegram_id,
                    "level": u.cefr_level,
                    "goal": u.goal,
                }
                for u in users
            ]
    except Exception as e:
        logger.warning(f"Failed to load students: {e}")
        return []


async def _load_existing_lessons(tutor_id: uuid.UUID) -> list[dict]:
    """Load upcoming + recent lessons for V2 time resolution context."""
    try:
        from src.database.repositories.booking_repo import BookingRepository
        from src.database.repositories.user_repo import UserRepository
        async with get_session() as session:
            repo = BookingRepository(session)
            user_repo = UserRepository(session)
            now = datetime.now(timezone.utc)
            bookings = await repo.get_upcoming_by_tutor(
                tutor_id=tutor_id,
                from_dt=now - timedelta(days=7),
                to_dt=now + timedelta(days=14),
            )
            result = []
            for b in bookings[:20]:  # keep context concise
                user = await user_repo.get_by_id(b.user_id)
                result.append({
                    "student": user.name if user else "?",
                    "datetime": b.scheduled_at.isoformat(),
                    "duration_min": b.duration_min,
                    "status": b.status,
                })
            return result
    except Exception as exc:
        logger.warning(f"Failed to load existing lessons: {exc}")
        return []


async def _find_student(name: str, tutor_id: uuid.UUID) -> Optional[dict]:
    """Find student by approximate name match."""
    students = await _load_students(tutor_id)
    name_lower = name.lower().strip()
    # Exact match first
    for s in students:
        if s["name"].lower() == name_lower:
            return s
    # Partial match (first name)
    for s in students:
        if name_lower in s["name"].lower() or s["name"].lower().split()[0] == name_lower:
            return s
    return None


async def _find_free_slots(
    tutor_id: uuid.UUID,
    around_dt: datetime,
    duration_min: int,
) -> list[str]:
    """§26: Return up to 3 nearest free slots around the requested time."""
    try:
        from src.database.repositories.booking_repo import BookingRepository
        async with get_session() as session:
            repo = BookingRepository(session)
            bookings = await repo.get_upcoming_by_tutor(
                tutor_id=tutor_id,
                from_dt=around_dt - timedelta(days=7),
                to_dt=around_dt + timedelta(days=7),
            )

        busy: set[datetime] = {b.scheduled_at for b in bookings}
        free_slots = []
        candidate = around_dt + timedelta(hours=1)

        while len(free_slots) < 3:
            if candidate not in busy:
                free_slots.append(candidate.isoformat())
            candidate += timedelta(hours=1)
            if candidate > around_dt + timedelta(days=3):
                break

        return free_slots
    except Exception:
        return []


def _parse_dt(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _serialize_result(result: AIAdminResult) -> str:
    """Serialize AIAdminResult for callback data (max 512 bytes)."""
    data = {
        "intent": result.intent,
        "confidence": result.confidence,
        "entities": result.entities,
        "actions": result.actions,
        "needs_confirmation": result.needs_confirmation,
    }
    return json.dumps(data, ensure_ascii=False)
