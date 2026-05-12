"""Shared OmicsClaw skill execution runner.

The public surface here is ``run_skill`` (and a few legacy aliases). The
heavy lifting was carved out of this module into ``omicsclaw.core.runtime``
during OMI-12 P1.4:

- ``runtime.argv_builder``    — argv + filtered LLM-supplied flags
- ``runtime.subprocess_driver`` — Popen + reaper + cancel + log streaming
- ``runtime.output_finalize`` — rename, README, reproducibility notebook
- ``runtime.pipeline_runner`` — ``spatial-pipeline`` chain

The repository-root ``omicsclaw.py`` file remains the CLI wrapper, but any
surface that needs to run a skill should import ``run_skill`` from here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from omicsclaw.common.report import build_output_dir_name
from omicsclaw.core.registry import ensure_registry_loaded, registry
from omicsclaw.core.runtime.argv_builder import (
    build_skill_argv,
    build_user_run_command,
    extract_flag_value,
    filter_forwarded_args,
)
from omicsclaw.core.runtime.output_finalize import (
    deduplicate_path,
    finalize_output_directory,
    write_pipeline_readme,
)
from omicsclaw.core.runtime.pipeline_runner import (
    SPATIAL_PIPELINE,
    run_pipeline_by_name,
    run_spatial_pipeline,
)
from omicsclaw.core.runtime.subprocess_driver import drive_subprocess
from omicsclaw.core.skill_result import SkillRunResult, build_skill_run_result


OMICSCLAW_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = OMICSCLAW_DIR / "output"
PYTHON = sys.executable

if str(OMICSCLAW_DIR) not in sys.path:
    sys.path.insert(0, str(OMICSCLAW_DIR))

_COLOUR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
BOLD = "\033[1m" if _COLOUR else ""
GREEN = "\033[32m" if _COLOUR else ""
RED = "\033[31m" if _COLOUR else ""
CYAN = "\033[36m" if _COLOUR else ""
RESET = "\033[0m" if _COLOUR else ""


# ---------------------------------------------------------------------------
# Backwards-compatible aliases — tests and a few external surfaces import
# these private helpers by name. Keep them re-exported so the carve-out is
# transparent to callers.
# ---------------------------------------------------------------------------

_extract_flag_value = extract_flag_value
_build_user_run_command = build_user_run_command
_deduplicate_path = deduplicate_path
_finalize_output_directory = finalize_output_directory
_write_pipeline_readme = write_pipeline_readme


def resolve_skill_alias(skill_name: str) -> str:
    """Resolve a user-facing skill name or legacy alias to its canonical alias."""
    skills = ensure_registry_loaded().skills
    if skill_name in skills:
        return skills[skill_name].get("alias", skill_name)

    for skill_key, skill_info in skills.items():
        legacy_aliases = skill_info.get("legacy_aliases", [])
        if skill_name in legacy_aliases:
            return skill_key

    if ":" in skill_name:
        _domain, skill = skill_name.split(":", 1)
        if skill in skills:
            return skill

    return skill_name


def run_skill(
    skill_name: str,
    *,
    input_path: str | None = None,
    input_paths: list[str] | None = None,
    output_dir: str | None = None,
    demo: bool = False,
    session_path: str | None = None,
    extra_args: list[str] | None = None,
    stdout_callback: Callable[[str], None] | None = None,
    stderr_callback: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> SkillRunResult:
    """Run a single skill via subprocess and return a ``SkillRunResult``.

    The runner returns a typed ``SkillRunResult`` natively (OMI-12 P1.6);
    callers that still expect the legacy dict shape should call
    ``.to_legacy_dict()`` at their own boundary. Internal consumers that
    used to immediately do ``coerce_skill_run_result(run_skill(...))`` can
    drop the coercion and use the returned model directly.

    When ``stdout_callback`` / ``stderr_callback`` are supplied the runner
    invokes them once per line as the skill emits output (newline stripped),
    so long-running skills produce visible logs in real time. Aggregated
    ``stdout`` / ``stderr`` strings are still returned on the result.

    When ``cancel_event`` is supplied the runner watches it; if the event is
    set while the skill is running the child process group receives SIGTERM,
    waits a short grace period, then SIGKILL, ensuring cancelled jobs do not
    leak children consuming CPU/GPU until natural completion.
    """
    skill_name = resolve_skill_alias(skill_name)

    # Any ``<name>-pipeline`` whose YAML lives in ``pipelines/`` is dispatched
    # through the generic chain runner. ``run_pipeline_by_name`` returns
    # ``None`` when no YAML matches the alias, in which case we fall through
    # to the regular skill registry lookup so genuinely unknown aliases still
    # surface the standard "Unknown skill" error.
    if skill_name.endswith("-pipeline"):
        pipeline_result = run_pipeline_by_name(
            skill_name,
            default_output_root=DEFAULT_OUTPUT_ROOT,
            err_factory=_err,
            input_path=input_path,
            output_dir=output_dir,
            demo=demo,
            session_path=session_path,
        )
        if pipeline_result is not None:
            return pipeline_result

    skills = ensure_registry_loaded().skills
    skill_info = skills.get(skill_name)
    if skill_info is None:
        return _err(skill_name, f"Unknown skill '{skill_name}'. Available: {list(skills.keys())}")

    script_path: Path = skill_info["script"]
    if not script_path.exists():
        return _err(skill_name, f"Script not found: {script_path}")

    resolved_input_paths: list[str] | None = None
    if input_paths and len(input_paths) >= 2:
        resolved_input_paths = [str(Path(p).resolve()) for p in input_paths]

    resolved_input = input_path
    if session_path and not input_path and not demo and not resolved_input_paths:
        from omicsclaw.common.session import SpatialSession

        session = SpatialSession.load(session_path)
        if session.h5ad_path:
            resolved_input = session.h5ad_path

    if resolved_input:
        resolved_input = str(Path(resolved_input).resolve())

    user_supplied_output_dir = output_dir is not None
    generated_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    requested_method = extract_flag_value(extra_args, "--method")

    if output_dir:
        out_dir = Path(output_dir).resolve()
    else:
        auto_name = build_output_dir_name(skill_name, generated_ts, method=requested_method)
        out_dir = deduplicate_path(DEFAULT_OUTPUT_ROOT / auto_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = build_skill_argv(
        python_executable=PYTHON,
        script_path=script_path,
        skill_info=skill_info,
        demo=demo,
        input_path=resolved_input,
        input_paths=resolved_input_paths,
        output_dir=out_dir,
    )
    if cmd is None:
        return _err(skill_name, "No --input, --demo, or --session provided.")

    domain = skill_info.get("domain", "unknown")
    domain_display = registry.domains.get(domain, {}).get("name", domain.title())
    if demo:
        mode_str = f"{CYAN}demo mode{RESET}"
    elif resolved_input_paths:
        mode_str = f"inputs: {', '.join(resolved_input_paths)}"
    else:
        mode_str = f"input: {resolved_input}"
    print(f"\n{BOLD}Running {domain_display} skill:{RESET} {GREEN}{skill_name}{RESET} ({mode_str})")
    print(f"{BOLD}Output:{RESET} {out_dir}\n")

    filtered = filter_forwarded_args(
        extra_args,
        allowed_extra_flags=skill_info.get("allowed_extra_flags", set()),
    )
    cmd.extend(filtered)

    t0 = time.time()
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(OMICSCLAW_DIR) + os.pathsep + env.get("PYTHONPATH", "")
        proc = drive_subprocess(
            cmd,
            cwd=script_path.parent,
            env=env,
            out_dir=out_dir,
            stdout_callback=stdout_callback,
            stderr_callback=stderr_callback,
            cancel_event=cancel_event,
        )
    except Exception as exc:
        duration = time.time() - t0
        return _err(skill_name, str(exc), duration=duration)

    duration = time.time() - t0

    final_out_dir = out_dir
    actual_method = requested_method
    readme_path = ""
    notebook_path = ""
    if proc.returncode == 0:
        user_command = build_user_run_command(
            skill_name=skill_name,
            demo=demo,
            input_path=resolved_input,
            output_dir=out_dir,
            forwarded_args=filtered,
        )
        final_out_dir, actual_method, readme_path, notebook_path, _ = finalize_output_directory(
            out_dir,
            skill_name=skill_name,
            skill_info=skill_info,
            timestamp=generated_ts,
            user_supplied_output_dir=user_supplied_output_dir,
            preferred_method=requested_method,
            actual_command=user_command,
        )

    output_files = sorted(
        [path.name for path in final_out_dir.rglob("*") if path.is_file()]
    ) if final_out_dir.exists() else []

    result = build_skill_run_result(
        skill=skill_name,
        success=proc.returncode == 0,
        exit_code=proc.returncode,
        output_dir=final_out_dir,
        files=output_files,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_seconds=duration,
        method=actual_method,
        readme_path=readme_path,
        notebook_path=notebook_path,
    )

    if session_path and result.success:
        _store_result_in_session(session_path, skill_name, final_out_dir)

    return result


def _store_result_in_session(session_path: str, skill_name: str, out_dir: Path) -> None:
    """Store skill result back into the session JSON."""
    try:
        from omicsclaw.common.session import SpatialSession

        result_json = out_dir / "result.json"
        if not result_json.exists():
            return
        session = SpatialSession.load(session_path)
        result_data = json.loads(result_json.read_text())
        session.add_skill_result(skill_name, result_data, output_dir=str(out_dir))

        processed = out_dir / "processed.h5ad"
        if processed.exists():
            session.h5ad_path = str(processed)
            session.mark_step(skill_name)

        session.save(session_path)
    except Exception:
        pass


def _err(skill: str, msg: str, duration: float = 0) -> SkillRunResult:
    return build_skill_run_result(
        skill=skill,
        success=False,
        exit_code=-1,
        output_dir=None,
        stderr=msg,
        duration_seconds=duration,
    )


__all__ = [
    "DEFAULT_OUTPUT_ROOT",
    "OMICSCLAW_DIR",
    "PYTHON",
    "SPATIAL_PIPELINE",
    "resolve_skill_alias",
    "run_skill",
]
