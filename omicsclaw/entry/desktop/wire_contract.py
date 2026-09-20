"""Versioned wire facts shared by the Desktop Surface and its clients.

This Module describes transport compatibility only.  Production
``/chat/stream`` is now a compatibility Adapter over the authoritative
ControlRuntime; explicit source request IDs are durably idempotent and separate
receipt/Event observation routes expose the canonical Turn.

Ported from ``omicsclaw/surfaces/desktop/wire_contract.py`` (plan 0031 §5.2,
task D2). **The eight ``*_SCHEMA_VERSION`` numbers and every descriptor body
are byte-identical to the source**, because an external client already depends
on them: changing one is migration coordination, not a backend rebuild step
(Q24). ``tests/entry/test_desktop_wire_contract.py`` pins that equality
against a literal copy of the pre-port descriptors.

**One import had to change, and the plan's "0 lines to change" is wrong
about why.** The source reads four bounds out of ``desktop/run_wire.py``,
which is a *relative* import and so never matched the plan's
``^(from|import) omicsclaw\\.(control|…)`` coupling scan — yet ``run_wire``
imports ``pydantic``, ``starlette``, the deleted ``omicsclaw.control`` and the
deleted ``omicsclaw.skill`` (singular, which plan 0031 §9-17 forbids from
``sys.modules`` outright). The four bounds are literals, so they are restated
below with their provenance rather than dragging two deleted packages into a
module whose whole job is to be importable.

The three non-chat descriptors describe routes this package does **not**
serve — ``/v1/turns``, ``/v1/runs`` and their observation seams belong to the
Run governance and attachment families plan 0031 §5.2 holds back. They are
kept because a descriptor is a statement about the *protocol*, and dropping
three of the four would hand the next reader a version table that has
silently forgotten what it is versioning. What is served here is named by
:data:`SERVED_PATHS`.
"""

from __future__ import annotations

from typing import Final

from ._chat_sse import CHAT_SSE_MAX_FRAME_BYTES, CHAT_SSE_QUEUE_MAX_ITEMS

# Restated from ``surfaces/desktop/run_wire.py:36-39`` — see the module
# docstring for why they are not imported from there.
DESKTOP_RUN_MAX_REQUEST_BYTES: Final = 64 * 1024
DESKTOP_RUN_MAX_JSON_NESTING: Final = 64
DESKTOP_RUN_READ_TIMEOUT_SECONDS: Final = 60
DESKTOP_RUN_INCIDENT_MAX_PAGE_SIZE: Final = 100


DESKTOP_CHAT_REQUEST_SCHEMA_VERSION: Final = 1
DESKTOP_CHAT_SSE_SCHEMA_VERSION: Final = 1
DESKTOP_CHAT_INTERRUPT_SCHEMA_VERSION: Final = 1
DESKTOP_TURN_SUBMISSION_SCHEMA_VERSION: Final = 1
DESKTOP_TURN_OBSERVATION_SCHEMA_VERSION: Final = 1
DESKTOP_RUN_REQUEST_SCHEMA_VERSION: Final = 1
DESKTOP_RUN_OBSERVATION_SCHEMA_VERSION: Final = 1
DESKTOP_RUN_INTEGRITY_INCIDENT_SCHEMA_VERSION: Final = 1


SERVED_PATHS: Final[tuple[str, ...]] = ("/chat/stream", "/health")
"""The two routes :func:`~omicsclaw.entry.desktop.server.create_desktop_app`
actually mounts.

Not part of the published contract — a fact about this port, so that
"``desktop_run_contract()`` exists" and "``/v1/runs`` answers" cannot be
confused for each other by anybody reading the descriptors above.
"""


def desktop_chat_contract() -> dict[str, int | bool]:
    """Return a fresh JSON-compatible Desktop chat contract descriptor."""

    return {
        "request_schema_version": DESKTOP_CHAT_REQUEST_SCHEMA_VERSION,
        "sse_schema_version": DESKTOP_CHAT_SSE_SCHEMA_VERSION,
        # V1 binds abort and owner cleanup to a fresh, per-submission
        # source_request_id.  A non-empty ID may be reused for transport retry
        # and resolves to the same durable Turn. Keep this version independent from
        # request/SSE framing: an older Backend can accept the same request
        # fields while still cancelling by session alone, which is not safe
        # for replacement streams.
        "interrupt_schema_version": DESKTOP_CHAT_INTERRUPT_SCHEMA_VERSION,
        "authoritative_ingress": True,
        "durable_ingress_idempotency": True,
        "source_request_id_required": True,
        "attachments_supported": False,
        "max_sse_frame_bytes": CHAT_SSE_MAX_FRAME_BYTES,
        "event_queue_capacity": CHAT_SSE_QUEUE_MAX_ITEMS,
        "producer_backpressure": True,
        "oversize_event_projection": True,
        "terminal_error_type_preserved": True,
    }


def desktop_turn_submission_contract() -> dict[str, int | bool | str]:
    """Describe the strict multipart subset implemented at ``/v1/turns``."""

    return {
        "request_schema_version": DESKTOP_TURN_SUBMISSION_SCHEMA_VERSION,
        "path": "/v1/turns",
        "multipart_supported": True,
        "json_supported": False,
        "attachments_supported": True,
        "file_references_supported": False,
        "legacy_json_files_supported": False,
        "project_commands_supported": False,
        "requested_options_supported": False,
        "retry_of_turn_supported": False,
        "explicit_conversation_supported": True,
        "idempotency_key_required": True,
        "declared_sha256_required": True,
        "max_attachments": 8,
        "max_attachment_bytes": 20 * 1024 * 1024,
        "max_batch_bytes": 50 * 1024 * 1024,
        "max_request_document_bytes": 2 * 1024 * 1024,
        "transport_overhead_allowance_bytes": 64 * 1024,
        "max_transport_bytes": 52 * 1024 * 1024 + 64 * 1024,
        "max_active_multipart_requests": 2,
        "max_inflight_transport_bytes": 2 * (52 * 1024 * 1024 + 64 * 1024),
        "multipart_read_timeout_seconds": 60,
    }


def desktop_turn_observation_contract() -> dict[str, int | bool | str]:
    """Describe the independent Receipt/Event/cancel V1 observation seam."""

    return {
        "schema_version": DESKTOP_TURN_OBSERVATION_SCHEMA_VERSION,
        "receipt_path": "/v1/turns/{turn_id}",
        "events_path": "/v1/turns/{turn_id}/events",
        "cancel_path": "/v1/turns/{turn_id}/cancel",
        "snapshot_first": True,
        "event_sequence_starts_at": 1,
        "typed_sse_events": True,
        "last_event_id_replay": True,
        "gap_follows_live": True,
        "durable_event_log": False,
        "interaction_resolution_supported": False,
    }


def desktop_run_contract() -> dict[str, int | bool | str]:
    """Describe the bounded canonical Simple Skill Run tracer."""

    return {
        "request_schema_version": DESKTOP_RUN_REQUEST_SCHEMA_VERSION,
        "observation_schema_version": DESKTOP_RUN_OBSERVATION_SCHEMA_VERSION,
        "submission_path": "/v1/runs",
        "receipt_path": "/v1/runs/{run_id}",
        "cancel_path": "/v1/runs/{run_id}/cancel",
        "replay_path": "/v1/runs/{run_id}/replay",
        "integrity_incident_observation_schema_version": (
            DESKTOP_RUN_INTEGRITY_INCIDENT_SCHEMA_VERSION
        ),
        "integrity_incident_list_path": "/v1/run-integrity-incidents",
        "max_integrity_incident_page_size": DESKTOP_RUN_INCIDENT_MAX_PAGE_SIZE,
        "integrity_incident_detail_supported": False,
        "integrity_incident_observation_starts_work": False,
        "simple_skill_supported": True,
        "demo_input_only": True,
        "parameters_supported": False,
        "resource_contract_required": True,
        "idempotency_key_required": True,
        "max_request_bytes": DESKTOP_RUN_MAX_REQUEST_BYTES,
        "max_json_nesting": DESKTOP_RUN_MAX_JSON_NESTING,
        "request_read_timeout_seconds": DESKTOP_RUN_READ_TIMEOUT_SECONDS,
        "events_supported": False,
        "observation_starts_work": False,
        "replay_uses_source_run_id": True,
        "replay_exposes_local_paths": False,
    }


__all__ = [
    "DESKTOP_CHAT_REQUEST_SCHEMA_VERSION",
    "DESKTOP_CHAT_SSE_SCHEMA_VERSION",
    "DESKTOP_CHAT_INTERRUPT_SCHEMA_VERSION",
    "DESKTOP_TURN_SUBMISSION_SCHEMA_VERSION",
    "DESKTOP_TURN_OBSERVATION_SCHEMA_VERSION",
    "DESKTOP_RUN_OBSERVATION_SCHEMA_VERSION",
    "DESKTOP_RUN_INTEGRITY_INCIDENT_SCHEMA_VERSION",
    "DESKTOP_RUN_REQUEST_SCHEMA_VERSION",
    "SERVED_PATHS",
    "desktop_chat_contract",
    "desktop_run_contract",
    "desktop_turn_observation_contract",
    "desktop_turn_submission_contract",
]
