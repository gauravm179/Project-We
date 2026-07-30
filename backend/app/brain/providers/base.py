from __future__ import annotations

from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        user_message: str,
        memory_context: str | None = None,
        system_prompt: str | None = None,
        *,
        specialist_slug: str | None = None,
    ) -> str:
        """Generate assistant output from a user message."""
