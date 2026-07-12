from __future__ import annotations

import httpx

from app.brain.providers.base import AIProvider


class OllamaProvider(AIProvider):
    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def generate(self, user_message: str) -> str:
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "user", "content": user_message},
            ],
        }
        url = f"{self._base_url}/api/chat"
        timeout = httpx.Timeout(30.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            body = response.json()

        return body.get("message", {}).get("content", "").strip() or "No response from Ollama."
