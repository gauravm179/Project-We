from __future__ import annotations

import asyncio

import httpx

from app.brain.providers.ollama import OllamaProvider


def test_ollama_provider_builds_reasoning_prompt(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"message": {"content": "Because 2+2=4.\n\nFinal answer: 4"}}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.brain.providers.ollama.httpx.AsyncClient", FakeClient)

    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="llama3.2",
        reasoning=True,
        temperature=0.2,
    )
    text = asyncio.run(
        provider.generate(
            "What is 2+2?",
            memory_context="fact:user_name=Alex",
            system_prompt="You are coding-bot.",
        )
    )

    assert text.startswith("Because")
    assert captured["url"].endswith("/api/chat")
    assert captured["json"]["model"] == "llama3.2"
    assert captured["json"]["options"]["temperature"] == 0.2
    system = captured["json"]["messages"][0]["content"]
    assert "Reason step by step" in system
    assert "You are coding-bot." in system
    assert "fact:user_name=Alex" in system


def test_ollama_falls_back_to_generate_on_chat_404(monkeypatch):
    calls: list[str] = []

    class FakeResponse:
        def __init__(self, status_code: int = 200, payload: dict | None = None):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = str(self._payload)
            self.request = httpx.Request("POST", "http://127.0.0.1:11434/api/chat")

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "error",
                    request=self.request,
                    response=httpx.Response(
                        self.status_code,
                        request=self.request,
                        json=self._payload,
                        text=self.text,
                    ),
                )

        def json(self) -> dict:
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            calls.append(url)
            if url.endswith("/api/chat"):
                return FakeResponse(404, {"error": "not found"})
            return FakeResponse(200, {"response": "fallback answer"})

    monkeypatch.setattr("app.brain.providers.ollama.httpx.AsyncClient", FakeClient)
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model="llama3.2")
    text = asyncio.run(provider.generate("hi"))
    assert text == "fallback answer"
    assert any(url.endswith("/api/chat") for url in calls)
    assert any(url.endswith("/api/generate") for url in calls)


def test_ollama_missing_model_message(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            request = httpx.Request("POST", url)
            response = httpx.Response(
                404,
                request=request,
                json={"error": "model 'llama3.2' not found"},
            )
            raise httpx.HTTPStatusError("error", request=request, response=response)

    monkeypatch.setattr("app.brain.providers.ollama.httpx.AsyncClient", FakeClient)
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model="llama3.2")
    try:
        asyncio.run(provider.generate("hi"))
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        msg = str(exc)
        assert "ollama pull llama3.2" in msg or "model" in msg.lower()
