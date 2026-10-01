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

**Which questions a standing grant may answer.** A surface can offer "stop
asking me about this tool" (the CLI's ``s``). That is only safe for questions
the tool's *own default* raised. On both paths above —— the gate asking, and
the gate handing the question down —— the gate binds
:func:`~omicsclaw.tools.ask_every_time` to say whether anything more specific
than that raised this one: a rule, a dangerous-command pattern, a protected
path. It has to be both paths, because a rule outranks a danger pattern: an
``ask: ["bash"]`` rule turns ``rm -rf /`` into a *rule* question, which is
handed down to ``bash`` like any other (plan 0049 §3).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from omicsclaw.schema import ToolDefinition
from omicsclaw.tools.base import ApprovalMode, RiskLevel, Tool, ToolPolicy
from omicsclaw.tools.context import (
    ApprovalDenied,
    ask_every_time,
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

PROTECTED_DIRNAME = ".omicsclaw"
"""The workspace directory holding the rule file, conversations and plans.

A tool that can write there can write an ``allow`` rule, and a rule outranks
every check after it —— so one unsupervised write would silence the gate for
this session and every later one. Changing anything there is therefore always
put to a person (plan 0049 §4). Reading it is not: a call whose tool declares
``read_only`` is never stopped by this.
"""

DOTENV_NAME = re.compile(r"(?<![\w.])\.env(?![\w-])", re.IGNORECASE)
"""A ``.env`` file named in a command line or a path: ``.env``, ``./.env``,
``/srv/app/.env``, ``.env.local`` —— and not a Python ``.environ``
attribute, ``.envrc`` or ``.venv``.

Protected for the same reason as the rule file, found by review after plan
0049 shipped protecting only that: ``.env`` sets
``OMICSCLAW_PERMISSION_MODE``, and ``bypass-all`` is decided before every
other check. One unsupervised ``echo … >> .env`` would switch the gate off
from the next start, and ``LLM_BASE_URL`` in the same file decides where
the API key is sent. The line drawn is *files that decide what OmicsClaw
asks about*: host-wide persistence (``.git/hooks``, ``~/.bashrc``) is not
enumerable, and only the sandbox answers it.

Matched by name rather than by path, because the program reads ``.env``
from two places (``omicsclaw.launch.dotenv_candidates``) and a shell
command names a file however it likes. Matched **without regard to case**,
because the default filesystems of macOS and Windows do not regard it
either: there ``.ENV`` *is* ``.env``. The cost is a question for a command
that merely mentions ``.env.example``.
"""

_WRITING_KEYS = frozenset(
    {
        COMMAND_ARGUMENT,
        "path",
        "file_path",
        "filepath",
        "filename",
        "file",
        "destination",
        "dest",
        "target",
    }
)
"""Principal arguments that say where something will be written or run.

The protected check reads only these. ``web_search``'s query,
``web_fetch``'s URL and ``plan_write``'s steps can mention ``.env``
without changing it, and a card that says "this changes a file" about a
search is a question the person cannot answer truthfully —— on a Channel
it is also a timeout that becomes a refusal. What this gives up is a tool
whose principal argument is something else and that writes anyway (an MCP
``move_file(source, destination)`` is read by its ``source``): the gate
reads one argument per call, and that limit is recorded where the
dangerous-command patterns record theirs.
"""


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

    PROTECTED = "protected"
    """The call would change a file that decides what OmicsClaw asks about:
    the directory :data:`PROTECTED_DIRNAME` names, the rule file, or a
    ``.env`` (:data:`DOTENV_NAME`)."""

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
    reason_shows_call: bool = False
    """Whether :attr:`reason` quotes everything the call holds, so a prompt
    carrying it need not show the arguments beside it."""


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
        """The session's posture, as :meth:`resolve` will read it next."""
        return self._mode

    def set_mode(self, mode: PermissionMode) -> PermissionMode:
        """Change the posture from the next call on. Returns the old one.

        A mechanism and nothing more: *which* changes are allowed is the
        composition root's rule
        (:meth:`~omicsclaw.entry.AgentApp.set_permission_mode`), not this
        object's. :meth:`resolve` reads the mode on every call and caches no
        decision, so switching here is exactly equivalent to having started
        in the new mode —— a call already being asked about keeps the answer
        it was resolved to, which is the only thing a switch cannot reach.
        """
        previous = self._mode
        self._mode = PermissionMode(mode)
        return previous

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
        2½. a call that could change :data:`PROTECTED_DIRNAME`, the rule
           file or a ``.env`` asks — **before** the rule file, because the
           thing being protected *is* the rule file: an ``allow`` rule that
           let a tool rewrite it would let the tool write the next ``allow``
           rule. ``.env`` is here because it can set ``bypass-all``.
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

        key = policy.rule_argument or principal_key(schema)
        argument_text = principal_argument(arguments, schema, declared=policy.rule_argument)

        if self._protected(key, argument_text, policy):
            return Resolution(
                Verdict.ASK,
                DecisionSource.PROTECTED,
                "this changes a file that decides what OmicsClaw asks about "
                f"({PROTECTED_DIRNAME}/, the rule file or .env). What is "
                "written there can switch these questions off from now on:"
                f"\n{argument_text}",
                RiskLevel.HIGH,
                reason_shows_call=_is_the_whole_call(arguments, key, argument_text),
            )

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

    def protects(
        self,
        arguments: str,
        *,
        policy: ToolPolicy,
        schema: Mapping[str, Any] | None = None,
    ) -> bool:
        """Whether this call is decided at stage 2½ of :meth:`resolve`.

        Such a call is asked about every time, and **no rule reaches it** ——
        including the ``allow`` rule "always" would write, because stage 2½
        comes before the rule file. A surface asks this before offering
        "always" on a card, so that it does not offer a grant that will be
        written, reported as remembered, and never consulted.
        """
        if self._mode is PermissionMode.BYPASS_ALL:
            return False
        return self._protected(
            policy.rule_argument or principal_key(schema),
            principal_argument(arguments, schema, declared=policy.rule_argument),
            policy,
        )

    def _protected(
        self, key: str | None, argument_text: str, policy: ToolPolicy
    ) -> bool:
        return (
            not policy.read_only
            and key in _WRITING_KEYS
            and self.touches_protected(argument_text)
        )

    def touches_protected(self, argument_text: str) -> bool:
        """Whether *argument_text* names a protected directory or file.

        A text test, deliberately: it reads a ``bash`` command line and a
        file path with the same rule, so ``cd .omicsclaw && …`` and
        ``./.omicsclaw/settings.json`` are both caught, in any letter case.

        **What it cannot see**, stated so nobody reads more into it: a name
        built at run time (``d=.en; echo >> ${d}v``), a shell glob that
        expands to one (``>> .en?``, ``.omics*/settings.json``), and any
        argument but the one the gate reads per call. Those are the limits
        of every dangerous-command pattern too. The protected files are
        guarded against a *careless* or *coaxed* model; against a
        determined one with an unsupervised shell, only the sandbox is.

        A rule file kept outside :data:`PROTECTED_DIRNAME` is recognised by
        its full path and by its file name, since a relative ``perm.json``
        or ``./perm.json`` names it as surely as the absolute path does.
        The default one, ``.omicsclaw/settings.json``, is recognised by its
        directory instead: matching every ``settings.json`` a project has
        would ask about an editor's configuration.
        """
        if not argument_text:
            return False
        folded = argument_text.casefold()
        if PROTECTED_DIRNAME in folded:
            return True
        if DOTENV_NAME.search(argument_text):
            return True
        store = self.store
        if store is None:
            return False
        rule_file = store.path
        if str(rule_file).casefold() in folded:
            return True
        if PROTECTED_DIRNAME in (part.casefold() for part in rule_file.parts):
            return False
        named = re.compile(
            rf"(?<![\w.-]){re.escape(rule_file.name)}(?![\w.-])", re.IGNORECASE
        )
        return named.search(argument_text) is not None

    def remember(
        self,
        tool_name: str,
        arguments: str,
        *,
        schema: Mapping[str, Any] | None = None,
        policy: ToolPolicy | None = None,
    ) -> str | None:
        """Persist "always allow" for exactly this call. Returns the pattern.

        The pattern is written against the argument :meth:`resolve` reads,
        so *policy* has to be the one the call is judged with: its
        ``rule_argument``, when set, replaces the schema's choice.

        ``None`` when there is no rule file to write to, which a surface
        should report to the person as "this run cannot remember that"
        rather than pretend succeeded — a remembered decision that was not
        written is a prompt they will see again and stop believing.
        """
        store = self.store
        if store is None:
            _log.info("cannot remember %s: no rule file is configured", tool_name)
            return None
        declared = policy.rule_argument if policy is not None else None
        pattern = literal_pattern(
            tool_name, principal_argument(arguments, schema, declared=declared)
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

        always = self._always_asked(policy, resolution)
        if self._tool_asks_better(policy, resolution):
            with ask_every_time(always):
                return await self._inner.execute(arguments)

        escalated = dataclasses.replace(
            policy,
            approval_mode=ApprovalMode.ASK,
            risk_level=resolution.risk_level,
        )
        with use_effective_policy(escalated), ask_every_time(always):
            await require_approval(
                self.name,
                arguments,
                reason=resolution.reason,
                reason_shows_call=resolution.reason_shows_call,
            )
        return await self._run_settled(arguments, policy)

    # ---- internals ------------------------------------------------------

    @staticmethod
    def _always_asked(policy: ToolPolicy, resolution: Resolution) -> bool:
        """Whether a standing "stop asking" grant must not answer this one.

        Everything but the tool's own ``ASK`` default: a rule, a danger
        pattern and a protected path are each more specific than "this tool
        usually asks", and a grant given for the general case must not
        silence the specific one. ``DENY_UNLESS_TRUSTED`` is included
        because its whole meaning is that consent is per call.
        """
        return (
            resolution.source is not DecisionSource.POLICY
            or policy.approval_mode is ApprovalMode.DENY_UNLESS_TRUSTED
        )

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
           is not, and nor is a protected path, so both are put to the person
           here rather than replaced by the tool's generic prompt.

        A handed-down question still carries whether it may be answered by a
        standing grant —— see :meth:`_always_asked` and the module docstring
        for why a *rule* question, which is handed down, needs that.
        """
        return (
            policy.prompts_for_itself
            and policy.approval_mode is not ApprovalMode.AUTO
            and resolution.source
            not in (DecisionSource.DANGER, DecisionSource.PROTECTED)
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


def _is_the_whole_call(arguments: str, key: str | None, argument_text: str) -> bool:
    """Whether *argument_text* is everything the call's *arguments* hold.

    True when it is the raw payload itself, and when the payload is a JSON
    object whose one key is *key*.
    """
    if argument_text == arguments:
        return True
    try:
        decoded = json.loads(arguments)
    except (ValueError, RecursionError):
        return False
    return isinstance(decoded, dict) and list(decoded) == [key]


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
