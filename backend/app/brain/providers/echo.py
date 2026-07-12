from app.brain.providers.base import AIProvider


class EchoProvider(AIProvider):
    async def generate(self, user_message: str) -> str:
        return f"You said: {user_message}"
