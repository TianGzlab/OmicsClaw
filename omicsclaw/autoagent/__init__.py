"""OmicsClaw AutoAgent — LLM-driven self-evolution.

Two operating modes:

1. **Parameter optimization** (``run_optimization``):
   A meta-agent reads a directive, diagnoses trial results, suggests
   parameter changes, and loops with keep/discard decisions.

2. **Harness evolution** (``run_harness_evolution``):
   A meta-agent modifies source code within a bounded editable surface,
   tests patches in a sandbox, and keeps/reverts based on hard gates
   and quality metrics.  Inspired by AutoAgent's program.md + bounded
   edit surface principle.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
import subprocess
import threading
from typing import Any, Callable

_logger = logging.getLogger(__name__)

# Branch names that are always considered protected.
_PROTECTED_BRANCH_NAMES = frozenset({
    "main", "master", "develop", "release", "production", "prod",
})


def _check_protected_branch(project_root: Path) -> str | None:
    """Return an error message if *project_root* is on a protected branch.

    Checks:
    1. Detached HEAD (no branch at all)
    2. Hardcoded protected names (main, master, develop, …)
    3. The remote default branch (``origin/HEAD``)

    Returns ``None`` when safe to proceed.
    """
    git_dir = project_root / ".git"
    if not git_dir.exists():
        return None  # not a git repo — nothing to protect

    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=project_root,
            timeout=5,
        ).stdout.strip()
    except Exception:
        return None  # git not available — skip check

    if branch == "HEAD":
        return (
            "Harness evolution cannot run on a detached HEAD. "
            "Please checkout or create a working branch first."
        )

    if branch.lower() in _PROTECTED_BRANCH_NAMES:
        return (
            f"Harness evolution refused to run on protected branch '{branch}'. "
            f"Create a feature branch (e.g. autoagent/{branch}-evolution) first."
        )

    # Check if this branch is the remote default branch
    try:
        default_ref = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, cwd=project_root,
            timeout=5,
        ).stdout.strip()
        # refs/remotes/origin/HEAD → refs/remotes/origin/main → "main"
        if default_ref:
            default_branch = default_ref.rsplit("/", 1)[-1]
            if branch == default_branch:
                return (
                    f"Harness evolution refused to run on the remote default "
                    f"branch '{branch}'. Create a feature branch first."
                )
    except Exception:
        pass  # no remote configured — skip

    return None


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


def _is_missing_fixed_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


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
    llm_provider_config: dict[str, str] | None = None,
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
    from omicsclaw.autoagent.search_space import SearchSpace, build_method_surface

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

    method_surface = build_method_surface(skill_name, method, param_hints)
    normalized_fixed_params = {
        name: value
        for name, value in (fixed_params or {}).items()
        if not _is_missing_fixed_value(value)
    }

    missing_fixed = [
        param.name
        for param in method_surface.fixed
        if param.required and param.name not in normalized_fixed_params
    ]
    if missing_fixed:
        error_message = (
            f"Missing required fixed parameters for {skill_name}/{method}: "
            + ", ".join(missing_fixed)
        )
        _emit_error_event(on_event, error_message)
        return {
            "success": False,
            "error": error_message,
        }

    search_space = SearchSpace.from_param_hints(
        skill_name, method, param_hints, normalized_fixed_params
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
        llm_provider_config=llm_provider_config,
        demo=demo,
        cancel_event=cancel_event,
    )

    result = loop.run(on_event=on_event)
    # Note: _finalize_result now emits the error event itself when
    # success=False, so we no longer need to emit it here.

    # 6. Build return summary  (param_loop)
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
        summary["best_trial"] = result.best_trial.to_dict()
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


# ---------------------------------------------------------------------------
# Harness evolution entry point
# ---------------------------------------------------------------------------


def run_harness_evolution(
    skill_name: str,
    method: str,
    input_path: str = "",
    cwd: str = "",
    output_dir: str = "",
    max_iterations: int = 10,
    fixed_params: dict[str, Any] | None = None,
    evolution_goal: str = "",
    surface_level: int = 2,
    explicit_files: list[str] | None = None,
    auto_promote: bool = False,
    llm_provider: str = "",
    llm_model: str = "",
    llm_provider_config: dict[str, str] | None = None,
    demo: bool = False,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Run the harness evolution loop — code-level skill improvement.

    Unlike ``run_optimization`` which only tunes parameters, this modifies
    source code within a bounded editable surface.

    Parameters
    ----------
    skill_name, method:
        Target skill and method to evolve.
    evolution_goal:
        Human-readable objective (e.g. "Upgrade QC from fixed thresholds
        to MAD-based adaptive filtering").
    surface_level:
        Max editable surface level (1=SKILL.md, 2=code, 3=config, 4=generated).
    explicit_files:
        Optional explicit file whitelist. Paths must stay inside the
        project root and cannot include frozen infrastructure.

    Returns a summary dict with harness-specific fields plus shared
    autoagent status metadata.
    """
    from omicsclaw.autoagent.edit_surface import EditSurface, build_sc_preprocessing_surface
    from omicsclaw.autoagent.evaluator import Evaluator
    from omicsclaw.autoagent.harness_loop import HarnessLoop
    from omicsclaw.autoagent.metrics_registry import get_metrics_for_skill
    from omicsclaw.autoagent.search_space import SearchSpace

    # 1. Resolve project root
    project_root = Path(__file__).resolve().parents[2]

    # NOTE: No branch check here — the sandbox fully isolates all trial
    # modifications from the source tree.  Promotion (file copy back) is
    # a separate, explicit step that has its own conflict detection.

    # 2. Resolve metrics
    metrics = get_metrics_for_skill(skill_name, method)
    if metrics is None:
        error_message = f"No metrics registered for skill '{skill_name}'."
        _emit_error_event(on_event, error_message)
        return {"success": False, "error": error_message}

    # 3. Build search space (for trial execution with default params)
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
            error_message = f"No param_hints for method '{method}' in '{skill_name}'."
            _emit_error_event(on_event, error_message)
            return {"success": False, "error": error_message}
    except Exception as e:
        error_message = f"Failed to load skill registry: {e}"
        _emit_error_event(on_event, error_message)
        return {"success": False, "error": error_message}

    normalized_fixed = {
        k: v for k, v in (fixed_params or {}).items()
        if not _is_missing_fixed_value(v)
    }
    search_space = SearchSpace.from_param_hints(
        skill_name, method, param_hints, normalized_fixed,
    )

    # 4. Build editable surface
    try:
        if skill_name == "sc-preprocessing" and explicit_files is None:
            surface = build_sc_preprocessing_surface(project_root)
        elif explicit_files:
            surface = EditSurface(
                max_level=surface_level,
                project_root=project_root,
                explicit_files=explicit_files,
            )
        else:
            surface = EditSurface(
                max_level=surface_level,
                project_root=project_root,
            )
    except ValueError as e:
        error_message = str(e)
        _emit_error_event(on_event, error_message)
        return {"success": False, "error": error_message}

    # 5. Resolve input path
    if input_path:
        input_path_obj = Path(input_path).expanduser()
        if input_path_obj.is_absolute():
            input_path = str(input_path_obj.resolve())
        elif cwd:
            input_path = str(
                (Path(cwd).expanduser().resolve() / input_path_obj).resolve()
            )

    # 6. Build evaluator
    evaluator = Evaluator(metrics, skill_name=skill_name, method=method)

    # 7. Resolve output directory
    try:
        output_root = _resolve_optimization_output_root(
            skill_name=skill_name,
            method=method,
            cwd=cwd,
            output_dir=output_dir,
        )
    except Exception as e:
        _emit_error_event(on_event, str(e))
        return {"success": False, "error": str(e)}

    # 8. Run harness loop
    loop = HarnessLoop(
        skill_name=skill_name,
        method=method,
        input_path=input_path,
        output_root=output_root,
        surface=surface,
        evaluator=evaluator,
        search_space=search_space,
        max_iterations=max_iterations,
        evolution_goal=evolution_goal,
        auto_promote=auto_promote,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_provider_config=llm_provider_config,
        demo=demo,
        cancel_event=cancel_event,
    )

    result = loop.run(on_event=on_event)

    # 9. Build return summary
    summary: dict[str, Any] = {
        "success": result.success,
        "mode": "harness_evolution",
        "skill": skill_name,
        "method": method,
        "evolution_goal": evolution_goal,
        "total_iterations": result.total_iterations,
        "patches_accepted": result.patches_accepted,
        "patches_rejected": result.patches_rejected,
        "improvement_pct": result.improvement_pct,
        "converged": result.converged,
        "output_dir": str(output_root),
        "accepted_files": result.accepted_patch_files,
        "accepted_patches": [patch.to_dict() for patch in result.accepted_patches],
        "accepted_patch_commits": [
            patch.commit_hash for patch in result.accepted_patches
        ],
        "accepted_patch_artifacts": [
            patch.artifact_path for patch in result.accepted_patches
        ],
        "promotion": result.promotion,
        "sandbox_repo": result.sandbox_repo,
        "source_project_commit": result.source_project_commit,
    }
    if not result.success:
        summary["error"] = result.error_message or "Harness evolution failed"
    if result.best_trial:
        summary["best_score"] = result.best_trial.composite_score
        summary["best_metrics"] = result.best_trial.raw_metrics

    return summary
