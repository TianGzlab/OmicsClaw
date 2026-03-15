"""Test Phase 2 session management integration."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.memory import SQLiteBackend, SecureFieldEncryptor
from bot.core import SessionManager


async def test_session_integration():
    """Test session manager integration."""
    print("Testing Phase 2 session management...")

    # Create temporary database
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    try:
        # Initialize memory store
        key = b"0" * 32
        encryptor = SecureFieldEncryptor(key)
        store = SQLiteBackend(db_path, encryptor)
        await store.initialize()

        # Create session manager
        manager = SessionManager(store)

        # Test session creation
        session = await manager.get_or_create("user123", "telegram", "chat456")
        print(f"✓ Session created: {session.session_id}")

        # Test session retrieval
        session2 = await manager.get_or_create("user123", "telegram", "chat456")
        assert session.session_id == session2.session_id
        print(f"✓ Session retrieved: {session2.session_id}")

        # Test session deletion
        await store.delete_session(session.session_id)
        session3 = await store.get_session(session.session_id)
        assert session3 is None
        print("✓ Session deleted successfully")

        print("\n✅ Phase 2 integration test passed!")

    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    asyncio.run(test_session_integration())
