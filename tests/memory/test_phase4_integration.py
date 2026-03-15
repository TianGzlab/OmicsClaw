"""Test Phase 4 automatic memory capture."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.memory import SQLiteBackend, SecureFieldEncryptor
from bot.core import SessionManager, _auto_capture_analysis


async def test_auto_capture():
    """Test automatic memory capture after skill execution."""
    print("Testing Phase 4 automatic memory capture...")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    try:
        # Initialize
        key = b"0" * 32
        encryptor = SecureFieldEncryptor(key)
        store = SQLiteBackend(db_path, encryptor)
        await store.initialize()

        # Set global memory_store for auto-capture
        import bot.core as core
        core.memory_store = store
        core.session_manager = SessionManager(store)

        # Create session
        session = await core.session_manager.get_or_create("user123", "telegram", "chat456")
        print(f"✓ Session created: {session.session_id}")

        # Simulate skill execution with auto-capture
        args = {
            "skill": "spatial-preprocessing",
            "method": "leiden",
            "file_path": "data/test.h5ad"
        }
        output_dir = Path("/tmp/test_output")

        await _auto_capture_analysis(session.session_id, "spatial-preprocessing", args, output_dir, True)
        print("✓ Auto-capture executed")

        # Verify memory was saved
        memories = await store.get_memories(session.session_id, "analysis")
        assert len(memories) == 1
        assert memories[0].skill == "spatial-preprocessing"
        assert memories[0].method == "leiden"
        assert memories[0].status == "completed"
        print(f"✓ Analysis memory captured: {memories[0].skill} ({memories[0].method})")

        print("\n✅ Phase 4 integration test passed!")

    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    asyncio.run(test_auto_capture())
