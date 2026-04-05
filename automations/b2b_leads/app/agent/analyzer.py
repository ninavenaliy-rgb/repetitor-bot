import json
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — ассистент для анализа B2B заявок производственной компании.
Извлеки из текста заявки следующие параметры в JSON:
- product: название продукта/изделия
- material: материал (сталь, пластик, алюминий, etc.)
- volume: объём заказа (число + единица)
- deadline: срок исполнения
- intent: тип запроса (order/quote/info/complaint)
- priority: приоритет (high/medium/low)
- summary: краткое описание на русском (1-2 предложения)

Если параметр не указан — null. Отвечай ТОЛЬКО JSON, без пояснений."""

FALLBACK_RESULT = {
    "product": None,
    "material": None,
    "volume": None,
    "deadline": None,
    "intent": "info",
    "priority": "medium",
    "summary": "Заявка требует уточнения деталей.",
    "needs_clarification": True,
}


async def analyze_lead(message: str) -> dict:
    try:
        result = await _call_ai(message)
        result["needs_clarification"] = _check_needs_clarification(result)
        return result
    except Exception as e:
        logger.warning(f"AI analysis failed: {e}. Using fallback.")
        return FALLBACK_RESULT


async def _call_ai(message: str) -> dict:
    import os
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("No AI API key configured")

    # Поддержка OpenAI-совместимых API
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
                "temperature": 0.1,
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)


def _check_needs_clarification(analysis: dict) -> bool:
    required = ["product", "volume"]
    return any(analysis.get(field) is None for field in required)
