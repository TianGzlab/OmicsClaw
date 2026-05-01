"""Tests for the SSE compaction-status payload helper."""
from __future__ import annotations

from omicsclaw.runtime.context_compaction import (
    CompactionEvent,
    build_compaction_status_payload,
)


def test_event_dataclass_round_trip():
    event = CompactionEvent(
        messages_compressed=12,
        tokens_saved_estimate=3400,
        applied_stages=("auto_compact",),
    )
    assert event.messages_compressed == 12
    assert event.tokens_saved_estimate == 3400
    assert event.applied_stages == ("auto_compact",)


def test_payload_with_tokens_saved():
    event = CompactionEvent(
        messages_compressed=12,
        tokens_saved_estimate=3400,
        applied_stages=("auto_compact",),
    )
    payload = build_compaction_status_payload(event)
    assert payload == {
        "notification": True,
        "subtype": "context_compressed",
        "message": (
            "Context compressed: 12 older messages summarized, "
            "~3,400 tokens saved"
        ),
        "stats": {"messagesCompressed": 12, "tokensSaved": 3400},
    }


def test_payload_without_tokens_saved_omits_token_clause():
    event = CompactionEvent(
        messages_compressed=4,
        tokens_saved_estimate=0,
        applied_stages=("snip_compact",),
    )
    payload = build_compaction_status_payload(event)
    assert payload["message"] == "Context compressed: 4 older messages summarized"
    assert payload["stats"]["tokensSaved"] == 0


def test_payload_subtype_is_stable_constant():
    """Frontend dispatch keys on this exact string — must not drift."""
    event = CompactionEvent(messages_compressed=1, tokens_saved_estimate=1, applied_stages=())
    assert build_compaction_status_payload(event)["subtype"] == "context_compressed"
