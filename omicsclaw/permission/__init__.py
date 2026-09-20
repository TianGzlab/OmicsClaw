"""Human-in-the-Loop permission control: whether a tool call happens at all.

Decides between the engine dispatching a call and the tool doing its work.
*How* a person is asked belongs elsewhere —
:func:`omicsclaw.tools.require_approval` puts the question and fails closed,
:class:`omicsclaw.entry.ApprovalBroker` carries it to a surface — and this
package does not touch either.

Three inputs, resolved in one pass by :class:`PermissionGate`:

- :class:`PermissionMode`, the session's posture;
- :class:`Rules`, a rule file matching on tool name *and* arguments;
- :class:`DangerPatterns`, built-in shell patterns worth a second look.

Usage: build a gate, wrap the tools, hand the registry to the engine::

    from omicsclaw.permission import PermissionGate, RuleStore, gate_tools

    gate = PermissionGate(
        mode=config.permission_mode,
        rules=RuleStore(workspace / ".omicsclaw" / "settings.json"),
    )
    registry = ToolRegistry(gate_tools(foundation_tools(config), gate))

Imports :mod:`omicsclaw.schema`, :mod:`omicsclaw.tools` and the standard
library, and nothing else in the ``omicsclaw`` namespace. In particular not
:mod:`omicsclaw.engine`, which is handed a registry and never learns anything
was gated, and not :mod:`omicsclaw.entry` — a gate is built from three
arguments, so a sub-agent, a benchmark runner or a test needs no ``AppConfig``
to make one.
"""

from __future__ import annotations

from .danger import (
    COMMAND_ARGUMENT,
    DEFAULT_DANGER_PATTERNS,
    DangerPattern,
    DangerPatterns,
)
from .gate import (
    DecisionSource,
    GatedTool,
    PermissionDenied,
    PermissionGate,
    Resolution,
    gate_tools,
)
from .modes import PermissionMode
from .rules import (
    CONFIG_KEY,
    PermissionConfigError,
    Rule,
    Rules,
    RuleStore,
    Verdict,
    literal_pattern,
    load_rules,
    principal_argument,
    principal_key,
    save_rules,
)

__all__ = [
    "COMMAND_ARGUMENT",
    "CONFIG_KEY",
    "DEFAULT_DANGER_PATTERNS",
    "DangerPattern",
    "DangerPatterns",
    "DecisionSource",
    "GatedTool",
    "PermissionConfigError",
    "PermissionDenied",
    "PermissionGate",
    "PermissionMode",
    "Resolution",
    "Rule",
    "RuleStore",
    "Rules",
    "Verdict",
    "gate_tools",
    "literal_pattern",
    "load_rules",
    "principal_argument",
    "principal_key",
    "save_rules",
]
