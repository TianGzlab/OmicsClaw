"""The foundation tools: the hands the agent actually works with.

Plan 0029, then its §12 follow-ups. ``read_file``, ``write_file``,
``edit_file`` and ``bash`` are built on the sandbox boundary in
:mod:`omicsclaw.tools._workspace` and the path locks in
:mod:`omicsclaw.tools._pathlock`, and are modelled on the reference
harness's ``read_file.go`` / ``write_file.go`` / ``edit_file.go`` /
``bash.go``. Those four are the canonical set: it is what
``cmd/harness9/main.go:275-278`` mounts, and what the two other harnesses
plan 0029 appendix A compares against converge on independently.

``web_fetch`` and ``web_search`` join them (owner, 2026-09-18, reversing
plan 0029 §2's ruling against building them in this step). They stand on
a *second* boundary rather than the filesystem one —
:mod:`omicsclaw.tools._websafety`, the SSRF gate that is to the network
what ``_workspace.py`` is to the disk — and they share the HTML reduction
in :mod:`omicsclaw.tools._html`. Read ``_websafety.py``'s docstring
before mounting either: the gate stops this agent reaching *internal*
addresses, and it does **not** and cannot stop data leaving in a URL.
That second thing is what their ``ASK`` policy is for.

The four file tools each take a
:class:`~omicsclaw.tools._workspace.Workspace`, so there is no useful
zero-argument instance of one and no ``builtin_tools()`` helper here:
mounting a foundation tool is always a decision about *which* workspace,
and that decision belongs to whoever is assembling the registry. The two
web tools take no workspace — their boundary is a destination, not a
path — which is why they are constructed keyword-only.

``bash`` is the one with **no boundary argument at all**, and therefore
nothing for either helper to check — its only boundary is the approval
gate, until something implements its
:class:`~omicsclaw.tools.builtin.bash.BashEnvironment` seam.

**Two of these names collide with the legacy layer and two do not.**
``read_file`` / ``write_file`` / ``edit_file`` deliberately differ from
``file_read`` / ``file_write`` / ``file_edit`` so both layers can be
mounted while the migration runs; ``web_fetch`` and ``web_search`` are
spelled identically in ``runtime/tools/builders/engineering.py``, so
those two cannot be, and whoever migrates has to retire one side. Each
module's ``TOOL_NAME`` docstring says which case it is.

**Plan 0028's three reference tools used to live here** —
``inspect_analysis_environment``, ``analyze_sequence`` and
``save_gene_panel``. They existed to answer one question with code
rather than a claim: *does what the registry and the adapters provide
survive contact with a tool that really does something?* The foundation
tools answer it better, because they are the real thing rather than a
demonstration, so the three were removed (owner, 2026-09-18) once
``read_file`` / ``write_file`` / ``bash`` carried every property the
three were built to prove:

- a plain callable wrapped with no ceremony → ``read_tool()``;
- a correctable Observation for a truncated payload, a missing field or
  a wrong type, with the run surviving → ``read_file``'s decode and
  validation tests;
- the out-of-band convention of plan 0028 §4 Q4 under real engine
  concurrency → ``tests/tools/test_context.py``;
- an approval prompt faithful to the exact bytes the model sent, which
  :class:`~omicsclaw.tools.function_tool.FunctionTool` cannot give →
  ``write_file`` and ``bash``, both hand-written against
  :class:`~omicsclaw.tools.base.Tool`.

**Standard library only, and the constraint shaped these tools too.**
``omicsclaw/tools/`` may import ``omicsclaw.schema`` and nothing else
inside this namespace, which ``tests/tools/test_tools_is_a_leaf_layer.py``
enforces by walking every module under the package — this subpackage
included, from the moment its files exist.
"""

from .bash import BashTool
from .edit import EditTool
from .read import read_tool
from .web_fetch import WebFetchTool
from .web_search import WebSearchTool
from .write import WriteTool

__all__ = [
    "BashTool",
    "EditTool",
    "WebFetchTool",
    "WebSearchTool",
    "WriteTool",
    "read_tool",
]
