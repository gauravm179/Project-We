from app.brain.providers.base import AIProvider


class EchoProvider(AIProvider):
    async def generate(
        self,
        user_message: str,
        memory_context: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        parts: list[str] = []
        if system_prompt:
            parts.append(f"[specialist: {system_prompt}]")
        parts.append(f"You said: {user_message}")
        if memory_context:
            parts.append("[local memory context used]")
        return "\n\n".join(parts)
