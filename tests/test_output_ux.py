"""Tests for human-friendly output directory UX."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import nbformat

from omicsclaw.common.report import (
    build_output_dir_name,
    extract_method_name,
    write_output_readme,
)


ROOT = Path(__file__).resolve().parent.parent


def _load_omicsclaw_script():
    spec = importlib.util.spec_from_file_location("omicsclaw_main_test", ROOT / "omicsclaw.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_method_name_prefers_summary_method():
    payload = {
        "summary": {"method": "cellcharter"},
        "data": {"params": {"method": "leiden"}},
    }
    assert extract_method_name(payload) == "cellcharter"


def test_write_output_readme_surfaces_method_params_and_entrypoints(tmp_path):
    payload = {
        "skill": "spatial-domains",
        "completed_at": "2026-03-29T06:26:34+00:00",
        "summary": {
            "method": "cellcharter",
            "n_domains": 2,
            "domain_counts": {"0": 10, "1": 8},
        },
        "data": {
            "params": {
                "method": "cellcharter",
                "resolution": 1.0,
                "auto_k": True,
            }
        },
    }
    (tmp_path / "report.md").write_text("# report\n", encoding="utf-8")
    (tmp_path / "figures").mkdir()
    (tmp_path / "reproducibility").mkdir()
    notebook_path = tmp_path / "reproducibility" / "analysis_notebook.ipynb"
    notebook_path.write_text("{}", encoding="utf-8")
    (tmp_path / "result.json").write_text(json.dumps(payload), encoding="utf-8")

    readme_path = write_output_readme(
        tmp_path,
        skill_alias="spatial-domain-identification",
        description="Identify tissue domains",
        result_payload=payload,
        notebook_path=notebook_path,
    )

    text = readme_path.read_text(encoding="utf-8")
    assert "spatial-domain-identification" in text
    assert "`cellcharter`" in text
    assert "`resolution`: 1" in text
    assert "Open `report.md`" in text
    assert "analysis_notebook.ipynb" in text
    assert "`figures/`" in text
    assert "Identify tissue domains" in text


def test_build_output_dir_name_includes_method_when_available():
    name = build_output_dir_name("spatial-domain-identification", "20260329_063000", method="CellCharter")
    assert name == "spatial-domain-identification__cellcharter__20260329_063000"


def test_run_skill_generates_readme_and_human_readable_dir(monkeypatch, tmp_path):
    oc = _load_omicsclaw_script()
    from omicsclaw.core import skill_runner

    fake_script = tmp_path / "fake_skill.py"
    fake_script.write_text("print('fake')\n", encoding="utf-8")

    monkeypatch.setattr(skill_runner, "DEFAULT_OUTPUT_ROOT", tmp_path)

    from omicsclaw.core.registry import SKILLS_DIR, registry

    monkeypatch.setattr(
        registry,
        "skills",
        {
            "fake-skill": {
                "script": fake_script,
                "domain": "demo",
                "demo_args": ["--demo"],
                "allowed_extra_flags": {"--method"},
                "description": "Synthetic test skill",
            }
        },
        raising=False,
    )
    monkeypatch.setattr(registry, "domains", {"demo": {"name": "Demo"}}, raising=False)
    monkeypatch.setattr(registry, "_loaded", True, raising=False)
    monkeypatch.setattr(registry, "_loaded_dir", SKILLS_DIR.resolve(), raising=False)

    import io

    class FakePopen:
        pid = 999999
        returncode = 0

        def __init__(self, cmd, **kwargs):
            self.cmd = cmd
            self.stdout = io.StringIO("ok\n")
            self.stderr = io.StringIO("")
            out_dir = Path(cmd[cmd.index("--output") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "report.md").write_text("# Fake report\n", encoding="utf-8")
            payload = {
                "skill": "fake-skill-internal",
                "completed_at": "2026-03-29T06:26:34+00:00",
                "summary": {"method": "cellcharter", "score": 0.98},
                "data": {"params": {"method": "cellcharter", "resolution": 1.0}},
            }
            (out_dir / "result.json").write_text(json.dumps(payload), encoding="utf-8")

        def wait(self):
            return self.returncode

    monkeypatch.setattr(skill_runner.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(skill_runner.time, "sleep", lambda _seconds: None)

    result = oc.run_skill("fake-skill", demo=True, extra_args=["--method", "cellcharter"])

    assert result.success is True
    assert result.method == "cellcharter"
    assert "__cellcharter__" in Path(result.output_dir).name
    assert Path(result.readme_path).exists()
    assert Path(result.notebook_path).exists()
    assert "README.md" in result.files
    assert "analysis_notebook.ipynb" in result.files
    readme_text = Path(result.readme_path).read_text(encoding="utf-8")
    assert "Synthetic test skill" in readme_text
    assert "cellcharter" in readme_text
    assert "analysis_notebook.ipynb" in readme_text

    notebook = nbformat.read(result.notebook_path, as_version=4)
    assert notebook.metadata["omicsclaw"]["skill"] == "fake-skill"
    sources = "\n".join(cell.source for cell in notebook.cells)
    assert "load_skill" in sources
    assert "ACTUAL_RUN_COMMAND" in sources
    assert "preview_function" in sources


def test_pipeline_readme_lists_step_methods(tmp_path):
    from omicsclaw.core.skill_runner import _write_pipeline_readme

    readme_path = _write_pipeline_readme(
        tmp_path,
        pipeline_name="spatial-pipeline",
        completed_at="2026-03-29T06:30:00+00:00",
        results={
            "preprocess": {
                "success": True,
                "method": "scanpy",
                "output_dir": str(tmp_path / "preprocess"),
                "notebook_path": str(tmp_path / "preprocess" / "reproducibility" / "analysis_notebook.ipynb"),
            },
            "domains": {
                "success": True,
                "method": "cellcharter",
                "output_dir": str(tmp_path / "domains"),
                "notebook_path": str(tmp_path / "domains" / "reproducibility" / "analysis_notebook.ipynb"),
            },
        },
    )

    text = readme_path.read_text(encoding="utf-8")
    assert "spatial-pipeline" in text
    assert "scanpy" in text
    assert "cellcharter" in text
    assert "`preprocess`" in text
    assert "analysis_notebook.ipynb" in text


def test_spatial_genes_help_does_not_require_scanpy_runtime():
    script = ROOT / "skills" / "spatial" / "spatial-genes" / "spatial_genes.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert result.returncode == 0
    assert "--morans-coord-type" in result.stdout
    assert "--sparkx-option" in result.stdout
    assert "--flashs-bandwidth" in result.stdout
