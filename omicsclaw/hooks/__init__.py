"""Interposition around a tool call: the seam, and the one hook nobody owned.

The gap this closes is an *extension point*. Everything this tree does
around a tool call today was written by the rebuild step that needed it —
the permission gate wraps a tool, the offloader edits the history during
compaction — and a deployment, a sub-agent or a future step wanting to
interpose anything has nowhere to put it. ``docs/plans/0031-entry-layer.md``
deferred the whole idea by name ("hooks：permission / danger / offload /
observability | 不做（Q13）") while ``entry/assembly.py`` reserved the
doorway: *"``tools`` is how hooks, permission wrappers, MCP tools and a
sub-agent's narrowed set all arrive later without this function
changing."* This package is what goes through it.

Usage — a chain, then the tools, then the gate::

    from omicsclaw.hooks import AuditHook, JsonlAuditSink, hook_tools

    hooks = (AuditHook(JsonlAuditSink(workspace / ".omicsclaw" / "audit.jsonl")),)
    registry = ToolRegistry(gate_tools(hook_tools(mounted, hooks), gate))

**Three of the reference harness's four hooks are not here, and that is
the design.** ``internal/hooks`` bundles the mechanism with four
policies; this tree already has homes for three of them, so only the
mechanism was missing:

=========================  ============================================
``hooks/hook.go``          this package — the interception seam
``permission/hook.go``     :mod:`omicsclaw.permission` (plan 0038)
``hooks/danger_hook.go``   :mod:`omicsclaw.permission` — ``DangerPatterns``
``hooks/offload.go``       :mod:`omicsclaw.context` — ``Offloader``
``hooks/plan_writer.go``   :mod:`omicsclaw.planning` — not a hook at all
``observability/hook.go``  :mod:`omicsclaw.hooks.audit` — the one left
=========================  ============================================

**One of those three is a narrowing rather than a full cover, and saying
so is the point of writing the table down.** ``context``'s ``Offloader``
moves the same bytes and writes the same kind of placeholder, but it is
driven by *budget pressure* during compaction, where ``hooks/offload.go``
runs unconditionally on every result over 10,000 characters; and it has
no equivalent of that hook's ``read_file``/``write_file``/``edit_file``
exclusion list. So a result that is large but not large enough to push
the conversation past ``Pressure.WARN`` is re-sent whole on every turn,
and a placeholder read back with ``read_file`` can be offloaded again.
Both are :mod:`omicsclaw.context`'s to decide, not this package's —
recorded here because the table would otherwise read as a claim that
nothing is missing.

Three decisions a reader should not have to re-derive:

**A hook decorates a tool, not the registry.** The reference wraps
``tools.Registry``; plan 0038 §2 rejected that for this tree and nothing
has changed. The engine probes the registry with :func:`isinstance` for
two optional Protocols, and a wrapper that forgets to forward one does
not fail — it silently charges a human's approval time to the tool's
timeout. See :class:`~omicsclaw.hooks.chain.HookedTool`.

**Hooks run inside the permission gate.** ``gate_tools(hook_tools(...))``,
in that order, matching the reference's chain order, where the permission
hook is first and the observability hook last
(``cmd/harness9/main.go:411-416`` — 413 alone builds the list, and the
appended ``obsHook`` is on 414-416). Permission therefore
decides before a hook is consulted, and a call a rule denied never
reaches one — the same blind spot the reference's observability hook has,
for the same reason.

**A hook cannot ask a human.** :mod:`omicsclaw.hooks.base` explains what
was dropped; this is why it can be. The gate publishes an ``AUTO``
policy before running the tool it settled, and
:func:`~omicsclaw.tools.require_approval` reads that first
(``tools/context.py:593-594``), so a question put from inside the chain
would answer itself. The behaviour is the reference's
``explicitlyAllowedContextKey`` reached by a mechanism that already
existed rather than by two more context keys — and it means "why was I
asked?" keeps exactly one answer, in the rule file.

Imports :mod:`omicsclaw.schema`, :mod:`omicsclaw.tools` and the standard
library. Not :mod:`omicsclaw.engine`, which is handed a registry and must
not learn that anything wraps a tool; not :mod:`omicsclaw.permission`,
which would make two leaves depend on each other for no gain — the gate
does not know about hooks either, and the composition root joins them in
one line. ``tests/hooks/test_hooks_is_a_leaf_layer.py`` is what enforces
it.
"""

from __future__ import annotations

from .audit import (
    SESSION_ID_KEY,
    AuditHook,
    AuditOutcome,
    AuditRecord,
    AuditSink,
    JsonlAuditSink,
    arguments_digest,
    outcome_of,
)
from .base import (
    Hook,
    HookAction,
    HookCall,
    HookDecision,
    HookDenied,
    ToolHook,
    allow,
    deny,
)
from .chain import HookedTool, hook_tools

__all__ = [
    "AuditHook",
    "AuditOutcome",
    "AuditRecord",
    "AuditSink",
    "Hook",
    "HookAction",
    "HookCall",
    "HookDecision",
    "HookDenied",
    "HookedTool",
    "JsonlAuditSink",
    "SESSION_ID_KEY",
    "ToolHook",
    "allow",
    "arguments_digest",
    "deny",
    "hook_tools",
    "outcome_of",
]
