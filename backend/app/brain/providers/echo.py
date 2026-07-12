from app.brain.providers.base import AIProvider


class EchoProvider(AIProvider):
    async def generate(self, user_message: str, memory_context: str | None = None) -> str:
        if memory_context:
            return f"You said: {user_message}\n\n[local memory context used]"
        return f"You said: {user_message}"
