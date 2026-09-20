"""``omicsclaw.mcp`` — tools that live in Model Context Protocol servers.

Reads a ``.mcp.json``, connects every server it names over stdio or
Streamable HTTP, and hands their tools over as ordinary
:class:`~omicsclaw.tools.MCPTool` objects::

    from omicsclaw.mcp import MCPManager, load_mcp_config

    manager = MCPManager(load_mcp_config(workspace / ".mcp.json"))
    await manager.start()                    # every server, concurrently
    registry = ToolRegistry([*foundation, *manager.tools()])
    ...
    await manager.aclose()

Once registered, an MCP tool is indistinguishable from a local one to the
engine. Inside the ``omicsclaw`` namespace this package imports only
``omicsclaw.tools`` (and through it ``omicsclaw.schema``) and
``omicsclaw.version``; everything else is the standard library.
"""

from .client import (
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    MCPClient,
    MCPToolError,
    RemoteTool,
    ServerInfo,
    render_result,
)
from .config import (
    MCPConfig,
    MCPConfigError,
    RejectedServer,
    ServerConfig,
    TransportKind,
    load_mcp_config,
    parse_mcp_config,
)
from .manager import (
    DEFAULT_CONNECT_TIMEOUT_S,
    DEFAULT_MAX_OUTPUT_CHARS,
    MCPManager,
    ServerState,
    ServerStatus,
    StatusListener,
    ToolDetail,
    open_transport,
    origin_of,
    truncate_output,
)
from .stdio import StdioTransport
from .streamable_http import HTTPTransport
from .transport import (
    MCPError,
    MCPProtocolError,
    MCPRemoteError,
    MCPTransportError,
    Transport,
)

__all__ = [
    "DEFAULT_CONNECT_TIMEOUT_S",
    "DEFAULT_MAX_OUTPUT_CHARS",
    "HTTPTransport",
    "MCPClient",
    "MCPConfig",
    "MCPConfigError",
    "MCPError",
    "MCPManager",
    "MCPProtocolError",
    "MCPRemoteError",
    "MCPToolError",
    "MCPTransportError",
    "PROTOCOL_VERSION",
    "RejectedServer",
    "RemoteTool",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "ServerConfig",
    "ServerInfo",
    "ServerState",
    "ServerStatus",
    "StatusListener",
    "StdioTransport",
    "ToolDetail",
    "Transport",
    "TransportKind",
    "load_mcp_config",
    "open_transport",
    "origin_of",
    "parse_mcp_config",
    "render_result",
    "truncate_output",
]
