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

_FAST_SYSTEM = (
    "You are a fast local assistant. Reply briefly and directly. "
    "Skip long reasoning unless the user asks for it. "
    "Stay local-first."
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
        keep_alive: str = "30m",
        num_predict: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._reasoning = reasoning
        self._keep_alive = keep_alive
        self._num_predict = num_predict

    def _system_text(self, memory_context: str | None, system_prompt: str | None) -> str:
        system_parts: list[str] = []
        system_parts.append(_REASONING_SYSTEM if self._reasoning else _FAST_SYSTEM)
        if system_prompt:
            # Keep specialist prompts, but trim huge dumps in fast mode.
            trimmed = system_prompt if self._reasoning else system_prompt[:1200]
            system_parts.append(trimmed)
        if memory_context:
            memory = memory_context if self._reasoning else memory_context[:800]
            system_parts.append(
                "Use this local memory context when useful. "
                "Do not claim internet access without explicit permission.\n"
                f"{memory}"
            )
        return "\n\n".join(system_parts)

    def _options(self) -> dict[str, float | int]:
        options: dict[str, float | int] = {"temperature": self._temperature}
        if self._num_predict is not None:
            options["num_predict"] = self._num_predict
        elif not self._reasoning:
            options["num_predict"] = 256
        return options

    async def generate(
        self,
        user_message: str,
        memory_context: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        system_text = self._system_text(memory_context, system_prompt)
        messages = []
        if system_text:
            messages.append({"role": "system", "content": system_text})
        messages.append({"role": "user", "content": user_message})

        timeout = httpx.Timeout(self._timeout_seconds, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                return await self._chat(client, messages)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    try:
                        return await self._generate(client, user_message, system_text)
                    except httpx.HTTPStatusError as gen_exc:
                        raise RuntimeError(self._friendly_http_error(gen_exc)) from gen_exc
                raise RuntimeError(self._friendly_http_error(exc)) from exc
            except httpx.HTTPError as exc:
                raise RuntimeError(
                    f"Cannot reach Ollama at {self._base_url}. "
                    f"Start it with `ollama serve`, then `ollama pull {self._model}`."
                ) from exc

    async def _chat(self, client: httpx.AsyncClient, messages: list[dict[str, str]]) -> str:
        response = await client.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "stream": False,
                "keep_alive": self._keep_alive,
                "messages": messages,
                "options": self._options(),
            },
        )
        response.raise_for_status()
        body = response.json()
        return body.get("message", {}).get("content", "").strip() or "No response from Ollama."

    async def _generate(
        self,
        client: httpx.AsyncClient,
        user_message: str,
        system_text: str,
    ) -> str:
        prompt = user_message
        if system_text:
            prompt = f"{system_text}\n\nUser: {user_message}\nAssistant:"
        response = await client.post(
            f"{self._base_url}/api/generate",
            json={
                "model": self._model,
                "stream": False,
                "keep_alive": self._keep_alive,
                "prompt": prompt,
                "system": system_text or None,
                "options": self._options(),
            },
        )
        response.raise_for_status()
        body = response.json()
        return (body.get("response") or "").strip() or "No response from Ollama."

    def _friendly_http_error(self, exc: httpx.HTTPStatusError) -> str:
        status = exc.response.status_code
        detail = ""
        try:
            detail = str(exc.response.json().get("error") or exc.response.text)
        except Exception:  # noqa: BLE001
            detail = exc.response.text

        if status == 404:
            return (
                f"Ollama returned 404 for model '{self._model}'. "
                f"Run: ollama pull {self._model} "
                f"(check installed models with: ollama list). "
                f"Details: {detail or 'not found'}"
            )
        return f"Ollama error {status}: {detail or str(exc)}"

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
                    name == self._model
                    or name.startswith(f"{self._model}:")
                    or name.startswith(self._model)
                    for name in models
                ),
                "models": ", ".join(models) if models else "",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "reachable": False,
                "model_configured": self._model,
                "model_available": False,
                "error": str(exc),
            }
