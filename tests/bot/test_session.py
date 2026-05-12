"""Unit tests for ``bot.session`` — SessionManager + LRU eviction.

The module owns chat-session state plus the ``init()`` lifecycle that
binds the LLM client and provider config onto ``bot.core``'s globals.
These tests drive the SessionManager and the LRU eviction in isolation —
``init()`` itself is exercised through the existing ``tests/test_oauth_
regressions.py`` and ``tests/test_bot_core_timeout.py`` files (the
backward-compat regression net), so we don't duplicate that here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


@pytest.fixture
def fake_store():
    """Minimal store stub matching the SessionManager contract."""

    class _FakeStore:
        def __init__(self):
            self.sessions: dict[str, dict] = {}
            self.calls: list[tuple[str, tuple, dict]] = []

        async def get_session(self, session_id):
            self.calls.append(("get_session", (session_id,), {}))
            return self.sessions.get(session_id)

        async def create_session(self, user_id, platform, chat_id, *, session_id):
            self.calls.append(
                ("create_session", (user_id, platform, chat_id), {"session_id": session_id})
            )
            self.sessions[session_id] = {
                "user_id": user_id,
                "platform": platform,
                "chat_id": chat_id,
                "session_id": session_id,
                "created_at": datetime.now(timezone.utc),
            }
            return self.sessions[session_id]

        async def update_session(self, session_id, fields):
            self.calls.append(("update_session", (session_id,), fields))
            self.sessions[session_id].update(fields)
            return self.sessions[session_id]

        async def get_memories(self, session_id, kind, *, limit):
            self.calls.append(("get_memories", (session_id, kind), {"limit": limit}))
            return []

    return _FakeStore()


@pytest.mark.asyncio
async def test_session_manager_creates_session_when_missing(fake_store):
    """First call for a (platform, user, chat) triple constructs the session."""
    from bot.session import SessionManager

    mgr = SessionManager(fake_store)
    session = await mgr.get_or_create("alice", "telegram", "12345")

    assert session["user_id"] == "alice"
    assert session["session_id"] == "telegram:alice:12345"
    create_calls = [c for c in fake_store.calls if c[0] == "create_session"]
    assert len(create_calls) == 1


@pytest.mark.asyncio
async def test_session_manager_updates_existing_session(fake_store):
    """Second call for the same triple touches last_activity instead of
    re-creating — preserves session state across reconnects."""
    from bot.session import SessionManager

    mgr = SessionManager(fake_store)
    await mgr.get_or_create("bob", "feishu", "777")
    fake_store.calls.clear()

    await mgr.get_or_create("bob", "feishu", "777")

    update_calls = [c for c in fake_store.calls if c[0] == "update_session"]
    create_calls = [c for c in fake_store.calls if c[0] == "create_session"]
    assert len(update_calls) == 1
    assert len(create_calls) == 0
    assert "last_activity" in update_calls[0][2]


@pytest.mark.asyncio
async def test_session_manager_load_context_returns_empty_when_no_memories(fake_store):
    """No stored memories → empty string (chat surface omits the context block)."""
    from bot.session import SessionManager

    mgr = SessionManager(fake_store)
    await mgr.get_or_create("carol", "slack", "abc")

    ctx = await mgr.load_context("slack:carol:abc")

    assert ctx == ""


@pytest.mark.asyncio
async def test_session_manager_load_context_renders_dataset_block(fake_store):
    """A dataset memory surfaces as the labelled "Current Dataset" block."""
    from bot.session import SessionManager

    fake_store.get_memories = _make_get_memories({
        "dataset": [SimpleNamespace(
            file_path="/tmp/sample.h5ad",
            platform="visium",
            n_obs=4321,
            n_vars=2000,
            preprocessing_state="raw",
        )],
    })

    mgr = SessionManager(fake_store)
    ctx = await mgr.load_context("anywhere")

    assert "**Current Dataset**" in ctx
    assert "/tmp/sample.h5ad" in ctx
    assert "visium" in ctx
    assert "4321" in ctx
    assert "preprocessed=raw" in ctx


@pytest.mark.asyncio
async def test_session_manager_load_context_swallows_per_kind_errors(fake_store):
    """A failing dataset fetch must not block analyses / preferences from
    rendering — each ``get_memories`` call is wrapped individually in the
    production loader, so this test pins that behaviour."""
    from bot.session import SessionManager

    async def _flaky_get_memories(session_id, kind, *, limit):
        if kind == "dataset":
            raise RuntimeError("decryption failed")
        if kind == "preference":
            return [SimpleNamespace(key="theme", value="dark")]
        return []

    fake_store.get_memories = _flaky_get_memories

    mgr = SessionManager(fake_store)
    ctx = await mgr.load_context("anywhere")

    assert "**User Preferences**" in ctx
    assert "theme: dark" in ctx
    assert "**Current Dataset**" not in ctx


def test_received_files_is_module_dict():
    """``bot.session.received_files`` is the canonical dict; ``bot.core``
    re-exports it. ``omicsclaw/app/_attachments.py`` reads via
    ``bot.core.received_files`` — both paths must point at the same object."""
    import bot.core
    import bot.session

    assert bot.core.received_files is bot.session.received_files
    bot.session.received_files["sentinel"] = {"chat_id": "test"}
    try:
        assert bot.core.received_files["sentinel"]["chat_id"] == "test"
    finally:
        bot.session.received_files.pop("sentinel", None)


def test_evict_lru_conversations_clears_tool_results_for_evicted_chats(monkeypatch):
    """When the transcript store evicts a stale chat_id,
    ``_evict_lru_conversations`` must call ``tool_result_store.clear(chat_id)``
    for every evicted id — otherwise tool result blobs leak. Drives the
    function with stand-in stores (no real disk / state)."""
    cleared: list = []

    fake_transcript_store = SimpleNamespace(
        max_conversations=0,
        evict_lru_conversations=lambda: ["chat-1", "chat-2"],
    )
    fake_tool_result_store = SimpleNamespace(
        clear=lambda chat_id: cleared.append(chat_id),
    )

    import bot.core as _core
    monkeypatch.setattr(_core, "transcript_store", fake_transcript_store, raising=False)
    monkeypatch.setattr(_core, "tool_result_store", fake_tool_result_store, raising=False)
    monkeypatch.setattr(_core, "MAX_CONVERSATIONS", 50, raising=False)

    from bot.session import _evict_lru_conversations

    _evict_lru_conversations()

    assert cleared == ["chat-1", "chat-2"]
    assert fake_transcript_store.max_conversations == 50


def _make_get_memories(by_kind: dict[str, list]):
    async def _impl(session_id, kind, *, limit):
        return by_kind.get(kind, [])
    return _impl
