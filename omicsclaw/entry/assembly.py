"""The composition root: five layers, wired once, by one function.

Plan 0031 task A. Every layer below this one names a hole in its own
docstring — ``engine/loop.py:34-38`` "the conversation arrives
assembled", ``context/__init__.py`` "``OMICSCLAW.md``, the model table and the
summarizing model are all the composition root's",
``tools/builtin/__init__.py`` "mounting a foundation tool is always a
decision about *which* workspace, and that decision belongs to whoever is
assembling the registry". They are five descriptions of this module.

:func:`build_app` is the only place that knows how the pieces fit. That
is the property worth defending: a second site that builds its own
registry or its own budget is a second deployment nobody configured.

**Three seams the assembly owns, each of which is silent when broken.**

*The two reserves have no defaults.*
:class:`~omicsclaw.context.ContextBudget` requires
``reserve_output_tokens`` and ``reserve_tool_tokens`` as positional
fields, and it requires them because nothing below can compute either:
the first comes from the model table in ``omicsclaw.provider``, the
second from the registry that was just built. See :func:`build_budget`.

*One workspace, six tools.* :func:`foundation_tools` constructs the
:class:`~omicsclaw.tools._workspace.Workspace` once and hands the same
object to every tool that takes one. Two workspaces would not raise —
they would give ``write_file`` and ``read_file`` two different sandbox
roots, and the agent would write a file it then cannot find.

*The registry goes to the engine unwrapped.*
:class:`~omicsclaw.tools.ToolRegistry` satisfies
:class:`~omicsclaw.engine.DeadlineAwareExecutor` and
:class:`~omicsclaw.engine.ConcurrencyAwareExecutor`, both
``runtime_checkable``, and the engine decides by :func:`isinstance`
whether to hand down a
:class:`~omicsclaw.tools.TimeoutPause`. Wrapping the registry for logging
or filtering without forwarding ``use_timeout_pause`` puts defect R3 back
in: a human's thinking time starts counting against the tool timeout
again, on the first layer that ever binds an approval channel. See
:func:`build_registry`.

**This layer is allowed to log, and is the first one that is.** The
logger is ``omicsclaw.entry``; nothing here configures it, so an
unconfigured process gets the root logger's default and warnings and
above are what reach a terminal. Two rules that are not style:
**no tool argument and no tool output is ever logged** — a ``bash``
command line, a ``write_file`` body and a ``web_fetch`` query string can
each carry a subject identifier, and :data:`SAFETY_RULES` rule 1 is
a rule a log statement can break — and no third-party logging library is
introduced.

**How the session registry gets here.** :func:`build_app` still returns
an app whose :attr:`AgentApp.sessions` is ``None``, and it always will:
the registry needs a finished app and the app names the registry, so
:func:`~omicsclaw.entry.session.attach_sessions` ties that knot in one
line with :func:`dataclasses.replace` rather than either object being
built twice. A deployment is therefore
``attach_sessions(await open_app(...))``, and an app that skipped that
call has no queues — :meth:`AgentApp.aclose` has nothing to drain and
``/chat/stream`` raises.

**Skills.** This module imports :mod:`omicsclaw.skills`:
:func:`foundation_tools` appends :func:`~omicsclaw.skills.use_skill_tool`
and :func:`default_sections` adds a skill catalogue section.
``AppConfig.skills_index`` is the switch, and ``off`` drops both. The
prompt is the contract, safety rules and tool guidance, then the
optional planning, execution sandbox and skills sections, the
environment, and the optional long-term memory block;
:func:`default_sections` documents when each optional one appears.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Sequence

from omicsclaw.context import (
    ContextBudget,
    MemoryExtractor,
    PromptAssembler,
    Section,
    Summarizer,
    estimate_tool_tokens,
    static,
    text_from_file,
)
from omicsclaw.engine import AgentEngine
from omicsclaw.hooks import (
    AuditHook,
    HookedTool,
    JsonlAuditSink,
    ToolHook,
    hook_tools,
)
from omicsclaw.mcp import (
    MCPManager,
    ServerState,
    StatusListener,
    load_mcp_config,
)
from omicsclaw.observability import Telemetry, build_telemetry
from omicsclaw.permission import (
    GatedTool,
    PermissionGate,
    PermissionMode,
    RuleStore,
    gate_tools,
)
from omicsclaw.planning import (
    PLAN_WRITE_TOOL_NAME,
    PLANNING_GUIDANCE,
    PLANNING_SECTION_HEADING,
    PlanBook,
    plan_write_tool,
)
from omicsclaw.provider import (
    LLMProvider,
    get_model_limits,
    provider_from_env,
    resolve_config,
)
from omicsclaw.sandbox import ChangeListener
from omicsclaw.schema import Message, Role, ToolDefinition
from omicsclaw.skills import SkillIndex, load_skills, use_skill_tool
from omicsclaw.subagent import TaskTool
from omicsclaw.tools import (
    ApprovalRequest,
    BashTool,
    EditTool,
    Tool,
    ToolRegistry,
    WebFetchTool,
    WebSearchTool,
    Workspace,
    WriteTool,
    read_tool,
)
from omicsclaw.tools.builtin.bash import BashEnvironment

from .config import AppConfig, SkillsIndex
from .memory import (
    MemoryBinding,
    memory_section,
    memory_tools,
    open_memory,
    prepare_memory,
)
from .planning import build_plan_book
from .project import step_runner_line
from .sandbox import (
    SandboxBinding,
    bash_policy,
    open_sandbox,
    sandbox_section,
    unstarted_sandbox,
)
from .skill_env import SkillEnvBinding, build_skill_env, log_skill_env
from .subagent import ChildRunner, build_subagent_registry

if TYPE_CHECKING:  # pragma: no cover - session.py imports this module
    from .session import SessionRegistry

__all__ = [
    "AgentApp",
    "CONTRACT_FILE",
    "LOGGER_NAME",
    "SAFETY_RULES",
    "SHUTDOWN_GRACE_S",
    "TOOL_GUIDANCE",
    "build_app",
    "build_budget",
    "build_hooks",
    "build_prompt",
    "build_registry",
    "build_skill_index",
    "build_summarizer",
    "default_sections",
    "foundation_tools",
    "open_app",
]

LOGGER_NAME = "omicsclaw.entry"
"""Root of this layer's logger tree. Every module here is a child of it,
so one ``logging.getLogger("omicsclaw.entry").setLevel(...)`` moves all
of them and a surface that takes over the terminal can reroute all of
them (the harness does this while its TUI is up, ``tui.go:365-367``)."""

logging.getLogger(LOGGER_NAME).addHandler(logging.NullHandler())
"""A library sets a handler and not a level.

The :class:`~logging.NullHandler` stops "no handlers could be found" from
appearing in a process that never configured logging; the level is left
:data:`~logging.NOTSET` so it is inherited, which for an unconfigured
process is the root logger's ``WARNING``. Calling ``setLevel`` here would
mean this package overrides an operator who already configured logging.
"""

_log = logging.getLogger(__name__)

CONTRACT_FILE = "OMICSCLAW.md"
"""The runtime contract: the agent's identity, operating rules and how it
uses skills. Read from beside the skill tree
(:meth:`~omicsclaw.entry.config.AppConfig.repo_root`) on every render and
placed first in the system prompt; when the file is absent the prompt has
no contract section."""

SHUTDOWN_GRACE_S = 5.0
"""Seconds a running exchange gets after shutdown is asked for.

**A judgement, not a measurement**, and the only number in this module
that is neither derived nor taken from the plan. The constraint it is
sized against is external: a container runtime sends ``SIGTERM`` and then
``SIGKILL`` after its own grace (Docker's default is 10 s), so a value
above that would be spent by a process that is about to be killed
anyway, and the rest of teardown needs room inside it. Whoever wires the
desktop server's ``lifespan`` or the channel runner's signal handler
should replace this with what those two actually get.
"""

SAFETY_RULES = """\
1. Genetic data never leaves this machine — all processing is local.
2. Every report, meaning each module's REPORT file and any summary of \
results you give, includes this disclaimer verbatim: "OmicsClaw is a \
research and educational tool for multi-omics analysis. It is not a \
medical device and does not provide clinical diagnoses. Consult a \
domain expert before making decisions based on these results."
3. When a skill does not give a parameter, threshold or cutoff, write \
the value you chose and the reason for it in the step. Never invent \
gene associations.
4. Warn before overwriting existing results, and tell the user before \
revising an accepted module."""
"""The agent's safety rules, and the only copy of them.

:data:`CONTRACT_FILE` does not repeat these rules. They are a constant
rather than text read from a file, so their section is always in the
prompt: a renamed heading or a missing file cannot drop it.
"""

TOOL_GUIDANCE = """\
- Prefer the tool that answers a question exactly: read a file with \
read_file rather than `cat` under bash.
- Every path is resolved inside the workspace sandbox; a path that \
leaves it is refused, not clamped.
- A tool that asks for approval is waiting on a person. Its reported \
duration includes that wait.
- A failed tool call is information, not an ending: read the error and \
correct the call."""
"""Static guidance about the six foundation tools.

Short because the tool definitions carry their own descriptions and
repeating them here would be two sources for one fact. What is here is
what a definition cannot say: the relationship *between* tools, and that
the sandbox refuses rather than clamps.
"""


def build_skill_index(config: AppConfig) -> SkillIndex:
    """Scan the workspace's skills once.

    Called once per :func:`build_app` and shared by the prompt section
    and the ``use_skill`` tool, so the catalogue the model is shown and
    the catalogue it can load are the same object. A missing directory
    yields an empty index.

    Returns an empty index without scanning when
    :attr:`~omicsclaw.entry.config.AppConfig.skills_index` is ``off``.
    """
    if config.skills_index is SkillsIndex.OFF:
        return SkillIndex(root=config.skills_root())
    index = load_skills(config.skills_root())
    if index.skipped:
        _log.warning(
            "%d skill file(s) under %s were not indexed; first: %s (%s)",
            len(index.skipped),
            config.skills_root(),
            index.skipped[0].path,
            index.skipped[0].reason,
        )
    return index


def foundation_tools(
    config: AppConfig,
    *,
    skills: SkillIndex | None = None,
    bash_environment: BashEnvironment | None = None,
    plans: PlanBook | None = None,
    memory: MemoryBinding | None = None,
    skill_env: SkillEnvBinding | None = None,
) -> tuple[Tool, ...]:
    """The six foundation tools, sharing one workspace, plus ``use_skill``.

    **This is the only place a :class:`~omicsclaw.tools._workspace.Workspace`
    is constructed**, which is the whole point: the four filesystem tools
    get the identical object, so there is no arrangement of arguments
    under which ``write_file`` writes somewhere ``read_file`` cannot
    look. ``web_fetch`` and ``web_search`` take none — their boundary is
    a destination, not a path — and that asymmetry is theirs, not an
    omission here.

    ``bash`` is constructed with :meth:`AppConfig.bash_timeout`, which is
    the derived half of the single timeout source. Its own
    ``max_timeout`` is that construction argument, so this call is what
    lets the model request the longer runs a deconvolution needs.

    ``use_skill`` is mounted last and only when the catalogue is actually
    advertised: it is the half of progressive disclosure that fetches,
    and a fetch tool for an index nobody was shown is a tool the model
    cannot name an argument for. Pass *skills* to share one scan with
    :func:`default_sections`; ``None`` scans again.

    *bash_environment* is where ``bash`` runs — a started sandbox's
    environment — and ``None`` means this machine. Only ``bash`` takes
    it: the file tools share the workspace, which the sandbox mounts at
    the same path.

    *plans* mounts ``plan_write`` over one book; ``None`` leaves it out.
    The book rather than a store, because this list is built once per
    deployment and a plan belongs to a session — the tool resolves which
    at call time. It is mounted **after** ``use_skill`` and last overall,
    so adding it does not move any earlier tool inside the byte-stable
    list a cached prompt prefix depends on (plan 0028).

    *memory* mounts ``memory_search`` and ``memory_write`` over one open
    memory database; ``None`` leaves both out. They go after
    ``plan_write`` for the same byte-stability reason: a pair appended at
    the end costs a cached prefix nothing, a pair inserted in the middle
    moves every tool after it.

    *skill_env* gives ``use_skill`` its environment-check callback, which
    changes what that tool returns and not which tools there are; when it
    carries ``install_skill_deps`` (``skill_env=install`` with ``bash`` on this
    machine), that tool is appended last.
    """
    workspace = Workspace(config.workspace)
    tools: tuple[Tool, ...] = (
        read_tool(workspace),
        WriteTool(workspace),
        EditTool(workspace),
        BashTool(
            workspace,
            timeout=config.bash_timeout(),
            environment=bash_environment,
        ),
        WebFetchTool(),
        WebSearchTool(),
    )
    if config.skills_index is not SkillsIndex.OFF:
        index = build_skill_index(config) if skills is None else skills
        annotate = skill_env.annotate if skill_env is not None else None
        tools = (*tools, use_skill_tool(index, annotate=annotate))
    if plans is not None:
        tools = (*tools, plan_write_tool(plans))
    if memory is not None:
        tools = (*tools, *memory_tools(memory))
    if skill_env is not None and skill_env.tool is not None:
        tools = (*tools, skill_env.tool)
    return tools


def build_permission_gate(config: AppConfig) -> PermissionGate:
    """The session's permission posture, over the rule file it names.

    A :class:`~omicsclaw.permission.RuleStore` rather than a fixed
    :class:`~omicsclaw.permission.Rules`, because a store re-reads its file
    on every call and that is what makes "always allow" take effect on the
    *next* tool call instead of the next process. The file need not exist: a
    missing one is an empty rule set, so the default costs nothing until
    somebody writes a rule.

    **A malformed rule file stops the app from starting**, here, rather than
    surfacing on the first ``bash`` call halfway through an analysis. That
    is :class:`~omicsclaw.permission.RuleStore`'s doing and this is where it
    is paid for — a security file with a typo in it is a control the
    operator believes is in force.
    """
    return PermissionGate(
        mode=config.permission_mode,
        rules=RuleStore(config.permission_rules_path()),
    )


def build_hooks(
    config: AppConfig, telemetry: Telemetry | None = None
) -> tuple[ToolHook, ...]:
    """The tool hooks this deployment asked for. Usually none.

    Returns an **empty tuple unless something switched a hook on**, and
    :func:`~omicsclaw.hooks.hook_tools` wraps nothing when handed one —
    so the default deployment's object graph is exactly what it was
    before :mod:`omicsclaw.hooks` existed. That is the property that
    makes adding this seam cheap to reason about: a regression in a
    deployment that mounts no hooks cannot be this package's.

    Today the only switch is :attr:`~omicsclaw.entry.AppConfig.audit_log`,
    which mounts an :class:`~omicsclaw.hooks.AuditHook` over a
    :class:`~omicsclaw.hooks.JsonlAuditSink`. A deployment wanting
    anything else — an OTEL sink, a domain guard — passes its own chain
    to :func:`build_app`; this function is the *configured* chain, not
    the only one.

    **Order is what this function decides**, and the two shipped hooks
    sit at opposite ends. The audit hook goes first on purpose: a chain
    closes in reverse, so the first hook mounted is the one still
    listening when a later hook refuses a call. *telemetry*'s tracing
    hook — present only when observability is active — is appended
    **last**, so its span measures the tool and not its neighbours; see
    :class:`~omicsclaw.observability.TracingHook`, which argues both
    positions together. This is also the reference harness's chain order
    (``cmd/harness9/main.go:411-416``).
    Mounted last it would never record a refusal. See
    :class:`~omicsclaw.hooks.AuditHook`.
    """
    hooks: list[ToolHook] = []
    if config.audit_log is not None:
        hooks.append(AuditHook(JsonlAuditSink(config.audit_log)))
    if telemetry is not None:
        hooks.extend(telemetry.tool_hooks())
    return tuple(hooks)


def build_registry(
    config: AppConfig,
    tools: Sequence[Tool] | None = None,
) -> ToolRegistry:
    """A registry over *tools*, or over the six foundation tools.

    Returns the :class:`~omicsclaw.tools.ToolRegistry` **itself**, and
    :func:`build_app` hands that object straight to
    :class:`~omicsclaw.engine.AgentEngine`. Nothing between them is
    allowed to wrap it unless the wrapper forwards
    ``use_timeout_pause`` and ``is_concurrency_safe``: both Protocols are
    ``runtime_checkable`` and the engine tests them with
    :func:`isinstance` in two separate places —
    ``engine/executor.py:379`` for ``DeadlineAwareExecutor`` and
    ``:326-327`` for ``ConcurrencyAwareExecutor`` — so a wrapper that
    forgets one does not fail. It quietly stops the timeout pause being
    handed down, and a human's approval time is charged to the tool's
    deadline again. That is defect R3, and this layer is the first thing
    in the rebuild that binds an approval channel at all.

    *tools* is how hooks, permission wrappers, MCP tools and a
    sub-agent's narrowed set all arrive later without this function
    changing (plan 0031 Q13). The same obligation applies to anything
    passed in.
    """
    return ToolRegistry(foundation_tools(config) if tools is None else tools)


def _environment_source(config: AppConfig) -> Section:
    """The one section whose text changes on its own.

    **The date is a date, never a timestamp.** DeepSeek and OpenAI cache
    by byte-exact prefix (ADR 0024), so the system prompt's cache value
    survives exactly as long as its bytes do: a date invalidates once a
    day, a clock reading invalidates every single turn. The harness
    injects the current date for a different reason it states outright
    (**harness9's** ``AGENTS.md:462``, the ``context`` row — not this
    repository's file of the same name) — a model whose training cut off
    earlier will
    otherwise reason and search as if it were still then — and that
    reason is why the field is here at all.

    Rendered fresh each turn, like every other section: a process that
    runs past midnight tells the model the new date. When the skill tree
    has a step runner, the section ends with the command that calls it;
    the contract refers to that line instead of naming a path.
    """

    def read() -> str:
        lines = [
            f"- Workspace: {config.workspace}",
            f"- Platform: {platform.system()} ({sys.platform})",
            f"- Today: {date.today().isoformat()}",
        ]
        runner = step_runner_line(config)
        if runner is not None:
            lines.append(runner)
        return "\n".join(lines)

    return Section("environment", "## Environment", read)


def _front_matter(config: AppConfig) -> tuple[Section, ...]:
    """The contract beside the skill tree, or the configured prompt files instead.

    A missing file contributes no section.
    """
    if config.system_prompt_files:
        return tuple(
            Section(f"prompt:{path.name}", "", text_from_file(path))
            for path in config.system_prompt_files
        )
    return (
        Section("contract", "", text_from_file(config.repo_root() / CONTRACT_FILE)),
    )


def _skills_section(config: AppConfig, index: SkillIndex) -> Section:
    """The catalogue block: one line per skill, or per domain.

    The body is produced on every render from *index*, which is a
    snapshot of one scan. A skill written by the agent mid-run therefore
    does not appear until the next scan; a deployment that needs it to
    passes ``sections=`` with a closure over
    :func:`~omicsclaw.skills.load_skills` instead.
    """
    compact = config.skills_index is SkillsIndex.COMPACT

    def read() -> str:
        return index.prompt_body(compact=compact)

    return Section("skills", "## Available skills", read)


def default_sections(
    config: AppConfig,
    *,
    skills: SkillIndex | None = None,
    sandbox: SandboxBinding | None = None,
    plan_tool: bool = True,
    memory: MemoryBinding | None = None,
) -> tuple[Section, ...]:
    """The sections of the default system prompt, in render order.

    contract → **safety rules** → tool guidance →
    [planning] → [execution sandbox] → [skills] → environment →
    [long-term memory].
    ``omicsclaw.context`` has no ``order`` field by ruling (plan 0030),
    so arrival order *is* render order and this tuple is where that order
    is decided.

    Planning sits directly after the tool guidance and before the two
    blocks that vary. It is static text about how to work, which is what
    the guidance above it is, and the ordering principle the skills
    section established is that the volatile blocks go last so an edited
    one invalidates as little of the cached prefix as possible.

    *plan_tool* says whether ``plan_write`` is actually mounted. It
    defaults to true because :func:`foundation_tools` mounts it whenever
    :attr:`~omicsclaw.entry.config.AppConfig.planning` is on, and a
    caller passing ``tools=`` to :func:`build_app` should pass ``False``
    unless it mounted one itself — a prompt instructing the model to use
    a tool that is not there costs turns on a capability the deployment
    does not have.

    **The catalogue section is absent with ``skills_index=off``.** Plan 0031 Q10 and
    §12-1 ruled the catalogue out of this step because this repository's
    skills were being redesigned; ``docs/plans/0032-skill-loader.md``
    landed after that and put it back. The reasoning behind the original
    ruling survives as the ``off`` switch: a model hunting for a skill
    that no longer exists is harder to diagnose than a model that was
    never told skills exist, so a deployment mid-migration turns the
    block off rather than shipping a stale directory.

    Pass *skills* to share one scan with :func:`foundation_tools`;
    ``None`` scans again.

    Pass *sandbox* to add an "Execution sandbox" section after the tool
    guidance, saying where ``bash`` runs — or that a requested sandbox is
    not running. A sandbox that is off adds nothing.

    Pass *memory* to add the long-term memory block, and note that it
    goes **after** the environment rather than before it. It is the most
    volatile block in the prompt — ``memory_write`` rewrites it
    mid-session, where the environment block only turns over at midnight
    — and the last block is the one whose edit invalidates the least of
    a cached prefix.

    A missing file yields ``""`` and takes its whole section with it
    (``text_from_file``), so a deployment with no ``OMICSCLAW.md`` beside
    its skill tree gets a prompt with no contract section.
    An empty skill index does the same. The safety, guidance and
    environment sections are not files and cannot vanish that way.
    """
    catalogue: tuple[Section, ...] = ()
    if config.skills_index is not SkillsIndex.OFF:
        index = build_skill_index(config) if skills is None else skills
        catalogue = (_skills_section(config, index),)

    execution: tuple[Section, ...] = ()
    described = sandbox_section(sandbox) if sandbox is not None else None
    if described is not None:
        execution = (described,)

    planning: tuple[Section, ...] = ()
    if config.planning and plan_tool:
        planning = (
            Section(
                "planning",
                PLANNING_SECTION_HEADING,
                static(PLANNING_GUIDANCE),
            ),
        )

    remembered: tuple[Section, ...] = ()
    if memory is not None:
        remembered = (memory_section(memory),)

    return (
        *_front_matter(config),
        Section("safety", "## Safety rules", static(SAFETY_RULES)),
        Section("tools", "## Tool guidance", static(TOOL_GUIDANCE)),
        *planning,
        *execution,
        *catalogue,
        _environment_source(config),
        *remembered,
    )


def build_prompt(sections: Sequence[Section]) -> PromptAssembler:
    """Fold *sections* into an assembler, preserving order.

    Returns the **assembler**, not one render of it. The distinction is
    the difference between a prompt that is rebuilt every turn and one
    that was frozen at process start: only the assembler has
    :meth:`~omicsclaw.context.PromptAssembler.render`, and only calling
    it again picks up an edited ``OMICSCLAW.md`` or tomorrow's date.
    Holding an
    :class:`~omicsclaw.context.AssembledPrompt` on
    :class:`AgentApp` instead would compile, run, and silently stop doing
    any of that.
    """
    assembler = PromptAssembler()
    for section in sections:
        assembler = assembler.with_section(section)
    return assembler


def build_budget(
    model: str,
    tools: Sequence[ToolDefinition],
) -> ContextBudget:
    """The window, and the two reserves carved out of it.

    Neither reserve has a default, and neither could: the output reserve
    is the model table's answer for *this* model and the tool reserve is
    what *this* registry's declarations cost. A default would be a number
    that is wrong for every deployment except the one it was measured on.

    An empty *model* gets
    :data:`~omicsclaw.provider.DEFAULT_MODEL_LIMITS`, whose
    ``output_tokens=8192`` means "unknown" rather than "8192" — an
    optimistic answer, recorded as debt in plan 0031 §11-2 and warned
    about here because this layer is the first that ever asks.
    """
    limits = get_model_limits(model)
    if not model:
        _log.warning(
            "no model named; budgeting against the default limits "
            "(%d context / %d output tokens), which mean 'unknown'",
            limits.context_tokens,
            limits.output_tokens,
        )
    return ContextBudget(
        context_tokens=limits.context_tokens,
        reserve_output_tokens=limits.output_tokens,
        reserve_tool_tokens=estimate_tool_tokens(tools),
    )


@dataclass(frozen=True, slots=True)
class _ProviderSummarizer:
    """A provider, narrowed to the one call compaction makes of it.

    Satisfies :class:`~omicsclaw.context.Summarizer` structurally. The
    five lines are the "explicit adapter" that Protocol's docstring asks
    for: they are where *no tools* and *a different model* are decided,
    and both are composition-root decisions rather than properties of
    summarization.
    """

    provider: LLMProvider
    timeout_s: float

    async def summarize(self, prompt: str, *, system: str) -> str:
        """One summary, or ``""`` if it took too long.

        **The timeout lives here and not around
        :func:`~omicsclaw.context.compact`** (plan 0031 Q11).
        ``compact`` degrades when the summarizer *fails* — it catches the
        exception and falls back to truncation, recording why in
        ``record.degraded``. An :func:`asyncio.timeout` wrapped around
        ``compact`` instead raises out of it, so the turn gets no
        compaction whatsoever. Both spellings survive a test that only
        asserts "it did not hang"; only this one degrades.

        Returning ``""`` rather than raising is what reaches that
        fallback: ``compact`` treats a summary with neither anchors nor
        text as structurally empty and truncates instead, which is the
        same outcome by a shorter path. Every other failure is left to
        propagate — ``compact`` catches those too, and a provider error
        deserves to appear in ``degraded`` with its own name on it.

        ``tools=None`` strips tools rather than meaning "the usual set"
        (``LLMProvider.generate``); a summarizer that could call tools is
        a summarizer that can act.
        """
        messages = (
            Message(role=Role.SYSTEM, content=system),
            Message(role=Role.USER, content=prompt),
        )
        try:
            async with asyncio.timeout(self.timeout_s):
                completion = await self.provider.generate(messages, None)
        except TimeoutError:
            _log.warning(
                "summary abandoned after %.1fs; compaction will truncate",
                self.timeout_s,
            )
            return ""
        return completion.message.content


def build_summarizer(
    provider: LLMProvider,
    config: AppConfig,
) -> Summarizer:
    """Wrap *provider* as the thing compaction is allowed to call.

    ``summary_model`` selects a second, usually cheaper model through
    :meth:`~omicsclaw.provider.LLMProvider.bind`, which returns a copy —
    two binds of one provider cannot observe each other, so the main
    conversation's configuration is untouched. An empty ``summary_model``
    reuses the provider as given rather than binding ``model=""``.
    """
    if config.summary_model:
        summarizing = provider.bind(model=config.summary_model)
    else:
        summarizing = provider
    return _ProviderSummarizer(summarizing, config.summary_timeout_s)


@dataclass(frozen=True, slots=True)
class AgentApp:
    """One assembled deployment: five layers, already wired.

    Frozen, and every field is something built once at start-up. The
    per-turn state — history, compaction state, the queue — belongs to
    :class:`~omicsclaw.entry.session.SessionRegistry`, which is the one
    field here that owns anything mutable — besides :attr:`mcp`, whose
    connections :meth:`aclose` closes, and :attr:`permission`, whose mode
    an operator can switch with :meth:`set_permission_mode`. That makes
    :attr:`config`'s ``permission_mode`` the *start-up* value: read the
    live one from ``permission.mode``.

    A test that needs a scripted provider passes it to
    :func:`build_app` as ``provider=``, which puts it under every
    consumer at once. See :func:`build_app`.
    """

    provider: LLMProvider
    """The backend. Bound once; per-request variation goes through
    :meth:`~omicsclaw.provider.LLMProvider.bind`, never by mutation."""

    registry: ToolRegistry
    """**The object the engine got**, not a view of it.

    Typed as the concrete :class:`~omicsclaw.tools.ToolRegistry` rather
    than as ``ToolExecutor`` for a reason that is checkable: the engine
    asks ``isinstance(executor, DeadlineAwareExecutor)`` and
    ``isinstance(executor, ConcurrencyAwareExecutor)`` before it hands
    down a timeout pause or schedules a barrier. Substituting anything
    that does not answer both is how a human's approval wait starts
    counting against ``tool_timeout`` again — the R3 defect the tool
    layer just finished repairing. ``test_assembly.py`` asserts both
    :func:`isinstance` checks on this field; removing that assertion is
    removing the only thing that notices."""

    engine: AgentEngine
    """Built over :attr:`provider`, :attr:`registry` and
    :meth:`AppConfig.engine_config`."""

    prompt: PromptAssembler
    """The **assembler**. ``render()`` is on it;
    :class:`~omicsclaw.context.AssembledPrompt` has only properties. A
    turn calls ``app.prompt.render()`` every time, which is what makes an
    edited ``OMICSCLAW.md`` and a new day visible."""

    tools_snapshot: tuple[ToolDefinition, ...]
    """``registry.available_tools()``, taken once.

    Stable bytes are the point: the tool half of the cached prefix is
    byte-stable by ruling (plan 0028), so a snapshot is both cheaper and
    more correct than re-deriving the list per turn. It follows that
    injecting tools mid-session invalidates that prefix, which is the
    cost MCP will have to weigh (plan 0031 Q13)."""

    budget: ContextBudget
    """What :func:`~omicsclaw.context.measure` measures against. Note
    that a turn must use ``report.budget`` downstream, not this object:
    ``measure`` returns whichever of the two is tighter."""

    summarizer: Summarizer | None
    """What compaction calls. ``None`` is legal and means compaction
    degrades to truncation every time — ``compact`` records that in
    ``record.degraded`` rather than failing."""

    config: AppConfig
    """The deployment this was built from, kept so a turn can read
    ``compact_at``, ``turn_timeout_s`` and ``approval_timeout_s`` without
    a second resolution."""

    skills: SkillIndex = field(default_factory=SkillIndex)
    """The one scan the prompt section and ``use_skill`` both read.

    Kept on the app so a surface can report what was loaded, and so
    ``app.skills.skipped`` is answerable without scanning again. Empty
    when ``skills_index=off`` or when the directory does not exist."""

    sessions: "SessionRegistry | None" = None
    """Conversations, their queues, and one task per running exchange.

    Lives in ``omicsclaw/entry/session.py`` and is annotated as a string
    under :data:`typing.TYPE_CHECKING`, because that module imports this
    one and the arrow may not point both ways.

    ``None`` as :func:`build_app` leaves it, and **not** a stage this
    field is waiting to leave: the registry is attached afterwards by
    :func:`~omicsclaw.entry.session.attach_sessions`, since it needs the
    finished app. ``None`` therefore means *this app was never attached*,
    which is legal — :func:`~omicsclaw.entry.turn.run_turn` drives one
    exchange against a caller-held history and needs only the prompt, the
    budget and the engine."""

    plans: PlanBook | None = None
    """One execution plan per session, and where ``plan_write`` writes.

    ``None`` means this deployment has no planning — either
    :attr:`~omicsclaw.entry.config.AppConfig.planning` is off, or a
    caller supplied its own tool list without a ``plan_write`` in it.
    :func:`~omicsclaw.entry.planning.build_injector` returns ``None`` for
    such an app, so nothing is injected and the prompt says nothing about
    planning: the three halves move together or not at all.

    The book is the object, not a snapshot of it. Asking it for a
    session's store is what restores that session's plan from disk, so
    reading this field is also the recovery path — see
    :meth:`~omicsclaw.planning.PlanBook.for_session`."""

    mcp: MCPManager | None = None
    """The connected MCP servers whose tools are in :attr:`registry`.

    ``None`` when the app was built without MCP. Its
    :meth:`~omicsclaw.mcp.MCPManager.statuses` say which servers connected
    and which failed."""

    sandbox: SandboxBinding | None = None
    """Where ``bash`` runs: a started container, a requested one that is
    not running (:attr:`~SandboxBinding.degraded`), or off. Always set by
    :func:`build_app`. Its container is removed by :meth:`aclose`."""

    memory_extractor: MemoryExtractor | None = None
    """Reads the messages a compaction summary is about to replace, to keep
    what outlives them.

    **An override, and ``None`` does not mean nothing is extracted.**
    :func:`~omicsclaw.entry.compaction.build_compactor` builds one from
    :attr:`memory` and :attr:`summarizer` whenever this is ``None``, which
    is what makes an app with memory on extract without anyone setting
    this. Set it to send extraction through something else — a second
    model, a recorder, a stub — and that object is used instead."""

    memory: MemoryBinding | None = None
    """The open memory database, and the two views built over it.

    ``None`` when :attr:`~omicsclaw.entry.config.AppConfig.memory` is off
    or the app was constructed directly. It is what
    :attr:`memory_extractor` writes into, what ``memory_search`` and
    ``memory_write`` reach, what the long-term memory prompt section
    renders, and what :func:`~omicsclaw.entry.session.attach_sessions`
    resumes conversations from — one database behind all four. Its
    connection is closed by :meth:`aclose`."""

    skill_env: SkillEnvBinding | None = None
    """The environment check behind ``use_skill``'s note, or ``None`` when it is
    off, when ``skills_index`` is off, or when the caller supplied its own tools."""

    telemetry: Telemetry = field(default_factory=Telemetry)
    """This deployment's recorder. **Never ``None``.**

    The default :class:`~omicsclaw.observability.Telemetry` records
    nothing, wraps nothing and mounts nothing, so a surface writes
    ``app.telemetry.run(...)`` unconditionally and no call site in
    ``entry/`` branches on whether observability is configured. See
    :mod:`omicsclaw.observability` for what that buys.

    Closed by :meth:`aclose`, after everything that might still be
    producing spans."""

    permission: PermissionGate | None = None
    """The gate in front of every tool in :attr:`registry`.

    Kept on the app for two things a surface cannot do without it: report
    the posture it is running under, and honour "always allow" through
    :meth:`~omicsclaw.permission.PermissionGate.remember`. Reading it is not
    how the gate takes effect — that happens inside each
    :class:`~omicsclaw.permission.GatedTool` — so a surface that ignores this
    field is still gated.

    ``None`` only in an app constructed directly rather than through
    :func:`build_app`, which always sets it — including for tools a caller
    passed in, because a deployment that adds a tool of its own is the case
    where losing the gate would be least visible."""

    def set_permission_mode(self, mode: PermissionMode) -> PermissionMode | None:
        """Switch the gate between ``default`` and ``auto-approve``.

        Returns the previous mode, or ``None`` when this app has no gate.
        Raises :exc:`ValueError` for any other transition: ``read-only`` is
        a promise a deployment made ("read this cohort, change nothing") and
        ``bypass-all`` one for an environment with nobody attached, and a
        command typed mid-session must neither make nor break either. The
        rule lives here rather than in a surface because every surface
        shares this object —— a Channel's many chats share one app.

        Logged at ``WARNING`` every time: the audit log records calls, not
        the posture they ran under, and afterwards the question "was this
        one asked about?" needs this line to answer.
        """
        if self.permission is None:
            return None
        target = PermissionMode(mode)
        current = self.permission.mode
        switchable = {PermissionMode.DEFAULT, PermissionMode.AUTO_APPROVE}
        if current not in switchable or target not in switchable:
            raise ValueError(
                f"the permission mode can only move between default and "
                f"auto-approve in a running session, not {current.value} -> "
                f"{target.value}; restart with --permission-mode instead"
            )
        previous = self.permission.set_mode(target)
        if previous is not target:
            _log.warning(
                "permission mode switched by the operator: %s -> %s",
                previous.value,
                target.value,
            )
        return previous

    def remember_approval(self, request: ApprovalRequest) -> str | None:
        """Persist an ``allow`` rule for exactly the call *request* describes.

        What a surface calls when a person answers "always allow". Returns
        the rule pattern that was written, or ``None`` when nothing was: no
        gate on this app, no rule file configured, or no tool of that name
        mounted.

        Lives here rather than on the gate because the pattern has to be
        matched against the same argument the gate will extract later, and
        that depends on the tool's own schema — which this object can look
        up and a surface should not have to.
        """
        if self.permission is None:
            return None
        tool = self.registry.get(request.tool_name)
        if tool is None:
            return None
        return self.permission.remember(
            request.tool_name,
            request.arguments,
            schema=tool.definition().input_schema,
            policy=self.registry.policy_for(request.tool_name),
        )

    def can_remember_approval(self, request: ApprovalRequest) -> bool:
        """Whether "always allow" could ever take effect for *request*.

        ``False`` for a call that changes a protected file —— the rule file,
        ``.omicsclaw/``, a ``.env`` —— which the gate decides before it
        reads any rule. Writing an ``allow`` rule for one would be reported
        as remembered and never consulted, and the next identical call
        would be asked about anyway; a surface uses this to not offer it.
        """
        if self.permission is None:
            return True
        tool = self.registry.get(request.tool_name)
        if tool is None:
            return True
        return not self.permission.protects(
            request.arguments,
            policy=self.registry.policy_for(request.tool_name),
            schema=tool.definition().input_schema,
        )

    async def aclose(self) -> None:
        """Stop accepting work, let what is running finish, then let go.

        The harness's ``main.go`` has five ``defer``s for this and this
        rebuild has one thing to release, so the whole of shutdown is
        delegating to the registry: stop admitting exchanges, give the
        running ones :data:`SHUTDOWN_GRACE_S`, then cancel and *reap* —
        an un-awaited cancelled task prints "Task exception was never
        retrieved" into a log nobody is reading by then.

        A CLI that exits after one answer can get away without this. The
        two long-lived surfaces cannot: a desktop server closes this from
        its ASGI ``lifespan``, and a channel runner closes it on
        ``SIGTERM``, which is how a container asks a process to stop.

        The MCP servers, the sandbox container and the memory database are
        closed **after** the sessions drain, so a tool call still running
        inside the grace period keeps its connection, its container and a
        writable memory until it finishes. The provider and the registry
        own nothing to close.

        Draining is skipped while :attr:`sessions` is ``None``: a turn
        driven directly through :func:`~omicsclaw.entry.turn.run_turn` is
        owned by its caller.
        """
        try:
            if self.sessions is not None:
                await self.sessions.shutdown(SHUTDOWN_GRACE_S)
        finally:
            try:
                if self.mcp is not None:
                    await self.mcp.aclose()
            finally:
                try:
                    if self.sandbox is not None:
                        await self.sandbox.aclose()
                finally:
                    try:
                        if self.memory is not None:
                            self.memory.close()
                    finally:
                        # Last, and after the sessions drained: a tool
                        # still finishing inside the grace period is still
                        # writing spans, and a backend shut down before it
                        # loses exactly the records of the shutdown.
                        await self.telemetry.aclose()


def build_app(
    config: AppConfig,
    *,
    tools: Sequence[Tool] | None = None,
    hooks: Sequence[ToolHook] | None = None,
    sections: Sequence[Section] | None = None,
    mcp: MCPManager | None = None,
    sandbox: SandboxBinding | None = None,
    telemetry: Telemetry | None = None,
    skills: SkillIndex | None = None,
    provider: LLMProvider | None = None,
) -> AgentApp:
    """Wire one deployment. The only function that knows the order.

    **Connects no MCP server.** *mcp* is an already-started
    :class:`~omicsclaw.mcp.MCPManager`; its tools are mounted after the
    others and it is kept on the app so :meth:`AgentApp.aclose` can close
    it. :func:`open_app` reads :meth:`AppConfig.mcp_config_path` and is the
    entry point a surface should call.

    ``tools=None`` mounts the six foundation tools on one workspace, plus
    ``use_skill`` unless ``skills_index=off``; ``sections=None`` builds
    the default prompt :func:`default_sections` describes. Both
    parameters exist so that three later things need no change here: a
    test can describe a whole app without touching the environment, a
    migration can add a tool by passing it, and a sub-agent is this same
    call with a narrower list.

    ``hooks=None`` takes the chain :func:`build_hooks` reads from the
    configuration, which is empty unless
    :attr:`~omicsclaw.entry.AppConfig.audit_log` is set; an explicit
    sequence replaces it, and ``()`` is how a caller says *no hooks even
    though the configuration asked for some*. The chain goes on **inside**
    the permission gate — see :mod:`omicsclaw.hooks` for the two
    consequences, of which the one to know is that a hook rewriting a
    tool's arguments is not re-judged by the gate.

    ``telemetry=None`` resolves one from the ``OTEL_*`` environment
    through :func:`~omicsclaw.observability.build_telemetry`, which is
    inactive unless ``OTEL_ENABLED=true``. Pass one to build a deployment
    that does not read the environment. An inactive
    :class:`~omicsclaw.observability.Telemetry` hands the provider back
    unwrapped and contributes no hook, so the object graph is exactly
    what it was before that layer existed.

    **``sessions`` is left ``None`` and stays that way.** The registry
    holds the app and the app names the registry, so it cannot be built
    here without building one of them twice;
    :func:`~omicsclaw.entry.session.attach_sessions` resolves that in one
    line afterwards and returns a *new* app. Do not replace the
    ``sessions=None`` below with a constructor — that is the mistake the
    circular reference is there to prevent.

    *provider* is the backend to use instead of
    :func:`~omicsclaw.provider.provider_from_env`. ``None`` builds one
    from the configuration and the environment. A provider passed here
    takes that one's place, so every consumer gets it: the telemetry
    wrapper, the summarizer, the sub-agent runner and the engine. The model name used for the context budget still comes
    from :func:`~omicsclaw.provider.resolve_config` over
    ``config.provider`` and ``config.model``, whatever *provider* is.
    This is how a test or an eval drives a whole deployment with a
    scripted backend.

    *skills* is the skill index to use instead of scanning again.

    **Starts no sandbox either.** *sandbox* is a binding from
    :func:`~omicsclaw.entry.sandbox.open_sandbox`; ``bash`` is built over
    its environment and the prompt says where ``bash`` runs. Without one,
    a configuration that asks for a sandbox is reported degraded — or
    refused with :exc:`~omicsclaw.sandbox.SandboxError` when
    ``sandbox_required`` is set. ``sandbox_auto_approve`` applies only to
    the ``bash`` built here, never to one passed in *tools*.

    **It does open the memory database**, unlike the two above, because
    opening a SQLite file needs no event loop and no process. The
    connection belongs to the returned app and is closed by
    :meth:`AgentApp.aclose`; a raise on the way out closes it here
    instead. What it does *not* do is the start-up maintenance that
    database wants — :func:`~omicsclaw.entry.memory.prepare_memory` is
    ``async`` and :func:`open_app` is what runs it.
    """
    binding = unstarted_sandbox(config) if sandbox is None else sandbox
    # Telemetry is resolved before the provider, because the provider is
    # the first thing it wraps. ``build_telemetry`` reads the OTEL_*
    # environment itself, the way ``provider_from_env`` reads its
    # credentials; an inactive one wraps nothing and the object graph
    # below is unchanged.
    observing = build_telemetry() if telemetry is None else telemetry
    # The model the provider will actually call, not the one the config
    # named: ``LLM_PROVIDER=deepseek`` alone leaves ``config.model`` empty
    # and runs the preset's default, and budgeting against ``""`` would
    # be the fallback window instead of that model's.
    model = resolve_config(config.provider, config.model).model
    backend = (
        provider_from_env(config.provider, config.model)
        if provider is None
        else provider
    )
    provider = observing.trace_provider(backend, model=model)
    # One scan, two consumers: the prompt advertises exactly what the
    # tool can load. Two scans would drift the moment a skill is written
    # between them.
    if skills is None:
        skills = build_skill_index(config)
    plans = build_plan_book(config)
    checking = build_skill_env(config, skills, binding) if tools is None else None
    # One database, four consumers: the two tools, the prompt section,
    # the extractor — and, once attach_sessions runs, the conversations.
    # A second open would be a second connection to the same file, and
    # nothing would close it.
    remembering = open_memory(config)
    try:
        if tools is None:
            mounted: Sequence[Tool] = foundation_tools(
                config,
                skills=skills,
                bash_environment=binding.environment,
                plans=plans,
                memory=remembering,
                skill_env=checking,
            )
        else:
            mounted = tools
        if mcp is not None:
            mounted = (*mounted, *mcp.tools())
        # What is mounted decides whether this deployment plans — not what
        # the configuration asked for. A caller that supplied its own tools
        # and left ``plan_write`` out gets no planning section and no
        # injected block, so the prompt cannot instruct the model to call a
        # tool that is not in the registry. The check is before the gate
        # because a GatedTool forwards the name it wraps and reading it
        # through the wrapper would be relying on that.
        if plans is not None and not any(
            tool.name == PLAN_WRITE_TOOL_NAME for tool in mounted
        ):
            plans = None
        # Hooks go on before the gate, so the gate ends up outside them:
        # permission resolves first and a call a rule denied never reaches
        # a hook, which is the reference harness's chain order
        # (main.go:413, permission hook first, observability last). The
        # consequence to know is on HookDecision.arguments — a hook that
        # rewrites a payload is not re-judged, because the gate already
        # decided. With no hooks configured this wraps nothing and the
        # object graph is unchanged.
        chain = build_hooks(config, observing) if hooks is None else hooks
        mounted = hook_tools(mounted, chain)
        # Every tool, including a caller's own and every MCP tool, goes
        # behind the gate before the registry ever sees one. Gating here
        # rather than inside build_registry keeps that function the seam its
        # docstring promises — a caller may still hand it an already-gated
        # list — while leaving exactly one place that decides a deployment
        # is gated at all.
        gate = build_permission_gate(config)
        mounted = gate_tools(mounted, gate)
        registry = build_registry(config, mounted)
        if tools is None:
            _apply_bash_policy(registry, mounted, binding, config)
        # ``task`` is mounted after everything else, including MCP, and
        # appended rather than inserted: it narrows the very registry it
        # is registered into, so it cannot be built before that registry
        # exists, and a tool added anywhere but the end would move every
        # tool after it inside the byte-stable list a cached prompt prefix
        # depends on. It goes through the same hook chain and the same
        # gate as every other tool.
        subagents = build_subagent_registry(config)
        if subagents is not None:
            runner = ChildRunner(
                provider=provider,
                parent=registry,
                config=config,
                sandbox=binding,
                skills=skills,
            )
            registry.register(
                gate_tools(hook_tools((TaskTool(subagents, runner),), chain), gate)[0]
            )
        snapshot = registry.available_tools()
        chosen = (
            default_sections(
                config,
                skills=skills,
                sandbox=binding,
                plan_tool=plans is not None,
                memory=remembering,
            )
            if sections is None
            else sections
        )

        app_prompt = build_prompt(chosen)
        budget = build_budget(model, snapshot)
        summarizer = build_summarizer(provider, config)
        # The registry goes in as itself — see build_registry on why nothing
        # may wrap it without forwarding both optional Protocols.
        #
        # The assembler goes in as the engine's default PromptSource, which
        # it satisfies structurally: ``render()`` returning an object with a
        # ``system_prompt``, no adapter, nothing dropped. It is a default and
        # not a binding — one engine serves every session this process runs,
        # and ``entry/turn.py`` passes the same assembler per call — but a
        # caller reaching for ``app.engine.exchange`` directly gets this
        # deployment's prompt rather than none.
        engine = AgentEngine(
            provider, registry, config.engine_config(), prompt=app_prompt
        )
    except BaseException:
        if remembering is not None:
            remembering.close()
        raise

    _log.info(
        "assembled: provider=%s tools=%d skills=%d planning=%s memory=%s "
        "subagents=%d window=%d workspace=%s sandbox=%s permission=%s rules=%d",
        provider.name,
        len(snapshot),
        len(skills),
        "on" if plans is not None else "off",
        "on" if remembering is not None else "off",
        len(subagents) if subagents is not None else 0,
        budget.context_tokens,
        config.workspace,
        _sandbox_state(binding),
        gate.mode.value,
        len(gate.rules),
    )

    return AgentApp(
        provider=provider,
        registry=registry,
        engine=engine,
        prompt=app_prompt,
        tools_snapshot=snapshot,
        budget=budget,
        summarizer=summarizer,
        config=config,
        skills=skills,
        sessions=None,
        plans=plans,
        mcp=mcp,
        sandbox=binding,
        permission=gate,
        memory=remembering,
        skill_env=checking,
        telemetry=observing,
    )


def _apply_bash_policy(
    registry: ToolRegistry,
    mounted: Sequence[Tool],
    binding: SandboxBinding,
    config: AppConfig,
) -> None:
    """Re-register the foundation ``bash`` under :func:`bash_policy`'s answer.

    **Re-registers the mounted object, which is the gated wrapper.** The
    ``bash`` in *mounted* is a :class:`~omicsclaw.permission.GatedTool` by
    the time this runs, so the search looks through the wrapper while the
    ``replace`` puts the wrapper back. Handing ``replace`` the inner
    :class:`~omicsclaw.tools.BashTool` instead would swap the one tool most
    worth gating for an ungated one, and every test would stay green because
    the tool still works — it would simply stop consulting the rule file and
    the dangerous-command patterns.
    """
    bash = next((tool for tool in mounted if _is_bash(tool)), None)
    if bash is None:
        return
    current = registry.policy_for(bash.name)
    chosen = bash_policy(binding, current, auto_approve=config.sandbox_auto_approve)
    if chosen != current:
        registry.replace(bash, chosen)
        _log.info("bash runs without approval: sandbox has no network")


def _is_bash(tool: Tool) -> bool:
    """Whether *tool* is the foundation ``bash``, however it is wrapped.

    **Unwraps repeatedly, not once.** A single ``tool.inner`` was correct
    while the gate was the only wrapper; mounting a hook chain makes
    ``bash`` a :class:`~omicsclaw.permission.GatedTool` around a
    :class:`~omicsclaw.hooks.HookedTool` around the
    :class:`~omicsclaw.tools.BashTool`, and a one-level unwrap then
    answers ``False`` — silently, so :func:`_apply_bash_policy` finds no
    ``bash``, never calls :func:`~omicsclaw.entry.sandbox.bash_policy`,
    and a sandboxed session asks for approval on every command with
    nothing raised and no test failing on the tool's behaviour.
    ``tests/entry/test_hook_wiring.py`` pins the two-wrapper case.
    """
    candidate = tool
    while isinstance(candidate, (GatedTool, HookedTool)):
        candidate = candidate.inner
    return isinstance(candidate, BashTool)


def _sandbox_state(binding: SandboxBinding) -> str:
    if binding.active:
        return "running"
    return "degraded" if binding.degraded else "off"


async def open_app(
    config: AppConfig,
    *,
    tools: Sequence[Tool] | None = None,
    hooks: Sequence[ToolHook] | None = None,
    sections: Sequence[Section] | None = None,
    on_mcp_change: StatusListener | None = None,
    on_sandbox_change: ChangeListener | None = None,
    telemetry: Telemetry | None = None,
) -> AgentApp:
    """:func:`build_app`, with the MCP servers of ``.mcp.json`` connected first.

    Every server in :meth:`AppConfig.mcp_config_path` is connected
    concurrently, each within :attr:`AppConfig.mcp_connect_timeout_s`,
    **before** the registry is built — so MCP tools are part of the tool
    snapshot and the context budget from the first turn, and the tool list
    does not change afterwards. ``${VAR}`` references in the file are
    expanded from the process environment.

    A server that fails to connect is logged and left out; the app still
    starts. A file that cannot be parsed raises
    :exc:`~omicsclaw.mcp.MCPConfigError`. Without a file this is exactly
    :func:`build_app`. *on_mcp_change* receives every status change while
    the servers connect.

    The sandbox :attr:`AppConfig.sandbox` asks for is started before the
    servers — see :func:`~omicsclaw.entry.sandbox.open_sandbox`; one that
    cannot start leaves ``bash`` on this machine, loudly, unless
    ``sandbox_required`` is set. *on_sandbox_change* receives every
    sandbox state change.

    The memory database :func:`build_app` opened is then swept: expired
    entries are deleted and ``MEMORY.md`` is rebuilt from what survives,
    so the first prompt of the process carries the memories that are
    still true rather than whatever the last process left on disk. A
    sweep that fails is logged and the app still starts — see
    :func:`~omicsclaw.entry.memory.prepare_memory`.

    Await it on the event loop that will serve the app: the server
    connections belong to that loop. Close the result with
    :meth:`AgentApp.aclose`, which also stops the servers, removes the
    container and closes the memory database. Raises :exc:`ValueError` if
    :attr:`AppConfig.mcp_connect_timeout_s` is not positive.
    """
    servers = load_mcp_config(config.mcp_config_path())
    sandbox = await open_sandbox(config, on_change=on_sandbox_change)
    try:
        skills = build_skill_index(config)
        if servers.is_empty:
            return await _swept(
                build_app(
                    config,
                    tools=tools,
                    hooks=hooks,
                    sections=sections,
                    sandbox=sandbox,
                    telemetry=telemetry,
                    skills=skills,
                )
            )

        manager = MCPManager(
            servers,
            connect_timeout_s=config.mcp_connect_timeout_s,
            cwd=config.workspace,
            request_timeout_s=config.tool_timeout_s,
            on_change=on_mcp_change,
        )
        await manager.start()
        _log_mcp_outcome(manager)
        try:
            return await _swept(
                build_app(
                    config,
                    tools=tools,
                    hooks=hooks,
                    sections=sections,
                    mcp=manager,
                    sandbox=sandbox,
                    telemetry=telemetry,
                    skills=skills,
                )
            )
        except BaseException:
            await manager.aclose()
            raise
    except BaseException:
        await sandbox.aclose()
        raise


async def _swept(app: AgentApp) -> AgentApp:
    """Run *app*'s start-up memory maintenance, log its skill environment, and hand it back.

    :param app: Freshly built deployment.
    :returns: The same app.
    :raises BaseException: Only a cancellation can get out, and it closes
        the memory database on the way — the app is never returned, so
        nothing else would.
    """
    try:
        await prepare_memory(app.memory)
        await log_skill_env(app.skill_env, app.config)
    except BaseException:
        if app.memory is not None:
            app.memory.close()
        raise
    return app


def _log_mcp_outcome(manager: MCPManager) -> None:
    """One line per server: what connected, what failed, what was skipped."""
    for status in manager.statuses():
        if status.state is ServerState.CONNECTED:
            _log.info("MCP server %s: %d tool(s)", status.name, len(status.tools))
        elif status.state is ServerState.FAILED:
            _log.warning("MCP server %s failed: %s", status.name, status.error)
        for skipped in status.skipped:
            _log.warning("MCP server %s: skipped %s", status.name, skipped)
