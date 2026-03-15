"""Abstract memory store interface."""

from abc import ABC, abstractmethod
from bot.memory.models import Session, BaseMemory


class MemoryStore(ABC):
    """Abstract interface for memory persistence."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize storage backend."""
        pass

    @abstractmethod
    async def create_session(self, user_id: str, platform: str, chat_id: str) -> Session:
        """Create new session."""
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Session | None:
        """Retrieve session by ID."""
        pass

    @abstractmethod
    async def update_session(self, session_id: str, updates: dict) -> None:
        """Update session fields."""
        pass

    @abstractmethod
    async def save_memory(self, session_id: str, memory: BaseMemory) -> str:
        """Save memory node, return memory_id."""
        pass

    @abstractmethod
    async def get_memories(
        self, session_id: str, memory_type: str | None = None, limit: int = 100
    ) -> list[BaseMemory]:
        """Retrieve memories for session."""
        pass

    @abstractmethod
    async def update_memory(self, memory_id: str, updates: dict) -> None:
        """Update memory fields."""
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        """Delete session and all memories."""
        pass
