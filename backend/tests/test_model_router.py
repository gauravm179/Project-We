from __future__ import annotations

from app.brain.model_router import choose_model_tier


def test_coding_specialist_always_tech():
    choice = choose_model_tier("hello", specialist_slug="coding-bot")
    assert choice.tier == "tech"
    assert "coding" in choice.reason


def test_casual_chat_uses_qwen_tier():
    choice = choose_model_tier("hey, how are you?")
    assert choice.tier == "chat"


def test_technical_message_uses_deepseek_tier():
    choice = choose_model_tier("Please debug this Python race condition in my asyncio code")
    assert choice.tier == "tech"


def test_code_fence_uses_tech():
    choice = choose_model_tier("```\ndef foo():\n    pass\n```\nwhat does this do?")
    assert choice.tier == "tech"


def test_web_learner_default_chat_unless_technical():
    chat = choose_model_tier("summarize this page", specialist_slug="web-learner-bot")
    assert chat.tier == "chat"
    tech = choose_model_tier(
        "explain this kubernetes concurrency bug", specialist_slug="web-learner-bot"
    )
    assert tech.tier == "tech"


def test_force_qwen_override():
    choice = choose_model_tier("use qwen for a simple question about weather words")
    assert choice.tier == "chat"
