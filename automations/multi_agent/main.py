"""
Точка входа мульти-агентной системы.
Полная производственная цепочка:
заявка → анализ → склад → мощности → цена → CRM → ответ клиенту
"""

import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

# Регистрация всех агентов
import automations.multi_agent.agents.analyzer   # noqa
import automations.multi_agent.agents.pricer     # noqa
import automations.multi_agent.agents.notifier   # noqa
import automations.multi_agent.agents.crm_agent  # noqa
import automations.multi_agent.agents.summarizer # noqa
import automations.multi_agent.agents.warehouse  # noqa
import automations.multi_agent.agents.capacity   # noqa

from automations.multi_agent.registry import registry


async def demo():
    print("\n" + "="*60)
    print("  ПРОИЗВОДСТВЕННАЯ МУЛЬТИ-АГЕНТНАЯ СИСТЕМА")
    print("="*60)

    print("\n📋 Зарегистрированные агенты:")
    for agent in registry.list_agents():
        print(f"  • [{', '.join(agent['tags'])}] {agent['name']}: {agent['description']}")

    task = {
        "name": "ООО МеталлСтрой",
        "phone": "+79001234567",
        "message": "Нужны стальные трубы диаметром 50мм, 20 тонн, срочно",
        "source": "website",
    }

    print(f"\n📥 Входящая заявка: {task['message']}")

    # ── Полная производственная цепочка ──────────────────────────────────────
    print("\n⛓  Производственная цепочка:")
    print("   analyzer → warehouse → capacity → pricer → crm\n")

    result = await registry.run_chain(
        task,
        chain=["analyzer", "warehouse", "capacity", "pricer", "crm"]
    )

    labels = {
        "analyzer":  "🔍 Анализ заявки",
        "warehouse": "📦 Склад",
        "capacity":  "🏭 Производство",
        "pricer":    "💰 Расчёт цены",
        "crm":       "📋 CRM",
    }

    for step in result["steps"]:
        name = step["agent"]
        res = step["result"]
        print(f"  {labels.get(name, name)}")

        if name == "analyzer":
            print(f"    Продукт:   {res.get('product')}")
            print(f"    Материал:  {res.get('material')}")
            print(f"    Объём:     {res.get('volume')}")
            print(f"    Приоритет: {res.get('priority')}")

        elif name == "warehouse":
            status_icon = {"in_stock": "✅", "partial": "⚠️", "shortage": "❌"}.get(res.get("status"), "❓")
            print(f"    {status_icon} {res.get('message')}")

        elif name == "capacity":
            print(f"    📅 {res.get('message')}")
            if res.get("delay_reason"):
                print(f"    ⚠️  Задержка: {res['delay_reason']}")

        elif name == "pricer":
            if "error" in res:
                print(f"    ⚠️  {res['error']}")
            else:
                print(f"    Итого: {res.get('total', 0):,.0f} ₽")
                print(f"    {res.get('note', '')}")

        elif name == "crm":
            print(f"    Лид создан: {res.get('lead_id')} [{res.get('crm')}]")

        print()

    # ── Авто-роутинг (Claude сам выбирает) ───────────────────────────────────
    print("─"*50)
    print("🔀 Авто-роутинг: 'Проверь наличие профиля стального'")
    spot_task = {"message": "Проверь наличие профиля стального", "product": "профиль", "material": "стальной"}
    routed = await registry.run(spot_task)
    print(f"  Claude выбрал агента: {routed['agent']}")
    print(f"  Результат: {routed['result'].get('message', routed['result'])}")

    print("\n✅ Демо завершено")


if __name__ == "__main__":
    asyncio.run(demo())
