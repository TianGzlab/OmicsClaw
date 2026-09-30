"""The ``run_skill`` tool: run one method of a skill as one supervised, scored trial."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from omicsclaw.ensemble.runner import HASH_TIMEOUT_S, EnsembleRunner, TrialResult
from omicsclaw.ensemble.space import SpecError
from omicsclaw.ensemble.store import read_json
from omicsclaw.ensemble.tuning.budget import BudgetExceeded, RunBudget
from omicsclaw.ensemble.tuning.scoring import KReference, score_trial
from omicsclaw.tools._workspace import PathRefused, Workspace
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import context_value, pause_tool_timeout
from omicsclaw.tools.function_tool import FunctionTool, ToolArgumentError

__all__ = [
    "RUN_SKILL_POLICY",
    "RUN_SKILL_SCHEMA",
    "RUN_SKILL_TOOL_NAME",
    "compact_result",
    "fixed_k_score",
    "reference_path",
    "run_skill_description",
    "run_skill_tool",
]

RUN_SKILL_TOOL_NAME = "run_skill"

BACKSTOP_MARGIN_S = 60.0

RUN_SKILL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "skill": {"type": "string", "description": "A skill listed in this tool's description."},
        "method": {"type": "string", "description": "One of that skill's methods."},
        "input": {"type": "string", "description": "workspace path of the input .h5ad"},
        "params": {
            "type": "object",
            "description": "Parameter names (snake_case) to values; omitted parameters take their defaults.",
        },
        "run_id": {
            "type": "string",
            "description": "Groups trials on one input for comparison; omitted, a new run is started.",
        },
        "timeout_s": {"type": "number", "description": "A tighter run-time limit for this trial, in seconds."},
    },
    "required": ["skill", "method", "input"],
    "additionalProperties": False,
}

RUN_SKILL_POLICY = ToolPolicy(
    risk_level=RiskLevel.MEDIUM,
    approval_mode=ApprovalMode.AUTO,
    read_only=False,
    concurrency_safe=True,
    writes_workspace=True,
    touches_network=False,
    allowed_in_background=False,
    tags=frozenset({"skills", "ensemble", "execution"}),
)


def run_skill_description(runner: EnsembleRunner) -> str:
    """What the model is told about ``run_skill`` in this deployment."""
    lines = [
        "Run one method of a skill as one trial: a supervised run of the skill's script "
        "in its own directory, followed by a quality score from the skill's internal "
        "metric panel. Use it to compare methods or parameter settings on the same input; "
        "several run_skill calls in the same turn run in parallel, limited by the shared "
        "GPU/memory/CPU pool.",
        "",
        "Runnable skills and methods:",
    ]
    for spec in runner.catalog.specs():
        lines.append(f"- {spec.skill}: {', '.join(spec.methods)}")
    hours = runner.call_ceiling_s / 3600
    lines += [
        "",
        "Use the same run_id for every trial you want to compare on one input; a run_id "
        "is bound to its skill and input. Call use_skill first if you need a method's "
        "parameters: a bad parameter is refused with the method's search space.",
        "Trial directories keep labels, metrics and result.json (and the processed .h5ad of "
        "each method's best trial) — no figures or reports. For an analysis the user will "
        "read, run the skill with bash as its SKILL.md describes.",
        f"One call can take hours: reading the input, up to {runner.max_queue_s:g} s waiting "
        f"for resources, {runner.max_trial_s:g} s running and then scoring, at most "
        f"{runner.call_ceiling_s:g} s (about {hours:.1f} h) in all. A turn "
        "timeout set by the deployment cancels trials still running.",
        "Failures, time-outs, memory limits and GPU methods that fell back to CPU "
        "(degraded: no_gpu) are reported as results, not hidden.",
        "When the run has a fixed-K reference (reference.json of a tuning run), the result "
        "carries fixed_k_score; it is comparable only between trials with the same number of "
        "clusters, and is null otherwise (use inspect_trials).",
    ]
    return "\n".join(lines)


def reference_path(runner: EnsembleRunner, run_id: str) -> Path | None:
    """The fixed-K reference of *run_id*: ``<run>/tuning/reference.json``, else ``<run>/reference.json``."""
    run_dir = runner.store.run_dir(run_id)
    for candidate in (run_dir / "tuning" / "reference.json", run_dir / "reference.json"):
        if candidate.is_file():
            return candidate
    return None


def fixed_k_score(result: TrialResult, reference: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The trial's fixed-K score and standard error against *reference* (a ``reference.json``), or ``None``."""
    if result.status != "ok" or not result.metrics or not reference:
        return None
    n_labels = result.metrics.get("n_labels")
    entry = (reference.get("per_k") or {}).get(str(n_labels))
    if entry is None:
        return None
    scored = score_trial(result.metrics, KReference.from_json(entry))
    if scored.score is None:
        return None
    return {"score": scored.score, "se": scored.se, "k": int(n_labels)}


def compact_result(result: TrialResult, reference: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The fields of *result* returned to the model.

    ``fixed_k_score`` is set when *reference* covers the trial's number of labels.
    """
    metrics: dict[str, Any] | None = None
    if result.metrics is not None:
        document = result.metrics
        raw = document.get("raw") or {}
        adjusted = document.get("adjusted") or {}
        metrics = {
            "score": document.get("score"),
            "n_labels": document.get("n_labels"),
            "components": {
                name: {"raw": raw.get(name), "adjusted": adjusted.get(name)} for name in raw
            },
        }
        if document.get("errors"):
            metrics["errors"] = document["errors"]
    fixed = fixed_k_score(result, reference)
    return {
        "status": result.status,
        "stage": result.stage,
        "run_id": result.run_id,
        "method": result.method,
        "trial": result.trial,
        "output_dir": result.output_dir,
        "params": result.params,
        "metrics": metrics,
        "fixed_k_score": fixed["score"] if fixed else None,
        "fixed_k_se": fixed["se"] if fixed else None,
        "wall_s": result.wall_s,
        "queued_s": result.queued_s,
        "peak_mem_gb": result.peak_mem_gb,
        "mem_metric": result.mem_metric,
        "lease_gpu": result.lease_gpu,
        "device": result.device,
        "device_source": result.device_source,
        "degraded": result.degraded,
        "h5ad": result.h5ad,
        "error": result.error,
        "log": result.log,
    }


def run_skill_tool(
    runner: EnsembleRunner,
    workspace: Workspace,
    *,
    backstop_margin_s: float = BACKSTOP_MARGIN_S,
    budget: RunBudget | None = None,
    input_check: Callable[[Path, str], Awaitable[None]] | None = None,
) -> FunctionTool:
    """Build ``run_skill`` over *runner*, resolving inputs inside *workspace*.

    *budget* counts every prepared trial against the calling session
    (``context_value("session_id")``) and method before it starts; past the
    cap the call is refused with :exc:`ToolArgumentError` and nothing runs.
    *input_check* is awaited with the input path and skill before a trial is
    prepared and raises :exc:`SpecError` to refuse the input.

    The whole call runs inside :func:`~omicsclaw.tools.context.pause_tool_timeout`,
    so the engine's per-tool timeout does not cut a long trial short; the tool
    bounds itself instead: preparing (hashing the input) is limited to
    ``HASH_TIMEOUT_S``, and everything after admission to the trial's run-time
    limit plus the scoring limit plus a margin. A trial that fails is an ordinary
    result; only invalid arguments raise :exc:`ToolArgumentError`.
    """

    async def run(
        skill: str,
        method: str,
        input: str,
        params: Mapping[str, Any] | None = None,
        run_id: str | None = None,
        timeout_s: float | None = None,
    ) -> str:
        path = _resolve(workspace, input)
        with pause_tool_timeout():
            if input_check is not None:
                try:
                    await input_check(path, skill)
                except SpecError as exc:
                    raise ToolArgumentError(str(exc)) from None
            try:
                spec = await asyncio.wait_for(
                    asyncio.to_thread(
                        runner.prepare,
                        skill=skill,
                        method=method,
                        input=path,
                        params=params or {},
                        run_id=run_id,
                        timeout_s=timeout_s,
                    ),
                    HASH_TIMEOUT_S,
                )
            except SpecError as exc:
                raise ToolArgumentError(str(exc)) from None
            except TimeoutError:
                raise RuntimeError(
                    f"reading and hashing {input!r} took longer than {HASH_TIMEOUT_S:g} s"
                ) from None
            if budget is not None:
                try:
                    budget.reserve(str(context_value("session_id", "")), spec.method)
                except BudgetExceeded as exc:
                    raise ToolArgumentError(str(exc)) from None
            backstop = spec.limits.timeout_s + runner.score_timeout_s + backstop_margin_s
            result = await runner.run(spec, backstop_s=backstop)
        reference = None
        store = getattr(runner, "store", None)
        if store is not None:
            located = reference_path(runner, result.run_id)
            reference = read_json(located) if located is not None else None
        return json.dumps(compact_result(result, reference), ensure_ascii=False)

    return FunctionTool(
        RUN_SKILL_TOOL_NAME,
        run_skill_description(runner),
        run,
        parameters=RUN_SKILL_SCHEMA,
        policy=RUN_SKILL_POLICY,
    )


def _resolve(workspace: Workspace, raw: str) -> Path:
    try:
        path = workspace.resolve(raw)
    except PathRefused as exc:
        raise ToolArgumentError(f"input: {exc}") from None
    if not path.is_file():
        raise ToolArgumentError(f"input: {raw!r} is not a file in the workspace")
    return path
