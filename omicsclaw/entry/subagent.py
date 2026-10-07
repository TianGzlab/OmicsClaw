"""Which sub-agents a deployment offers, and how one is actually run.

:func:`build_subagent_registry` joins :mod:`omicsclaw.subagent` to this
deployment: the built-in ``general-purpose`` and ``module-reviewer`` agents
plus whatever is written under :meth:`~omicsclaw.entry.config.AppConfig.agents_root`, with
unreadable files reported here because that package may not log.

:class:`ChildRunner` is the other half — the
:class:`~omicsclaw.subagent.Delegate` that builds a child engine over the
parent's own provider and tools and drives one exchange with it.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from omicsclaw.engine import (
    AgentEngine,
    EngineConfig,
    EngineEventType,
    RunResult,
    StopReason,
)
from omicsclaw.planning import PLAN_WRITE_TOOL_NAME
from omicsclaw.provider import LLMProvider
from omicsclaw.schema import Role
from omicsclaw.skills import SkillIndex
from omicsclaw.subagent import (
    TASK_TOOL_NAME,
    ChildPrompt,
    SubAgentDefinition,
    SubAgentRegistry,
    load_agents,
)
from omicsclaw.tools import ToolRegistry, report_progress
from omicsclaw.tools.context import current_context, report_usage
from omicsclaw.subagent.task_tool import REVIEW_MODULE_KEY
from omicsclaw.tools.base import Tool

from .config import AppConfig
from .memory import MEMORY_WRITE_TOOL_NAME
from .project import REVIEW_BRIEF_FILE
from .review import ReviewArchive
from .sandbox import SandboxBinding, sandbox_section

__all__ = [
    "GENERAL_PURPOSE",
    "MODULE_REVIEWER",
    "ChildRunner",
    "DelegationIncomplete",
    "build_subagent_registry",
]

_log = logging.getLogger(__name__)

_WITHHELD_FROM_SUB_AGENTS: Mapping[str, str] = MappingProxyType(
    {
        PLAN_WRITE_TOOL_NAME: "acts on the calling conversation's plan",
        MEMORY_WRITE_TOOL_NAME: "writes memory that every later conversation reads",
    }
)
"""Parent tools no sub-agent is given, each mapped to the reason why.

:meth:`ChildRunner._child_registry` leaves every one of them out of every
sub-agent's tool set, whatever the sub-agent's definition asks for. A
tool belongs here for any reason that holds for every sub-agent — it acts
on the calling conversation's own state, it reaches conversations other
than this one, it needs a person the sub-agent does not have. Each reason
is a phrase whose subject is the tool, because it is quoted after the
tool's name in the load-time warning and in the ``general-purpose``
description.

:data:`~omicsclaw.subagent.TASK_TOOL_NAME` is withheld as well but is not
listed: :meth:`~omicsclaw.subagent.SubAgentDefinition.resolve_tools`
removes it, and its reason is :data:`_DELEGATION_REASON`.
"""

_DELEGATION_REASON = "would let a sub-agent start sub-agents of its own"
"""Why no sub-agent is given :data:`~omicsclaw.subagent.TASK_TOOL_NAME`,
worded like the reasons in :data:`_WITHHELD_FROM_SUB_AGENTS`."""


def _withheld_reasons(
    withheld: Mapping[str, str] = _WITHHELD_FROM_SUB_AGENTS,
) -> dict[str, str]:
    """Every tool name no sub-agent is given, mapped to the reason why.

    :param withheld: the tools :meth:`ChildRunner._child_registry` removes.
    :returns: :data:`~omicsclaw.subagent.TASK_TOOL_NAME` first, then
        *withheld* in its own order.
    """
    return {TASK_TOOL_NAME: _DELEGATION_REASON, **withheld}


def _explain(reasons: Mapping[str, str]) -> str:
    """``"name, which reason; name, which reason"`` over *reasons*."""
    return "; ".join(f"{name}, which {reason}" for name, reason in reasons.items())


def _general_purpose_description(withheld: Mapping[str, str]) -> str:
    """The ``general-purpose`` description, naming each tool it is not given.

    :param withheld: the tools :meth:`ChildRunner._child_registry` removes,
        mapped to the reason why. ``task`` is named ahead of them.
    :returns: the text the model chooses this sub-agent by.
    """
    return (
        "General-purpose agent for open-ended sub-tasks: researching a "
        "question across many files, running a multi-step analysis to a "
        "conclusion, or any search where you are not confident the first "
        "few attempts will find the answer. Runs on the same model as the "
        "main agent with every tool except "
        f"{_explain(_withheld_reasons(withheld))}."
    )


GENERAL_PURPOSE = SubAgentDefinition(
    name="general-purpose",
    description=_general_purpose_description(_WITHHELD_FROM_SUB_AGENTS),
    system_prompt=(
        "You are a sub-agent working on one task delegated to you by "
        "another agent.\n\n"
        "- You cannot see the conversation you were delegated from. "
        "Everything you were told is in the task itself; if something "
        "is missing, work from what you can find rather than asking, "
        "because there is nobody to ask.\n"
        "- You cannot delegate further. Do the work yourself with the "
        "tools you have.\n"
        "- Your final reply is the only thing that is handed back. Make "
        "it self-contained: state what you found, the file paths and "
        "commands that back it up, and anything you could not settle. "
        "Do not refer to work you did as if the reader watched it."
    ),
    source="builtin",
)
"""The sub-agent every deployment has.

Its ``tools``, ``model`` and ``max_turns`` are all left empty, so it
inherits the parent's whole tool set (minus delegation and
:data:`_WITHHELD_FROM_SUB_AGENTS`) and the parent's model. Its
description is rendered from that mapping.
"""


MODULE_REVIEWER_PROMPT = f"""\
You review one analysis module of an OmicsClaw project. You can read files \
and load skills; you cannot change anything, and nobody will answer questions.

Read the module in this order:
1. results/<NN_slug>/{REVIEW_BRIEF_FILE}, which the latest replay wrote; \
read it with start_line=1, which returns it whole. For each step it gives the step's first cell, the skill functions the ledger \
recorded, what the step read and wrote with sizes, and the end of its log; \
then each table's shape and first rows (the whole table when it is small), \
every output file with its size, and the replay record with its changed and \
orphan outputs. Without a brief, start from \
results/<NN_slug>/provenance/manifest.json.
2. Each step file the brief lists, analysis/<NN_slug>/README.md and the \
REPORT (results/<NN_slug>/M<NN>_<slug>_REPORT.md), each in full with \
start_line=1, so every line comes back numbered for your findings.
3. Further files only for a check that 1 and 2 leave open. Read a large file \
in slices with start_line and end_line. Binary files (.h5ad, images) are \
covered by their sizes in the brief and by what the validate step asserts; \
notebooks/ repeats the step files with their output.

Check every item below and note each finding with its file and line:
1. Each step file: inputs come from data/ or an earlier module's \
intermediate/ or tables/; every value the skill does not give has a stated \
reason; the skill functions the step's first cell names match the ones the \
manifest recorded; where a skill function covers the work and the step does \
not use it, the step says why.
2. The validate step checks the outputs the REPORT relies on.
3. The REPORT (M<NN>_<slug>_REPORT.md): every number matches a table or log \
in results/<NN_slug>/; every figure it cites exists and is not listed under \
orphan_outputs; claims stay within what the steps computed; it carries the \
disclaimer.
4. The replay in the manifest succeeded and covers the current step files.

Your first line is the verdict, exactly `VERDICT: APPROVE` or \
`VERDICT: REVISE`. Then list the findings, most serious first. Choose REVISE \
when any finding would change a number, a figure or a conclusion."""
"""The ``module-reviewer`` sub-agent's instructions."""

MODULE_REVIEWER = SubAgentDefinition(
    name="module-reviewer",
    description=(
        "Reviews one analysis module after it has been replayed and before the user "
        "accepts it: reads its step files, outputs, manifest and report, and returns "
        "VERDICT: APPROVE or VERDICT: REVISE with findings. Read-only."
    ),
    system_prompt=MODULE_REVIEWER_PROMPT,
    tools=("read_file", "use_skill"),
    source="builtin",
)
"""The read-only reviewer of a finished module.

Only ``read_file`` and ``use_skill``: a reviewer that could edit the module
could make its own verdict untrue. The review brief and the manifest name
every file to read, which stands in for listing directories.
"""


class DelegationIncomplete(RuntimeError):
    """A sub-agent's run ended without it writing a conclusion.

    Raised by :meth:`ChildRunner.delegate`; the ``task`` tool's registry
    reports it to the parent model as an ``is_error`` Observation.
    """


def build_subagent_registry(config: AppConfig) -> SubAgentRegistry | None:
    """The sub-agents this deployment offers, or ``None``.

    ``None`` when :attr:`~omicsclaw.entry.config.AppConfig.subagents` is
    off, and that ``None`` is what the rest of the wiring branches on: no
    ``task`` tool is mounted and nothing about delegation reaches the
    model.

    Files under :meth:`~omicsclaw.entry.config.AppConfig.agents_root`
    are loaded after the built-ins (``general-purpose``, then
    ``module-reviewer``), so a file of the same name replaces that
    built-in in place. A file that cannot be
    read or parsed is logged and skipped. A file whose ``tools:`` names a
    tool no sub-agent is given — ``task``, or one in
    :data:`_WITHHELD_FROM_SUB_AGENTS` — is registered, and a warning names
    each such tool and the reason it is withheld.
    """
    if not config.subagents:
        return None
    registry = SubAgentRegistry([GENERAL_PURPOSE, MODULE_REVIEWER])
    for definition in load_agents(config.agents_root(), on_error=_report):
        try:
            registry.register(definition)
        except ValueError as exc:
            _report(Path(definition.source or definition.name), exc)
            continue
        _warn_withheld(definition)
    return registry


class ChildRunner:
    """Runs one sub-agent against a narrowed copy of the parent's registry.

    Satisfies :class:`~omicsclaw.subagent.Delegate`. Holds the pieces a
    child engine is built from rather than a finished app, because the
    ``task`` tool is mounted into the very registry it narrows.

    **The child's tools are the parent's own objects**, already gated and
    already hooked, re-registered under the policy the parent resolved for
    each of them. Rebuilding them would drop both, and resolving their
    policies afresh would drop a deployment's ``register(policy=)``
    override — which lives on the parent registry and not on the tools.
    """

    __slots__ = ("_config", "_parent", "_provider", "_sandbox", "_skills")

    def __init__(
        self,
        *,
        provider: LLMProvider,
        parent: ToolRegistry,
        config: AppConfig,
        sandbox: SandboxBinding | None = None,
        skills: SkillIndex | None = None,
    ) -> None:
        self._provider = provider
        self._parent = parent
        self._config = config
        self._sandbox = sandbox
        self._skills = skills

    async def delegate(self, definition: SubAgentDefinition, prompt: str) -> str:
        """Run *definition* once over *prompt* and return its conclusion.

        :returns: the sub-agent's closing message when it finished on its
            own; a short note naming it when that message is empty; or,
            when the output limit cut the closing message off, that
            partial text behind a line saying so.
        :raises DelegationIncomplete: the run ended without any closing
            text — it hit its turn ceiling, or the output limit cut it off
            before it wrote a word. The message names the sub-agent and
            the reason, and after a turn ceiling carries the last text the
            sub-agent wrote, if it wrote any. No tool output is ever
            returned or quoted.

        The usage of every model turn of the sub-agent is handed to
        :func:`~omicsclaw.tools.context.report_usage` (``None`` when the
        backend did not report it), so a caller counting a run's tokens
        counts the delegation too.

        Progress is forwarded to whatever the parent turn bound, one line
        per tool the sub-agent starts, so a person watching a long
        delegation sees something other than a stalled tool call. Thought
        tokens and text deltas are not forwarded: what the caller asked
        for is the conclusion.

        No conversation is passed to the child engine, which is the whole
        of the context isolation: there is no path by which the parent's
        history could reach it.
        """
        module = current_context().values.get(REVIEW_MODULE_KEY)
        archive = ReviewArchive(self._config.workspace, module) if isinstance(module, str) else None
        if archive:
            prompt = f"Review module {module}.\n\n{prompt}"
        engine = AgentEngine(
            self._provider.bind(model=definition.model)
            if definition.model
            else self._provider,
            self._child_registry(definition),
            self._engine_config(definition),
        )
        result: RunResult | None = None
        async for event in engine.exchange_stream(
            prompt, prompt=self._child_prompt(definition)
        ):
            if event.type is EngineEventType.TOOL_START and event.tool_call:
                await report_progress(
                    f"[{definition.name}] {event.tool_call.name}",
                    tool_name="task",
                )
            elif event.type is EngineEventType.TURN_END:
                await report_usage(event.usage)
            elif event.result is not None:
                result = event.result
        conclusion = _conclusion(definition.name, result)
        if archive:
            if result is None or result.stop_reason is not StopReason.CONVERGED:
                raise DelegationIncomplete("Only a completed review can be archived for acceptance")
            path = archive.save(conclusion)
            return f"Review saved: {path}\n\n{conclusion}"
        return conclusion

    def _child_registry(self, definition: SubAgentDefinition) -> ToolRegistry:
        """The parent's tools the sub-agent may use, with their policies.

        :returns: the tools :meth:`SubAgentDefinition.resolve_tools` allows,
            minus :data:`_WITHHELD_FROM_SUB_AGENTS`, each registered under
            the policy the parent registry resolved for it.

        The parent's registration order is preserved, so two sub-agents
        with the same tool set present it to the model identically.
        """
        child = ToolRegistry()
        for name in definition.resolve_tools(self._parent.names()):
            if name in _WITHHELD_FROM_SUB_AGENTS:
                continue
            tool: Tool | None = self._parent.get(name)
            if tool is None:
                continue
            child.register(tool, self._parent.policy_for(name))
        return child

    def _engine_config(self, definition: SubAgentDefinition) -> EngineConfig:
        """The parent's budget, with the sub-agent's turn ceiling if it set one."""
        config = self._config.engine_config()
        if definition.max_turns > 0:
            return dataclasses.replace(config, max_turns=definition.max_turns)
        return config

    def _child_prompt(self, definition: SubAgentDefinition) -> ChildPrompt:
        """The sub-agent's prompt, carrying this deployment's own facts.

        The execution-environment description is the same one the parent
        was given, because the sub-agent runs the parent's ``bash``: told
        it is inside a container when the sandbox failed to start, it
        would install packages onto the user's machine.
        """
        return ChildPrompt(
            instructions=definition.system_prompt,
            workspace=str(self._config.workspace),
            environment=_environment_text(self._sandbox),
            skills=definition.skills,
            loader=self._skills.get_full_content if self._skills else None,
        )


def _conclusion(name: str, result: RunResult | None) -> str:
    """What a delegation hands back, read off the child run's result.

    :param name: the sub-agent's name, used in the notes and errors.
    :param result: the child run's result, or ``None`` when none arrived.
    :returns: as described on :meth:`ChildRunner.delegate`.
    :raises DelegationIncomplete: as described on
        :meth:`ChildRunner.delegate`, and when *result* is ``None``.
    """
    if result is None:
        raise DelegationIncomplete(f"sub-agent {name!r} ended without a result")
    closing = _closing_text(result)
    if result.stop_reason is StopReason.CONVERGED:
        return closing or f"[{name}] finished without a final message"
    if result.stop_reason is StopReason.TRUNCATED:
        if closing:
            return (
                f"[{name}] was cut off at the output limit; what it wrote "
                f"before that is incomplete:\n\n{closing}"
            )
        raise DelegationIncomplete(
            f"sub-agent {name!r} was cut off at the output limit before it "
            "wrote a conclusion"
        )
    detail = (
        f"sub-agent {name!r} stopped at the turn limit ({result.turns}) "
        "without a conclusion"
    )
    last = _last_text(result)
    if last:
        detail += f"; the last thing it wrote was:\n\n{last}"
    raise DelegationIncomplete(detail)


def _closing_text(result: RunResult) -> str:
    """The run's last message's text if the sub-agent wrote it, else ``""``."""
    final = result.final_message
    if final is None or final.role is not Role.ASSISTANT:
        return ""
    return final.content if final.content.strip() else ""


def _last_text(result: RunResult) -> str:
    """The most recent non-blank text the sub-agent wrote, or ``""``."""
    for message in reversed(result.messages):
        if message.role is Role.ASSISTANT and message.content.strip():
            return message.content
    return ""


def _warn_withheld(definition: SubAgentDefinition) -> None:
    """Log the names in *definition*'s ``tools:`` that no sub-agent is given.

    One warning per definition, naming each such tool with its reason from
    :func:`_withheld_reasons`; nothing is logged when there are none.
    """
    reasons = _withheld_reasons()
    listed = {name: reasons[name] for name in definition.tools if name in reasons}
    if listed:
        _log.warning(
            "sub-agent %r (%s) lists tools under tools: that no sub-agent is "
            "given, and will run without them: %s",
            definition.name,
            definition.source or "no file",
            _explain(listed),
        )


def _environment_text(binding: SandboxBinding | None) -> str:
    """The parent's execution-sandbox prompt block, or ``""`` when off."""
    if binding is None:
        return ""
    section = sandbox_section(binding)
    if section is None:
        return ""
    return f"{section.heading}\n\n{section.source()}"


def _report(path: Path, error: Exception) -> None:
    """Log one unusable agent file and carry on.

    The file's contents are not logged: an agent file is a system prompt,
    and this package logs no prompt text.
    """
    _log.warning("could not load the sub-agent file %s: %s", path, error)
