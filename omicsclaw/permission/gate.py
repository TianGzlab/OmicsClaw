"""Where a tool call is permitted, refused, or put to a person.

:class:`PermissionGate` decides; :class:`GatedTool` acts on the decision.

**The gate decorates a tool, not the registry.** :func:`gate_tools` wraps each
:class:`~omicsclaw.tools.Tool` that a registry is built over, so the gate runs
*inside* :meth:`~omicsclaw.tools.ToolRegistry.execute` and reads the policy
that registry already resolved. Two consequences for a caller:

- Nothing wraps the registry, so the optional Protocols the engine probes for
  (``DeadlineAwareExecutor``, ``ConcurrencyAwareExecutor``) keep working — in
  particular a human's approval time still stays out of the per-tool timeout.
- **A tool registered without passing through :func:`gate_tools` is not
  gated.** Composing the registry is where that has to be got right.

**Who asks a human.** A verdict of ``ask`` does not mean *the gate* asks. A
tool that declares :attr:`~omicsclaw.tools.ToolPolicy.prompts_for_itself` puts
the question itself, with a prompt that can describe the actual effect — the
diff ``edit_file`` is about to write, the whole URL ``web_fetch`` is about to
request. The gate asks in every other case, and in two cases even when the
tool claims otherwise:

- the tool would self-approve this time, because its resolved
  ``approval_mode`` is ``AUTO`` and a rule escalated the call;
- a dangerous-command pattern matched, where the pattern's reason is
  something the tool does not know and a person needs to read.

Either way a call is put to a human **at most once**: after the gate asks, it
runs the tool with consent already recorded, so the tool's own
``require_approval`` returns immediately.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from omicsclaw.schema import ToolDefinition
from omicsclaw.tools.base import ApprovalMode, RiskLevel, Tool, ToolPolicy
from omicsclaw.tools.context import (
    ApprovalDenied,
    effective_policy,
    require_approval,
    use_effective_policy,
)

from .danger import COMMAND_ARGUMENT, DangerPatterns
from .modes import PermissionMode
from .rules import (
    RuleStore,
    Rules,
    Verdict,
    literal_pattern,
    principal_argument,
    principal_key,
)

_log = logging.getLogger(__name__)


class PermissionDenied(ApprovalDenied):
    """The gate refused before the tool ran. Nobody was asked.

    A subclass of :exc:`~omicsclaw.tools.ApprovalDenied`, so one ``except``
    covers all three ways consent can be absent: a rule said no, a person said
    no, or there was nobody to ask. Distinct so a log can tell a policy refusal
    (edit the rule file) from a human one.
    """


class DecisionSource(StrEnum):
    """Which stage of the pipeline decided. Carried so a refusal is actionable."""

    MODE = "mode"
    """:class:`~omicsclaw.permission.PermissionMode` — the session's posture."""

    RULE = "rule"
    """A line of the rule file matched."""

    DANGER = "danger"
    """A built-in dangerous-command pattern matched."""

    POLICY = "policy"
    """Nothing above matched, so the tool's own
    :class:`~omicsclaw.tools.ToolPolicy` answered."""


@dataclass(frozen=True, slots=True)
class Resolution:
    """What the gate decided, and enough to explain it to somebody.

    Returned by :meth:`PermissionGate.resolve`, which is a pure function of its
    arguments: it asks nobody and runs nothing, so a caller can use it to
    preview what a rule file would do.
    """

    verdict: Verdict
    source: DecisionSource
    reason: str
    """Why, in words meant for a person. Reaches a human as
    :attr:`~omicsclaw.tools.ApprovalRequest.reason` and a model as the text
    of a :exc:`PermissionDenied`."""
    risk_level: RiskLevel
    """The blast radius to show in a prompt. The tool's own level, unless a
    dangerous-command pattern raised it."""


class PermissionGate:
    """Mode plus rules plus danger patterns, resolved in one pass.

    Held by a composition root and shared by every gated tool: one object,
    so "what is this session permitted to do" has one answer and changing it
    changes every tool at once.
    """

    __slots__ = ("_danger", "_mode", "_rules")

    def __init__(
        self,
        *,
        mode: PermissionMode = PermissionMode.DEFAULT,
        rules: RuleStore | Rules | None = None,
        danger: DangerPatterns | None = None,
    ) -> None:
        """``rules=None`` is an empty rule set, which is the ordinary case.

        A :class:`~omicsclaw.permission.RuleStore` re-reads its file on every
        call, so "always allow" takes effect on the next one; a plain
        :class:`~omicsclaw.permission.Rules` is fixed for the session and is
        what a test or an embedded deployment passes.
        """
        self._mode = mode
        self._rules = rules
        self._danger = DangerPatterns() if danger is None else danger

    @property
    def mode(self) -> PermissionMode:
        """The session's posture. Set once; there is no setter."""
        return self._mode

    @property
    def store(self) -> RuleStore | None:
        """The rule file, when rules came from one.

        How a surface reaches :meth:`~omicsclaw.permission.RuleStore.remember`
        to honour "always allow". ``None`` when the rules are fixed, which a
        surface should read as "this deployment has nowhere to remember
        things" rather than as an error.
        """
        return self._rules if isinstance(self._rules, RuleStore) else None

    @property
    def rules(self) -> Rules:
        """The rules as they stand now."""
        if self._rules is None:
            return Rules()
        if isinstance(self._rules, RuleStore):
            return self._rules.current
        return self._rules

    def resolve(
        self,
        tool_name: str,
        arguments: str,
        *,
        policy: ToolPolicy,
        schema: Mapping[str, Any] | None = None,
    ) -> Resolution:
        """Decide, without acting. Asks nobody, runs nothing, never raises.

        The stages, first answer wins:

        1. ``bypass-all`` allows — before the rule file, so the one mode
           whose meaning is "no checks" genuinely has none.
        2. ``read-only`` denies anything not declaring ``read_only=True``.
        3. the rule file, ``deny`` before ``allow`` before ``ask``.
        4. the dangerous-command patterns, for a tool whose principal
           argument its own schema calls ``command``.
        5. ``auto-approve`` allows whatever is left.
        6. the tool's own ``approval_mode``.

        Stage 4 is reached exactly when no line of the rule file spoke about
        the call, so a rule — in either direction — always outranks a
        dangerous-command pattern.
        """
        if self._mode is PermissionMode.BYPASS_ALL:
            return Resolution(
                Verdict.ALLOW,
                DecisionSource.MODE,
                "permission mode bypass-all: every check in this layer is off",
                policy.risk_level,
            )

        if self._mode is PermissionMode.READ_ONLY and not policy.read_only:
            return Resolution(
                Verdict.DENY,
                DecisionSource.MODE,
                f"permission mode read-only: {tool_name} does not declare "
                "read_only, and a claim nobody wrote is not a claim",
                policy.risk_level,
            )

        key = principal_key(schema)
        argument_text = principal_argument(arguments, schema)

        rule = self.rules.evaluate(tool_name, argument_text)
        if rule is not None:
            return Resolution(
                rule.verdict,
                DecisionSource.RULE,
                f"permission rule {rule.verdict.value} {rule.pattern!r}",
                policy.risk_level,
            )

        if key == COMMAND_ARGUMENT:
            found = self._danger.inspect(argument_text)
            if found is not None:
                return Resolution(
                    Verdict.ASK,
                    DecisionSource.DANGER,
                    found.reason,
                    found.risk_level,
                )

        if self._mode is PermissionMode.AUTO_APPROVE:
            return Resolution(
                Verdict.ALLOW,
                DecisionSource.MODE,
                "permission mode auto-approve: no rule and no danger pattern "
                "spoke about this call",
                policy.risk_level,
            )

        settled = policy.approval_mode is ApprovalMode.AUTO
        return Resolution(
            Verdict.ALLOW if settled else Verdict.ASK,
            DecisionSource.POLICY,
            f"tool policy approval_mode={policy.approval_mode.value}",
            policy.risk_level,
        )

    def remember(
        self,
        tool_name: str,
        arguments: str,
        *,
        schema: Mapping[str, Any] | None = None,
    ) -> str | None:
        """Persist "always allow" for exactly this call. Returns the pattern.

        ``None`` when there is no rule file to write to, which a surface
        should report to the person as "this run cannot remember that"
        rather than pretend succeeded — a remembered decision that was not
        written is a prompt they will see again and stop believing.
        """
        store = self.store
        if store is None:
            _log.info("cannot remember %s: no rule file is configured", tool_name)
            return None
        pattern = literal_pattern(
            tool_name, principal_argument(arguments, schema)
        )
        store.remember(pattern)
        return pattern


class GatedTool:
    """One tool, with :class:`PermissionGate` in front of its ``execute``.

    Satisfies :class:`~omicsclaw.tools.Tool` structurally and delegates
    everything the model can see, so a gated tool and an ungated one are
    indistinguishable in a prompt. That is the same rule
    :class:`~omicsclaw.tools.ToolPolicy` follows and for the same reason: a
    model shown its own approval rules is a model invited to argue with
    them.
    """

    __slots__ = ("_gate", "_inner")

    def __init__(self, inner: Tool, gate: PermissionGate) -> None:
        self._inner = inner
        self._gate = gate

    @property
    def inner(self) -> Tool:
        """The tool being gated. For introspection, not for calling around."""
        return self._inner

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def policy(self) -> ToolPolicy | None:
        """The inner tool's own declaration, passed straight through.

        Read by :meth:`~omicsclaw.tools.ToolRegistry.register` when a
        deployment names no policy. Without it every gated tool would fall back
        to the registry's ``ToolPolicy()`` default instead.
        """
        return getattr(self._inner, "policy", None)

    def definition(self) -> ToolDefinition:
        return self._inner.definition()

    async def execute(self, arguments: str) -> str:
        """Resolve, then do one of three things.

        ``deny`` raises before the inner tool is touched. ``allow`` runs it
        with a settled policy, so its own ``require_approval`` returns at
        once and nobody is asked twice. ``ask`` either asks here and then
        runs settled, or — when the tool asks better than this could — hands
        the question down untouched. See the module docstring for which.

        :raises PermissionDenied: the call was refused. Nobody was asked and
            the inner tool did not run.

        Arguments are never logged — this is the layer that sees a ``bash``
        command line and a ``write_file`` body.
        """
        policy = self._policy()
        schema = self._schema()
        resolution = self._gate.resolve(
            self.name, arguments, policy=policy, schema=schema
        )

        if resolution.verdict is Verdict.DENY:
            _log.warning(
                "permission denied: tool=%s source=%s",
                self.name,
                resolution.source.value,
            )
            raise PermissionDenied(f"{self.name} refused — {resolution.reason}")

        if resolution.verdict is Verdict.ALLOW:
            _log.debug(
                "permission allowed: tool=%s source=%s",
                self.name,
                resolution.source.value,
            )
            return await self._run_settled(arguments, policy)

        if self._tool_asks_better(policy, resolution):
            return await self._inner.execute(arguments)

        escalated = dataclasses.replace(
            policy,
            approval_mode=ApprovalMode.ASK,
            risk_level=resolution.risk_level,
        )
        with use_effective_policy(escalated):
            await require_approval(
                self.name, arguments, reason=resolution.reason
            )
        return await self._run_settled(arguments, policy)

    # ---- internals ------------------------------------------------------

    @staticmethod
    def _tool_asks_better(policy: ToolPolicy, resolution: Resolution) -> bool:
        """Whether to hand the question down instead of asking here.

        Three conditions, all required:

        1. the tool **claims** to prompt for itself. The claim is read, never
           inferred from ``approval_mode``: ``ASK`` says what the deployment
           wants, and a tool that never calls ``require_approval`` runs
           regardless of it. An undeclared tool is asked about here.
        2. the tool would still ask *this time*. An ``AUTO`` tool that a rule
           escalated to ``ask`` self-approves, so deferring to it would make
           the rule have no effect.
        3. the reason is one the tool already knows. A dangerous-command match
           is not, so it is put to the person here rather than replaced by the
           tool's generic prompt.
        """
        return (
            policy.prompts_for_itself
            and policy.approval_mode is not ApprovalMode.AUTO
            and resolution.source is not DecisionSource.DANGER
        )

    async def _run_settled(self, arguments: str, policy: ToolPolicy) -> str:
        """Run the inner tool with consent already given for this call.

        Publishes the resolved policy with ``approval_mode=AUTO``, which
        :func:`~omicsclaw.tools.require_approval` reads first, so a tool that
        asks for itself returns immediately instead of putting the same
        question to the same person again. The binding is unwound on every
        exit path by :func:`~omicsclaw.tools.use_effective_policy`, so the
        next call on this Task resolves for itself.

        Only ``approval_mode`` is changed. ``read_only``, ``risk_level`` and
        the rest are the deployment's resolved values and stay as they are —
        a settled approval is not a licence to rewrite the policy.
        """
        with use_effective_policy(
            dataclasses.replace(policy, approval_mode=ApprovalMode.AUTO)
        ):
            return await self._inner.execute(arguments)

    def _policy(self) -> ToolPolicy:
        """The policy to judge with, most authoritative first.

        The registry's published resolution, then the inner tool's own
        declaration, then ``ToolPolicy()`` — which asks. The same three-step
        order :func:`~omicsclaw.tools.require_approval` documents, and for
        the same reason: this runs inside
        :meth:`~omicsclaw.tools.ToolRegistry.execute` in production, so step
        one normally answers, and the other two are for a gated tool driven
        directly from a script or a test.
        """
        published = effective_policy()
        if published is not None:
            return published
        declared = getattr(self._inner, "policy", None)
        return declared if isinstance(declared, ToolPolicy) else ToolPolicy()

    def _schema(self) -> Mapping[str, Any] | None:
        """The inner tool's argument schema, or ``None`` if it has none.

        Never raises. ``definition()`` belongs to a Protocol this package does
        not own — an MCP proxy builds one on demand — and a proxy whose server
        has gone away must not turn a permission decision into a crash. Without
        a schema, rules match against the raw JSON payload.
        """
        try:
            schema = self._inner.definition().input_schema
        except Exception:  # noqa: BLE001 — see the docstring
            _log.debug("no schema readable for %s", self.name, exc_info=True)
            return None
        return schema if isinstance(schema, Mapping) else None


def gate_tools(tools: Iterable[Tool], gate: PermissionGate) -> tuple[Tool, ...]:
    """Every tool, gated, in the order given. Idempotent.

    Order is preserved because a registry's tool-list order is part of the
    prompt bytes a vendor caches on.

    An already-gated tool is returned as it is, so calling this twice over the
    same list does not produce two wrappers — which would resolve twice and ask
    a person twice.
    """
    return tuple(
        tool if isinstance(tool, GatedTool) else GatedTool(tool, gate)
        for tool in tools
    )


__all__ = [
    "DecisionSource",
    "GatedTool",
    "PermissionDenied",
    "PermissionGate",
    "Resolution",
    "gate_tools",
]
