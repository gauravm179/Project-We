from __future__ import annotations

import asyncio

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
