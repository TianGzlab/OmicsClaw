"""``omicsclaw.entry.desktop`` — the Desktop Surface's two HTTP routes.

Plan 0031 task D2. The client on the other side of this package is a
**separate project**: ``OmicsClaw-App`` (Electron + Next.js), whose
``src/app/api/chat/route.ts`` describes itself as a Transform Proxy and says
so in its own comment — "Forward to Python backend
(127.0.0.1:8765/chat/stream)". This package is that contract's
*implementation*, not its author (Q24), which is why
:mod:`~omicsclaw.entry.desktop.wire_contract` is carried across with its
eight schema versions untouched and why no frame name is minted here that
the client does not already parse.

Two routes, and only two: ``POST /chat/stream`` and ``GET /health``. Skills,
providers, MCP, outputs, the bridge, the memory proxy and the Run governance
routes stay in ``omicsclaw/surfaces/desktop/server.py`` until the steps they
belong to arrive (plan 0031 §5.2).

**Importing this package never imports a web framework.** ``fastapi`` is
imported inside :func:`~omicsclaw.entry.desktop.server.create_desktop_app`,
so the wire contract, the request bounds and the frame projection are all
readable and testable where no server is installed — which is this
repository's own environment (plan 0031 trap 13).
"""

from __future__ import annotations

from ._chat_sse import (
    CHAT_SSE_MAX_FRAME_BYTES,
    CHAT_SSE_QUEUE_MAX_ITEMS,
    render_chat_sse_frame,
    utf8_size,
)
from .server import (
    BACKEND_PROCESS_EPOCH,
    ChatStream,
    create_desktop_app,
    health_payload,
    open_chat_stream,
)
from .turn_observation import (
    KEEPALIVE_INTERVAL_S,
    DesktopChatSSEBody,
    desktop_chat_frame,
    desktop_terminal_frames,
)
from .turn_submission import (
    DEFAULT_MAX_JSON_NESTING,
    DEFAULT_MAX_REQUEST_BYTES,
    ChatStreamRequest,
    DesktopIngressError,
    decode_chat_stream_request,
    parse_chat_stream_document,
)
from .wire_contract import (
    DESKTOP_CHAT_INTERRUPT_SCHEMA_VERSION,
    DESKTOP_CHAT_REQUEST_SCHEMA_VERSION,
    DESKTOP_CHAT_SSE_SCHEMA_VERSION,
    DESKTOP_RUN_INTEGRITY_INCIDENT_SCHEMA_VERSION,
    DESKTOP_RUN_OBSERVATION_SCHEMA_VERSION,
    DESKTOP_RUN_REQUEST_SCHEMA_VERSION,
    DESKTOP_TURN_OBSERVATION_SCHEMA_VERSION,
    DESKTOP_TURN_SUBMISSION_SCHEMA_VERSION,
    SERVED_PATHS,
    desktop_chat_contract,
    desktop_run_contract,
    desktop_turn_observation_contract,
    desktop_turn_submission_contract,
)

__all__ = [
    "BACKEND_PROCESS_EPOCH",
    "CHAT_SSE_MAX_FRAME_BYTES",
    "CHAT_SSE_QUEUE_MAX_ITEMS",
    "DEFAULT_MAX_JSON_NESTING",
    "DEFAULT_MAX_REQUEST_BYTES",
    "DESKTOP_CHAT_INTERRUPT_SCHEMA_VERSION",
    "DESKTOP_CHAT_REQUEST_SCHEMA_VERSION",
    "DESKTOP_CHAT_SSE_SCHEMA_VERSION",
    "DESKTOP_RUN_INTEGRITY_INCIDENT_SCHEMA_VERSION",
    "DESKTOP_RUN_OBSERVATION_SCHEMA_VERSION",
    "DESKTOP_RUN_REQUEST_SCHEMA_VERSION",
    "DESKTOP_TURN_OBSERVATION_SCHEMA_VERSION",
    "DESKTOP_TURN_SUBMISSION_SCHEMA_VERSION",
    "KEEPALIVE_INTERVAL_S",
    "SERVED_PATHS",
    "ChatStream",
    "ChatStreamRequest",
    "DesktopChatSSEBody",
    "DesktopIngressError",
    "create_desktop_app",
    "decode_chat_stream_request",
    "desktop_chat_contract",
    "desktop_chat_frame",
    "desktop_run_contract",
    "desktop_terminal_frames",
    "desktop_turn_observation_contract",
    "desktop_turn_submission_contract",
    "health_payload",
    "open_chat_stream",
    "parse_chat_stream_document",
    "render_chat_sse_frame",
    "utf8_size",
]
