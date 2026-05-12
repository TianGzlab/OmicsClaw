"""Run a multi-step skill chain described by a ``PipelineConfig``.

OMI-12 P2.7: the spatial chain used to be a hard-coded
``SPATIAL_PIPELINE = [...]`` list with a dedicated ``_run_spatial_pipeline``
function. New pipelines now live as ``pipelines/<name>.yaml`` files (see
``pipeline_config``); this module is the generic runner that consumes one.

For backward compatibility ``SPATIAL_PIPELINE`` is still exposed — it's
derived from ``pipelines/spatial-pipeline.yaml`` so a config edit is the
single source of truth.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omicsclaw.common.report import build_output_dir_name
from omicsclaw.core.skill_result import SkillRunResult, build_skill_run_result

from .output_finalize import write_pipeline_readme
from .pipeline_config import (
    PipelineConfig,
    PipelineConfigError,
    load_pipeline_config,
)


def _load_spatial_pipeline_skill_names() -> list[str]:
    """Resolve the spatial chain at import time, falling back to a stable list.

    The YAML is the source of truth — but we don't want a missing file
    (e.g. an incomplete install or a wheel that didn't ship ``pipelines/``)
    to break callers that just want the constant. The fallback mirrors
    the historical hard-coded order so behaviour stays unchanged.
    """
    try:
        config = load_pipeline_config("spatial-pipeline")
    except PipelineConfigError:
        config = None
    if config is None:
        return [
            "spatial-preprocess",
            "spatial-domains",
            "spatial-de",
            "spatial-genes",
            "spatial-statistics",
        ]
    return list(config.skill_names)


SPATIAL_PIPELINE: list[str] = _load_spatial_pipeline_skill_names()


def run_pipeline(
    config: PipelineConfig,
    *,
    default_output_root: Path,
    err_factory,
    input_path: str | None = None,
    output_dir: str | None = None,
    demo: bool = False,
    session_path: str | None = None,
) -> SkillRunResult:
    """Run an arbitrary skill chain described by ``config`` end-to-end.

    ``err_factory`` is the runner's ``_err`` helper, injected to avoid an
    import cycle. ``default_output_root`` is also injected so tests that
    monkeypatch ``skill_runner.DEFAULT_OUTPUT_ROOT`` for the regular
    ``run_skill`` path do not need to learn about this module.

    Returns a ``SkillRunResult`` natively (OMI-12 P1.6); callers that need
    the legacy dict shape should call ``.to_legacy_dict()`` themselves.
    """
    if not input_path and not session_path and not demo:
        return err_factory(config.name, "Requires --input, --demo, or --session.")

    # Late import keeps this module a leaf in the dependency DAG: skill_runner
    # imports pipeline_runner, not the other way around.
    from omicsclaw.core.skill_runner import run_skill

    if output_dir:
        out_dir = Path(output_dir)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = default_output_root / build_output_dir_name(config.name, ts)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results: dict[str, Any] = {}
    current_input = input_path
    chain_basename = config.chain_output_basename

    for skill_name in config.skill_names:
        skill_out = out_dir / skill_name
        print(f"  Running {skill_name}...")
        result = run_skill(
            skill_name=skill_name,
            input_path=current_input,
            output_dir=str(skill_out),
            demo=demo and current_input is None,
            session_path=session_path,
        )
        all_results[skill_name] = {
            "success": result.success,
            "duration": result.duration_seconds,
            "method": result.method,
            "output_dir": result.output_dir or "",
            "readme_path": result.readme_path,
            "notebook_path": result.notebook_path,
        }
        if not result.success:
            print(f"FAILED: {skill_name}")
            if result.stderr:
                print(f"    {result.stderr[:200]}")
            break

        baton = skill_out / chain_basename
        if baton.exists():
            current_input = str(baton)

    completed_at = datetime.now(timezone.utc).isoformat()
    skill_names = list(config.skill_names)
    summary = {
        "pipeline": skill_names,
        "results": all_results,
        "completed_at": completed_at,
    }
    summary_path = out_dir / "pipeline_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    pipeline_readme = write_pipeline_readme(
        out_dir,
        pipeline_name=config.name,
        results=all_results,
        completed_at=completed_at,
    )

    succeeded = sum(1 for result in all_results.values() if result["success"])
    return build_skill_run_result(
        skill=config.name,
        success=succeeded == len(skill_names),
        exit_code=0 if succeeded == len(skill_names) else 1,
        output_dir=out_dir,
        files=[path.name for path in out_dir.rglob("*") if path.is_file()],
        stdout=f"Pipeline: {succeeded}/{len(skill_names)} skills succeeded.",
        stderr="",
        duration_seconds=sum(result["duration"] for result in all_results.values()),
        readme_path=pipeline_readme,
        notebook_path="",
    )


def run_spatial_pipeline(
    *,
    default_output_root: Path,
    err_factory,
    input_path: str | None = None,
    output_dir: str | None = None,
    demo: bool = False,
    session_path: str | None = None,
) -> SkillRunResult:
    """Thin wrapper preserved for backward compatibility.

    Loads ``pipelines/spatial-pipeline.yaml`` and delegates to
    :func:`run_pipeline`. New callers should use :func:`run_pipeline_by_name`
    or :func:`run_pipeline` directly.
    """
    try:
        config = load_pipeline_config("spatial-pipeline")
    except PipelineConfigError as exc:
        return err_factory("spatial-pipeline", f"Pipeline config invalid: {exc}")
    if config is None:
        return err_factory(
            "spatial-pipeline",
            "pipelines/spatial-pipeline.yaml not found",
        )
    return run_pipeline(
        config,
        default_output_root=default_output_root,
        err_factory=err_factory,
        input_path=input_path,
        output_dir=output_dir,
        demo=demo,
        session_path=session_path,
    )


def run_pipeline_by_name(
    name: str,
    *,
    default_output_root: Path,
    err_factory,
    input_path: str | None = None,
    output_dir: str | None = None,
    demo: bool = False,
    session_path: str | None = None,
) -> SkillRunResult | None:
    """Load ``pipelines/<name>.yaml`` and run it; return ``None`` when absent.

    ``None`` lets the dispatcher fall through to the regular skill registry
    lookup instead of fabricating an error result the caller didn't ask for
    — a missing YAML for a name ending in ``-pipeline`` is just "no pipeline
    by that alias", not "the user's request was broken".
    """
    try:
        config = load_pipeline_config(name)
    except PipelineConfigError as exc:
        return err_factory(name, f"Pipeline config invalid: {exc}")
    if config is None:
        return None
    return run_pipeline(
        config,
        default_output_root=default_output_root,
        err_factory=err_factory,
        input_path=input_path,
        output_dir=output_dir,
        demo=demo,
        session_path=session_path,
    )
