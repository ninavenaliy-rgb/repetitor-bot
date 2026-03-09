# Repetitor Bot

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.x-009688?logo=telegram&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-red)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?logo=fastapi)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-412991?logo=openai&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)

**Production-ready Telegram bot for language tutors** — automates student management, scheduling, AI-powered homework checking, payments, and engagement.

Built with Python, aiogram 3, SQLAlchemy 2, FastAPI. Designed for solo tutors and small language schools.

---

## Features

| Category | What it does |
|---|---|
| **Student CRM** | Add students, track CEFR level, notes, progress (0–100%) |
| **Scheduling** | Book lessons, conflict detection, Google Calendar sync |
| **Reminders** | Automated T-24h / T-2h push notifications to students |
| **AI Homework** | GPT-4o-mini checks grammar & vocabulary, gives feedback |
| **AI Lesson Plans** | Generates structured lesson plans by topic & level |
| **Payments** | Lesson packages (4/8/12 lessons), debt tracking, income analytics |
| **Subscriptions** | Trial → paid plans via Telegram Stars built-in payments |
| **Referrals** | Tutor-to-tutor referral system with bonus tracking |
| **Placement Test** | 12-question adaptive CEFR test for new students |
| **Engagement** | Daily Word of the Day, streak tracking, churn detection |
| **Analytics** | Income charts, no-show rate, student progress dashboard |
| **Multi-language** | Student UI in RU / EN / ES / DE |

---

## Tech Stack

```
Python 3.11
├── aiogram 3.x          — Telegram Bot framework (async, FSM, middleware)
├── SQLAlchemy 2.0       — Async ORM (PostgreSQL in prod, SQLite locally)
├── FastAPI + Uvicorn    — Internal analytics dashboard
├── OpenAI API           — GPT-4o-mini for homework & lesson plans
├── Celery + Redis       — Background tasks (production)
└── Docker Compose       — One-command deployment
```

---

## Architecture

```
Telegram Bot (aiogram 3)
        │
    Middleware stack
    ├── AuthMiddleware       — auto-create User/Tutor from telegram_id
    ├── SubscriptionMiddleware — feature gates by plan
    └── StudentLimitMiddleware — enforce student count limits
        │
    Handler routers (17 modules)
    ├── Registration, Start, Placement
    ├── Tutor Panel (students, schedule, payments, income)
    ├── Homework, Lesson Plan (AI)
    ├── Subscriptions, Referrals, Feedback
    └── Admin panel
        │
    Services layer
    ├── BookingService, EngagementService, AnalyticsService
    ├── SubscriptionService  — trial, upgrade, downgrade, cancel
    ├── AIService            — homework check + lesson plan generation
    └── ReminderService      — async background loops (no Celery locally)
        │
    Repository layer (SQLAlchemy async)
    └── PostgreSQL (prod) / SQLite (dev)
```

---

## Quick Start (local, no Docker needed)

```bash
git clone https://github.com/YOUR_USERNAME/repetitor-bot
cd repetitor-bot

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in BOT_TOKEN (required), OPENAI_API_KEY (for AI features)
# DATABASE_URL defaults to SQLite automatically for local dev

python -m src.main
```

The bot uses **SQLite locally** — no PostgreSQL or Redis needed for development.

---

## Production Deployment (Docker)

```bash
cp .env.example .env
# Edit .env: BOT_TOKEN, OPENAI_API_KEY, DB_PASSWORD, DASHBOARD_SECRET_KEY

docker-compose up -d

# Run DB migrations
docker-compose exec bot alembic upgrade head
```

Services started: bot + FastAPI dashboard + PostgreSQL + Redis + Celery worker.

---

## Project Structure

```
repetitor-bot/
├── config/
│   ├── settings.py          # Pydantic Settings (env vars)
│   └── constants.py
├── src/
│   ├── main.py              # Entry point, background task loops
│   ├── bot/
│   │   ├── handlers/        # 17 aiogram routers
│   │   ├── keyboards/       # Reply & inline keyboards
│   │   ├── middlewares/     # Auth, logging
│   │   ├── states/          # FSM state groups
│   │   └── locales.py       # i18n strings (RU/EN/ES/DE)
│   ├── database/
│   │   ├── models.py        # SQLAlchemy ORM models
│   │   ├── models_subscription.py
│   │   ├── engine.py        # Async engine, session factory
│   │   ├── repositories/    # Data access layer (8 repos)
│   │   └── seeds.py         # Subscription plan seeding
│   ├── services/            # Business logic layer
│   │   ├── ai_service.py
│   │   ├── booking_service.py
│   │   ├── subscription_service.py
│   │   ├── engagement_service.py
│   │   ├── analytics_service.py
│   │   └── reminder_service.py
│   ├── middleware/          # Subscription & admin middleware
│   ├── api/                 # REST API endpoints
│   └── web/                 # FastAPI dashboard
├── data/
│   ├── placement_questions.json   # CEFR test questions
│   └── word_bank.json             # Daily word database
├── tests/
├── alembic/                 # DB migrations
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Subscription Plans

| Feature | Trial (7 days) | START 990₽/mo | PRO 1990₽/mo |
|---|---|---|---|
| Students | Unlimited | Unlimited | Unlimited |
| Scheduling & reminders | ✅ | ✅ | ✅ |
| AI homework check | 30/mo | 30/mo | Unlimited |
| AI lesson plans | ✅ | — | ✅ |
| Detailed analytics | ✅ | Basic | Full |
| Google Calendar sync | — | — | ✅ |
| Parent notifications | — | — | ✅ |

Payment via **Telegram Stars** (built-in, no external payment provider needed).

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | Yes | From @BotFather |
| `BOT_USERNAME` | No | Bot username without @ (for invite links) |
| `DATABASE_URL` | No | Defaults to SQLite for local dev |
| `OPENAI_API_KEY` | No | GPT-4o-mini for AI features |
| `GOOGLE_CALENDAR_CREDENTIALS_PATH` | No | Service account JSON |
| `ADMIN_USER_IDS` | No | Comma-separated Telegram IDs |
| `FEEDBACK_CHAT_ID` | No | Chat/channel for student feedback |

---

## License

MIT
