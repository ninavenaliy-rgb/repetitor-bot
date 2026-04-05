"""Агент создания резюме/отчёта по задаче."""
import os
import httpx
from automations.multi_agent.registry import registry


@registry.register(
    name="summarizer",
    description="Создаёт краткое резюме или отчёт по результатам работы других агентов",
    tags=["output", "ai"],
)
async def summarizer_agent(task: dict) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"summary": str(task)}

    prompt = f"Составь краткое деловое резюме (3-5 предложений на русском) по данным: {task}"

    try:
        if os.getenv("ANTHROPIC_API_KEY"):
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 300,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                return {"summary": resp.json()["content"][0]["text"]}
    except Exception as e:
        return {"summary": f"Ошибка генерации: {e}"}
