"""Localization strings for student-facing interface.

Tutor panel stays in Russian. Student interface supports 4 languages.
Usage: t(lang, 'key') or t(lang, 'key', name='Иван', level='B2')
"""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        # Welcome
        "welcome_new": (
            "Привет! Рада видеть вас здесь.\n\n"
            "Я помогу учить английский удобно — без скучных учебников.\n\n"
            "За 5 минут определю ваш уровень, запишу к репетитору "
            "и буду присылать новое слово каждый день.\n\n"
            "Давайте начнём — <b>какая у вас цель?</b>"
        ),
        "welcome_back": (
            "С возвращением, {name}!\n\n"
            "Ваш уровень: <b>{level}</b>\n"
            "Цель: <b>{goal}</b>\n\n"
            "Выберите действие:"
        ),
        # Goals
        "goal_general": "Разговорный английский",
        "goal_business": "Бизнес-английский",
        "goal_ielts": "IELTS / TOEFL",
        "goal_oge_ege": "ОГЭ / ЕГЭ",
        "goal_not_set": "Не указана",
        "goal_chosen": (
            "Отлично! Цель: <b>{goal}</b>.\n\n"
            "Теперь давайте определим ваш уровень английского — это займёт всего 5 минут!"
        ),
        # Reply keyboard buttons
        "btn_book": "Записаться на урок",
        "btn_my_lessons": "Мои уроки",
        "btn_homework": "Проверить домашку",
        "btn_profile": "Мой профиль",
        "btn_word_of_day": "📚 Слово дня",
        # Inline keyboard buttons
        "btn_placement": "Пройти тест (5 мин)",
        "btn_know_level": "Я уже знаю свой уровень",
        "btn_retake_test": "Пройти тест уровня",
        # Lessons
        "no_tutor": (
            "У вас пока нет назначенного репетитора.\n"
            "Обратитесь к вашему преподавателю для подключения."
        ),
        "no_lessons": (
            "У вас нет запланированных уроков.\n\n"
            "Нажмите «{btn}», чтобы выбрать время."
        ),
        "upcoming_lessons": "<b>Ваши ближайшие уроки:</b>\n",
        # Profile
        "profile_body": (
            "<b>Ваш профиль</b>\n\n"
            "Имя: {name}\n"
            "Уровень: <b>{level}</b>\n"
            "Цель: {goal}\n\n"
            "Чтобы пройти тест уровня заново, нажмите кнопку ниже."
        ),
        # Homework
        "homework_prompt": (
            "<b>Проверка домашнего задания (AI)</b>\n\n"
            "Отправьте текст (эссе, письмо, предложения) "
            "и я проверю грамматику, лексику и оценю уровень.\n\n"
            "Просто напишите или вставьте текст:"
        ),
        "homework_too_short": "Отправьте более длинный текст — хотя бы несколько предложений.",
        "homework_too_long": "Текст слишком длинный. Максимум — 5000 символов.",
        "homework_thinking": "Анализирую ваш текст...",
        "homework_limit": (
            "Вы исчерпали дневной лимит проверок.\n"
            "Попробуйте завтра или попросите репетитора проверить!"
        ),
        "what_next": "Что дальше?",
        # Placement
        "skip_placement": "Хорошо! Тест можно пройти позже.\nВыберите действие:",
        # Language
        "choose_language": "Выберите язык интерфейса / Choose your language:",
        "language_set": "Язык изменён ✅",
        # Homework report sections
        "hw_title": "Анализ домашнего задания",
        "hw_strengths": "Что хорошо:",
        "hw_corrections": "Исправления:",
        "hw_vocab": "Словарный запас:",
        "hw_topics": "Темы для изучения:",
        "hw_level": "Уровень текста",
        # Invite
        "invite_success": (
            "✅ Вы успешно подключились к репетитору <b>{name}</b>!\n\n"
            "Теперь вам будут доступны расписание уроков и домашние задания."
        ),
        "invite_invalid": "Ссылка приглашения недействительна или устарела.",
        # Level
        "level_not_set": "Не определён",
    },

    "en": {
        "welcome_new": (
            "Hello! I'm your English learning assistant.\n\n"
            "I can help you:\n"
            "— Assess your level in 5 minutes\n"
            "— Book lessons with your tutor\n"
            "— Check homework with AI\n"
            "— Send a daily word for practice\n\n"
            "What is your learning goal?"
        ),
        "welcome_back": (
            "Welcome back, {name}!\n\n"
            "Your level: <b>{level}</b>\n"
            "Goal: <b>{goal}</b>\n\n"
            "Choose an action:"
        ),
        "goal_general": "Conversational English",
        "goal_business": "Business English",
        "goal_ielts": "IELTS / TOEFL",
        "goal_oge_ege": "OGE / EGE",
        "goal_not_set": "Not set",
        "goal_chosen": (
            "Great! Goal: <b>{goal}</b>.\n\n"
            "Now let's assess your English level — it only takes 5 minutes!"
        ),
        "btn_book": "Book a lesson",
        "btn_my_lessons": "My lessons",
        "btn_homework": "Check homework",
        "btn_profile": "My profile",
        "btn_word_of_day": "📚 Word of the Day",
        "btn_placement": "Level test (5 min)",
        "btn_know_level": "I already know my level",
        "btn_retake_test": "Retake level test",
        "no_tutor": (
            "You don't have an assigned tutor yet.\n"
            "Contact your teacher to connect."
        ),
        "no_lessons": (
            "You have no upcoming lessons.\n\n"
            "Tap «{btn}» to choose a time."
        ),
        "upcoming_lessons": "<b>Your upcoming lessons:</b>\n",
        "profile_body": (
            "<b>Your profile</b>\n\n"
            "Name: {name}\n"
            "Level: <b>{level}</b>\n"
            "Goal: {goal}\n\n"
            "Press the button below to retake the level test."
        ),
        "homework_prompt": (
            "<b>Homework Check (AI)</b>\n\n"
            "Send your text (essay, letter, sentences) "
            "and I'll check grammar, vocabulary and estimate your level.\n\n"
            "Just type or paste your text:"
        ),
        "homework_too_short": "Please send a longer text — at least a few sentences.",
        "homework_too_long": "Text is too long. Maximum is 5,000 characters.",
        "homework_thinking": "Analysing your text...",
        "homework_limit": (
            "You've reached your daily check limit.\n"
            "Try again tomorrow or ask your tutor!"
        ),
        "what_next": "What's next?",
        "skip_placement": "OK! You can take the test later.\nChoose an action:",
        "choose_language": "Выберите язык интерфейса / Choose your language:",
        "language_set": "Language changed ✅",
        "hw_title": "Homework Analysis",
        "hw_strengths": "What's good:",
        "hw_corrections": "Corrections:",
        "hw_vocab": "Vocabulary:",
        "hw_topics": "Topics to study:",
        "hw_level": "Text level",
        "invite_success": (
            "✅ You have successfully connected to tutor <b>{name}</b>!\n\n"
            "You now have access to your lesson schedule and homework."
        ),
        "invite_invalid": "The invitation link is invalid or has expired.",
        "level_not_set": "Not assessed",
    },

    "es": {
        "welcome_new": (
            "¡Hola! Soy tu asistente de aprendizaje de inglés.\n\n"
            "Puedo ayudarte a:\n"
            "— Evaluar tu nivel en 5 minutos\n"
            "— Reservar clases con tu tutor\n"
            "— Revisar tareas con IA\n"
            "— Enviarte una palabra diaria para practicar\n\n"
            "¿Cuál es tu objetivo de aprendizaje?"
        ),
        "welcome_back": (
            "¡Bienvenido de vuelta, {name}!\n\n"
            "Tu nivel: <b>{level}</b>\n"
            "Objetivo: <b>{goal}</b>\n\n"
            "Elige una acción:"
        ),
        "goal_general": "Inglés conversacional",
        "goal_business": "Inglés de negocios",
        "goal_ielts": "IELTS / TOEFL",
        "goal_oge_ege": "OGE / EGE",
        "goal_not_set": "No definido",
        "goal_chosen": (
            "¡Genial! Objetivo: <b>{goal}</b>.\n\n"
            "¡Ahora evaluemos tu nivel de inglés — solo toma 5 minutos!"
        ),
        "btn_book": "Reservar clase",
        "btn_my_lessons": "Mis clases",
        "btn_homework": "Revisar tarea",
        "btn_profile": "Mi perfil",
        "btn_word_of_day": "📚 Palabra del día",
        "btn_placement": "Test de nivel (5 min)",
        "btn_know_level": "Ya conozco mi nivel",
        "btn_retake_test": "Repetir test de nivel",
        "no_tutor": (
            "Todavía no tienes un tutor asignado.\n"
            "Contacta a tu profesor para conectarte."
        ),
        "no_lessons": (
            "No tienes clases programadas.\n\n"
            "Toca «{btn}» para elegir un horario."
        ),
        "upcoming_lessons": "<b>Tus próximas clases:</b>\n",
        "profile_body": (
            "<b>Tu perfil</b>\n\n"
            "Nombre: {name}\n"
            "Nivel: <b>{level}</b>\n"
            "Objetivo: {goal}\n\n"
            "Pulsa el botón de abajo para repetir el test de nivel."
        ),
        "homework_prompt": (
            "<b>Revisión de tareas (IA)</b>\n\n"
            "Envía tu texto (ensayo, carta, oraciones) "
            "y revisaré gramática, vocabulario y estimaré tu nivel.\n\n"
            "Simplemente escribe o pega tu texto:"
        ),
        "homework_too_short": "Envía un texto más largo — al menos unas pocas oraciones.",
        "homework_too_long": "El texto es demasiado largo. Máximo 5.000 caracteres.",
        "homework_thinking": "Analizando tu texto...",
        "homework_limit": (
            "Has alcanzado tu límite diario de revisiones.\n"
            "¡Inténtalo mañana o pregunta a tu tutor!"
        ),
        "what_next": "¿Qué sigue?",
        "skip_placement": "¡De acuerdo! Puedes hacer el test más tarde.\nElige una acción:",
        "choose_language": "Выберите язык интерфейса / Choose your language:",
        "language_set": "Idioma cambiado ✅",
        "hw_title": "Análisis de tarea",
        "hw_strengths": "Lo que está bien:",
        "hw_corrections": "Correcciones:",
        "hw_vocab": "Vocabulario:",
        "hw_topics": "Temas para estudiar:",
        "hw_level": "Nivel del texto",
        "invite_success": (
            "✅ ¡Te has conectado exitosamente con el tutor <b>{name}</b>!\n\n"
            "Ahora tienes acceso a tu horario de clases y tareas."
        ),
        "invite_invalid": "El enlace de invitación no es válido o ha expirado.",
        "level_not_set": "Sin evaluar",
    },

    "de": {
        "welcome_new": (
            "Hallo! Ich bin dein Englisch-Lernassistent.\n\n"
            "Ich kann dir helfen:\n"
            "— Dein Niveau in 5 Minuten einschätzen\n"
            "— Unterrichtsstunden beim Tutor buchen\n"
            "— Hausaufgaben mit KI prüfen\n"
            "— Ein tägliches Wort zum Üben senden\n\n"
            "Was ist dein Lernziel?"
        ),
        "welcome_back": (
            "Willkommen zurück, {name}!\n\n"
            "Dein Niveau: <b>{level}</b>\n"
            "Ziel: <b>{goal}</b>\n\n"
            "Wähle eine Aktion:"
        ),
        "goal_general": "Konversationsenglisch",
        "goal_business": "Business-Englisch",
        "goal_ielts": "IELTS / TOEFL",
        "goal_oge_ege": "OGE / EGE",
        "goal_not_set": "Nicht festgelegt",
        "goal_chosen": (
            "Super! Ziel: <b>{goal}</b>.\n\n"
            "Jetzt bestimmen wir dein Englischniveau — das dauert nur 5 Minuten!"
        ),
        "btn_book": "Stunde buchen",
        "btn_my_lessons": "Meine Stunden",
        "btn_homework": "Hausaufgaben prüfen",
        "btn_profile": "Mein Profil",
        "btn_word_of_day": "📚 Wort des Tages",
        "btn_placement": "Einstufungstest (5 Min)",
        "btn_know_level": "Ich kenne mein Niveau bereits",
        "btn_retake_test": "Einstufungstest wiederholen",
        "no_tutor": (
            "Du hast noch keinen zugewiesenen Tutor.\n"
            "Kontaktiere deinen Lehrer, um dich zu verbinden."
        ),
        "no_lessons": (
            "Du hast keine geplanten Stunden.\n\n"
            "Tippe auf «{btn}», um eine Zeit zu wählen."
        ),
        "upcoming_lessons": "<b>Deine nächsten Stunden:</b>\n",
        "profile_body": (
            "<b>Dein Profil</b>\n\n"
            "Name: {name}\n"
            "Niveau: <b>{level}</b>\n"
            "Ziel: {goal}\n\n"
            "Drücke den Button unten, um den Einstufungstest zu wiederholen."
        ),
        "homework_prompt": (
            "<b>Hausaufgaben-Check (KI)</b>\n\n"
            "Sende deinen Text (Aufsatz, Brief, Sätze) "
            "und ich prüfe Grammatik, Wortschatz und schätze dein Niveau ein.\n\n"
            "Schreibe oder füge deinen Text einfach ein:"
        ),
        "homework_too_short": "Bitte schicke einen längeren Text — mindestens ein paar Sätze.",
        "homework_too_long": "Der Text ist zu lang. Maximum sind 5.000 Zeichen.",
        "homework_thinking": "Analysiere deinen Text...",
        "homework_limit": (
            "Du hast dein tägliches Check-Limit erreicht.\n"
            "Versuche es morgen oder frag deinen Tutor!"
        ),
        "what_next": "Was kommt als Nächstes?",
        "skip_placement": "OK! Du kannst den Test später machen.\nWähle eine Aktion:",
        "choose_language": "Выберите язык интерфейса / Choose your language:",
        "language_set": "Sprache geändert ✅",
        "hw_title": "Hausaufgaben-Analyse",
        "hw_strengths": "Was gut ist:",
        "hw_corrections": "Korrekturen:",
        "hw_vocab": "Wortschatz:",
        "hw_topics": "Themen zum Lernen:",
        "hw_level": "Textniveau",
        "invite_success": (
            "✅ Du hast dich erfolgreich mit Tutor <b>{name}</b> verbunden!\n\n"
            "Du hast jetzt Zugang zu deinem Stundenplan und Hausaufgaben."
        ),
        "invite_invalid": "Der Einladungslink ist ungültig oder abgelaufen.",
        "level_not_set": "Nicht bewertet",
    },
}

ALL_LANGS = list(STRINGS.keys())

# Pre-computed sets for F.text.in_() matching — one set per button key
ALL_BTN_BOOK = {STRINGS[lang]["btn_book"] for lang in ALL_LANGS}
ALL_BTN_MY_LESSONS = {STRINGS[lang]["btn_my_lessons"] for lang in ALL_LANGS}
ALL_BTN_HOMEWORK = {STRINGS[lang]["btn_homework"] for lang in ALL_LANGS}
ALL_BTN_PROFILE = {STRINGS[lang]["btn_profile"] for lang in ALL_LANGS}
ALL_BTN_WORD = {STRINGS[lang]["btn_word_of_day"] for lang in ALL_LANGS}


def t(lang: str, key: str, **kwargs: str) -> str:
    """Return translated string for lang, falling back to Russian."""
    text = STRINGS.get(lang, STRINGS["ru"]).get(key) or STRINGS["ru"].get(key, key)
    return text.format(**kwargs) if kwargs else text


def lang_from_text(text: str) -> str | None:
    """Detect which language a button text belongs to. Returns lang code or None."""
    for lang, strings in STRINGS.items():
        if text in strings.values():
            return lang
    return None
