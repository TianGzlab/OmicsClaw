"""Core optimization loop — the meta-agent experiment cycle.

Mirrors AutoAgent's experiment loop (program.md lines 142-154):
  1. Run baseline with defaults
  2. LLM reads directive + history → diagnoses → suggests next params
  3. Runner executes the trial
  4. Evaluator scores the output
  5. Judge decides keep/discard
  6. Loop until max_trials or convergence
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from omicsclaw.autoagent.directive import build_directive
from omicsclaw.autoagent.errors import OptimizationCancelled
from omicsclaw.autoagent.evaluator import EvaluationResult, Evaluator
from omicsclaw.autoagent.experiment_ledger import ExperimentLedger, TrialRecord
from omicsclaw.autoagent.judge import JudgmentResult, judge
from omicsclaw.autoagent.metrics_registry import MetricDef
from omicsclaw.autoagent.reproduce import build_reproduce_command
from omicsclaw.autoagent.runner import TrialExecution, execute_trial
from omicsclaw.autoagent.search_space import SearchSpace

logger = logging.getLogger(__name__)

# Type alias for the event callback
EventCallback = Callable[[str, dict[str, Any]], None] | None

from omicsclaw.autoagent.constants import (
    CONSECUTIVE_CRASH_LIMIT,
    ERROR_OUTPUT_MAX_CHARS,
    SCORE_DIFF_EPSILON,
    parse_bool,
)


@dataclass
class OptimizationResult:
    """Final result of an optimization run."""

    best_trial: TrialRecord | None
    ledger: ExperimentLedger
    improvement_pct: float = 0.0
    total_trials: int = 0
    converged: bool = False
    success: bool = True
    error_message: str | None = None


def _coerce_llm_result(result: Any) -> tuple[dict[str, Any] | None, str]:
    """Normalize `_ask_llm()` results.

    The production contract is ``(suggestion_dict | None, error_reason)``, but
    tests and local overrides may still return the older ``dict`` / ``None``
    shapes. Accept both so a malformed override does not crash the loop.
    """
    if result is None:
        return None, "LLM returned no suggestion"

    if isinstance(result, tuple):
        if len(result) != 2:
            return None, (
                "LLM returned an invalid tuple payload "
                f"of length {len(result)}."
            )
        suggestion, error_reason = result
        if suggestion is not None and not isinstance(suggestion, dict):
            return None, (
                "LLM returned an invalid suggestion payload of type "
                f"{type(suggestion).__name__}."
            )
        return suggestion, str(error_reason or "")

    if isinstance(result, dict):
        return result, ""

    return None, (
        "LLM returned an invalid payload of type "
        f"{type(result).__name__}."
    )


class OptimizationLoop:
    """LLM-driven parameter optimization loop.

    The loop mirrors AutoAgent's experiment cycle:
    - Run baseline with default parameters
    - In each iteration: build directive → LLM suggests params →
      run trial → evaluate → judge keep/discard → record → loop
    """

    def __init__(
        self,
        skill_name: str,
        method: str,
        input_path: str,
        output_root: Path,
        search_space: SearchSpace,
        evaluator: Evaluator,
        metrics: dict[str, MetricDef],
        max_trials: int = 20,
        llm_provider: str = "",
        llm_model: str = "",
        demo: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.skill_name = skill_name
        self.method = method
        self.input_path = input_path
        self.output_root = Path(output_root)
        self.search_space = search_space
        self.evaluator = evaluator
        self.metrics = metrics
        self.max_trials = max_trials
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.demo = demo
        self.cancel_event = cancel_event

        self.output_root.mkdir(parents=True, exist_ok=True)
        self.ledger = ExperimentLedger(self.output_root / "experiment_ledger.jsonl")

    def run(self, on_event: EventCallback = None) -> OptimizationResult:
        """Execute the full optimization loop.

        Parameters
        ----------
        on_event:
            Optional callback ``(event_type, data)`` for real-time progress.
            Event types: ``trial_start``, ``trial_complete``,
            ``trial_judgment``, ``reasoning``, ``progress``, ``done``,
            ``error``.
        """
        def emit(event_type: str, data: dict[str, Any]) -> None:
            if on_event:
                on_event(event_type, data)

        # Step 1: Baseline
        self._raise_if_cancelled()
        self._emit_progress(on_event, phase="baseline", completed=0)
        baseline_params = self.search_space.defaults_dict()
        baseline = self._run_trial(
            trial_id=0,
            params=baseline_params,
            description="baseline",
            on_event=on_event,
        )

        # If the baseline trial crashed, the optimization is fundamentally
        # broken (wrong input path, missing dependency, bad default params).
        # Report the crash honestly and stop immediately.
        if baseline.status == "crash":
            baseline.status = "crash"  # preserve, do NOT overwrite to "baseline"
            self.ledger.append(baseline)

            emit("trial_complete", {
                "trial_id": 0, "score": baseline.composite_score,
                "metrics": baseline.raw_metrics, "status": "crash",
                "error_output": baseline.error_output,
            })

            # Build a useful error message from the real stderr output
            error_detail = "Baseline trial crashed — skill execution failed."
            if baseline.error_output:
                # Extract the most useful line (usually the last non-empty line)
                lines = [l for l in baseline.error_output.splitlines() if l.strip()]
                tail = "\n".join(lines[-5:]) if len(lines) > 5 else "\n".join(lines)
                error_detail += f"\n{tail}"

            logger.error(
                "Baseline trial crashed (score=%s). stderr:\n%s",
                baseline.composite_score,
                baseline.error_output[:500] if baseline.error_output else "(no output)",
            )
            return self._finalize_result(
                baseline=baseline,
                best=baseline,
                converged=False,
                success=False,
                error_message=error_detail,
                on_event=on_event,
            )

        # Baseline succeeded — mark it and continue
        baseline.status = "baseline"
        self.ledger.append(baseline)
        best = baseline

        emit("trial_complete", {
            "trial_id": 0, "score": baseline.composite_score,
            "metrics": baseline.raw_metrics, "status": "baseline",
        })
        self._emit_progress(
            on_event,
            phase="baseline",
            completed=len(self.ledger),
            best_score=best.composite_score,
        )

        # Warn if baseline produced non-finite metrics (skill ran but
        # metrics extraction failed — possibly wrong metric registry).
        if math.isfinite(baseline.composite_score) is False:
            logger.warning(
                "Baseline trial succeeded but scored %s "
                "(metrics may not be registered for this skill).",
                baseline.composite_score,
            )

        # Step 2: Iterative optimization
        consecutive_crashes = 0
        converged = False

        for trial_id in range(1, self.max_trials):
            self._raise_if_cancelled()

            # Build directive and ask LLM for next params
            directive = build_directive(
                self.skill_name,
                self.method,
                self.search_space,
                self.metrics,
                self.ledger,
                self.max_trials,
            )
            self._raise_if_cancelled()
            suggestion, llm_error = _coerce_llm_result(self._ask_llm(directive))
            self._raise_if_cancelled()

            if suggestion is None:
                logger.warning("LLM failed: %s", llm_error)
                return self._finalize_result(
                    baseline=baseline,
                    best=best,
                    converged=converged,
                    success=False,
                    error_message=llm_error or "LLM returned no suggestion",
                    on_event=on_event,
                )

            if suggestion.get("converged"):
                reasoning = suggestion.get("reasoning", "LLM indicated convergence")
                emit("reasoning", {"trial_id": trial_id, "reasoning": reasoning})
                converged = True
                break

            params = suggestion.get("params", {})
            params = self._validate_and_clamp_params(params)
            reasoning = suggestion.get("reasoning", "")
            emit("reasoning", {"trial_id": trial_id, "reasoning": reasoning})

            # Run trial
            self._raise_if_cancelled()
            emit("trial_start", {"trial_id": trial_id, "params": params})
            trial = self._run_trial(
                trial_id=trial_id,
                params=params,
                description=reasoning,
                on_event=on_event,
            )
            trial.reasoning = reasoning
            trial_crashed = trial.status == "crash"

            # Judge keep/discard
            judgment = judge(trial, best, self.ledger, baseline_params=baseline_params)
            if not trial_crashed:
                trial.status = judgment.decision

            if judgment.new_best:
                best = trial
                consecutive_crashes = 0
            elif trial_crashed:
                consecutive_crashes += 1
            else:
                consecutive_crashes = 0

            self.ledger.append(trial)

            emit("trial_complete", {
                "trial_id": trial_id,
                "score": trial.composite_score,
                "metrics": trial.raw_metrics,
                "status": trial.status,
                **({"error_output": trial.error_output} if trial.error_output else {}),
            })
            emit("trial_judgment", {
                "trial_id": trial_id,
                "decision": judgment.decision,
                "reason": judgment.reason,
                "new_best": judgment.new_best,
                "learning_signal": judgment.learning_signal,
            })
            self._emit_progress(
                on_event,
                phase="optimizing",
                completed=len(self.ledger),
                best_score=best.composite_score,
            )

            if trial_crashed and consecutive_crashes >= CONSECUTIVE_CRASH_LIMIT:
                logger.warning("Stopping optimization after 3 consecutive crashes.")
                return self._finalize_result(
                    baseline=baseline,
                    best=best,
                    converged=converged,
                    success=False,
                    error_message="3 consecutive crashes — stopping.",
                    on_event=on_event,
                )
        return self._finalize_result(
            baseline=baseline,
            best=best,
            converged=converged,
            success=True,
            error_message=None,
            on_event=on_event,
        )

    # ----- internal -----

    def _emit_progress(
        self,
        on_event: EventCallback,
        *,
        phase: str,
        completed: int,
        total: int | None = None,
        best_score: float | None = None,
    ) -> None:
        """Emit progress with completed-trial semantics.

        While the loop is running, ``total`` defaults to the configured trial
        budget. Successful early termination emits a final progress snapshot
        with ``total == completed`` to close the stream at 100%.
        """
        if not on_event:
            return

        payload: dict[str, Any] = {
            "phase": phase,
            "completed": completed,
            "total": total if total is not None else self.max_trials,
        }
        if best_score is not None:
            payload["best_score"] = best_score
        on_event("progress", payload)

    def _run_trial(
        self,
        trial_id: int,
        params: dict[str, Any],
        description: str = "",
        on_event: EventCallback = None,
    ) -> TrialRecord:
        """Execute a single trial and evaluate its output."""
        self._raise_if_cancelled()
        trial_output = self.output_root / f"trial_{trial_id:04d}"
        trial_output.mkdir(parents=True, exist_ok=True)

        execution = execute_trial(
            skill_name=self.skill_name,
            input_path=self.input_path,
            output_dir=trial_output,
            params=params,
            search_space=self.search_space,
            demo=self.demo,
            cancel_event=self.cancel_event,
        )
        self._raise_if_cancelled()

        if not execution.success:
            # Capture the last portion of stderr for diagnostics.
            # Truncate to avoid bloating the ledger with huge tracebacks.
            error_output = (execution.stderr or execution.stdout or "").strip()
            if len(error_output) > ERROR_OUTPUT_MAX_CHARS:
                error_output = "...\n" + error_output[-ERROR_OUTPUT_MAX_CHARS:]
            return TrialRecord(
                trial_id=trial_id,
                params=params,
                composite_score=float("-inf"),
                status="crash",
                reasoning=description,
                output_dir=execution.output_dir,
                duration_seconds=execution.duration_seconds,
                error_output=error_output,
            )

        self._raise_if_cancelled()
        eval_result = self.evaluator.evaluate(Path(execution.output_dir), params=params)

        return TrialRecord(
            trial_id=trial_id,
            params=params,
            composite_score=eval_result.composite_score,
            raw_metrics=eval_result.raw_metrics,
            status="pending",  # will be set by judge
            reasoning=description,
            output_dir=execution.output_dir,
            duration_seconds=execution.duration_seconds,
        )

    def _validate_and_clamp_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Validate and clamp LLM-suggested params to search space bounds.

        Handles:
        - float/int: type coercion + range clamping
        - bool: proper parsing of string representations ("false", "0", "no" → False)
        - categorical: reject values not in choices, fall back to default
        """
        clamped = dict(params)
        param_lookup = {p.name: p for p in self.search_space.tunable}
        for pname, pvalue in list(clamped.items()):
            pdef = param_lookup.get(pname)
            if pdef is None:
                continue
            # Type coercion
            try:
                if pdef.param_type == "float":
                    pvalue = float(pvalue)
                elif pdef.param_type == "int":
                    pvalue = int(round(float(pvalue)))
                elif pdef.param_type == "bool":
                    pvalue = parse_bool(pvalue)
                elif pdef.param_type == "categorical":
                    # Reject values not in the allowed choices
                    if pdef.choices is not None and pvalue not in pdef.choices:
                        logger.warning(
                            "Param %s=%r not in choices %s, using default %r",
                            pname, pvalue, pdef.choices, pdef.default,
                        )
                        pvalue = pdef.default
            except (ValueError, TypeError):
                pvalue = pdef.default
            # Range clamping for numeric types
            if pdef.low is not None and isinstance(pvalue, (int, float)):
                pvalue = max(pdef.low, pvalue)
            if pdef.high is not None and isinstance(pvalue, (int, float)):
                pvalue = min(pdef.high, pvalue)
            clamped[pname] = pvalue
        return clamped

    def _ask_llm(self, directive: str) -> tuple[dict[str, Any] | None, str]:
        """Send the directive to the LLM and parse the parameter suggestion.

        Returns ``(suggestion_dict, error_reason)``.  On success the error
        reason is empty.  On failure the suggestion is ``None`` and the
        reason contains a human-readable message suitable for the frontend.
        """
        self._raise_if_cancelled()
        try:
            response_text = self._call_llm(directive)
        except OptimizationCancelled:
            raise
        except Exception as e:
            reason = str(e)
            logger.error("LLM call failed: %s", reason)
            return None, f"LLM call failed: {reason}"

        self._raise_if_cancelled()
        parsed = self._parse_llm_response(response_text)
        if parsed is None:
            return None, "LLM response could not be parsed as JSON."
        return parsed, ""

    def _call_llm(self, directive: str) -> str:
        """Call the LLM via OpenAI-compatible API."""
        from omicsclaw.core.provider_registry import resolve_provider

        api_key_env = os.environ.get("LLM_API_KEY", "")
        base_url, model, api_key = resolve_provider(
            provider=self.llm_provider,
            base_url="",
            model=self.llm_model,
            api_key="",
        )

        if not api_key:
            raise RuntimeError(
                "No LLM API key found. Set LLM_API_KEY or a provider-specific "
                "key (e.g. DEEPSEEK_API_KEY) in your environment."
            )

        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url or None)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a parameter optimization agent. Respond ONLY with valid JSON."},
                {"role": "user", "content": directive},
            ],
            temperature=0.7,
            max_tokens=1024,
        )
        return response.choices[0].message.content or ""

    def _parse_llm_response(self, text: str) -> dict[str, Any] | None:
        """Parse the LLM response as JSON, handling markdown fences."""
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last line (fences)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            logger.warning("Failed to parse LLM response as JSON: %s", text[:200])
            return None

    def _write_summary(self, result: OptimizationResult) -> None:
        """Write a summary.json with the best parameters and run stats."""
        best = result.best_trial
        summary: dict[str, Any] = {
            "success": result.success,
            "skill": self.skill_name,
            "method": self.method,
            "total_trials": result.total_trials,
            "improvement_pct": result.improvement_pct,
            "converged": result.converged,
        }
        if result.error_message:
            summary["error"] = result.error_message
        if best:
            summary["best_trial_id"] = best.trial_id
            summary["best_score"] = best.composite_score
            summary["best_params"] = best.params
            summary["best_metrics"] = best.raw_metrics
            summary["reproduce_command"] = self._build_reproduce_command(best)

        path = self.output_root / "summary.json"
        path.write_text(json.dumps(summary, indent=2, default=str))

    def _build_reproduce_command(self, trial: TrialRecord) -> str:
        """Build a CLI command to reproduce the best trial."""
        return build_reproduce_command(
            skill_name=self.skill_name,
            method=self.method,
            params=trial.params,
            fixed_params=self.search_space.fixed,
            input_path=self.input_path,
            demo=self.demo,
        )

    def _finalize_result(
        self,
        baseline: TrialRecord,
        best: TrialRecord,
        converged: bool,
        success: bool,
        error_message: str | None,
        on_event: EventCallback = None,
    ) -> OptimizationResult:
        baseline_score = baseline.composite_score
        best_score = best.composite_score
        improvement_pct = 0.0
        if (
            math.isfinite(baseline_score)
            and math.isfinite(best_score)
            and abs(baseline_score) > 1e-12
        ):
            improvement_pct = ((best_score - baseline_score) / abs(baseline_score)) * 100

        result = OptimizationResult(
            best_trial=best,
            ledger=self.ledger,
            improvement_pct=round(improvement_pct, 2),
            total_trials=len(self.ledger),
            converged=converged,
            success=success,
            error_message=error_message,
        )

        self._raise_if_cancelled()
        self._write_summary(result)

        if success and on_event:
            if result.total_trials < self.max_trials:
                self._emit_progress(
                    on_event,
                    phase="complete",
                    completed=result.total_trials,
                    total=result.total_trials,
                    best_score=best.composite_score,
                )
            on_event("done", {
                "best_trial": best.to_dict() if best else None,
                "improvement_pct": result.improvement_pct,
                "total_trials": result.total_trials,
                "converged": converged,
                "reproduce_command": self._build_reproduce_command(best) if best else "",
            })

        return result

    def _raise_if_cancelled(self) -> None:
        if self.cancel_event and self.cancel_event.is_set():
            raise OptimizationCancelled("Optimization cancelled")
