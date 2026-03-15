"""Test Phase 3 memory context injection."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.memory import SQLiteBackend, SecureFieldEncryptor
from bot.memory.models import DatasetMemory, AnalysisMemory, PreferenceMemory
from bot.core import SessionManager


async def test_memory_context_injection():
    """Test memory context loading and formatting."""
    print("Testing Phase 3 memory context injection...")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    try:
        # Initialize
        key = b"0" * 32
        encryptor = SecureFieldEncryptor(key)
        store = SQLiteBackend(db_path, encryptor)
        await store.initialize()
        manager = SessionManager(store)

        # Create session
        session = await manager.get_or_create("user123", "telegram", "chat456")
        print(f"✓ Session created: {session.session_id}")

        # Add dataset memory
        dataset = DatasetMemory(
            file_path="data/brain_visium.h5ad",
            platform="Visium",
            n_obs=3000,
            n_vars=2000,
            preprocessing_state="clustered"
        )
        await store.save_memory(session.session_id, dataset)
        print("✓ Dataset memory saved")

        # Add analysis memory
        analysis = AnalysisMemory(
            source_dataset_id=dataset.memory_id,
            skill="spatial-preprocessing",
            method="leiden",
            parameters={"resolution": 0.8},
            status="completed"
        )
        await store.save_memory(session.session_id, analysis)
        print("✓ Analysis memory saved")

        # Add preference memory
        pref = PreferenceMemory(
            domain="spatial-genes",
            key="svg_method",
            value="SPARK-X"
        )
        await store.save_memory(session.session_id, pref)
        print("✓ Preference memory saved")

        # Load context
        context = await manager.load_context(session.session_id)
        print(f"\n✓ Memory context loaded ({len(context)} chars):")
        print("---")
        print(context)
        print("---")

        # Verify context contains expected information
        assert "brain_visium.h5ad" in context
        assert "Visium" in context
        assert "spatial-preprocessing" in context
        assert "SPARK-X" in context
        print("\n✅ Phase 3 integration test passed!")

    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    asyncio.run(test_memory_context_injection())
