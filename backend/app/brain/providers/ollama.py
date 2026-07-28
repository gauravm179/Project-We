from __future__ import annotations

import httpx

from app.brain.providers.base import AIProvider

_REASONING_SYSTEM = (
    "You are a careful local assistant. For questions and coding tasks:\n"
    "1) Restate the goal briefly.\n"
    "2) Reason step by step.\n"
    "3) Give a clear final answer or working code.\n"
    "4) Call out assumptions and edge cases.\n"
    "Stay local-first. Do not claim live internet access unless the user approved it."
)


class OllamaProvider(AIProvider):
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_seconds: float = 120.0,
        temperature: float = 0.2,
        reasoning: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._reasoning = reasoning

    async def generate(
        self,
        user_message: str,
        memory_context: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        messages = []
        system_parts: list[str] = []
        if self._reasoning:
            system_parts.append(_REASONING_SYSTEM)
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
            "options": {
                "temperature": self._temperature,
            },
        }
        url = f"{self._base_url}/api/chat"
        timeout = httpx.Timeout(self._timeout_seconds, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            body = response.json()

        return body.get("message", {}).get("content", "").strip() or "No response from Ollama."

    async def healthcheck(self) -> dict[str, str | bool]:
        url = f"{self._base_url}/api/tags"
        timeout = httpx.Timeout(5.0, connect=2.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                models = [item.get("name", "") for item in response.json().get("models", [])]
            return {
                "ok": True,
                "reachable": True,
                "model_configured": self._model,
                "model_available": any(
                    name == self._model or name.startswith(f"{self._model}:") or name.startswith(self._model)
                    for name in models
                ),
                "models": ", ".join(models) if models else "",
            }
        except Exception as exc:  # noqa: BLE001 - surface provider health cleanly
            return {
                "ok": False,
                "reachable": False,
                "model_configured": self._model,
                "model_available": False,
                "error": str(exc),
            }
