"""``omicsclaw.entry.desktop`` — the Desktop Surface's HTTP routes.

The client on the other side is a **separate project**, ``OmicsClaw-App``
(Electron + Next.js), whose server-side proxy forwards to this backend.
The backend defines the wire contract and versions it
(:mod:`~omicsclaw.entry.desktop.wire_contract`); the client implements the
version ``GET /health`` publishes.

Routes: ``POST /chat/stream``, ``POST /chat/permission``,
``POST /chat/abort``, ``POST /chat/session-permission-profile``,
``GET``/``PUT /workspace``, ``GET /env/doctor``, ``GET``/``HEAD
/health``, and the management routes ``GET /skills``,
``GET /skills/{domain}/{name}``, ``GET /mcp/servers``,
``GET``/``PUT /providers``, ``POST /providers/test`` and
``POST /chat/title``, and the read-only file routes ``GET /files/tree`` and
``GET /files/serve``
(:data:`~omicsclaw.entry.desktop.wire_contract.SERVED_PATHS`).

:class:`~omicsclaw.entry.desktop.providers.DotenvSettings` is the
deployment's ``.env`` as ``create_desktop_app(settings=...)`` takes it;
the process shell builds it.

**Importing this package never imports a web framework.** ``fastapi`` is
imported inside :func:`~omicsclaw.entry.desktop.server.create_desktop_app`,
so the wire contract, the request bounds and the frame projection are all
readable and testable where no server is installed.
"""

from __future__ import annotations

from ._chat_sse import (
    CHAT_SSE_MAX_FRAME_BYTES,
    CHAT_SSE_QUEUE_MAX_ITEMS,
    render_chat_sse_frame,
    utf8_size,
)
from .catalog import mcp_servers, skill_catalog, skill_detail
from .doctor import doctor_report, effective_model
from .files import (
    FILES_SERVE_MAX_BYTES,
    FILES_TREE_MAX_NODES,
    file_tree,
    resolve_in_workspace,
    serve_target,
)
from .interactions import (
    DesktopInteractions,
    PendingApproval,
    abort_chat,
    answer_permission,
    change_permission_profile,
)
from .providers import (
    DotenvSettings,
    SettingsFile,
    provider_listing,
    provider_settings_updates,
    save_provider,
)
from .server import (
    BACKEND_PROCESS_EPOCH,
    ChatStream,
    change_workspace,
    create_desktop_app,
    health_payload,
    is_json_media_type,
    open_chat_stream,
    workspace_payload,
)
from .title import generate_title
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
    SERVED_PATHS,
    desktop_chat_contract,
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
    "FILES_SERVE_MAX_BYTES",
    "FILES_TREE_MAX_NODES",
    "KEEPALIVE_INTERVAL_S",
    "SERVED_PATHS",
    "ChatStream",
    "ChatStreamRequest",
    "DesktopChatSSEBody",
    "DesktopIngressError",
    "DesktopInteractions",
    "DotenvSettings",
    "PendingApproval",
    "SettingsFile",
    "abort_chat",
    "answer_permission",
    "change_permission_profile",
    "change_workspace",
    "create_desktop_app",
    "decode_chat_stream_request",
    "desktop_chat_contract",
    "desktop_chat_frame",
    "desktop_terminal_frames",
    "doctor_report",
    "effective_model",
    "file_tree",
    "generate_title",
    "health_payload",
    "is_json_media_type",
    "mcp_servers",
    "open_chat_stream",
    "parse_chat_stream_document",
    "provider_listing",
    "provider_settings_updates",
    "render_chat_sse_frame",
    "resolve_in_workspace",
    "save_provider",
    "serve_target",
    "skill_catalog",
    "skill_detail",
    "utf8_size",
    "workspace_payload",
]
