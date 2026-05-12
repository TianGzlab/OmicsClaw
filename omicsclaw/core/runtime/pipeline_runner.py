"""Run the pre-defined ``spatial-pipeline`` chain end-to-end.

The pipeline is currently a hard-coded list — see OMI-12 P2.7 for the
plan to make pipelines data-driven (``pipelines/<name>.yaml``).
For now the chain stays inline so this PR is a pure refactor.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omicsclaw.common.report import build_output_dir_name
from omicsclaw.core.skill_result import build_skill_run_result

from .output_finalize import write_pipeline_readme


SPATIAL_PIPELINE: list[str] = [
    "spatial-preprocess",
    "spatial-domains",
    "spatial-de",
    "spatial-genes",
    "spatial-statistics",
]


def run_spatial_pipeline(
    *,
    default_output_root: Path,
    err_factory,
    input_path: str | None = None,
    output_dir: str | None = None,
    demo: bool = False,
    session_path: str | None = None,
) -> dict:
    """Run the standard spatial analysis pipeline end-to-end.

    ``err_factory`` is the runner's ``_err`` helper, injected to avoid an
    import cycle. ``default_output_root`` is also injected so tests that
    monkeypatch ``skill_runner.DEFAULT_OUTPUT_ROOT`` for the regular
    ``run_skill`` path do not need to learn about this module.
    """
    if not input_path and not session_path and not demo:
        return err_factory("spatial-pipeline", "Requires --input, --demo, or --session.")

    # Late import keeps this module a leaf in the dependency DAG: skill_runner
    # imports pipeline_runner, not the other way around.
    from omicsclaw.core.skill_runner import run_skill

    if output_dir:
        out_dir = Path(output_dir)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = default_output_root / build_output_dir_name("spatial-pipeline", ts)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results: dict[str, Any] = {}
    current_input = input_path

    for skill_name in SPATIAL_PIPELINE:
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
            "success": result["success"],
            "duration": result["duration_seconds"],
            "method": result.get("method"),
            "output_dir": result.get("output_dir", ""),
            "readme_path": result.get("readme_path", ""),
            "notebook_path": result.get("notebook_path", ""),
        }
        if not result["success"]:
            print(f"FAILED: {skill_name}")
            if result.get("stderr"):
                print(f"    {result['stderr'][:200]}")
            break

        processed = skill_out / "processed.h5ad"
        if processed.exists():
            current_input = str(processed)

    completed_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "pipeline": SPATIAL_PIPELINE,
        "results": all_results,
        "completed_at": completed_at,
    }
    summary_path = out_dir / "pipeline_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    pipeline_readme = write_pipeline_readme(
        out_dir,
        pipeline_name="spatial-pipeline",
        results=all_results,
        completed_at=completed_at,
    )

    succeeded = sum(1 for result in all_results.values() if result["success"])
    return build_skill_run_result(
        skill="spatial-pipeline",
        success=succeeded == len(SPATIAL_PIPELINE),
        exit_code=0 if succeeded == len(SPATIAL_PIPELINE) else 1,
        output_dir=out_dir,
        files=[path.name for path in out_dir.rglob("*") if path.is_file()],
        stdout=f"Pipeline: {succeeded}/{len(SPATIAL_PIPELINE)} skills succeeded.",
        stderr="",
        duration_seconds=sum(result["duration"] for result in all_results.values()),
        readme_path=pipeline_readme,
        notebook_path="",
    ).to_legacy_dict()
