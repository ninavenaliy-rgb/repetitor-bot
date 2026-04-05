"""
Интерактивный установщик B2B Lead Automation.
Запуск: python setup.py
"""

import os
import sys


# ─── Цвета в терминале ────────────────────────────────────────────────────────

def green(text): return f"\033[92m{text}\033[0m"
def yellow(text): return f"\033[93m{text}\033[0m"
def cyan(text): return f"\033[96m{text}\033[0m"
def bold(text): return f"\033[1m{text}\033[0m"
def red(text): return f"\033[91m{text}\033[0m"


def ask(question: str, default: str = "", required: bool = False) -> str:
    hint = f" [{default}]" if default else (" (обязательно)" if required else " (Enter — пропустить)")
    while True:
        answer = input(cyan(f"  {question}{hint}: ")).strip()
        if not answer and default:
            return default
        if not answer and required:
            print(red("  ⚠️  Это поле обязательно"))
            continue
        return answer or ""


def ask_choice(question: str, options: list, default: str = None) -> str:
    print(cyan(f"  {question}"))
    for i, opt in enumerate(options, 1):
        marker = " ← по умолчанию" if opt == default else ""
        print(f"    {i}. {opt}{marker}")
    while True:
        raw = input(cyan(f"  Выбери номер [{options.index(default) + 1 if default in options else 1}]: ")).strip()
        if not raw and default:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        print(red("  Введи цифру из списка"))


def section(title: str):
    print(f"\n{'─'*50}")
    print(bold(f"  {title}"))
    print('─'*50)


# ─── Главная логика ───────────────────────────────────────────────────────────

def run():
    print()
    print(bold("=" * 50))
    print(bold("  🚀 B2B Lead Automation — Установка"))
    print(bold("=" * 50))
    print("  Скрипт создаст файл .env с твоими настройками.")
    print("  Просто отвечай на вопросы. Enter = пропустить.\n")

    config = {}

    # ── База данных ──────────────────────────────────────────────────────────
    section("1/7  База данных")
    db_type = ask_choice("Где запускаем?", ["Локально (SQLite)", "Свой сервер (PostgreSQL)"], default="Локально (SQLite)")

    if "SQLite" in db_type:
        config["DATABASE_URL"] = "sqlite+aiosqlite:///./b2b_leads.db"
        print(green("  ✓ SQLite — не нужно ничего устанавливать"))
    else:
        host = ask("Хост БД", default="localhost")
        port = ask("Порт", default="5432")
        db_name = ask("Имя базы", default="b2b_leads")
        db_user = ask("Пользователь", default="postgres")
        db_pass = ask("Пароль", required=True)
        config["DATABASE_URL"] = f"postgresql+asyncpg://{db_user}:{db_pass}@{host}:{port}/{db_name}"

    # ── Redis ────────────────────────────────────────────────────────────────
    section("2/7  Redis (очереди)")
    use_redis = ask_choice("Использовать Redis?", ["Да", "Нет, без очередей"], default="Нет, без очередей")
    if use_redis == "Да":
        redis_host = ask("Redis хост", default="localhost")
        redis_port = ask("Redis порт", default="6379")
        config["REDIS_URL"] = f"redis://{redis_host}:{redis_port}"
    else:
        config["REDIS_URL"] = ""

    # ── AI ───────────────────────────────────────────────────────────────────
    section("3/7  AI (для анализа заявок)")
    ai_provider = ask_choice("Какой AI провайдер?", ["Anthropic (Claude)", "OpenAI (GPT)", "Пропустить"], default="Anthropic (Claude)")
    if "Anthropic" in ai_provider:
        config["ANTHROPIC_API_KEY"] = ask("Anthropic API ключ", required=True)
    elif "OpenAI" in ai_provider:
        config["OPENAI_API_KEY"] = ask("OpenAI API ключ", required=True)

    # ── CRM ──────────────────────────────────────────────────────────────────
    section("4/7  CRM")
    crm = ask_choice("Какая CRM?", ["Bitrix24", "amoCRM", "Без CRM (внутренняя)"], default="Без CRM (внутренняя)")

    if crm == "Bitrix24":
        config["CRM_TYPE"] = "bitrix24"
        config["BITRIX24_WEBHOOK_URL"] = ask("Webhook URL (из настроек Bitrix24)", required=True)
        config["BITRIX24_DEFAULT_MANAGER"] = ask("ID менеджера по умолчанию", default="1")
    elif crm == "amoCRM":
        config["CRM_TYPE"] = "amocrm"
        config["AMOCRM_DOMAIN"] = ask("Домен (например: company.amocrm.ru)", required=True)
        config["AMOCRM_TOKEN"] = ask("Долгосрочный токен", required=True)
        config["AMOCRM_PIPELINE_ID"] = ask("ID воронки", default="0")
        config["AMOCRM_DEFAULT_MANAGER"] = ask("ID менеджера по умолчанию", default="0")
    else:
        config["CRM_TYPE"] = "internal"

    # ── Мессенджеры ──────────────────────────────────────────────────────────
    section("5/7  Мессенджеры")
    print("  Настрой каналы для отправки сообщений клиентам.\n")

    # WhatsApp
    use_wa = ask_choice("WhatsApp (Meta Business API)?", ["Да", "Нет"], default="Нет")
    if use_wa == "Да":
        config["WHATSAPP_TOKEN"] = ask("WhatsApp Access Token", required=True)
        config["WHATSAPP_PHONE_ID"] = ask("Phone Number ID", required=True)

    # Telegram
    use_tg = ask_choice("Telegram Bot?", ["Да", "Нет"], default="Нет")
    if use_tg == "Да":
        config["TELEGRAM_BOT_TOKEN"] = ask("Telegram Bot Token (@BotFather)", required=True)

    # VK
    use_vk = ask_choice("ВКонтакте?", ["Да", "Нет"], default="Нет")
    if use_vk == "Да":
        config["VK_TOKEN"] = ask("VK API ключ группы", required=True)
        config["VK_GROUP_ID"] = ask("ID группы VK", required=True)

    # ── Email ────────────────────────────────────────────────────────────────
    section("6/7  Email (SMTP)")
    use_email = ask_choice("Настроить email?", ["Да", "Нет"], default="Да")
    if use_email == "Да":
        provider = ask_choice("Провайдер?", ["Яндекс", "Gmail", "Другой"], default="Яндекс")
        if provider == "Яндекс":
            config["SMTP_HOST"] = "smtp.yandex.ru"
            config["SMTP_PORT"] = "465"
        elif provider == "Gmail":
            config["SMTP_HOST"] = "smtp.gmail.com"
            config["SMTP_PORT"] = "587"
        else:
            config["SMTP_HOST"] = ask("SMTP хост", required=True)
            config["SMTP_PORT"] = ask("SMTP порт", default="465")
        config["SMTP_USER"] = ask("Email адрес", required=True)
        config["SMTP_PASSWORD"] = ask("Пароль / App Password", required=True)
        config["SMTP_FROM_NAME"] = ask("Имя отправителя", default="Отдел продаж")

    # ── SMS ──────────────────────────────────────────────────────────────────
    use_sms = ask_choice("SMS через sms.ru?", ["Да", "Нет"], default="Нет")
    if use_sms == "Да":
        config["SMSRU_API_ID"] = ask("API ID из sms.ru", required=True)

    # ── Итог ─────────────────────────────────────────────────────────────────
    section("7/7  Сохранение")

    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        overwrite = ask_choice(f".env уже существует. Перезаписать?", ["Да", "Нет"], default="Да")
        if overwrite == "Нет":
            env_path = env_path.replace(".env", ".env.new")
            print(yellow(f"  Сохраняем как {env_path}"))

    lines = ["# B2B Lead Automation — конфигурация\n"]
    for key, value in config.items():
        if value:
            lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(green(f"\n  ✅ Файл сохранён: {env_path}"))
    print()
    print(bold("  Готово! Запуск:"))
    print("    docker-compose up        — с Docker")
    print("    uvicorn app.main:app --reload  — локально")
    print()
    print(bold("  Тест webhook:"))
    print('    curl -X POST http://localhost:8000/webhook \\')
    print('      -H "Content-Type: application/json" \\')
    print('      -d \'{"name":"Тест","phone":"+79001234567","message":"Нужны трубы 10 тонн","source":"website"}\'')
    print()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print(red("\n\n  Отменено."))
        sys.exit(0)
