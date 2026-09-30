"""The shape of one eval case and of what running it produced."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from omicsclaw.context import CompactionRecord, Pressure
from omicsclaw.engine import StopReason
from omicsclaw.schema import ToolCall, ToolResult
from omicsclaw.tools import ApprovalDecision, ApprovalRequest

from .assertions import Assertion, Failure
from .provider import RecordedCall

if TYPE_CHECKING:
    from omicsclaw.observability import Telemetry

    from .stubs import StubResult

__all__ = [
    "ApprovalPolicy",
    "ApprovalRecord",
    "Case",
    "CaseProvider",
    "FsChange",
    "Headroom",
    "Result",
    "SkillRun",
]


@runtime_checkable
class CaseProvider(Protocol):
    """What the Runner reads from a case's provider, besides the LLM protocol.

    :class:`~omicsclaw.evals.provider.ScriptedProvider` has all four; so
    does a recording wrapper around a real provider.
    """

    @property
    def calls(self) -> tuple[RecordedCall, ...]: ...

    @property
    def side_calls(self) -> tuple[RecordedCall, ...]: ...

    @property
    def turn_index(self) -> int: ...

    @property
    def exhausted(self) -> int: ...


ApprovalPolicy = Callable[[ApprovalRequest], ApprovalDecision]
"""A function that answers each approval request as it arrives."""


@dataclass(frozen=True)
class Headroom:
    """Which compaction tier a case means to reach, and when.

    The Runner sizes the context window from these numbers so that the
    first model call is below ``WARN`` and call *trigger_call* lands in
    *target*. For a ``FULL`` target the first-call condition means
    ``B < 3G`` (``B`` the first call's tokens, ``G`` *trigger_tokens*),
    about 14.1k tokens for ``G = 4700``.

    The calls in between may still reach ``WARN``. That writes nothing
    back when there is no large result to offload, so it does not
    disturb the case. A compaction that does write back before
    *trigger_call* fails the run with ``headroom_missed``.

    :param target: The tier to reach: ``WARN``, ``SOFT`` or ``FULL``.
    :param trigger_call: The main-line call (0-based) before which the
        tier should be reached.
    :param trigger_tokens: How many tokens the conversation is expected
        to grow between the first call and that one. The case author
        estimates it from the script.
    """

    target: Pressure
    trigger_call: int
    trigger_tokens: int


@dataclass(frozen=True)
class Case:
    """One scripted scenario and what must hold after it runs.

    :param id: ``"<category>/<name>"``.
    :param category: Must equal the prefix of *id*.
    :param prompt: The first user message.
    :param provider: A factory returning a fresh provider per run: a
        :class:`~omicsclaw.evals.provider.ScriptedProvider`, or any
        :class:`~omicsclaw.provider.LLMProvider` that is also a
        :class:`CaseProvider`.
    :param assertions: What is checked after the run.
    :param followups: Further user messages, sent in the same session
        after the first exchange ends.
    :param max_turns: The engine's turn ceiling.
    :param permission: ``"auto"`` runs in auto-approve mode, where only
        dangerous commands, ask rules and protected paths ask; ``"ask"``
        runs in the default mode, where every tool with an ask policy
        asks.
    :param approvals: Answers to approval requests, in the order the
        requests arrive. A ``bool`` becomes an
        :class:`~omicsclaw.tools.ApprovalDecision`. May instead be an
        :data:`ApprovalPolicy`, called once per request; a policy never
        runs out, so it never records ``approval_unscripted``.
    :param skill_stubs: Skill name to the output a run of its script
        returns instead of running.
    :param skill_fallback: The output a run of any other skill's script
        returns instead of running (see
        :func:`~omicsclaw.evals.stubs.stubbed_skill_runs`). ``None`` runs
        those scripts for real.
    :param compaction: Whether compaction is expected. When false, any
        compaction fails the case.
    :param headroom: Required when *compaction* is true.
    :param files: Files written into the workspace before the run,
        relative path to content.
    :param outside_files: Files written into a sibling directory of the
        workspace, which the case can check is left alone.
    :param env: Extra environment variables for the run.
    :param network: Whether outbound connections are allowed. The rest of
        the hermetic environment applies either way.
    :param config: :class:`~omicsclaw.entry.AppConfig` field overrides.
    :param telemetry: A factory for the telemetry to assemble with.
        ``None`` uses an inactive one.
    :raises ValueError: *category* is not the prefix of *id*, or
        *compaction* is true without *headroom*.
    """

    id: str
    category: str
    prompt: str
    provider: Callable[[], CaseProvider]
    assertions: tuple[Assertion, ...]
    followups: tuple[str, ...] = ()
    max_turns: int = 20
    permission: Literal["auto", "ask"] = "auto"
    approvals: tuple[bool | ApprovalDecision, ...] | ApprovalPolicy = ()
    skill_stubs: Mapping[str, StubResult] = field(default_factory=dict)
    skill_fallback: StubResult | None = None
    compaction: bool = False
    headroom: Headroom | None = None
    files: Mapping[str, str | bytes] = field(default_factory=dict)
    outside_files: Mapping[str, str] = field(default_factory=dict)
    env: Mapping[str, str] = field(default_factory=dict)
    network: bool = False
    config: Mapping[str, object] = field(default_factory=dict)
    telemetry: Callable[[], Telemetry] | None = None

    def __post_init__(self) -> None:
        prefix, sep, rest = self.id.partition("/")
        if not sep or not rest or prefix != self.category:
            raise ValueError(
                f"case id {self.id!r} must be '<category>/<name>' with category {self.category!r}"
            )
        if self.compaction and self.headroom is None:
            raise ValueError(f"case {self.id!r} sets compaction=True without a headroom")
        if self.permission not in ("auto", "ask"):
            raise ValueError(f"permission must be 'auto' or 'ask', not {self.permission!r}")


@dataclass(frozen=True)
class SkillRun:
    """One ``bash`` command that ran a skill's script.

    :param skill: The skill name.
    :param domain: The skill's domain in the index.
    :param command: The command as sent.
    :param stubbed: Whether the stub answered instead of a real run.
    """

    skill: str
    domain: str
    command: str
    stubbed: bool


@dataclass(frozen=True)
class ApprovalRecord:
    """One approval request and how the Runner answered it.

    :param tool: The tool that asked.
    :param risk: The risk level it declared.
    :param reason: The reason it gave.
    :param approved: The answer.
    :param scripted: Whether the answer came from the case's script.
        ``False`` means the script had none left and the Runner denied it.
    """

    tool: str
    risk: str
    reason: str
    approved: bool
    scripted: bool


@dataclass(frozen=True)
class FsChange:
    """A file that differs between the snapshots taken before and after.

    :param path: The absolute path.
    :param kind: ``"created"``, ``"modified"`` or ``"deleted"``.
    """

    path: str
    kind: Literal["created", "modified", "deleted"]


@dataclass(frozen=True)
class Result:
    """What running one :class:`Case` produced.

    ``turn_count`` counts main-line model calls across every exchange,
    retries included; ``engine_turns`` is the sum of the engine's own
    ``RunResult.turns``. ``tool_calls_executed`` and ``tool_calls`` come
    from ``TOOL_START`` frames, so they include calls the permission gate
    later refused. ``final_output`` is the last exchange's reply, and
    ``run_error`` the exception of the first exchange that failed.
    """

    case: Case
    passed: bool
    turn_count: int
    engine_turns: int
    stop_reason: StopReason | None
    tool_calls_executed: tuple[str, ...]
    tool_calls: tuple[ToolCall, ...]
    tool_results: tuple[ToolResult, ...]
    final_output: str
    run_error: BaseException | None
    failures: tuple[Failure, ...]
    warnings: tuple[Failure, ...]
    duration_s: float
    provider_calls: tuple[RecordedCall, ...]
    side_calls: tuple[RecordedCall, ...]
    skill_runs: tuple[SkillRun, ...]
    approvals: tuple[ApprovalRecord, ...]
    fs_changes: tuple[FsChange, ...]
    compactions: tuple[CompactionRecord, ...]
    workspace: Path
    stop_reasons: tuple[StopReason, ...] = ()
    """One stop reason per exchange that completed, in order."""
