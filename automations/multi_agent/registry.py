"""
AgentRegistry — оркестратор мульти-агентной системы.
Регистрирует агентов, маршрутизирует задачи через Claude, выполняет цепочки.
"""

import os
import json
import logging
from typing import Callable, Awaitable, Any
from dataclasses import dataclass, field
import httpx

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    name: str
    description: str
    handler: Callable[[dict], Awaitable[dict]]
    tags: list = field(default_factory=list)


class AgentRegistry:
    def __init__(self):
        self._agents: dict = {}
        self._api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")

    # ─── Регистрация ─────────────────────────────────────────────────────────

    def register(self, name: str, description: str, tags: list = None):
        """Декоратор для регистрации агента."""
        def decorator(fn: Callable):
            self._agents[name] = AgentInfo(
                name=name,
                description=description,
                handler=fn,
                tags=tags or [],
            )
            logger.info(f"Agent registered: {name}")
            return fn
        return decorator

    def register_agent(self, name: str, description: str, handler: Callable, tags: list = None):
        """Прямая регистрация без декоратора."""
        self._agents[name] = AgentInfo(
            name=name,
            description=description,
            handler=handler,
            tags=tags or [],
        )
        logger.info(f"Agent registered: {name}")

    # ─── Роутинг ─────────────────────────────────────────────────────────────

    async def route(self, task: dict) -> str:
        """
        Claude выбирает нужного агента по описанию задачи.
        Возвращает имя агента.
        """
        if not self._agents:
            raise ValueError("No agents registered")

        agents_list = "\n".join(
            f'- "{name}": {info.description}'
            for name, info in self._agents.items()
        )

        prompt = f"""У тебя есть следующие агенты:
{agents_list}

Задача: {json.dumps(task, ensure_ascii=False)}

Ответь ТОЛЬКО именем агента (одно слово из списка выше), без пояснений."""

        agent_name = await self._ask_claude(prompt)
        agent_name = agent_name.strip().strip('"').strip("'")

        if agent_name not in self._agents:
            # Fallback: ищем частичное совпадение
            for name in self._agents:
                if name.lower() in agent_name.lower():
                    return name
            # Берём первого если ничего не нашли
            logger.warning(f"Unknown agent '{agent_name}', using first registered")
            return next(iter(self._agents))

        return agent_name

    # ─── Выполнение ──────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        """Автоматически выбрать агента и выполнить задачу."""
        agent_name = await self.route(task)
        logger.info(f"Routed to agent: {agent_name}")
        return await self.run_agent(agent_name, task)

    async def run_agent(self, name: str, task: dict) -> dict:
        """Выполнить конкретного агента по имени."""
        if name not in self._agents:
            raise ValueError(f"Agent '{name}' not found")
        agent = self._agents[name]
        result = await agent.handler(task)
        return {"agent": name, "result": result}

    async def run_chain(self, task: dict, chain: list) -> dict:
        """
        Выполнить цепочку агентов последовательно.
        Результат каждого передаётся следующему.
        """
        context = task.copy()
        history = []

        for agent_name in chain:
            logger.info(f"Chain step: {agent_name}")
            output = await self.run_agent(agent_name, context)
            history.append(output)
            # Результат предыдущего агента добавляется в контекст следующего
            context[f"{agent_name}_result"] = output["result"]

        return {"chain": chain, "steps": history, "final": history[-1]["result"]}

    async def run_parallel(self, task: dict, agents: list) -> dict:
        """Запустить нескольких агентов параллельно."""
        import asyncio
        tasks = [self.run_agent(name, task) for name in agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            "parallel": agents,
            "results": {
                name: (r if not isinstance(r, Exception) else {"error": str(r)})
                for name, r in zip(agents, results)
            }
        }

    # ─── Утилиты ─────────────────────────────────────────────────────────────

    def list_agents(self) -> list:
        return [
            {"name": a.name, "description": a.description, "tags": a.tags}
            for a in self._agents.values()
        ]

    async def _ask_claude(self, prompt: str) -> str:
        if not self._api_key:
            raise ValueError("ANTHROPIC_API_KEY or OPENAI_API_KEY not set")

        # Поддержка Anthropic API
        if os.getenv("ANTHROPIC_API_KEY"):
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 50,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                return resp.json()["content"][0]["text"]

        # Fallback: OpenAI
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "max_tokens": 50,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


# Глобальный реестр (синглтон)
registry = AgentRegistry()
