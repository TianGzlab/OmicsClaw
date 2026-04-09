"""Harness loop — code-level evolution of OmicsClaw skills.

Upgrades the autoagent from parameter optimization to bounded code
evolution.  The loop:

1. **Baseline**: Run the unmodified skill, collect RunTrace, evaluate.
2. **Iterate**: Build harness directive → LLM suggests patch →
   validate → create isolated worktree → apply → run trial →
   collect trace → hard gates → evaluate → keep/discard →
   record accepted commits and patch artifacts.
3. **Termination**: Max iterations, convergence, or 3 consecutive failures.

The harness loop preserves the existing ``param_loop`` (optimization_loop.py)
and adds a code-evolution layer on top.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from omicsclaw.autoagent.constants import (
    CONSECUTIVE_CRASH_LIMIT,
    ERROR_OUTPUT_MAX_CHARS,
)
from omicsclaw.autoagent.edit_surface import EditSurface
from omicsclaw.autoagent.errors import MetricConfigError, OptimizationCancelled
from omicsclaw.autoagent.evaluator import Evaluator
from omicsclaw.autoagent.experiment_ledger import ExperimentLedger, TrialRecord
from omicsclaw.autoagent.failure_memory import FailureBank, FailureRecord
from omicsclaw.autoagent.hard_gates import run_hard_gates
from omicsclaw.autoagent.harness_directive import build_harness_directive
from omicsclaw.autoagent.harness_workspace import (
    AcceptedPatchRecord,
    HarnessWorkspace,
    PromotionResult,
)
from omicsclaw.autoagent.judge import judge
from omicsclaw.autoagent.patch_engine import (
    PatchPlan,
    apply_patch,
    parse_patch_response,
    validate_patch,
)
from omicsclaw.autoagent.runner import execute_trial
from omicsclaw.autoagent.search_space import SearchSpace
from omicsclaw.autoagent.trace import RunTrace, TraceCollector, clear_result_json_cache

logger = logging.getLogger(__name__)

EventCallback = Callable[[str, dict[str, Any]], None] | None


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class HarnessResult:
    """Final result of a harness evolution run."""

    best_trial: TrialRecord | None = None
    improvement_pct: float = 0.0
    total_iterations: int = 0
    patches_accepted: int = 0
    patches_rejected: int = 0
    converged: bool = False
    success: bool = True
    error_message: str | None = None
    accepted_patch_files: list[str] = field(default_factory=list)
    accepted_patches: list[AcceptedPatchRecord] = field(default_factory=list)
    promotion: dict[str, Any] = field(default_factory=dict)
    sandbox_repo: str = ""
    source_project_commit: str = ""


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------


class HarnessLoop:
    """Code-level evolution loop for OmicsClaw skills.

    Parameters
    ----------
    skill_name, method:
        Target skill and method to evolve.
    input_path:
        Path to input data (or empty for demo mode).
    output_root:
        Root directory for trial outputs.
    surface:
        Editable surface defining which files can be modified.
    evaluator:
        Evaluates trial outputs to produce quality scores.
    search_space:
        Parameter search space (used for trial execution).
    max_iterations:
        Maximum evolution iterations.
    evolution_goal:
        Human-readable description of the evolution objective.
    demo:
        If True, use --demo flag for trial execution.
    """

    def __init__(
        self,
        skill_name: str,
        method: str,
        input_path: str,
        output_root: Path,
        surface: EditSurface,
        evaluator: Evaluator,
        search_space: SearchSpace,
        *,
        max_iterations: int = 10,
        evolution_goal: str = "",
        auto_promote: bool = False,
        llm_provider: str = "",
        llm_model: str = "",
        llm_provider_config: dict[str, str] | None = None,
        demo: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.skill_name = skill_name
        self.method = method
        self.input_path = input_path
        self.output_root = Path(output_root)
        self.surface = surface
        self.evaluator = evaluator
        self.search_space = search_space
        self.max_iterations = max_iterations
        self.evolution_goal = evolution_goal
        self.auto_promote = auto_promote
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.llm_provider_config = dict(llm_provider_config or {})
        self.demo = demo
        self.cancel_event = cancel_event

        self.output_root.mkdir(parents=True, exist_ok=True)
        self.ledger = ExperimentLedger(self.output_root / "experiment_ledger.jsonl")
        self.failure_bank = FailureBank(self.output_root / "failure_bank.jsonl")

    def run(self, on_event: EventCallback = None) -> HarnessResult:
        """Execute the full harness evolution loop."""

        def emit(event_type: str, data: dict[str, Any]) -> None:
            if on_event:
                on_event(event_type, data)

        workspace = HarnessWorkspace(self.surface.project_root, self.output_root)
        try:
            workspace.create()
        except Exception as exc:
            logger.error("Failed to create harness sandbox: %s", exc)
            return self._finalize(
                baseline=None,
                best=None,
                converged=False,
                patches_accepted=0,
                patches_rejected=0,
                accepted_files=[],
                accepted_patches=[],
                promotion=None,
                workspace=workspace,
                success=False,
                error_message=f"Failed to create harness sandbox: {exc}",
                on_event=on_event,
            )

        # ---- Step 1: Baseline (unmodified code) ----
        self._raise_if_cancelled()
        self._emit_progress(
            emit,
            phase="baseline",
            completed=0,
            iteration=0,
        )

        baseline_params = self.search_space.defaults_dict()
        baseline, baseline_trace = self._run_and_trace(
            trial_id=0,
            params=baseline_params,
            description="baseline (unmodified code)",
            project_root=workspace.repo_root,
        )
        baseline.code_state = workspace.baseline_code_state()

        if baseline.status == "crash":
            self.ledger.append(baseline)
            return self._finalize(
                baseline=baseline,
                best=baseline,
                converged=False,
                patches_accepted=0,
                patches_rejected=0,
                accepted_files=[],
                accepted_patches=[],
                promotion=None,
                workspace=workspace,
                success=False,
                error_message=(
                    "Baseline crashed — skill cannot run with current code. "
                    f"stderr: {baseline.error_output[:300]}"
                ),
                on_event=on_event,
            )

        baseline.status = "baseline"
        self.ledger.append(baseline)
        best = baseline
        traces: list[RunTrace] = [baseline_trace]

        emit("trial_complete", {
            "trial_id": 0,
            "iteration": 0,
            "score": baseline.composite_score,
            "status": "baseline",
        })
        self._emit_progress(
            emit,
            phase="baseline",
            completed=1,
            best_score=baseline.composite_score,
            iteration=0,
        )

        if not math.isfinite(baseline.composite_score):
            return self._finalize(
                baseline=baseline,
                best=baseline,
                converged=False,
                patches_accepted=0,
                patches_rejected=0,
                accepted_files=[],
                accepted_patches=[],
                promotion=None,
                workspace=workspace,
                success=False,
                error_message=(
                    f"Baseline scored {baseline.composite_score} — "
                    "metrics extraction failed."
                ),
                on_event=on_event,
            )

        # ---- Step 2: Iterative evolution ----
        consecutive_failures = 0
        patches_accepted = 0
        patches_rejected = 0
        accepted_files: list[str] = []
        accepted_patches: list[AcceptedPatchRecord] = []
        converged = False

        for iteration in range(1, self.max_iterations + 1):
            self._raise_if_cancelled()
            self._emit_progress(
                emit,
                phase="evolving",
                completed=iteration,
                best_score=best.composite_score,
                iteration=iteration,
            )

            # Build directive
            gate_verdict = run_hard_gates(
                traces[-1],
                Path(best.output_dir) if best.output_dir else self.output_root,
            )
            directive = build_harness_directive(
                skill_name=self.skill_name,
                method=self.method,
                surface=self.surface,
                traces=traces,
                gate_verdict=gate_verdict,
                failure_history=self.failure_bank.to_directive_context(),
                iteration=iteration,
                max_iterations=self.max_iterations,
                evolution_goal=self.evolution_goal,
            )

            # Ask LLM for patch
            self._raise_if_cancelled()
            emit("reasoning", {
                "trial_id": iteration,
                "iteration": iteration,
                "phase": "asking_llm",
            })

            try:
                response_text = self._call_llm(directive)
            except OptimizationCancelled:
                raise
            except Exception as exc:
                logger.error("LLM call failed: %s", exc)
                promotion = self._promote_workspace(workspace, accepted_files)
                return self._finalize(
                    baseline, best, converged, patches_accepted,
                    patches_rejected, accepted_files, accepted_patches,
                    promotion=promotion,
                    workspace=workspace,
                    success=False,
                    error_message=f"LLM call failed: {exc}",
                    on_event=on_event,
                )

            # Parse patch
            self._raise_if_cancelled()
            try:
                patch = parse_patch_response(response_text)
            except ValueError as exc:
                logger.warning("Failed to parse LLM patch: %s", exc)
                self._record_iteration_rejection_without_trial(
                    emit,
                    iteration=iteration,
                    params=baseline_params,
                    reasoning="",
                    reason=str(exc),
                    stage="parse",
                )
                consecutive_failures += 1
                if consecutive_failures >= CONSECUTIVE_CRASH_LIMIT:
                    promotion = self._promote_workspace(workspace, accepted_files)
                    return self._finalize(
                        baseline, best, converged, patches_accepted,
                        patches_rejected, accepted_files, accepted_patches,
                        promotion=promotion,
                        workspace=workspace,
                        success=False,
                        error_message="3 consecutive parse failures.",
                        on_event=on_event,
                    )
                continue

            if patch.converged:
                emit("reasoning", {
                    "trial_id": iteration,
                    "iteration": iteration,
                    "reasoning": patch.reasoning,
                })
                converged = True
                break

            emit("reasoning", {
                "trial_id": iteration,
                "iteration": iteration,
                "reasoning": patch.reasoning,
                "diff_summary": patch.diff_summary,
            })

            trial: TrialRecord | None = None
            trial_trace: RunTrace | None = None
            modified: list[str] = []

            with workspace.trial_worktree(iteration, self.surface) as (
                trial_root,
                trial_surface,
            ):
                validation = validate_patch(patch, trial_surface)
                if not validation.valid:
                    logger.warning(
                        "Patch validation failed: %s", validation.error_summary,
                    )
                    self._record_failure(
                        iteration, patch,
                        gate_failures=["validation"],
                        error_summary=validation.error_summary,
                    )
                    self._record_iteration_rejection_without_trial(
                        emit,
                        iteration=iteration,
                        params=baseline_params,
                        reasoning=patch.reasoning,
                        reason=validation.error_summary,
                        stage="validation",
                    )
                    consecutive_failures += 1
                    patches_rejected += 1
                    if consecutive_failures >= CONSECUTIVE_CRASH_LIMIT:
                        promotion = self._promote_workspace(workspace, accepted_files)
                        return self._finalize(
                            baseline, best, converged, patches_accepted,
                            patches_rejected, accepted_files, accepted_patches,
                            promotion=promotion,
                            workspace=workspace,
                            success=False,
                            error_message=(
                                f"{CONSECUTIVE_CRASH_LIMIT} consecutive patch "
                                "validation failures."
                            ),
                            on_event=on_event,
                        )
                    continue

                try:
                    modified = apply_patch(patch, trial_surface)
                except (PermissionError, ValueError) as exc:
                    logger.warning("Patch application failed: %s", exc)
                    self._record_failure(
                        iteration, patch,
                        gate_failures=["apply"],
                        error_summary=str(exc),
                    )
                    self._record_iteration_rejection_without_trial(
                        emit,
                        iteration=iteration,
                        params=baseline_params,
                        reasoning=patch.reasoning,
                        reason=str(exc),
                        stage="apply",
                    )
                    consecutive_failures += 1
                    patches_rejected += 1
                    if consecutive_failures >= CONSECUTIVE_CRASH_LIMIT:
                        promotion = self._promote_workspace(workspace, accepted_files)
                        return self._finalize(
                            baseline, best, converged, patches_accepted,
                            patches_rejected, accepted_files, accepted_patches,
                            promotion=promotion,
                            workspace=workspace,
                            success=False,
                            error_message=(
                                f"{CONSECUTIVE_CRASH_LIMIT} consecutive patch "
                                "application failures."
                            ),
                            on_event=on_event,
                        )
                    continue

                self._raise_if_cancelled()
                emit("trial_start", {
                    "trial_id": iteration,
                    "iteration": iteration,
                    "files": modified,
                    "params": {},
                })

                trial, trial_trace = self._run_and_trace(
                    trial_id=iteration,
                    params=baseline_params,
                    description=patch.reasoning,
                    project_root=trial_root,
                )
                trial.reasoning = patch.reasoning
                traces.append(trial_trace)

                trial_output = Path(trial.output_dir) if trial.output_dir else (
                    self.output_root / f"trial_{iteration:04d}"
                )
                gate_result = run_hard_gates(trial_trace, trial_output)

                if not gate_result.all_passed:
                    logger.info(
                        "Iter %d: hard gates FAILED in sandbox — discarding. %s",
                        iteration, gate_result.summary(),
                    )
                    trial.status = "discard"
                    self._record_failure(
                        iteration, patch,
                        gate_failures=[g.name for g in gate_result.failed_gates],
                        error_summary=gate_result.summary(),
                    )
                    # Patch was successfully applied and executed — reset the
                    # "cannot produce a valid patch" counter.  Gate failures
                    # are quality issues, not patch authoring failures.
                    consecutive_failures = 0
                    patches_rejected += 1
                    self.ledger.append(trial)

                    emit("trial_judgment", {
                        "trial_id": iteration,
                        "iteration": iteration,
                        "decision": "discard",
                        "reason": gate_result.summary(),
                    })
                    emit("trial_complete", {
                        "trial_id": iteration,
                        "iteration": iteration,
                        "score": trial.composite_score,
                        "status": trial.status,
                    })
                    continue

                prior_best_score = best.composite_score
                judgment = judge(
                    trial, best, self.ledger,
                    baseline_params=baseline_params,
                    metrics=self.evaluator.metrics,
                )
                if trial.status != "crash":
                    trial.status = judgment.decision

                if judgment.new_best:
                    try:
                        accepted_record = workspace.commit_accepted_patch(
                            iteration=iteration,
                            worktree=trial_root,
                            patch=patch,
                            modified_files=modified,
                        )
                    except Exception as exc:
                        logger.error(
                            "Iter %d: failed to record accepted patch: %s",
                            iteration,
                            exc,
                        )
                        trial.status = "discard"
                        self._record_failure(
                            iteration, patch,
                            gate_failures=["record"],
                            error_summary=str(exc),
                        )
                        consecutive_failures += 1
                        patches_rejected += 1
                        self.ledger.append(trial)
                        emit("trial_judgment", {
                            "trial_id": iteration,
                            "iteration": iteration,
                            "decision": "discard",
                            "reason": f"Failed to record accepted patch: {exc}",
                        })
                        emit("trial_complete", {
                            "trial_id": iteration,
                            "iteration": iteration,
                            "score": trial.composite_score,
                            "status": trial.status,
                        })
                        if consecutive_failures >= CONSECUTIVE_CRASH_LIMIT:
                            break
                        continue

                    trial.code_state = accepted_record.to_dict()
                    best = trial
                    consecutive_failures = 0
                    patches_accepted += 1
                    accepted_files.extend(modified)
                    accepted_patches.append(accepted_record)
                    logger.info(
                        "Iter %d: ACCEPTED patch (%s). Score: %.4f -> %.4f",
                        iteration, patch.diff_summary,
                        prior_best_score, trial.composite_score,
                    )
                else:
                    # Patch applied, executed, and scored — just didn't improve.
                    # This is NOT a patch authoring failure; reset the counter.
                    consecutive_failures = 0
                    patches_rejected += 1
                    self._record_failure(
                        iteration, patch,
                        gate_failures=[],
                        error_summary=f"Score did not improve: {judgment.reason}",
                    )
                    logger.info(
                        "Iter %d: DISCARDED patch. %s", iteration, judgment.reason,
                    )

                self.ledger.append(trial)
                emit("trial_judgment", {
                    "trial_id": iteration,
                    "iteration": iteration,
                    "decision": judgment.decision,
                    "reason": judgment.reason,
                    "new_best": judgment.new_best,
                })
                emit("trial_complete", {
                    "trial_id": iteration,
                    "iteration": iteration,
                    "score": trial.composite_score,
                    "status": trial.status,
                })

        promotion = self._promote_workspace(workspace, accepted_files)
        if best is not None and best.status in {"baseline", "keep"}:
            best.code_state = (
                accepted_patches[-1].to_dict()
                if accepted_patches and best.status == "keep"
                else workspace.baseline_code_state()
            )

        return self._finalize(
            baseline, best, converged, patches_accepted,
            patches_rejected, accepted_files, accepted_patches,
            promotion=promotion,
            workspace=workspace,
            success=True,
            on_event=on_event,
        )

    # ----- internal -----

    def _run_and_trace(
        self,
        trial_id: int,
        params: dict[str, Any],
        description: str = "",
        project_root: str | Path | None = None,
    ) -> tuple[TrialRecord, RunTrace]:
        """Execute a trial and collect its RunTrace."""
        self._raise_if_cancelled()
        trial_output = self.output_root / f"trial_{trial_id:04d}"
        trial_output.mkdir(parents=True, exist_ok=True)

        clear_result_json_cache()

        execution = execute_trial(
            skill_name=self.skill_name,
            input_path=self.input_path,
            output_dir=trial_output,
            params=params,
            search_space=self.search_space,
            project_root=project_root,
            demo=self.demo,
            cancel_event=self.cancel_event,
        )
        self._raise_if_cancelled()

        # Collect trace
        trace = TraceCollector.collect(
            trial_id=trial_id,
            skill_name=self.skill_name,
            method=self.method,
            execution=execution,
            output_dir=Path(execution.output_dir),
            user_params=params,
            skill_defaults=self.search_space.defaults_dict(),
        )
        trace.save(Path(execution.output_dir))

        # Build trial record
        if not execution.success:
            error_output = (execution.stderr or execution.stdout or "").strip()
            if len(error_output) > ERROR_OUTPUT_MAX_CHARS:
                error_output = "...\n" + error_output[-ERROR_OUTPUT_MAX_CHARS:]
            record = TrialRecord(
                trial_id=trial_id,
                params=params,
                composite_score=float("-inf"),
                status="crash",
                reasoning=description,
                output_dir=execution.output_dir,
                duration_seconds=execution.duration_seconds,
                error_output=error_output,
            )
            return record, trace

        try:
            eval_result = self.evaluator.evaluate(
                Path(execution.output_dir), params=params,
            )
        except MetricConfigError as exc:
            logger.error("Metric config error for trial %d: %s", trial_id, exc)
            record = TrialRecord(
                trial_id=trial_id,
                params=params,
                composite_score=float("-inf"),
                status="crash",
                reasoning=description,
                output_dir=execution.output_dir,
                duration_seconds=execution.duration_seconds,
                error_output=f"MetricConfigError: {exc}",
            )
            return record, trace
        except Exception as exc:
            logger.error("Evaluation failed for trial %d: %s", trial_id, exc)
            record = TrialRecord(
                trial_id=trial_id,
                params=params,
                composite_score=float("-inf"),
                status="crash",
                reasoning=description,
                output_dir=execution.output_dir,
                duration_seconds=execution.duration_seconds,
                error_output=f"Evaluation error: {exc}",
            )
            return record, trace

        # Enrich trace with evaluation metrics
        trace.quality.quality_metrics = dict(eval_result.raw_metrics)

        record = TrialRecord(
            trial_id=trial_id,
            params=params,
            composite_score=eval_result.composite_score,
            raw_metrics=eval_result.raw_metrics,
            status="pending",
            reasoning=description,
            output_dir=execution.output_dir,
            duration_seconds=execution.duration_seconds,
            evaluation_success=eval_result.success,
            missing_metrics=eval_result.missing_metrics,
        )
        return record, trace

    def _call_llm(self, directive: str) -> str:
        """Call the LLM via OpenAI-compatible API."""
        from omicsclaw.autoagent.llm_client import call_llm

        return call_llm(
            directive,
            system_prompt=(
                "You are a harness engineer for OmicsClaw. "
                "You modify skill code to improve analysis quality. "
                "Respond ONLY with valid JSON following the specified format."
            ),
            temperature=0.4,
            max_tokens=4096,
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            llm_provider_config=self.llm_provider_config,
        )

    def _record_failure(
        self,
        iteration: int,
        patch: PatchPlan,
        gate_failures: list[str],
        error_summary: str,
    ) -> None:
        """Record a failed patch in the failure bank."""
        self.failure_bank.append(FailureRecord(
            iteration=iteration,
            reasoning=patch.reasoning,
            diff_summary=patch.diff_summary,
            description=patch.description,
            gate_failures=gate_failures,
            error_summary=error_summary,
            target_files=[d.file for d in patch.diffs],
        ))

    def _record_iteration_rejection_without_trial(
        self,
        emit: Callable[[str, dict[str, Any]], None],
        *,
        iteration: int,
        params: dict[str, Any],
        reasoning: str,
        reason: str,
        stage: str,
    ) -> TrialRecord:
        """Record and emit a rejected iteration that failed before execution.

        Validation / patch-application / parse failures never reach
        ``trial_start`` or the evaluator, but the frontend still needs a
        terminal event so the iteration does not remain stuck in ``pending``.
        """
        record = TrialRecord(
            trial_id=iteration,
            params=dict(params),
            composite_score=float("-inf"),
            status="discard",
            reasoning=reasoning,
            error_output=reason,
        )
        self.ledger.append(record)
        emit("trial_judgment", {
            "trial_id": iteration,
            "iteration": iteration,
            "decision": "discard",
            "reason": reason,
            "new_best": False,
            "stage": stage,
        })
        emit("trial_complete", {
            "trial_id": iteration,
            "iteration": iteration,
            "score": None,
            "status": record.status,
            "error": reason,
            "stage": stage,
        })
        return record

    def _finalize(
        self,
        baseline: TrialRecord | None,
        best: TrialRecord | None,
        converged: bool,
        patches_accepted: int,
        patches_rejected: int,
        accepted_files: list[str],
        accepted_patches: list[AcceptedPatchRecord],
        promotion: PromotionResult | None,
        workspace: HarnessWorkspace | None,
        success: bool = True,
        error_message: str | None = None,
        on_event: EventCallback = None,
    ) -> HarnessResult:
        """Build final result and emit done event."""
        improvement_pct = 0.0
        bs = baseline.composite_score if baseline else float("nan")
        bt = best.composite_score if best else float("nan")
        if baseline and best and math.isfinite(bs) and math.isfinite(bt) and abs(bs) > 1e-12:
            improvement_pct = ((bt - bs) / abs(bs)) * 100

        result = HarnessResult(
            best_trial=best,
            improvement_pct=round(improvement_pct, 2),
            total_iterations=len(self.ledger),
            patches_accepted=patches_accepted,
            patches_rejected=patches_rejected,
            converged=converged,
            success=success,
            error_message=error_message,
            accepted_patch_files=sorted(set(accepted_files)),
            accepted_patches=list(accepted_patches),
            promotion=promotion.to_dict() if promotion else {},
            sandbox_repo=str(workspace.repo_root) if workspace else "",
            source_project_commit=(
                workspace.source_project_commit if workspace else ""
            ),
        )

        # Write summary
        summary = {
            "success": success,
            "skill": self.skill_name,
            "method": self.method,
            "evolution_goal": self.evolution_goal,
            "total_iterations": result.total_iterations,
            "patches_accepted": patches_accepted,
            "patches_rejected": patches_rejected,
            "improvement_pct": result.improvement_pct,
            "converged": converged,
            "accepted_files": result.accepted_patch_files,
            "accepted_patch_commits": [
                patch.commit_hash for patch in accepted_patches
            ],
            "accepted_patch_artifacts": [
                patch.artifact_path for patch in accepted_patches
            ],
            "accepted_patches": [
                patch.to_dict() for patch in accepted_patches
            ],
            "promotion": result.promotion,
            "sandbox_repo": result.sandbox_repo,
            "source_project_commit": result.source_project_commit,
        }
        if error_message:
            summary["error"] = error_message
        if best:
            summary["best_score"] = best.composite_score
        if baseline:
            summary["baseline_score"] = baseline.composite_score

        (self.output_root / "harness_summary.json").write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )

        if on_event:
            if success:
                on_event("done", {
                    "best_trial": best.to_dict() if best else None,
                    "best_score": best.composite_score if best else None,
                    "improvement_pct": result.improvement_pct,
                    "total_trials": result.total_iterations,
                    "total_iterations": result.total_iterations,
                    "patches_accepted": patches_accepted,
                    "patches_rejected": patches_rejected,
                    "converged": converged,
                    "accepted_files": result.accepted_patch_files,
                    "accepted_patch_commits": summary["accepted_patch_commits"],
                    "promotion": result.promotion,
                })
            else:
                on_event("error", {"message": error_message or "Failed"})

        return result

    def _emit_progress(
        self,
        emit: Callable[[str, dict[str, Any]], None],
        *,
        phase: str,
        completed: int,
        total: int | None = None,
        best_score: float | None = None,
        iteration: int | None = None,
    ) -> None:
        """Emit progress in a shape compatible with the older optimize UI.

        The frontend that consumes ``/optimize`` was originally built against
        ``OptimizationLoop`` and expects ``completed``/``total`` fields rather
        than harness-specific ``iteration`` names. Emit both so the harness UI
        stays backwards compatible while still exposing iteration semantics.
        """
        payload: dict[str, Any] = {
            "phase": phase,
            "completed": completed,
            "total": total if total is not None else self.max_iterations,
        }
        if best_score is not None:
            payload["best_score"] = best_score
        if iteration is not None:
            payload["iteration"] = iteration
        emit("progress", payload)

    def _promote_workspace(
        self,
        workspace: HarnessWorkspace,
        accepted_files: list[str],
    ) -> PromotionResult:
        if not accepted_files:
            return PromotionResult(
                status="not_needed",
                message="No accepted files to promote.",
                journal_path=str(workspace.promotion_journal_path),
            )
        if not self.auto_promote:
            logger.info(
                "Promotion skipped (auto_promote=False). "
                "Accepted patches remain in sandbox: %s",
                workspace.repo_root,
            )
            return PromotionResult(
                status="skipped",
                message=(
                    "Automatic promotion disabled. Use the Promote action "
                    "in the UI to apply accepted patches to the source tree."
                ),
                journal_path=str(workspace.promotion_journal_path),
            )
        try:
            return workspace.promote_accepted_state(accepted_files)
        except Exception as exc:
            logger.error("Failed to promote accepted sandbox state: %s", exc)
            return PromotionResult(
                status="failed",
                message=f"Failed to promote accepted sandbox state: {exc}",
                journal_path=str(workspace.promotion_journal_path),
            )

    def _raise_if_cancelled(self) -> None:
        if self.cancel_event and self.cancel_event.is_set():
            raise OptimizationCancelled("Harness evolution cancelled")
