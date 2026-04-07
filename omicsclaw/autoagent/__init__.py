"""OmicsClaw AutoAgent — LLM-driven parameter optimization.

Inspired by AutoAgent's self-evolution architecture: a meta-agent reads
a directive, diagnoses trial results, suggests parameter changes, and
loops with keep/discard decisions.
"""

from __future__ import annotations

from pathlib import Path
import re
import threading
from typing import Any, Callable


def _emit_error_event(
    on_event: Callable[[str, dict[str, Any]], None] | None,
    message: str,
) -> None:
    if on_event:
        on_event("error", {"message": message})


def _sanitize_output_token(value: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip())
    sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-")
    return sanitized or "optimize"


def _resolve_optimization_output_root(
    skill_name: str,
    method: str,
    cwd: str = "",
    output_dir: str = "",
) -> Path:
    resolved_output_dir = output_dir.strip()
    if resolved_output_dir:
        output_root = Path(resolved_output_dir).expanduser()
        if not output_root.is_absolute() and cwd.strip():
            output_root = Path(cwd).expanduser().resolve() / output_root
        return output_root

    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = (
        f"optimize_{_sanitize_output_token(skill_name)}_"
        f"{_sanitize_output_token(method)}_{ts}"
    )

    resolved_cwd = cwd.strip()
    if resolved_cwd:
        workspace_dir = Path(resolved_cwd).expanduser().resolve()
        if not workspace_dir.is_dir():
            raise ValueError(f"Working directory does not exist: {workspace_dir}")
        return workspace_dir / "output" / run_name

    return Path("output") / run_name


def run_optimization(
    skill_name: str,
    method: str,
    input_path: str = "",
    cwd: str = "",
    output_dir: str = "",
    max_trials: int = 20,
    fixed_params: dict[str, Any] | None = None,
    llm_provider: str = "",
    llm_model: str = "",
    demo: bool = False,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Run the full autoagent optimization loop.

    This is the main entry point used by both the CLI and the API.

    Returns a summary dict with best_params, improvement_pct, etc.
    """
    from omicsclaw.autoagent.evaluator import Evaluator
    from omicsclaw.autoagent.metrics_registry import get_metrics_for_skill
    from omicsclaw.autoagent.optimization_loop import OptimizationLoop
    from omicsclaw.autoagent.reproduce import build_reproduce_command
    from omicsclaw.autoagent.search_space import SearchSpace

    # 1. Resolve metrics
    metrics = get_metrics_for_skill(skill_name, method)
    if metrics is None:
        error_message = (
            f"No metrics registered for skill '{skill_name}'. Check metrics_registry.py."
        )
        _emit_error_event(on_event, error_message)
        return {
            "success": False,
            "error": error_message,
        }

    # 2. Build search space from skill registry
    try:
        from omicsclaw.core.registry import registry

        registry.load_all()
        skill_info = registry.skills.get(skill_name)
        if skill_info is None:
            error_message = f"Unknown skill: {skill_name}"
            _emit_error_event(on_event, error_message)
            return {"success": False, "error": error_message}

        param_hints = skill_info.get("param_hints", {}).get(method)
        if param_hints is None:
            error_message = (
                f"No param_hints for method '{method}' in skill '{skill_name}'."
            )
            _emit_error_event(on_event, error_message)
            return {
                "success": False,
                "error": error_message,
            }
    except Exception as e:
        error_message = f"Failed to load skill registry: {e}"
        _emit_error_event(on_event, error_message)
        return {"success": False, "error": error_message}

    search_space = SearchSpace.from_param_hints(
        skill_name, method, param_hints, fixed_params
    )

    if not search_space.tunable:
        error_message = (
            f"No tunable parameters found for {skill_name}/{method} (all may be fixed)."
        )
        _emit_error_event(on_event, error_message)
        return {
            "success": False,
            "error": error_message,
        }

    # 2b. Resolve the input path against the user's workspace when possible.
    # Relative paths without a workspace are ambiguous and otherwise end up
    # being resolved against the backend process directory.
    if input_path:
        input_path_obj = Path(input_path).expanduser()
        if input_path_obj.is_absolute():
            input_path = str(input_path_obj.resolve())
        elif cwd:
            input_path = str(
                (Path(cwd).expanduser().resolve() / input_path_obj).resolve()
            )
        else:
            error_message = (
                f"Relative input_path requires cwd: {input_path!r}. "
                "Provide an absolute input path or set cwd."
            )
            _emit_error_event(on_event, error_message)
            return {"success": False, "error": error_message}

    # 3. Build evaluator
    evaluator = Evaluator(metrics, skill_name=skill_name, method=method)

    # 4. Resolve output directory
    try:
        output_root = _resolve_optimization_output_root(
            skill_name=skill_name,
            method=method,
            cwd=cwd,
            output_dir=output_dir,
        )
    except Exception as e:
        error_message = str(e)
        _emit_error_event(on_event, error_message)
        return {"success": False, "error": error_message}

    # 5. Run the loop
    loop = OptimizationLoop(
        skill_name=skill_name,
        method=method,
        input_path=input_path,
        output_root=output_root,
        search_space=search_space,
        evaluator=evaluator,
        metrics=metrics,
        max_trials=max_trials,
        llm_provider=llm_provider,
        llm_model=llm_model,
        demo=demo,
        cancel_event=cancel_event,
    )

    result = loop.run(on_event=on_event)
    if not result.success:
        _emit_error_event(on_event, result.error_message or "Optimization failed")

    # 6. Build return summary
    summary: dict[str, Any] = {
        "success": result.success,
        "skill": skill_name,
        "method": method,
        "total_trials": result.total_trials,
        "improvement_pct": result.improvement_pct,
        "converged": result.converged,
        "output_dir": str(output_root),
        "ledger_path": str(output_root / "experiment_ledger.jsonl"),
    }
    if not result.success:
        summary["error"] = result.error_message or "Optimization failed"
    if result.best_trial:
        summary["best_trial_id"] = result.best_trial.trial_id
        summary["best_score"] = result.best_trial.composite_score
        summary["best_params"] = result.best_trial.params
        summary["best_metrics"] = result.best_trial.raw_metrics
        summary["reproduce_command"] = build_reproduce_command(
            skill_name=skill_name,
            method=method,
            params=result.best_trial.params,
            fixed_params=search_space.fixed,
            input_path=input_path,
            demo=demo,
        )

    return summary
