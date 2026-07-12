from __future__ import annotations

from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    async def generate(self, user_message: str) -> str:
        """Generate assistant output from a user message."""
