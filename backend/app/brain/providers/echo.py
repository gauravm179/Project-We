from app.brain.providers.base import AIProvider


class EchoProvider(AIProvider):
    async def generate(
        self,
        user_message: str,
        memory_context: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Deterministic stub used for tests when Ollama/Llama is not configured."""
        # Main-bot path (no specialist prompt): keep simple for unit tests.
        if not system_prompt:
            parts = [f"You said: {user_message}"]
            if memory_context:
                parts.append("[local memory context used]")
            return "\n\n".join(parts)

        parts: list[str] = [
            "ECHO MODE (not a real model).",
            "To get real code answers, restart with local Llama:",
            "  export PROJECT_WE_PROVIDER=ollama",
            "  export PROJECT_WE_OLLAMA_MODEL=llama3.2",
            "  ollama pull llama3.2",
            "",
            f"You said: {user_message}",
            "[specialist: active]",
        ]
        if "LEARNED SKILLS" in system_prompt:
            parts.append("LEARNED SKILLS")
            for line in system_prompt.splitlines():
                if line.startswith("[SKILL:"):
                    parts.append(line.strip())
        if "CODING GUIDELINES" in system_prompt:
            parts.append("CODING GUIDELINES")
        if memory_context:
            parts.append("[local memory context used]")
            if "LESSONS FROM PAST MISTAKES" in memory_context:
                parts.append("LESSONS FROM PAST MISTAKES")
        return "\n".join(parts)
