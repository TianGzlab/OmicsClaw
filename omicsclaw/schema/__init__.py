"""``omicsclaw.schema`` — the system's unified blood.

Per ADR 0077. The single vocabulary in which the Main Loop, the model
adapter, the tool layer, and the memory layer talk to each other.

    from omicsclaw.schema import Message, Role, ToolCall, ToolResult

Defined before the Main Loop because the loop body *is* the movement of
these types — ``Message → ToolCall → ToolResult → Message``. There is no
loop to write until they exist.

**Leaf package.** Standard library only — no ``omicsclaw`` imports, no
third-party dependency, no I/O, no logging. Every component depends on it
and it depends on none, which is what keeps the dependency graph acyclic.

**Vendor-neutral.** Nothing here mirrors any vendor's payload shape.
Translating OpenAI / Anthropic / DeepSeek / Ollama formats into and out
of these types belongs to the model adapter layer. A vendor field name
appearing in this package is a bug.
"""

from .message import (
    Message,
    Role,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)
from .stream import StreamChunk, StreamChunkType

__all__ = [
    "Message",
    "Role",
    "StreamChunk",
    "StreamChunkType",
    "ToolCall",
    "ToolDefinition",
    "ToolResult",
    "Usage",
]
