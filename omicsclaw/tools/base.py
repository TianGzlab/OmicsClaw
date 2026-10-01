"""``omicsclaw/tools`` — what a tool *is*, and what may be said about one.

Plan 0028 §2. Steps 1–3 gave the system a vocabulary
(:mod:`omicsclaw.schema`), an interpreter that speaks it
(:mod:`omicsclaw.provider`) and a loop that moves it
(:mod:`omicsclaw.engine`). This module answers the question that layer
deliberately left open: what does the loop's :class:`ToolExecutor` seam
actually dispatch *to*?

**A tool is one object.** Its name, the schema the model is shown, and
the code that runs are three faces of a single thing, so they live
together. The arrangement being replaced splits them across a metadata
record, a separate ``dict[str, Callable]``, and a string key matched at
start-up — under which "what does this tool do" has no single place that
answers it, and a parameter change has to be made twice with nothing
checking that both were made.

**Two vocabularies, deliberately not one.**
:class:`~omicsclaw.schema.ToolDefinition` is what a *model* is told;
:class:`ToolPolicy` is what this *machine* is allowed to do. They are
separate types because they have separate destinations: the first is
serialized into a prompt, the second must never be. Keeping policy off
:class:`Tool` entirely means there is nowhere for it to leak from — the
same argument :class:`~omicsclaw.engine.executor.ToolExecutor` makes for
its own two-method surface.

**Leaf-adjacent.** ``omicsclaw.schema`` and the standard library. Nothing
else in the ``omicsclaw`` namespace — not ``provider``, not ``engine``,
and above all not ``omicsclaw.runtime.tools``, the legacy layer this one
is built to replace. ``tests/tools/test_tools_is_a_leaf_layer.py`` is the
only thing enforcing that, so it is enforced by test rather than implied
by a package name.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from omicsclaw.schema import ToolDefinition


@runtime_checkable
class Tool(Protocol):
    """One tool: its own name, its own description, its own execution.

    A :class:`~typing.Protocol`, not a base class, for the reason
    :class:`~omicsclaw.provider.base.LLMProvider` and
    :class:`~omicsclaw.engine.executor.ToolExecutor` are Protocols:
    satisfying it is a matter of shape, so a test double is a dozen lines
    that import nothing from here, and a future adapter — a wrapped
    callable, a proxied MCP tool — is not forced to inherit anything.

    ``runtime_checkable`` makes ``isinstance`` work for conformance
    tests. Note what that check can and cannot see: it verifies the three
    members exist, not their signatures and not that ``execute`` is a
    coroutine function. Shape is checked by the type checker; the
    registry only awaits what it is handed.

    **Policy is absent on purpose.** Risk level and approval mode are not
    part of being a tool; see :class:`ToolPolicy`. An implementation
    *may* carry a ``policy`` attribute as its own default, and the
    registry will read it, but nothing requires one and it is not part of
    this Protocol — so a tool that omits it is still a tool.
    """

    @property
    def name(self) -> str:
        """The identifier the model calls this tool by.

        Must equal ``definition().name``. Two independent sources for one
        identity is a latent bug — a registry keyed on one while the
        model is shown the other routes every call to nothing — so
        :meth:`~omicsclaw.tools.registry.ToolRegistry.register` checks
        the two agree and refuses the tool if they do not.
        """
        ...

    def definition(self) -> ToolDefinition:
        """What the model is told: name, description, argument schema.

        A method rather than a stored attribute so a tool whose schema
        depends on its construction — an MCP proxy, a skill wrapper —
        needs no extra machinery to express that.
        """
        ...

    async def execute(self, arguments: str) -> str:
        """Run this tool and return the text the model will read.

        ``arguments`` is the **raw JSON payload**, unparsed, exactly as
        :attr:`~omicsclaw.schema.ToolCall.arguments` carries it. Parsing
        is this tool's business, not the loop's: the byte-exact payload is
        what prompt-prefix caching and replay evidence depend on, and a
        decode-then-re-encode can reorder keys and silently change it.
        Adapters that prefer a validated ``dict`` do that decoding inside
        themselves, so the convenience is available without the seam
        having to carry it.

        The whole :class:`~omicsclaw.schema.ToolCall` is **not** passed.
        A tool has no business knowing ``call.id``; handing it over is how
        one acquires a dependency on a field whose value no layer
        guarantees.

        Failure is reported by raising. The registry turns an exception
        into an ``is_error`` Observation so the model can read what went
        wrong and correct it, which is where that translation belongs —
        a tool written for this interface does not have to know the
        result type exists.
        """
        ...


class RiskLevel(StrEnum):
    """How much damage running this tool can do.

    A :class:`~enum.StrEnum`, so ``RiskLevel.LOW == "low"`` holds and the
    values stay byte-compatible with the strings the existing tool layer
    already persists in approval records.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ApprovalMode(StrEnum):
    """Whether a human has to say yes before this tool runs."""

    AUTO = "auto"
    """Runs without asking."""

    ASK = "ask"
    """Requires an approval decision from whoever owns the session."""

    DENY_UNLESS_TRUSTED = "deny_unless_trusted"
    """Refused outright unless the calling context is a trusted one."""


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """Local execution policy for one tool. **Never enters a prompt.**

    Carried beside a tool rather than on it, and never inside
    :class:`~omicsclaw.schema.ToolDefinition`, because these fields
    describe what *this machine* will permit — not what the model needs
    to know to call something. A model shown its own approval rules is a
    model invited to argue with them.

    **``ToolPolicy()`` describes a tool that declared nothing, and a tool
    that declared nothing is not evidence of a safe tool.** The fields
    split into two kinds, and the split decides the defaults:

    *Permissions* — :attr:`risk_level`, :attr:`approval_mode`,
    :attr:`concurrency_safe`, :attr:`allowed_in_background` — answer
    "what may this be allowed to do". Each defaults to the guarded value,
    so the cost of a forgotten declaration is a prompt rather than a
    silent grant. A tool that really is cheap and harmless says so in one
    line, and only the tool's author can know that.

    *Claims* — :attr:`read_only`, :attr:`writes_workspace`,
    :attr:`writes_config`, :attr:`touches_network` — are assertions about
    effects, and default to the absence of an assertion. **A gate must
    not grant anything on the strength of a ``False`` nobody wrote**: an
    offline deployment wanting "provably does not reach the network"
    should require ``read_only=True`` or an explicit tag, because
    ``touches_network=False`` is what an undeclared tool looks like too.
    :attr:`approval_mode` is the authoritative field; these four are
    advisory.

    (Plan 0028 §2 sketches the defaults the other way round — ``LOW`` /
    ``AUTO`` / ``concurrency_safe=True`` — which contradicts its own §4
    Q5, where the declared-nothing case is required to resolve to "the
    most conservative rather than the most convenient set". Q5 wins: a
    default that is also the most permissive value makes the rule it is
    meant to encode untestable.)

    Nothing in :mod:`omicsclaw.tools` enforces any of this. The registry
    stores a policy and answers questions about it; deciding what ``ASK``
    or ``DENY_UNLESS_TRUSTED`` *does* belongs to the layer that knows who
    is asking, which this one deliberately does not.
    """

    risk_level: RiskLevel = RiskLevel.HIGH
    """Blast radius if this tool misbehaves. Permission: guarded default."""

    approval_mode: ApprovalMode = ApprovalMode.ASK
    """Whether a human decision gates execution. Permission: a tool that
    never considered approval does not get to run unattended."""

    read_only: bool = False
    """Claims to change nothing anywhere."""

    concurrency_safe: bool = False
    """May run beside other tools in the same turn. Permission —
    parallelism is earned, and the existing tool layer defaults it to
    ``False`` as well.

    Read at schedule time through
    :meth:`~omicsclaw.tools.registry.ToolRegistry.is_concurrency_safe`: a
    ``False`` here makes the call a barrier in the engine's scheduler, run
    with nothing else of that turn's in flight."""

    writes_workspace: bool = False
    """Claims to create or modify files in the session workspace."""

    writes_config: bool = False
    """Claims to modify persistent configuration or session state."""

    touches_network: bool = False
    """Claims to open a network connection."""

    prompts_for_itself: bool = False
    """Claims to call :func:`~omicsclaw.tools.context.require_approval` inside
    its own ``execute``, with a prompt describing the actual effect.

    A claim, so it defaults to the absence of one, and here the two values are
    not symmetric: ``True`` asks an outer gate to *stand back*, so ``True`` is
    the value that must be written deliberately. A tool that says nothing gets
    asked about by whoever is gating it — one prompt either way, and the cost
    of a forgotten declaration is a plainer prompt rather than a call nobody
    saw.

    It exists because "``approval_mode`` is ``ASK``, therefore the tool asks"
    is a convention and not a guarantee. A tool that never calls
    ``require_approval`` runs regardless of what its ``approval_mode`` says,
    so a gate deferring to it on that basis would let exactly the calls it
    exists to catch straight through. Nothing in this package reads this
    field; :class:`omicsclaw.permission.GatedTool` does, and
    ``tests/permission/test_foundation_tools_keep_their_prompts.py`` checks
    that every tool declaring it really does ask."""

    allowed_in_background: bool = False
    """May run in a detached turn with nobody watching. Permission."""

    rule_argument: str | None = None
    """The argument permission rules match this tool's calls against, in
    place of the first required ``string`` of its schema. Permission.

    A list of strings is matched as its distinct values, sorted and joined
    with ``", "``, so an "always allow" for that list covers the same set
    in any order, whatever the other arguments are. That widens what one
    remembered rule allows, so ``None``, which keeps the schema-derived
    argument, is the guarded default. Set it only on a tool whose own
    checks bound what the other arguments can do: ``install_skill_deps``
    names ``skills``, because its packages are limited to what those
    skills declare and go into an isolated overlay. Read by
    :class:`omicsclaw.permission.PermissionGate`, nothing in this package."""

    tags: frozenset[str] = frozenset()
    """Free-form labels for the assembly layer to filter on.

    This is where surface gating lands once that layer exists: the
    registry offers the labels and never decides who may see what. Empty
    by default, which matches no allow-list.
    """


__all__ = ["ApprovalMode", "RiskLevel", "Tool", "ToolPolicy"]
