"""Run one :class:`~omicsclaw.evals.case.Case` through the production assembly.

:func:`arun_case` builds a deployment with
:func:`~omicsclaw.entry.build_app`, handing it the case's scripted
provider, attaches an in-memory session store, and drives every message
through :meth:`~omicsclaw.entry.session.SessionRegistry.submit` the way a
surface does. It answers approval requests from the case's script or policy,
records the frames it observes, snapshots the case's temporary directory
before and after, then checks the case's assertions.

Everything runs in one process, one case at a time: the environment
edits and the replacement of ``bash``'s local runner are process-wide.
Under ``pytest-xdist`` each worker is its own process, so workers do not
interfere, and cases inside one worker still run in order.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import math
import time
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from omicsclaw.context import (
    CompactionRecord,
    ContextBudget,
    Pressure,
    estimate_messages_tokens,
    estimate_tool_tokens,
)
from omicsclaw.engine import StopReason
from omicsclaw.entry import AppConfig, build_app
from omicsclaw.entry.config import SandboxMode, SkillEnvMode, SkillsIndex
from omicsclaw.entry.events import TurnEventType
from omicsclaw.entry.session import InMemorySessionStore, attach_sessions
from omicsclaw.entry.turn import compose
from omicsclaw.observability import Telemetry
from omicsclaw.permission import PermissionMode
from omicsclaw.schema import ToolCall, ToolResult
from omicsclaw.skills import SkillIndex, load_skills
from omicsclaw.tools import ApprovalDecision

from .assertions import Failure
from .case import ApprovalRecord, Case, FsChange, Headroom, Result, SkillRun
from .hermetic import hermetic_env
from .stubs import REPO_ROOT, stubbed_skill_runs

__all__ = [
    "CASE_TIMEOUT_S",
    "EVAL_MODEL",
    "EVAL_PROVIDER",
    "OUTPUT_RESERVE",
    "SESSION_ID",
    "arun_case",
    "eval_config",
    "headroom_budget",
    "run_case",
    "skill_index",
]

EVAL_PROVIDER = "anthropic"
EVAL_MODEL = "claude-sonnet-4-5"
"""The model name the deployment budgets for. No request ever reaches it."""

SESSION_ID = "eval"
CASE_TIMEOUT_S = 30.0
OUTPUT_RESERVE = 1024
"""The output reserve of the window a compaction case is given."""

_NEXT_TIER = {
    Pressure.WARN: "soft_at",
    Pressure.SOFT: "full_at",
    Pressure.FULL: "emergency_at",
}
_TIER = {
    Pressure.WARN: "warn_at",
    Pressure.SOFT: "soft_at",
    Pressure.FULL: "full_at",
}


@lru_cache(maxsize=4)
def skill_index(root: Path = REPO_ROOT / "skills") -> SkillIndex:
    """The skill index of *root*, scanned once per process."""
    return load_skills(root)


def eval_config(case: Case, workspace: Path) -> AppConfig:
    """The :class:`~omicsclaw.entry.AppConfig` a case runs under.

    The repository's skills, the ``claude-sonnet-4-5`` window, no skill
    environment probing, no sandbox, and auto-approve or default
    permission mode, with the case's ``config`` applied last.
    """
    fields: dict[str, object] = {
        "workspace": workspace,
        "skills_dir": REPO_ROOT / "skills",
        "provider": EVAL_PROVIDER,
        "model": EVAL_MODEL,
        "skill_env": SkillEnvMode.OFF,
        "sandbox": SandboxMode.OFF,
        "permission_mode": (
            PermissionMode.AUTO_APPROVE if case.permission == "auto" else PermissionMode.DEFAULT
        ),
        "max_turns": case.max_turns,
    }
    fields.update(case.config)
    return AppConfig(**fields)  # type: ignore[arg-type]


def headroom_budget(
    baseline: int, tool_tokens: int, headroom: Headroom
) -> tuple[ContextBudget | None, str]:
    """Size a window so the first call is quiet and the trigger call hits the target.

    With ``B`` = *baseline*, ``G`` = ``headroom.trigger_tokens`` and ``t``
    the target tier's threshold, the usable window is
    ``U = floor((B + G) / t)``. It is feasible when ``B / U`` is below
    the ``WARN`` threshold and ``(B + G) / U`` is below the next tier's.
    For a ``FULL`` target the first condition works out to ``B < 3G``.
    Only the first call is checked here; :func:`arun_case` reports a
    compaction written back before the trigger call as ``headroom_missed``.

    :returns: ``(budget, "")`` when feasible, or ``(None, reason)``.
    :raises ValueError: the target is not ``WARN``, ``SOFT`` or ``FULL``.
    """
    if headroom.target not in _TIER:
        raise ValueError(f"headroom target must be WARN, SOFT or FULL, not {headroom.target}")
    probe = ContextBudget(
        context_tokens=1, reserve_output_tokens=0, reserve_tool_tokens=0, safety_ratio=0.0
    )
    threshold = getattr(probe, _TIER[headroom.target])
    ceiling = getattr(probe, _NEXT_TIER[headroom.target])
    grown = baseline + headroom.trigger_tokens
    usable = math.floor(grown / threshold)
    numbers = f"B={baseline}, G={headroom.trigger_tokens}, U={usable}"
    if usable <= 0 or baseline / usable >= probe.warn_at:
        return None, (
            f"the first call would already be at WARN ({numbers}, B/U={baseline / max(usable, 1):.3f}); "
            "raise trigger_tokens or pick a lower target"
        )
    if grown / usable >= ceiling:
        return None, (
            f"the trigger call would overshoot {headroom.target} ({numbers}); "
            "lower trigger_tokens or pick a higher target"
        )
    budget = ContextBudget(
        context_tokens=usable + OUTPUT_RESERVE + tool_tokens,
        reserve_output_tokens=OUTPUT_RESERVE,
        reserve_tool_tokens=tool_tokens,
        safety_ratio=0.0,
    )
    return budget, ""


def _snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    state: dict[str, tuple[int, int, str]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            stat = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        state[str(path)] = (stat.st_size, stat.st_mtime_ns, digest)
    return state


def _changes(
    before: Mapping[str, tuple[int, int, str]], after: Mapping[str, tuple[int, int, str]]
) -> tuple[FsChange, ...]:
    changes: list[FsChange] = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            changes.append(FsChange(path, "created"))
        elif path not in after:
            changes.append(FsChange(path, "deleted"))
        elif before[path] != after[path]:
            changes.append(FsChange(path, "modified"))
    return tuple(changes)


def _write(root: Path, files: Mapping[str, str | bytes]) -> None:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")


def _check_trigger(
    headroom: Headroom | None,
    record: CompactionRecord,
    calls_made: int,
    sizing: str,
    failures: list[Failure],
) -> None:
    """Record ``headroom_missed`` when a compaction writes back too early.

    A compaction observed after *calls_made* model calls precedes call
    number *calls_made*. It is too early when that is before
    ``headroom.trigger_call``. Compactions that were not written back
    are ignored, as is a case without a headroom.

    *calls_made* is read when the Runner sees the frame. A frame seen
    late gives a higher count, so a delay can hide an early compaction
    but cannot report one that did not happen.
    """
    if headroom is None or not record.written_back or calls_made >= headroom.trigger_call:
        return
    failures.append(
        Failure(
            "headroom_missed",
            f"a {record.pressure} compaction was written back before call {calls_made}, "
            f"earlier than trigger_call={headroom.trigger_call} ({sizing}); "
            "the calls before the trigger call already reached a tier that writes back",
        )
    )


def _decision(answer: bool | ApprovalDecision) -> ApprovalDecision:
    if isinstance(answer, ApprovalDecision):
        return answer
    return ApprovalDecision(approved=answer, reason="" if answer else "denied by the eval script")


async def arun_case(case: Case, tmp_path: Path, *, timeout_s: float = CASE_TIMEOUT_S) -> Result:
    """Run *case* in *tmp_path* and check its assertions.

    Creates ``ws`` (the workspace), ``outside`` (a sibling directory for
    ``outside_files``) and ``home`` under *tmp_path*. Besides the case's
    own assertions, the run fails on: an approval request the script had
    no answer for (``approval_unscripted``; never with an approval policy), a compaction in a case that
    does not expect one (``compaction_unexpected``), a ``GAP`` frame
    (``stream_gap``), a window that cannot be sized from the case's
    headroom (``headroom_infeasible``), a compaction written back before
    the headroom's trigger call (``headroom_missed``), a run longer than *timeout_s*
    (``case_timeout``) and a stubbed skill script that is missing or
    called without ``--output`` (``stub_target_missing``).

    :param case: The case.
    :param tmp_path: An empty directory the run may use.
    :param timeout_s: The limit for driving every exchange.
    :returns: The result, with ``passed`` false when any hard check failed.
    :raises ValueError: the case's provider factory returned a provider
        that has already been called.
    """
    workspace = tmp_path / "ws"
    outside = tmp_path / "outside"
    home = tmp_path / "home"
    for directory in (workspace, outside, home):
        directory.mkdir(parents=True, exist_ok=True)
    _write(workspace, case.files)
    _write(outside, case.outside_files)

    provider = case.provider()
    if provider.turn_index != 0 or provider.side_calls:
        raise ValueError(
            f"case {case.id}: the provider factory returned a provider that was already used"
        )

    failures: list[Failure] = []
    warnings: list[Failure] = []
    tool_names: list[str] = []
    tool_calls: list[ToolCall] = []
    tool_results: list[ToolResult] = []
    approvals: list[ApprovalRecord] = []
    compactions: list[CompactionRecord] = []
    skill_runs: list[SkillRun] = []
    stop_reasons: list[StopReason] = []
    engine_turns = 0
    final_output = ""
    run_error: BaseException | None = None
    policy = case.approvals if callable(case.approvals) else None
    queue = [] if policy is not None else list(case.approvals)

    started = time.monotonic()
    with hermetic_env(home, case.env, block_network=not case.network):
        before = _snapshot(tmp_path)
        config = eval_config(case, workspace)
        app = build_app(
            config,
            provider=provider,
            telemetry=case.telemetry() if case.telemetry is not None else Telemetry(),
            skills=skill_index() if config.skills_index is not SkillsIndex.OFF else None,
        )
        try:
            feasible = True
            sizing = ""
            if case.compaction:
                assert case.headroom is not None
                messages, _ = compose(app, (), case.prompt)
                baseline = estimate_messages_tokens(messages)
                budget, reason = headroom_budget(
                    baseline,
                    estimate_tool_tokens(app.tools_snapshot),
                    case.headroom,
                )
                if budget is None:
                    failures.append(Failure("headroom_infeasible", reason))
                    feasible = False
                else:
                    app = dataclasses.replace(app, budget=budget)
                    sizing = (
                        f"B={baseline}, G={case.headroom.trigger_tokens}, "
                        f"U={budget.context_tokens - budget.reserve_output_tokens - budget.reserve_tool_tokens}"
                    )
            app = attach_sessions(app, store=InMemorySessionStore(), abandon_grace_s=None)
            assert app.sessions is not None

            async def drive() -> None:
                nonlocal engine_turns, final_output, run_error
                for text in (case.prompt, *case.followups):
                    handle = await app.sessions.submit(SESSION_ID, text)
                    try:
                        async for frame in handle.observe():
                            kind = frame.type
                            if kind is TurnEventType.TOOL_START and frame.engine is not None:
                                call = frame.engine.tool_call
                                if call is not None:
                                    tool_names.append(call.name)
                                    tool_calls.append(call)
                            elif kind is TurnEventType.TOOL_RESULT and frame.engine is not None:
                                if frame.engine.tool_result is not None:
                                    tool_results.append(frame.engine.tool_result)
                            elif kind is TurnEventType.APPROVAL_REQUIRED and frame.approval is not None:
                                request = frame.approval
                                if policy is not None:
                                    decision = _decision(policy(request))
                                    scripted = True
                                elif queue:
                                    decision = _decision(queue.pop(0))
                                    scripted = True
                                else:
                                    decision = ApprovalDecision(
                                        approved=False, reason="unscripted approval"
                                    )
                                    scripted = False
                                    failures.append(
                                        Failure(
                                            "approval_unscripted",
                                            f"{request.tool_name} asked ({request.risk_level}): "
                                            f"{request.reason[:200]}",
                                        )
                                    )
                                approvals.append(
                                    ApprovalRecord(
                                        tool=request.tool_name,
                                        risk=str(request.risk_level),
                                        reason=request.reason,
                                        approved=decision.approved,
                                        scripted=scripted,
                                    )
                                )
                                await handle.approve(frame.request_id, decision)
                            elif kind is TurnEventType.COMPACTION and frame.compaction is not None:
                                compactions.append(frame.compaction)
                                _check_trigger(
                                    case.headroom, frame.compaction, len(provider.calls), sizing, failures
                                )
                            elif kind is TurnEventType.GAP:
                                failures.append(
                                    Failure("stream_gap", f"frames lost: {frame.gap}")
                                )
                            elif kind is TurnEventType.EXCHANGE_END:
                                if frame.terminal == "failed":
                                    run_error = frame.error
                        outcome = await handle.wait()
                    finally:
                        handle.cancel()
                    if outcome is None:
                        if run_error is None:
                            run_error = handle.error or RuntimeError(
                                f"exchange ended {handle.terminal}"
                            )
                        final_output = ""
                        return
                    engine_turns += outcome.result.turns
                    stop_reasons.append(outcome.result.stop_reason)
                    final_output = outcome.reply

            if feasible:
                with stubbed_skill_runs(
                    case.skill_stubs, app.skills, skill_runs, failures, fallback=case.skill_fallback
                ):
                    try:
                        async with asyncio.timeout(timeout_s):
                            await drive()
                    except TimeoutError:
                        failures.append(
                            Failure("case_timeout", f"the run took longer than {timeout_s}s")
                        )
        finally:
            await app.aclose()
        after = _snapshot(tmp_path)

    duration = time.monotonic() - started
    if not case.compaction and compactions:
        failures.append(
            Failure(
                "compaction_unexpected",
                f"{len(compactions)} compaction(s) at {[str(c.pressure) for c in compactions]}",
            )
        )
    if provider.exhausted:
        warnings.append(
            Failure(
                "script_exhausted",
                f"{provider.exhausted} model call(s) after the script ran out",
                is_soft=True,
            )
        )
    for run in skill_runs:
        if not run.stubbed:
            warnings.append(
                Failure("skill_ran_unstubbed", f"{run.skill}: {run.command}", is_soft=True)
            )

    draft = Result(
        case=case,
        passed=False,
        turn_count=len(provider.calls),
        engine_turns=engine_turns,
        stop_reason=stop_reasons[-1] if stop_reasons else None,
        tool_calls_executed=tuple(tool_names),
        tool_calls=tuple(tool_calls),
        tool_results=tuple(tool_results),
        final_output=final_output,
        run_error=run_error,
        failures=(),
        warnings=(),
        duration_s=duration,
        provider_calls=provider.calls,
        side_calls=provider.side_calls,
        skill_runs=tuple(skill_runs),
        approvals=tuple(approvals),
        fs_changes=_changes(before, after),
        compactions=tuple(compactions),
        workspace=workspace,
        stop_reasons=tuple(stop_reasons),
    )
    for assertion in case.assertions:
        try:
            failure = assertion.check(draft)
        except Exception as error:  # an assertion that crashes is a failed one
            failure = Failure(assertion.name, f"raised {type(error).__name__}: {error}")
        if failure is None:
            continue
        (warnings if failure.is_soft else failures).append(failure)
    return dataclasses.replace(
        draft,
        passed=not failures,
        failures=tuple(failures),
        warnings=tuple(warnings),
    )


def run_case(case: Case, tmp_path: Path, *, timeout_s: float = CASE_TIMEOUT_S) -> Result:
    """Run *case* on a fresh event loop. See :func:`arun_case`."""
    return asyncio.run(arun_case(case, tmp_path, timeout_s=timeout_s))
