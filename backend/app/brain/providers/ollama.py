from __future__ import annotations

import httpx

from app.brain.providers.base import AIProvider


class OllamaProvider(AIProvider):
    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def generate(
        self,
        user_message: str,
        memory_context: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        messages = []
        system_parts: list[str] = []
        if system_prompt:
            system_parts.append(system_prompt)
        if memory_context:
            system_parts.append(
                "Use this local memory context when useful. "
                "Do not claim internet access without explicit permission.\n"
                f"{memory_context}"
            )
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self._model,
            "stream": False,
            "messages": messages,
        }
        url = f"{self._base_url}/api/chat"
        timeout = httpx.Timeout(30.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            body = response.json()

        return body.get("message", {}).get("content", "").strip() or "No response from Ollama."
