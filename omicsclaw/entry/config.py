"""``omicsclaw.entry`` — the one place a deployment is read.

Plan 0031 task A, decision Q8. Every layer below this one was built to
know nothing about its environment: ``EngineConfig`` reads no variables
on purpose (plan 0027: "a turn ceiling that moves with the shell makes
two runs of one benchmark incomparable"), ``omicsclaw.context`` takes
the contract file and the model table as callables and integers, and
``omicsclaw.tools`` takes a :class:`~omicsclaw.tools._workspace.Workspace`
rather than finding one. All of that knowledge arrives here.

**One parse point, and it fetches one thing.**
:func:`resolve_app_config` is the only place a deployment is
interpreted, but as of plan 0037 §5.4 it no longer *fetches* anything:
the command line and the process environment are handed to it by
:func:`omicsclaw.launch.main`, which is the only reader of those two
globals in the program. This module therefore takes no interest in the
process it runs in, and the rule over this package is now flat — no
module under ``omicsclaw/entry/`` names either global, with no
exemption list. The one declared exception to the whole arrangement
survives from plan 0031 Q8 and lives a layer down:
:func:`omicsclaw.provider.provider_from_env` keeps reading its own API
key, because moving a secret through this dataclass would only add a
place it can be printed from. Everything else — which workspace, which
model, how long a tool may run — is a field below.

**The timeout is one number, written once.** ``tool_timeout_s`` is the
single source for both halves of the ceiling a tool runs under:
:meth:`AppConfig.engine_config` derives the scheduler's
``EngineConfig.tool_timeout`` and :meth:`AppConfig.bash_timeout` derives
what ``bash`` is constructed with, one
:data:`~omicsclaw.tools.builtin.bash.ENGINE_TIMEOUT_MARGIN` below it.
Plan 0031 §12-2 is blunt about why two independent literals are not
acceptable: the day somebody raises the ceiling they will raise one of
them, and half of this mechanism does not help. The margin is imported
rather than re-typed for the same reason.

**Bad input is refused, not defaulted.** ``omicsclaw/provider/config.py``
replaces an unparseable environment value with its default; this module
raises :exc:`AppConfigError` instead. The divergence is deliberate and
narrow: a provider setting that silently falls back costs one slow
request, while ``OMICSCLAW_TOOL_TIMEOUT_S=6OO`` silently falling back to
60 s is exactly the failure §12-2 exists to prevent, and a single parse
point is the only place that can say so out loud.

**What this module does not read.** No ``.env`` file, and that is no
longer a gap. The reference harness loads ``cwd/.env``
(``main.go:117``) and this repository's ``.env.example`` documents ``.env``
as the way channel credentials are supplied, but a resolver that returns
a value cannot make ``provider_from_env`` see a variable without
mutating the live environment behind its caller's back. Loading it
belongs to whatever owns the process, and since plan 0037's review
:func:`omicsclaw.launch._adopt_dotenv` does it — before this function
is called, without overriding anything already exported. Between the
delivery and the review the promise was recorded in three places and
implemented in none, which is the failure mode "recorded as open" has
when nobody is counting.

``os`` is still imported, for :data:`os.pathsep` in :func:`_as_paths`
and nothing else. Plan 0037 §5.4 predicted the import would go with the
default; separator-joined path lists are the reason it does not.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from enum import StrEnum
from pathlib import Path
from typing import Callable, Mapping, Sequence

from omicsclaw.context import Pressure
from omicsclaw.engine import EngineConfig
from omicsclaw.permission import PermissionMode
from omicsclaw.planning import DEFAULT_GATE_TURNS
from omicsclaw.sandbox import SandboxConfig, host_user
from omicsclaw.tools.builtin.bash import ENGINE_TIMEOUT_MARGIN

__all__ = [
    "AppConfig",
    "AppConfigError",
    "mem_total_gib",
    "SandboxMode",
    "SkillEnvMode",
    "SkillsIndex",
    "fields_set_by_argv",
    "resolve_app_config",
]


class SkillsIndex(StrEnum):
    """How much of the skill catalogue the system prompt carries."""

    FULL = "full"
    """One line per skill, descriptions included. About 8.5k tokens over
    this repository's 96 skills, and stable enough to sit in a cached
    prefix."""

    COMPACT = "compact"
    """One line per domain, names only. About 600 tokens; the model
    routes on names alone."""

    OFF = "off"
    """No skills section, and ``use_skill`` is not mounted either. One
    switch with one meaning: advertising a tool for a catalogue the model
    was never shown is worse than having neither."""


class SkillEnvMode(StrEnum):
    """What the deployment does about the Python packages a skill declares."""

    OFF = "off"
    """Nothing: ``use_skill`` returns the body and the directory, as before."""

    PROBE = "probe"
    """``use_skill`` appends a note saying which declared packages the
    ``python`` that ``bash`` runs can import. The default. Changes the tool's
    result only, never the system prompt or the tool definitions."""

    INSTALL = "install"
    """As ``probe``, and ``install_skill_deps`` is mounted while ``bash`` runs
    on this machine: after approval it installs declared packages into an
    overlay environment, from this machine's pip configuration. Refused by
    ``oc desktop``, which has no approval channel."""


class SandboxMode(StrEnum):
    """Where ``bash`` runs."""

    OFF = "off"
    """On this machine, as the agent's own user. The default."""

    DOCKER = "docker"
    """In a container started by :mod:`omicsclaw.sandbox`. Needs
    :attr:`AppConfig.sandbox_image`."""


STATE_DIRNAME = ".omicsclaw"
"""Directory under the workspace for the files the agent writes about
itself: the permission rules, the plans, the offloaded tool results, the
compaction records, the memory database and its précis. One name, so the
six cannot end up in five places."""


class AppConfigError(ValueError):
    """A deployment that cannot be read, named at the point it is read.

    A :exc:`ValueError` rather than a new hierarchy: the callers are a
    process entry point and a test, and both want one thing — the
    message — from whichever of ``argv``, the environment or an override
    was wrong.
    """


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Everything a deployment decides, and nothing it discovers later.

    Frozen because it is read from several tasks at once and a field that
    changes under a running turn would change what that turn was measured
    against. ``slots`` for the same reason every dataclass in this
    rebuild has them: a typo on an attribute should be an error, not a
    new field.
    """

    workspace: Path
    """Sandbox root for every filesystem tool. No default: which
    directory an agent may write to is not a thing to guess.
    :func:`resolve_app_config` supplies :meth:`Path.cwd`, matching
    ``main.go:112``."""

    model: str = ""
    """``""`` means "let the provider layer detect one". See
    :meth:`~omicsclaw.entry.assembly.build_budget` for the cost: an
    empty name buys :data:`~omicsclaw.provider.DEFAULT_MODEL_LIMITS`,
    whose ``output_tokens=8192`` means *unknown*, not *8192*."""

    provider: str = ""
    """``""`` means "detect from whichever API key is present"."""

    tool_timeout_s: float = 600.0
    """The single source for both halves of a tool's ceiling.

    600 s is the owner's ruling (plan 0031 §12-2, reversing the draft's
    60 s): a ``spatial-deconv`` run or a STAR alignment is minutes to
    hours, and the 60 s the engine defaults to was an unacknowledged
    port. **Do not write this number anywhere else** — see the module
    docstring."""

    max_turns: int = 50
    """Model calls one exchange may make. Matches
    :class:`~omicsclaw.engine.EngineConfig`'s own default, restated here
    because this layer is the first thing that actually sets it."""

    system_prompt_files: tuple[Path, ...] = ()
    """Front-matter files of the system prompt, in order.

    Empty means the default: ``OMICSCLAW.md`` beside the skill tree
    (:meth:`repo_root`). Non-empty **replaces** it; each file becomes one
    section, still followed by the safety, tool-guidance and environment
    sections, which are not files and cannot be switched off. See
    :func:`~omicsclaw.entry.assembly.default_sections`.

    Named ``system`` in full because the surface half of the command line
    has a ``--prompt-file`` of its own carrying the **user's** message
    (the harness's ``RunOnce``). The two live on opposite sides of ``--``
    and would never collide, but one of them being reachable by the other
    one's name is how a task brief becomes a persona without any error."""

    summary_model: str = ""
    """Model for compaction summaries. ``""`` reuses the main one.

    A cheaper model is the usual choice and the reason this is separate;
    binding it is a composition-root decision, which is why
    :class:`~omicsclaw.context.summary.Summarizer` is narrower than
    :class:`~omicsclaw.provider.LLMProvider` rather than the same shape."""

    summary_timeout_s: float = 90.0
    """Wall clock for one summary call, applied to the **summarizer**.

    Plan 0031 Q11. Wrapping :func:`~omicsclaw.context.compact` in
    :func:`asyncio.timeout` instead produces a raised
    :exc:`TimeoutError` and *no compaction at all*, because ``compact``
    only degrades on exceptions raised by the summarizer it called. The
    difference is invisible in a test that asserts "it did not hang"."""

    approval_timeout_s: float | None = None
    """Deadline on one human approval. ``None`` = wait forever.

    ``None`` suits a CLI, where a person is present and a prompt can sit.
    A channel surface **must** set a number: plan 0031 Q12, and
    ``omicsclaw/tools/context.py``'s own note that "a surface that asks a
    human still owes a deadline". Expiry denies — fail closed."""

    turn_timeout_s: float | None = None
    """Wall clock for one exchange, independent of per-tool ceilings.

    Without it, :attr:`tool_timeout_s` times :attr:`max_turns` is how
    long one stuck ``bash`` can hold a session. Plan 0031 §12-2 makes
    this a precondition of the 600 s ruling, not an option beside it."""

    skills_dir: Path | None = None
    """Directory scanned for ``SKILL.md`` files.

    ``None`` means :attr:`workspace` / ``skills``. An absent directory is
    an empty index rather than an error, so a workspace with no skills
    gets a prompt with no skills section."""

    skills_index: SkillsIndex = SkillsIndex.FULL
    """Which rendering of the catalogue goes into the system prompt, and
    whether ``use_skill`` is mounted at all. See :class:`SkillsIndex`."""

    planning: bool = True
    """Whether the agent keeps an execution plan (plan 0039).

    One switch with one meaning, following ``skills_index=off``: it
    mounts or unmounts ``plan_write``, adds or removes the planning
    section of the system prompt, and decides whether a plan block is
    injected before each model call. Half of it — a prompt that tells the
    model to plan with a tool that is not there, or a tool nothing
    mentions — is worse than neither half.

    On by default. The reference harness treats planning as a native
    capability rather than a mode (``plan.go:3-5``), and a capability
    that defaults to off is a mode with extra steps."""

    planning_gate_turns: int = DEFAULT_GATE_TURNS
    """Consecutive read-only turns before the model is nudged to plan.

    ``0`` disables the nudge and leaves the rest of planning intact,
    which is what a surface with its own idea of when to interrupt should
    set. See :data:`~omicsclaw.planning.DEFAULT_GATE_TURNS` for where the
    number comes from — it is derived from :attr:`max_turns`, so a
    deployment that raises the turn ceiling a long way should raise this
    too."""

    subagents: bool = True
    """Whether the agent may delegate a sub-task to a sub-agent.

    One switch with one meaning, following :attr:`planning`: it mounts or
    unmounts the ``task`` tool, and with it the whole of delegation. The
    built-in ``general-purpose`` sub-agent and any definition found under
    :meth:`agents_root` are loaded only when it is on.

    On by default. Off is a deployment that wants every tool call to
    happen in the one conversation a person is watching."""

    memory: bool = True
    """Whether this deployment remembers anything across sessions.

    One switch with one meaning, following :attr:`planning`: it opens or
    leaves closed ``<workspace>/.omicsclaw/memory.db``, and with it the
    ``memory_search`` and ``memory_write`` tools, the long-term memory
    section of the system prompt, the extraction that runs before a
    compaction, and the SQLite store conversations are resumed from.
    Half of it — a prompt block nothing ever writes to, or an extractor
    filling a store nothing ever reads — is worse than neither half.

    ``false`` is a deployment that keeps nothing: conversations live in
    the process that served them and end with it. Not about container
    memory; that is :attr:`sandbox_memory`."""

    skill_env: SkillEnvMode = SkillEnvMode.PROBE
    """Whether ``use_skill`` reports the declared packages ``bash``'s ``python``
    cannot import, and whether ``install_skill_deps`` is mounted. See
    :class:`SkillEnvMode`; has no effect with ``skills_index=off``, and
    read-only mode gets no note."""

    skill_env_dir: Path | None = None
    """Where overlays are kept; ``None`` is ``$XDG_CACHE_HOME/omicsclaw/envs``,
    else ``~/.cache/omicsclaw/envs``. :func:`resolve_app_config` makes a
    relative path absolute against the current directory."""

    skill_env_install_timeout_s: float = 1800.0
    """Upper bound on one ``install_skill_deps`` installation, the dry run
    included. Must be positive."""

    ensemble: bool | None = None
    """Whether ``run_skill`` is mounted.

    ``None`` (unset) mounts it when the execution environment passes the
    start-up self-check and logs a warning otherwise; ``True`` makes a failed
    self-check refuse start-up; ``False`` leaves it out, and then the system
    prompt and every other tool definition are exactly those of a deployment
    without it."""

    ensemble_gpus: str = ""
    """GPUs trials may use: ``""`` detects them with ``nvidia-smi`` (inside
    the sandbox when it runs), ``none`` uses none, or a comma-separated list
    of device ids as the execution environment numbers them."""

    ensemble_slots_per_gpu: int = 1
    """Trials that may share one GPU at a time."""

    ensemble_memory_gb: float = 0.0
    """Memory the trial pool may hand out; ``0`` means all that is left after
    the tmpfs, shared memory and :attr:`ensemble_reserved_gb`. A larger value
    is capped to that."""

    ensemble_reserved_gb: float = 64.0
    """Memory kept outside the trial pool for ``bash``, system processes and
    the page cache."""

    ensemble_cpus: int = 0
    """CPUs the trial pool may hand out; ``0`` means this machine's count, or
    the sandbox's ``--cpus`` when that is smaller."""

    ensemble_memory_gb_cap: float = 0.0
    """Upper bound on any one trial's memory limit; ``0`` keeps each method's."""

    ensemble_max_trial_s: float = 7200.0
    """Upper bound on any one trial's run time, scoring excluded."""

    ensemble_max_queue_s: float = 7200.0
    """How long a trial may wait for resources before it fails."""

    ensemble_keep_all: bool = False
    """Keep every trial's full output instead of labels, metrics and the best
    trial's ``.h5ad``."""

    ensemble_python: str = ""
    """Interpreter for trials and scoring: empty means this process's own on
    this machine and ``python`` in the sandbox."""

    ensemble_tools: str = "all"
    """Which ensemble tools are mounted when the ensemble is on: ``all``
    (``run_skill``, ``inspect_trials``, ``select_result``,
    ``optimize_params``), ``free`` (the first three) or ``tuning`` (only
    ``optimize_params``)."""

    ensemble_run_budget: str = ""
    """New ``run_skill`` trials one session may start: empty for no limit, a
    number for all methods together, or ``method:count,...`` per method.
    ``optimize_params`` draws from the same account."""

    ensemble_tuning_model: str = ""
    """Model ``optimize_params`` asks; empty is the agent's own model."""

    ensemble_tuning_provider: str = ""
    """Provider of :attr:`ensemble_tuning_model`; empty is the agent's own."""

    ensemble_tuning_tissue: bool = True
    """``False`` makes ``optimize_params`` drop its ``tissue`` argument."""

    ensemble_tuning_images: bool = False
    """Partition images for the K decision. Not supported: ``True`` refuses
    start-up with the ensemble on."""

    ensemble_tuning_budget: int = 12
    """New parameter sets ``optimize_params`` tries per method at the chosen K."""

    ensemble_tuning_max_s: float = 43200.0
    """Longest one ``optimize_params`` call may run, in seconds."""

    ensemble_obs_allowlist: str = ""
    """Comma-separated ``obs`` columns an ensemble input may have; empty
    allows any. Inputs with other columns are refused by ``run_skill`` and
    ``optimize_params``."""

    ensemble_seed: int | None = 0
    """Seed of every trial process (``random``, numpy, torch with deterministic
    algorithms, ``PYTHONHASHSEED=0``); ``None`` (``none``) leaves trials unseeded."""

    launch_id: str = ""
    """Identifier a desktop launcher minted for *this* backend process.

    Read back verbatim by ``GET /health`` and by nothing else. An Electron
    parent that started this process compares it against the id it passed
    and refuses a backend that answers with anything else
    (``OmicsClaw-App/src/lib/backend-health.ts:313``) — otherwise a
    leftover backend on the same port is indistinguishable from the child
    it just started.

    Here rather than read from the environment at the route, because plan
    0031 Q8 allows exactly one environment reader and it is
    :func:`resolve_app_config`. ``""`` is an unmanaged launch: a developer
    running ``oc desktop`` by hand has no parent to match."""

    compact_at: Pressure = Pressure.WARN
    """Lowest pressure tier that triggers compaction before a model call.

    ``warn`` lets every tier act — offload first, then half and full
    summaries; a higher tier skips the cheaper steps below it.

    :class:`~omicsclaw.context.Pressure` is a :class:`~enum.StrEnum` and
    therefore compares **alphabetically**: ``EMERGENCY >= FULL`` is
    ``False``. Whoever compares this field against a report must map the
    tiers to an order first (plan 0031 trap 0)."""

    max_queued_per_session: int = 2
    """Exchanges that may wait behind a running one before submission is
    refused outright. Plan 0031 Q7: a bounded queue that says no is a
    semantic, an unbounded one is a leak."""

    delta_ring_size: int = 2048
    """Text/reasoning/progress events one turn's replay buffer keeps.

    Bounded on purpose — the desktop client's published contract already
    declares ``event_queue_capacity`` and ``producer_backpressure``.
    Control events are never dropped regardless (plan 0031 Q14)."""

    max_sessions: int = 256
    """Sessions held in memory. The eviction victim is the
    least-recently-used **idle** one; a running session is never a
    victim (plan 0031 Q6)."""

    mcp_config: Path | None = None
    """The ``.mcp.json`` naming MCP servers to connect at start-up.

    ``None`` means :attr:`workspace` / ``.mcp.json``. A missing file means
    no MCP servers."""

    mcp_connect_timeout_s: float = 30.0
    """How long one MCP server may take to start and complete its
    handshake; one that has not finished by then is killed. Servers
    connect concurrently, so start-up waits about this long at most."""

    sandbox: SandboxMode = SandboxMode.OFF
    """Where ``bash`` runs. See :class:`SandboxMode`."""

    sandbox_image: str = ""
    """Container image for :attr:`SandboxMode.DOCKER`. Required there, and
    must already be pulled: nothing is downloaded at start-up."""

    sandbox_network: str = "none"
    """Container network. ``none`` means commands cannot reach any network;
    any other value is passed to ``--network`` as given."""

    sandbox_memory: str = "auto"
    """``--memory`` for the container. ``auto`` is 80% of this machine's
    ``MemTotal``, leaving the rest to the host and its page cache; empty means
    no cap. See :meth:`sandbox_memory_value`."""

    sandbox_cpus: str = ""
    """``--cpus`` for the container; empty means no cap."""

    sandbox_gpus: str = ""
    """``--gpus`` for the container, e.g. ``all``; empty means none."""

    sandbox_user: str = ""
    """``--user`` for the container. Empty means this process's
    ``uid:gid``; rootless Docker and Podman usually want ``0:0``."""

    sandbox_mounts: tuple[Path, ...] = ()
    """Extra host directories mounted read-only, at the same path."""

    sandbox_tmpfs_size: str = "64g"
    """Size of the container's ``/tmp`` tmpfs."""

    sandbox_shm_size: str = "128g"
    """``--shm-size`` for the container; empty keeps the runtime's 64 MiB."""

    sandbox_pids_limit: int = 65536
    """``--pids-limit`` for the container; threads count against it."""

    sandbox_nofile: int = 65536
    """``--ulimit nofile`` for the container; ``0`` keeps the image's."""

    sandbox_code_in_image: bool = False
    """The image already holds this repository's ``omicsclaw/`` and
    ``skills/``, so they are not mounted from the host. See
    :meth:`sandbox_config`."""

    sandbox_bootstrap: str = ""
    """Command run once in the workspace after the container starts."""

    sandbox_bootstrap_timeout_s: float = 600.0
    """Budget for :attr:`sandbox_bootstrap`."""

    sandbox_runtime: str = "docker"
    """Container CLI: a name on ``PATH`` or a path."""

    sandbox_required: bool = False
    """Refuse to start when the sandbox cannot be started, instead of
    running ``bash`` on this machine."""

    sandbox_auto_approve: bool = False
    """Run ``bash`` without asking, but only while the sandbox is running
    with :attr:`sandbox_network` ``none``. Otherwise ``bash`` still asks."""

    permission_mode: PermissionMode = PermissionMode.DEFAULT
    """How much this session is trusted. See
    :class:`~omicsclaw.permission.PermissionMode`.

    ``default`` — rules decide and the tools' own policies answer the rest —
    is the guarded value, so a deployment that says nothing gets the
    foundation tools' own ``ASK`` declarations rather than a posture nobody
    chose."""

    permission_rules: Path | None = None
    """The rule file, or ``None`` for the default location.

    ``None`` is resolved by :meth:`permission_rules_path`; a missing file is
    an empty rule set rather than an error, so the default costs nothing
    when nobody has written one."""

    audit_log: Path | None = None
    """Where to append one line per tool call, or ``None`` for no log.

    **There is no default location, unlike every other file this config
    names.** A rule file that does not exist is an empty rule set, which
    costs a deployment nothing; an audit trail that appears without being
    asked for is a file about a person, written because nobody said no.
    So this one is opt-in, and naming a path is the whole of switching it
    on — :func:`~omicsclaw.entry.assembly.build_hooks` mounts an
    :class:`~omicsclaw.hooks.AuditHook` when it is set and mounts nothing
    when it is not.

    The arguments of a call are **not** recorded, only a digest of them;
    see :func:`~omicsclaw.hooks.arguments_digest` for why."""

    def state_dir(self) -> Path:
        """Where this deployment keeps the files the agent writes about itself.

        :returns: ``<workspace>/.omicsclaw``, which may not exist yet —
            each writer under it creates what it needs.
        """
        return self.workspace / STATE_DIRNAME

    def permission_rules_path(self) -> Path:
        """The permission rule file, with the default resolved.

        ``<workspace>/.omicsclaw/settings.json``, mirroring
        :meth:`mcp_config_path`'s shape and the reference harness's
        ``.harness9/settings.json``. Inside the workspace because the rules
        are a property of *this* project's data: a whitelist reasonable for
        a public test tree is not one for a cohort.
        """
        if self.permission_rules is not None:
            return self.permission_rules
        return self.state_dir() / "settings.json"

    def __post_init__(self) -> None:
        """Refuse a value no deployment can mean, however the configuration was built.

        :raises AppConfigError: :attr:`skill_env_install_timeout_s` is not positive.
        """
        if not self.skill_env_install_timeout_s > 0:
            raise AppConfigError(
                f"skill_env_install_timeout_s must be positive, not {self.skill_env_install_timeout_s!r}"
            )

    def skills_root(self) -> Path:
        """The directory to scan for skills, with the default resolved.

        One place answers this, so the prompt section and the
        ``use_skill`` tool cannot end up scanning two different trees.
        """
        if self.skills_dir is not None:
            return self.skills_dir
        return self.workspace / "skills"

    def plans_root(self) -> Path:
        """Where this deployment's plan files are kept.

        ``<workspace>/.omicsclaw/plans/``, beside the offloaded tool
        results and compaction records that
        :mod:`omicsclaw.entry.compaction` writes — per-session state the
        conversation does not carry is one idea, and it has one place.
        Not configurable separately: a plan directory pointing somewhere
        other than the rest of that state is a way to lose half of a
        session's memory while keeping the other half.
        """
        return self.state_dir() / "plans"

    def agents_root(self) -> Path:
        """Where this deployment's sub-agent definition files are kept.

        ``<workspace>/.omicsclaw/agents/``, beside the plans and the rest
        of the per-session state. A missing directory means no sub-agents
        beyond the built-in one; nothing is created here.
        """
        return self.state_dir() / "agents"

    def mcp_config_path(self) -> Path:
        """The MCP configuration file, with the default resolved."""
        if self.mcp_config is not None:
            return self.mcp_config
        return self.workspace / ".mcp.json"

    def repo_root(self) -> Path:
        """The directory holding the ``skills/`` tree, and ``omicsclaw/`` beside it."""
        return self.skills_root().parent

    def code_mounts(self) -> tuple[Path, ...]:
        """``<repo>/omicsclaw`` and ``<repo>/skills``, when the sandbox must be given them.

        Empty when :attr:`sandbox_code_in_image` is set, when either directory
        is missing, or when the workspace already is or contains the
        repository (its mount covers both).
        """
        if self.sandbox_code_in_image:
            return ()
        root = self.repo_root().resolve()
        code = (root / "omicsclaw", root / "skills")
        if not all(path.is_dir() for path in code):
            return ()
        workspace = self.workspace.resolve()
        if root == workspace or workspace in root.parents:
            return ()
        return code

    def sandbox_memory_value(self, meminfo: Path = Path("/proc/meminfo")) -> str:
        """:attr:`sandbox_memory` with ``auto`` resolved to 80% of ``MemTotal``.

        ``auto`` on a machine without a readable *meminfo* resolves to ``""``
        (no cap).
        """
        if self.sandbox_memory.strip().lower() != "auto":
            return self.sandbox_memory
        total_gib = mem_total_gib(meminfo)
        if total_gib is None:
            return ""
        return f"{int(total_gib * 0.8)}g"

    def sandbox_config(self) -> SandboxConfig | None:
        """The container settings, or ``None`` when :attr:`sandbox` is off.

        The repository's ``omicsclaw/`` and ``skills/`` are added to the
        read-only mounts (see :meth:`code_mounts`) whether or not
        :attr:`ensemble` is on, so ``bash`` sees the same skill code either way.

        Raises :exc:`~omicsclaw.sandbox.SandboxConfigError` for an unusable
        setting, including a missing :attr:`sandbox_image`.
        """
        if self.sandbox is SandboxMode.OFF:
            return None
        mounts = tuple(self.sandbox_mounts)
        mounts += tuple(path for path in self.code_mounts() if path not in mounts)
        return SandboxConfig(
            image=self.sandbox_image,
            network=self.sandbox_network,
            memory=self.sandbox_memory_value(),
            cpus=self.sandbox_cpus,
            gpus=self.sandbox_gpus,
            read_only_mounts=mounts,
            tmpfs_size=self.sandbox_tmpfs_size,
            shm_size=self.sandbox_shm_size,
            pids_limit=self.sandbox_pids_limit,
            nofile=self.sandbox_nofile,
            bootstrap=self.sandbox_bootstrap,
            bootstrap_timeout_s=self.sandbox_bootstrap_timeout_s,
            runtime=self.sandbox_runtime,
            user=self.sandbox_user or host_user(),
        )

    def engine_config(self) -> EngineConfig:
        """The engine's half of the deployment, derived not restated.

        Two fields cross over and no more: the engine is deliberately
        ignorant of everything else here.
        """
        return EngineConfig(
            max_turns=self.max_turns,
            tool_timeout=self.tool_timeout_s,
        )

    def bash_timeout(self) -> float:
        """What ``bash`` is constructed with: the ceiling, minus the margin.

        :data:`~omicsclaw.tools.builtin.bash.ENGINE_TIMEOUT_MARGIN` is
        imported from the tool that defines it rather than copied, so a
        margin that changes there changes here. The subtraction leaves
        the engine's own deadline room to fire first and report a timeout
        the model can act on, instead of the tool and the scheduler
        racing to the same instant.
        """
        return self.tool_timeout_s - ENGINE_TIMEOUT_MARGIN


def mem_total_gib(meminfo: Path = Path("/proc/meminfo")) -> float | None:
    """``MemTotal`` of *meminfo* in GiB, or ``None`` when it cannot be read."""
    try:
        with open(meminfo, encoding="ascii") as source:
            for line in source:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024**2
    except (OSError, ValueError, IndexError):
        return None
    return None


def _as_path(raw: str) -> Path:
    return Path(raw).expanduser()


def _as_str(raw: str) -> str:
    return raw


def _as_int(raw: str) -> int:
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise AppConfigError(f"{raw!r} is not an integer") from exc


def _as_float(raw: str) -> float:
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise AppConfigError(f"{raw!r} is not a number") from exc


def _as_optional_float(raw: str) -> float | None:
    """``""`` and ``none`` both mean "no deadline", spelled either way.

    A shell cannot express :data:`None`, and an operator who wants to
    switch a deadline off will write one of these two.
    """
    if raw.strip().lower() in {"", "none"}:
        return None
    return _as_float(raw)


def _as_skills_index(raw: str) -> SkillsIndex:
    try:
        return SkillsIndex(raw.strip().lower())
    except ValueError as exc:
        modes = ", ".join(mode.value for mode in SkillsIndex)
        raise AppConfigError(f"{raw!r} is not a skills index mode ({modes})") from exc


def _as_pressure(raw: str) -> Pressure:
    """A tier by name, refusing anything that is not one.

    An unknown name lists the five that exist rather than falling back to
    a tier nobody asked for. ``high`` is the one worth naming: it was in
    plan 0031's draft and never existed, and a silent fallback would have
    turned that typo into a compaction threshold chosen by accident.
    """
    try:
        return Pressure(raw.strip().lower())
    except ValueError as exc:
        known = ", ".join(tier.value for tier in Pressure)
        raise AppConfigError(
            f"{raw!r} is not a pressure tier — known tiers are {known}"
        ) from exc


def _as_bool(raw: str) -> bool:
    """``true``/``false`` and their usual spellings; anything else is refused."""
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise AppConfigError(f"{raw!r} is not a boolean (true/false)")


def _as_skill_env(raw: str) -> SkillEnvMode:
    try:
        return SkillEnvMode(raw.strip().lower())
    except ValueError as exc:
        modes = ", ".join(mode.value for mode in SkillEnvMode)
        raise AppConfigError(f"{raw!r} is not a skill_env mode ({modes})") from exc


def _as_positive_float(raw: str) -> float:
    value = _as_float(raw)
    if not value > 0:
        raise AppConfigError(f"{raw!r} is not a positive number")
    return value


def _as_ensemble_tools(raw: str) -> str:
    value = raw.strip().lower()
    if value not in ("all", "free", "tuning"):
        raise AppConfigError(f"{raw!r} is not an ensemble tools mode (all, free, tuning)")
    return value


def _as_seed(raw: str) -> int | None:
    if raw.strip().lower() in ("none", "off", ""):
        return None
    value = _as_int(raw)
    if value < 0:
        raise AppConfigError(f"{raw!r} is not a non-negative seed")
    return value


def _as_run_budget(raw: str) -> str:
    from omicsclaw.ensemble.tuning.budget import parse_budget

    try:
        parse_budget(raw)
    except ValueError as exc:
        raise AppConfigError(f"{raw!r} is not a run budget: {exc}") from exc
    return raw.strip()


def _as_sandbox_mode(raw: str) -> SandboxMode:
    try:
        return SandboxMode(raw.strip().lower())
    except ValueError as exc:
        modes = ", ".join(mode.value for mode in SandboxMode)
        raise AppConfigError(f"{raw!r} is not a sandbox mode ({modes})") from exc


def _as_permission_mode(raw: str) -> PermissionMode:
    """A posture by name, refusing anything that is not one.

    Refusing matters more here than for the other enums on this page. A
    typo in ``--permission-mode bypass_all`` that fell back to the default
    would be a *tightening*, which somebody notices; a typo that fell back
    to anything else is a session running with fewer controls than the
    operator asked for and no way to tell from the outside.
    """
    try:
        return PermissionMode(raw.strip().lower())
    except ValueError as exc:
        modes = ", ".join(mode.value for mode in PermissionMode)
        raise AppConfigError(
            f"{raw!r} is not a permission mode ({modes})"
        ) from exc


def _as_paths(raw: str) -> tuple[Path, ...]:
    """Split on :data:`os.pathsep`, the separator paths already use."""
    return tuple(Path(part).expanduser() for part in raw.split(os.pathsep) if part)


def _as_optional_path(raw: str) -> Path | None:
    """``""`` and ``none`` both mean "use the default location"."""
    if raw.strip().lower() in {"", "none"}:
        return None
    return _as_path(raw)


@dataclass(frozen=True, slots=True)
class _Option:
    """One settable field, and the two places a deployment may set it.

    Declaring the flag, the environment names and the parser together is
    what keeps :func:`resolve_app_config` a single loop rather than one
    branch per field — and it is why adding a setting cannot accidentally
    reach only one of the two sources.
    """

    field: str
    flag: str
    env: tuple[str, ...]
    parse: Callable[[str], object]
    repeatable: bool = False
    """A flag that may be given more than once, accumulating rather than
    replacing. Only meaningful when :attr:`parse` returns a tuple."""


_OPTIONS: tuple[_Option, ...] = (
    _Option("workspace", "--workspace", ("OMICSCLAW_WORKSPACE",), _as_path),
    _Option("model", "--model", ("OMICSCLAW_MODEL", "LLM_MODEL"), _as_str),
    _Option(
        "provider",
        "--provider",
        ("OMICSCLAW_PROVIDER", "LLM_PROVIDER"),
        _as_str,
    ),
    _Option(
        "tool_timeout_s",
        "--tool-timeout",
        ("OMICSCLAW_TOOL_TIMEOUT_S",),
        _as_float,
    ),
    _Option("max_turns", "--max-turns", ("OMICSCLAW_MAX_TURNS",), _as_int),
    _Option(
        "system_prompt_files",
        "--system-prompt-file",
        ("OMICSCLAW_SYSTEM_PROMPT_FILES",),
        _as_paths,
        repeatable=True,
    ),
    _Option(
        "summary_model",
        "--summary-model",
        ("OMICSCLAW_SUMMARY_MODEL",),
        _as_str,
    ),
    _Option(
        "summary_timeout_s",
        "--summary-timeout",
        ("OMICSCLAW_SUMMARY_TIMEOUT_S",),
        _as_float,
    ),
    _Option(
        "approval_timeout_s",
        "--approval-timeout",
        ("OMICSCLAW_APPROVAL_TIMEOUT_S",),
        _as_optional_float,
    ),
    _Option(
        "turn_timeout_s",
        "--turn-timeout",
        ("OMICSCLAW_TURN_TIMEOUT_S",),
        _as_optional_float,
    ),
    _Option(
        "skills_dir",
        "--skills-dir",
        ("OMICSCLAW_SKILLS_DIR",),
        _as_optional_path,
    ),
    _Option(
        "skills_index",
        "--skills-index",
        ("OMICSCLAW_SKILLS_INDEX",),
        _as_skills_index,
    ),
    _Option(
        "launch_id",
        "--launch-id",
        ("OMICSCLAW_DESKTOP_LAUNCH_ID",),
        _as_str,
    ),
    _Option("memory", "--memory", ("OMICSCLAW_MEMORY",), _as_bool),
    _Option("planning", "--planning", ("OMICSCLAW_PLANNING",), _as_bool),
    _Option(
        "planning_gate_turns",
        "--planning-gate-turns",
        ("OMICSCLAW_PLANNING_GATE_TURNS",),
        _as_int,
    ),
    _Option("subagents", "--subagents", ("OMICSCLAW_SUBAGENTS",), _as_bool),
    _Option("skill_env", "--skill-env", ("OMICSCLAW_SKILL_ENV",), _as_skill_env),
    _Option("skill_env_dir", "--skill-env-dir", ("OMICSCLAW_SKILL_ENV_DIR",), _as_optional_path),
    _Option(
        "skill_env_install_timeout_s",
        "--skill-env-install-timeout",
        ("OMICSCLAW_SKILL_ENV_INSTALL_TIMEOUT_S",),
        _as_positive_float,
    ),
    _Option("ensemble", "--ensemble", ("OMICSCLAW_ENSEMBLE",), _as_bool),
    _Option("ensemble_gpus", "--ensemble-gpus", ("OMICSCLAW_ENSEMBLE_GPUS",), _as_str),
    _Option(
        "ensemble_slots_per_gpu",
        "--ensemble-slots-per-gpu",
        ("OMICSCLAW_ENSEMBLE_SLOTS_PER_GPU",),
        _as_int,
    ),
    _Option(
        "ensemble_memory_gb",
        "--ensemble-memory-gb",
        ("OMICSCLAW_ENSEMBLE_MEMORY_GB",),
        _as_float,
    ),
    _Option(
        "ensemble_reserved_gb",
        "--ensemble-reserved-gb",
        ("OMICSCLAW_ENSEMBLE_RESERVED_GB",),
        _as_float,
    ),
    _Option("ensemble_cpus", "--ensemble-cpus", ("OMICSCLAW_ENSEMBLE_CPUS",), _as_int),
    _Option(
        "ensemble_memory_gb_cap",
        "--ensemble-memory-gb-cap",
        ("OMICSCLAW_ENSEMBLE_MEMORY_GB_CAP",),
        _as_float,
    ),
    _Option(
        "ensemble_max_trial_s",
        "--ensemble-max-trial",
        ("OMICSCLAW_ENSEMBLE_MAX_TRIAL_S",),
        _as_float,
    ),
    _Option(
        "ensemble_max_queue_s",
        "--ensemble-max-queue",
        ("OMICSCLAW_ENSEMBLE_MAX_QUEUE_S",),
        _as_float,
    ),
    _Option(
        "ensemble_keep_all",
        "--ensemble-keep-all",
        ("OMICSCLAW_ENSEMBLE_KEEP_ALL",),
        _as_bool,
    ),
    _Option("ensemble_python", "--ensemble-python", ("OMICSCLAW_ENSEMBLE_PYTHON",), _as_str),
    _Option("ensemble_tools", "--ensemble-tools", ("OMICSCLAW_ENSEMBLE_TOOLS",), _as_ensemble_tools),
    _Option("ensemble_run_budget", "--ensemble-run-budget", ("OMICSCLAW_ENSEMBLE_RUN_BUDGET",), _as_run_budget),
    _Option("ensemble_tuning_model", "--ensemble-tuning-model", ("OMICSCLAW_ENSEMBLE_TUNING_MODEL",), _as_str),
    _Option(
        "ensemble_tuning_provider",
        "--ensemble-tuning-provider",
        ("OMICSCLAW_ENSEMBLE_TUNING_PROVIDER",),
        _as_str,
    ),
    _Option(
        "ensemble_tuning_tissue",
        "--ensemble-tuning-tissue",
        ("OMICSCLAW_ENSEMBLE_TUNING_TISSUE",),
        _as_bool,
    ),
    _Option(
        "ensemble_tuning_images",
        "--ensemble-tuning-images",
        ("OMICSCLAW_ENSEMBLE_TUNING_IMAGES",),
        _as_bool,
    ),
    _Option(
        "ensemble_tuning_budget",
        "--ensemble-tuning-budget",
        ("OMICSCLAW_ENSEMBLE_TUNING_BUDGET",),
        _as_int,
    ),
    _Option(
        "ensemble_tuning_max_s",
        "--ensemble-tuning-max",
        ("OMICSCLAW_ENSEMBLE_TUNING_MAX_S",),
        _as_positive_float,
    ),
    _Option("ensemble_seed", "--ensemble-seed", ("OMICSCLAW_ENSEMBLE_SEED",), _as_seed),
    _Option(
        "ensemble_obs_allowlist",
        "--ensemble-obs-allowlist",
        ("OMICSCLAW_ENSEMBLE_OBS_ALLOWLIST",),
        _as_str,
    ),
    _Option("compact_at", "--compact-at", ("OMICSCLAW_COMPACT_AT",), _as_pressure),
    _Option(
        "max_queued_per_session",
        "--max-queued-per-session",
        ("OMICSCLAW_MAX_QUEUED_PER_SESSION",),
        _as_int,
    ),
    _Option(
        "delta_ring_size",
        "--delta-ring-size",
        ("OMICSCLAW_DELTA_RING_SIZE",),
        _as_int,
    ),
    _Option("max_sessions", "--max-sessions", ("OMICSCLAW_MAX_SESSIONS",), _as_int),
    _Option(
        "mcp_config",
        "--mcp-config",
        ("OMICSCLAW_MCP_CONFIG",),
        _as_optional_path,
    ),
    _Option(
        "mcp_connect_timeout_s",
        "--mcp-connect-timeout",
        ("OMICSCLAW_MCP_CONNECT_TIMEOUT_S",),
        _as_float,
    ),
    _Option("sandbox", "--sandbox", ("OMICSCLAW_SANDBOX",), _as_sandbox_mode),
    _Option(
        "sandbox_image",
        "--sandbox-image",
        ("OMICSCLAW_SANDBOX_IMAGE",),
        _as_str,
    ),
    _Option(
        "sandbox_network",
        "--sandbox-network",
        ("OMICSCLAW_SANDBOX_NETWORK",),
        _as_str,
    ),
    _Option(
        "sandbox_memory",
        "--sandbox-memory",
        ("OMICSCLAW_SANDBOX_MEMORY",),
        _as_str,
    ),
    _Option("sandbox_cpus", "--sandbox-cpus", ("OMICSCLAW_SANDBOX_CPUS",), _as_str),
    _Option("sandbox_gpus", "--sandbox-gpus", ("OMICSCLAW_SANDBOX_GPUS",), _as_str),
    _Option("sandbox_user", "--sandbox-user", ("OMICSCLAW_SANDBOX_USER",), _as_str),
    _Option(
        "sandbox_mounts",
        "--sandbox-mount",
        ("OMICSCLAW_SANDBOX_MOUNTS",),
        _as_paths,
        repeatable=True,
    ),
    _Option(
        "sandbox_tmpfs_size",
        "--sandbox-tmpfs-size",
        ("OMICSCLAW_SANDBOX_TMPFS_SIZE",),
        _as_str,
    ),
    _Option(
        "sandbox_shm_size",
        "--sandbox-shm-size",
        ("OMICSCLAW_SANDBOX_SHM_SIZE",),
        _as_str,
    ),
    _Option(
        "sandbox_pids_limit",
        "--sandbox-pids-limit",
        ("OMICSCLAW_SANDBOX_PIDS_LIMIT",),
        _as_int,
    ),
    _Option(
        "sandbox_nofile",
        "--sandbox-nofile",
        ("OMICSCLAW_SANDBOX_NOFILE",),
        _as_int,
    ),
    _Option(
        "sandbox_code_in_image",
        "--sandbox-code-in-image",
        ("OMICSCLAW_SANDBOX_CODE_IN_IMAGE",),
        _as_bool,
    ),
    _Option(
        "sandbox_bootstrap",
        "--sandbox-bootstrap",
        ("OMICSCLAW_SANDBOX_BOOTSTRAP",),
        _as_str,
    ),
    _Option(
        "sandbox_bootstrap_timeout_s",
        "--sandbox-bootstrap-timeout",
        ("OMICSCLAW_SANDBOX_BOOTSTRAP_TIMEOUT_S",),
        _as_float,
    ),
    _Option(
        "sandbox_runtime",
        "--sandbox-runtime",
        ("OMICSCLAW_SANDBOX_RUNTIME",),
        _as_str,
    ),
    _Option(
        "sandbox_required",
        "--sandbox-required",
        ("OMICSCLAW_SANDBOX_REQUIRED",),
        _as_bool,
    ),
    _Option(
        "sandbox_auto_approve",
        "--sandbox-auto-approve",
        ("OMICSCLAW_SANDBOX_AUTO_APPROVE",),
        _as_bool,
    ),
    _Option(
        "permission_mode",
        "--permission-mode",
        ("OMICSCLAW_PERMISSION_MODE",),
        _as_permission_mode,
    ),
    _Option(
        "permission_rules",
        "--permission-rules",
        ("OMICSCLAW_PERMISSION_RULES",),
        _as_optional_path,
    ),
    _Option(
        "audit_log",
        "--audit-log",
        ("OMICSCLAW_AUDIT_LOG",),
        _as_optional_path,
    ),
)
"""Every field of :class:`AppConfig` that a deployment can set.

The generic model and provider names are the ones
``omicsclaw/provider/config.py:632-641`` already reads, listed in the
same precedence (repo-namespaced first), so setting ``LLM_MODEL`` moves
both this layer's budget and the provider's request rather than only one
of them. Everything else is ``OMICSCLAW_``-prefixed because it did not
exist before this layer.
"""

_BY_FLAG: Mapping[str, _Option] = {option.flag: option for option in _OPTIONS}

_ARGV_TERMINATOR = "--"
"""Everything after it is somebody else's flags.

A surface has its own command line — ``oc cli -- --session X`` — and it
is :mod:`omicsclaw.launch` that cuts the line here and gives each half
to its owner. Refusing unknown flags is what makes a typo loud; the
terminator is what stops that strictness from making the rule unusable.
"""


def _first_env(env: Mapping[str, str], names: Sequence[str]) -> str:
    for name in names:
        value = env.get(name, "")
        if value:
            return value
    return ""


def _from_env(env: Mapping[str, str]) -> dict[str, object]:
    resolved: dict[str, object] = {}
    for option in _OPTIONS:
        raw = _first_env(env, option.env)
        if not raw:
            continue
        try:
            resolved[option.field] = option.parse(raw)
        except AppConfigError as exc:
            names = " / ".join(option.env)
            raise AppConfigError(f"{names}: {exc}") from exc
    return resolved


def _from_argv(argv: Sequence[str]) -> dict[str, object]:
    resolved: dict[str, object] = {}
    tokens = list(argv)
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == _ARGV_TERMINATOR:
            break
        flag, _, inline = token.partition("=")
        option = _BY_FLAG.get(flag)
        if option is None:
            raise AppConfigError(
                f"unknown option {token!r}; pass a surface's own flags "
                f"after {_ARGV_TERMINATOR!r}"
            )
        if inline:
            raw, index = inline, index + 1
        elif index + 1 < len(tokens):
            raw, index = tokens[index + 1], index + 2
        else:
            raise AppConfigError(f"{flag} needs a value")
        try:
            value = option.parse(raw)
        except AppConfigError as exc:
            raise AppConfigError(f"{flag}: {exc}") from exc
        if option.repeatable and isinstance(value, tuple):
            previous = resolved.get(option.field)
            earlier = previous if isinstance(previous, tuple) else ()
            resolved[option.field] = earlier + value
        else:
            resolved[option.field] = value
    return resolved


def fields_set_by_argv(argv: Sequence[str]) -> frozenset[str]:
    """The :class:`AppConfig` fields a deployment command line sets.

    For a surface that has to tell a person *why* a setting will not take
    effect —— the CLI's ``/auto``, reporting that ``--permission-mode``
    will outrank what it wrote —— without spelling a deployment flag
    itself: the flag set is this module's, and a second list of it is plan
    0031 Q8's second parse point. Raises :exc:`AppConfigError` when *argv*
    itself would be refused; it reads no environment, so a bad variable is
    :func:`resolve_app_config`'s to report.
    """
    return frozenset(_from_argv(argv))


def resolve_app_config(
    argv: Sequence[str],
    env: Mapping[str, str],
    **overrides: object,
) -> AppConfig:
    """Read the deployment once, from the three places it can come from.

    Precedence is later-wins over three layers: *env*, then *argv*, then
    *overrides*. An explicit keyword beats a command line beats a
    variable, which is the order of how deliberately each was chosen.

    **Both sources are required arguments** (plan 0037 §5.4). They used
    to default to the process's own, which made this the one function
    that fetched them and made two parameters exist only so that a test
    could avoid mutating globals. An injection point that only tests use
    is a design that has not finished; the process shell now passes both
    on the production path, so the defaults are gone.

    **One thing is still fetched, and plan 0037 §5.4 called this
    function pure anyway.** :attr:`AppConfig.workspace` falls back to
    :meth:`Path.cwd` below — the harness's ``os.Getwd()`` at
    ``main.go:112``, which that harness reads in its *process shell* and
    this one reads here. It is the same class of dependency as the two
    that were lifted out, and it survived because nothing scanned for
    it: the rule over this package names two globals and the working
    directory is a third. Left in place rather than promoted to a third
    parameter, because every caller would then have to supply a value
    they have no opinion about; recorded so that "pure" is not claimed
    for something that reads the process it runs in. The result is
    resolved to an absolute path here, so every tool below sees one
    spelling of it.

    Raises :exc:`AppConfigError` for an unparseable value, an unknown
    flag, or an override that is not a field of :class:`AppConfig`.
    """
    arguments = list(argv)
    source = env

    known = {field.name for field in fields(AppConfig)}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise AppConfigError(f"not fields of AppConfig: {unknown}")

    values: dict[str, object] = {}
    values.update(_from_env(source))
    values.update(_from_argv(arguments))
    values.update(overrides)

    chosen = values.get("workspace")
    workspace = chosen if isinstance(chosen, Path) else Path.cwd()
    values["workspace"] = workspace.expanduser().resolve()
    overlays = values.get("skill_env_dir")
    if isinstance(overlays, Path):
        values["skill_env_dir"] = overlays.expanduser().resolve()

    return AppConfig(**values)  # type: ignore[arg-type]
