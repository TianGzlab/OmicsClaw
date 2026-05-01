"""Tests for the SSE compaction-event handler the desktop server wires up."""
from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock


def _stub_optional_modules() -> None:
    """server.py pulls in httpx via llm_timeout; stub for unit tests."""
    if "httpx" not in sys.modules:
        httpx_stub = types.ModuleType("httpx")

        class _StubHTTPError(Exception):
            pass

        httpx_stub.HTTPError = _StubHTTPError  # type: ignore[attr-defined]
        httpx_stub.ConnectError = _StubHTTPError  # type: ignore[attr-defined]
        httpx_stub.TimeoutException = _StubHTTPError  # type: ignore[attr-defined]
        httpx_stub.get = lambda *_, **__: None  # type: ignore[attr-defined]
        sys.modules["httpx"] = httpx_stub
    for stub_name in ("openai", "tiktoken", "fastapi"):
        if stub_name not in sys.modules:
            sys.modules[stub_name] = types.ModuleType(stub_name)


def test_handler_pushes_status_frame_to_queue() -> None:
    _stub_optional_modules()
    try:
        from omicsclaw.app._compaction_event_bridge import (
            make_compaction_event_handler,
        )
    except ImportError as exc:
        import pytest
        pytest.skip(f"server bridge unavailable: {exc}")

    from omicsclaw.runtime.context_compaction import CompactionEvent

    queue = MagicMock()
    handler = make_compaction_event_handler(queue)

    event = CompactionEvent(
        messages_compressed=7,
        tokens_saved_estimate=2100,
        applied_stages=("auto_compact",),
    )
    handler(event)

    queue.put_nowait.assert_called_once()
    frame = queue.put_nowait.call_args[0][0]
    assert frame["type"] == "status"
    payload = json.loads(frame["data"])
    assert payload["notification"] is True
    assert payload["subtype"] == "context_compressed"
    assert payload["stats"]["messagesCompressed"] == 7
    assert payload["stats"]["tokensSaved"] == 2100
    assert "7 older messages" in payload["message"]
    assert "~2,100 tokens" in payload["message"]
