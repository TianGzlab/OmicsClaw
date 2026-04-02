import json
import os
from pathlib import Path
import time

import pytest

from omicsclaw.core.registry import OmicsRegistry
from omicsclaw.core.skill_scaffolder import (
    create_skill_scaffold,
    find_latest_autonomous_analysis,
    infer_skill_name,
)


def test_infer_skill_name_falls_back_to_request_tokens():
    assert infer_skill_name("Create a CellCharter spatial domains skill", "spatial") == (
        "cellcharter-spatial-domains"
    )


def test_create_skill_scaffold_creates_registry_loadable_skill(tmp_path: Path):
    result = create_skill_scaffold(
        request="Create a reusable kinase activity skill for phosphoproteomics.",
        domain="proteomics",
        skill_name="proteomics-kinase-activity",
        summary="Kinase activity inference scaffold for phosphoproteomics matrices.",
        methods=["ksea"],
        trigger_keywords=["kinase activity", "ksea"],
        skills_root=tmp_path,
    )

    skill_dir = Path(result.skill_dir)
    assert skill_dir.exists()
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "proteomics_kinase_activity.py").exists()
    assert (skill_dir / "tests" / "test_proteomics_kinase_activity.py").exists()
    assert (skill_dir / "scaffold_spec.json").exists()
    assert (skill_dir / "manifest.json").exists()
    assert (skill_dir / "completion_report.json").exists()
    assert result.completion["status"] == "complete"
    assert result.completion["completed"] is True

    registry = OmicsRegistry()
    registry.load_all(tmp_path)

    info = registry.skills.get("proteomics-kinase-activity")
    assert info is not None
    assert info["domain"] == "proteomics"
    assert info["script"].name == "proteomics_kinase_activity.py"


def test_create_skill_scaffold_can_promote_autonomous_analysis(tmp_path: Path):
    output_root = tmp_path / "output"
    source_dir = output_root / "peak-detection__20260331_055254__f8024e5c"
    repro_dir = source_dir / "reproducibility"
    repro_dir.mkdir(parents=True)

    notebook = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Plan\n"]},
            {
                "cell_type": "code",
                "metadata": {},
                "outputs": [],
                "execution_count": 1,
                "source": [
                    'ANALYSIS_GOAL = "detect peaks"\n',
                    'ANALYSIS_CONTEXT = ""\n',
                    'WEB_CONTEXT = "docs"\n',
                    'INPUT_FILE = ""\n',
                    f'AUTONOMOUS_OUTPUT_DIR = "{source_dir}"\n',
                    "def _blocked(*args, **kwargs):\n    raise RuntimeError('x')\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "outputs": [],
                "execution_count": 2,
                "source": [
                    "from pathlib import Path\n",
                    "out = Path(AUTONOMOUS_OUTPUT_DIR) / 'detected.txt'\n",
                    "out.write_text('ok', encoding='utf-8')\n",
                ],
            },
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (repro_dir / "analysis_notebook.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    (source_dir / "analysis_plan.md").write_text("1. detect peaks\n", encoding="utf-8")
    (source_dir / "result_summary.md").write_text("# success\n", encoding="utf-8")
    (source_dir / "web_sources.md").write_text("source docs\n", encoding="utf-8")
    (source_dir / "capability_decision.json").write_text(
        json.dumps({"domain": "orchestrator"}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = create_skill_scaffold(
        request="Package the successful peak detection run as a skill.",
        domain="",
        skill_name="peak-detection-skill",
        summary="Reusable peak detection skill.",
        skills_root=tmp_path / "skills",
        source_analysis_dir=source_dir,
        output_root=output_root,
    )

    skill_dir = Path(result.skill_dir)
    script_text = (skill_dir / "peak_detection_skill.py").read_text(encoding="utf-8")
    assert "Promoted OmicsClaw skill" in script_text
    assert "out = Path(AUTONOMOUS_OUTPUT_DIR) / 'detected.txt'" in script_text
    assert (skill_dir / "references" / "source_analysis_notebook.ipynb").exists()
    assert (skill_dir / "references" / "source_result_summary.md").exists()
    assert (skill_dir / "manifest.json").exists()
    assert (skill_dir / "completion_report.json").exists()
    assert result.completion["status"] == "complete"
    assert result.completion["completed"] is True


def test_create_skill_scaffold_rejects_incomplete_autonomous_analysis(tmp_path: Path):
    source_dir = tmp_path / "output" / "incomplete-analysis"
    repro_dir = source_dir / "reproducibility"
    repro_dir.mkdir(parents=True)
    (repro_dir / "analysis_notebook.ipynb").write_text("{}", encoding="utf-8")
    (source_dir / "analysis_plan.md").write_text("plan\n", encoding="utf-8")
    (source_dir / "result_summary.md").write_text("summary\n", encoding="utf-8")
    (source_dir / "completion_report.json").write_text(
        json.dumps({"completed": False, "status": "failed"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not promotable"):
        create_skill_scaffold(
            request="Promote the failed analysis.",
            domain="orchestrator",
            skill_name="failed-analysis-skill",
            skills_root=tmp_path / "skills",
            source_analysis_dir=source_dir,
        )


def test_find_latest_autonomous_analysis_returns_newest(tmp_path: Path):
    output_root = tmp_path / "output"
    older = output_root / "older"
    newer = output_root / "newer"
    for path in (older, newer):
        (path / "reproducibility").mkdir(parents=True)
        (path / "reproducibility" / "analysis_notebook.ipynb").write_text("{}", encoding="utf-8")
        (path / "analysis_plan.md").write_text("plan\n", encoding="utf-8")
        (path / "result_summary.md").write_text("summary\n", encoding="utf-8")

    future_ts = time.time() + 60
    for target in (
        newer,
        newer / "reproducibility" / "analysis_notebook.ipynb",
        newer / "analysis_plan.md",
        newer / "result_summary.md",
    ):
        os.utime(target, (future_ts, future_ts))
    latest = find_latest_autonomous_analysis(output_root=output_root)
    assert latest == newer


def test_find_latest_autonomous_analysis_skips_incomplete_completion_reports(tmp_path: Path):
    output_root = tmp_path / "output"
    incomplete = output_root / "incomplete"
    complete = output_root / "complete"
    for path in (incomplete, complete):
        (path / "reproducibility").mkdir(parents=True)
        (path / "reproducibility" / "analysis_notebook.ipynb").write_text("{}", encoding="utf-8")
        (path / "analysis_plan.md").write_text("plan\n", encoding="utf-8")
        (path / "result_summary.md").write_text("summary\n", encoding="utf-8")
    (incomplete / "completion_report.json").write_text(
        json.dumps({"completed": False, "status": "failed"}),
        encoding="utf-8",
    )
    (complete / "completion_report.json").write_text(
        json.dumps({"completed": True, "status": "complete"}),
        encoding="utf-8",
    )

    assert find_latest_autonomous_analysis(output_root=output_root) == complete
