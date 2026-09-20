"""``omicsclaw.tools`` — the hands the loop acts through.

Plan 0028, step 4 of the staged rebuild. Steps 1–3 delivered the
vocabulary (:mod:`omicsclaw.schema`), the interpreter that speaks it
(:mod:`omicsclaw.provider`) and the loop that moves it
(:mod:`omicsclaw.engine`). This package is what the loop dispatches to::

    from omicsclaw.tools import ToolRegistry

    registry = ToolRegistry()
    registry.register(InspectDataTool(workspace))
    defs = registry.available_tools()          # → provider
    result = await registry.execute(call)      # → Observation

:class:`~omicsclaw.tools.registry.ToolRegistry` satisfies
:class:`omicsclaw.engine.executor.ToolExecutor` **structurally**, without
importing :mod:`omicsclaw.engine`: the engine declared the smallest
Protocol that lets it act, and this package matches its shape. Nothing
here is wired into production — the existing tool layer under
``omicsclaw.runtime.tools`` still serves every surface, untouched, and
migrating its tools onto this one is a later step.

Two adapters mean most tools need no class of their own:
:class:`~omicsclaw.tools.function_tool.FunctionTool` wraps a plain
callable and turns a model's bad arguments into something it can correct,
and :class:`~omicsclaw.tools.mcp_tool.MCPTool` makes a tool that lives in
another process indistinguishable from one that lives here.

:mod:`omicsclaw.tools.context` is the third piece and the least obvious:
``execute(arguments)`` takes one argument on purpose, so a tool that has
to ask a human for permission, or say how far along it is, reaches its
caller through :mod:`contextvars` rather than through a widened seam. The
conventions — who binds, who reads, and what an unbound channel means —
are written down there because the mechanism works by a property of the
engine that nobody would otherwise know to preserve.

:mod:`omicsclaw.tools.builtin` holds the **foundation** tools:
``read_tool``, :class:`~omicsclaw.tools.builtin.write.WriteTool`,
:class:`~omicsclaw.tools.builtin.edit.EditTool` and
:class:`~omicsclaw.tools.builtin.bash.BashTool` (plan 0029 and its §12
follow-ups), plus
:class:`~omicsclaw.tools.builtin.web_fetch.WebFetchTool` and
:class:`~omicsclaw.tools.builtin.web_search.WebSearchTool` — the hands
the agent works with, not a starter set. The fifty tools under
``omicsclaw.runtime.tools`` are migrated later, one at a time.

The three file tools stand on this package's private helpers —
``_workspace.py``, the sandbox boundary every filesystem tool shares, and
``_pathlock.py``, the per-path lock that stops two writes from losing
each other wherever the engine's own barrier does not reach — overlapping
turns above all. The two web tools stand on ``_websafety.py``,
which is the same idea applied to a different boundary: an SSRF gate
every request passes, plus the pinned transport that is the only thing
allowed to open a socket. ``bash`` stands on none of them, because it has
no path to check and no destination to resolve; what bounds it is the
approval gate its policy declares. None of the six is wired into
production.

Plan 0028's three reference tools used to sit beside them, as evidence
that the pieces above hold up for a tool that really does something.
They were removed once the foundation tools carried every property they
were built to prove — see :mod:`omicsclaw.tools.builtin` for which
property moved where.

**A leaf layer.** Inside the ``omicsclaw`` namespace this package imports
``omicsclaw.schema`` and nothing else — not ``provider``, not ``engine``,
and not ``omicsclaw.runtime.tools``, which is the tempting one precisely
because it is also called ``tools``. Nothing about the package layout
prevents that import; ``tests/tools/test_tools_is_a_leaf_layer.py``
does, by walking the AST of every module here.
"""

from ._workspace import Workspace
from .base import ApprovalMode, RiskLevel, Tool, ToolPolicy
from .builtin import (
    BashTool,
    EditTool,
    WebFetchTool,
    WebSearchTool,
    WriteTool,
    read_tool,
)
from .context import (
    ApprovalChannel,
    ApprovalDecision,
    ApprovalDenied,
    ApprovalRequest,
    ApprovalUnavailable,
    ProgressSink,
    ProgressUpdate,
    TimeoutPause,
    ToolContext,
    context_value,
    current_context,
    effective_policy,
    pause_tool_timeout,
    report_progress,
    require_approval,
    reset_tool_context,
    set_tool_context,
    use_effective_policy,
    use_timeout_pause,
    use_tool_context,
)
from .function_tool import FunctionTool, ToolArgumentError
from .mcp_tool import MCPCaller, MCPTool, mcp_tool_name, sanitize_mcp_name
from .registry import (
    ToolAlreadyRegistered,
    ToolNameMismatch,
    ToolRegistrationError,
    ToolRegistry,
)

__all__ = [
    "ApprovalChannel",
    "ApprovalDecision",
    "ApprovalDenied",
    "ApprovalMode",
    "ApprovalRequest",
    "ApprovalUnavailable",
    "BashTool",
    "EditTool",
    "FunctionTool",
    "MCPCaller",
    "MCPTool",
    "ProgressSink",
    "ProgressUpdate",
    "RiskLevel",
    "TimeoutPause",
    "Tool",
    "ToolAlreadyRegistered",
    "ToolArgumentError",
    "ToolContext",
    "ToolNameMismatch",
    "ToolPolicy",
    "ToolRegistrationError",
    "ToolRegistry",
    "WebFetchTool",
    "WebSearchTool",
    "WriteTool",
    "context_value",
    "current_context",
    "effective_policy",
    "mcp_tool_name",
    "pause_tool_timeout",
    "read_tool",
    "report_progress",
    "require_approval",
    "reset_tool_context",
    "sanitize_mcp_name",
    "set_tool_context",
    "use_effective_policy",
    "use_timeout_pause",
    "use_tool_context",
]
