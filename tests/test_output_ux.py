"""Tests for human-friendly output directory UX."""

from __future__ import annotations

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
    replay_path = tmp_path / "reproducibility" / "replay.json"
    replay_path.write_text("{}", encoding="utf-8")
    (tmp_path / "reproducibility" / "replay.sh").write_text(
        "#!/bin/sh\noc replay replay.json\n",
        encoding="utf-8",
    )
    (tmp_path / "result.json").write_text(json.dumps(payload), encoding="utf-8")

    readme_path = write_output_readme(
        tmp_path,
        skill_alias="spatial-domain-identification",
        description="Identify tissue domains",
        result_payload=payload,
        replay_path=replay_path,
    )

    text = readme_path.read_text(encoding="utf-8")
    assert "spatial-domain-identification" in text
    assert "`cellcharter`" in text
    assert "`resolution`: 1" in text
    assert "Open `report.md`" in text
    assert "reproducibility/replay.json" in text
    assert "reproducibility/replay.sh" in text
    assert "`figures/`" in text
    assert "Identify tissue domains" in text


def test_write_output_readme_does_not_advertise_hardlinked_report(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("# unowned report\n", encoding="utf-8")
    (tmp_path / "report.md").hardlink_to(source)

    readme_path = write_output_readme(
        tmp_path,
        skill_alias="spatial-domain-identification",
    )

    text = readme_path.read_text(encoding="utf-8")
    assert "This run did not generate `report.md`" in text
    assert "Open `report.md`" not in text


def test_write_output_readme_does_not_inventory_contained_directory_symlink(
    tmp_path: Path,
) -> None:
    real_dir = tmp_path / "figures"
    real_dir.mkdir()
    (tmp_path / "figures-alias").symlink_to(
        real_dir.name,
        target_is_directory=True,
    )

    readme_path = write_output_readme(tmp_path, skill_alias="demo")

    text = readme_path.read_text(encoding="utf-8")
    assert "`figures/`" in text
    assert "figures-alias" not in text


def test_build_output_dir_name_includes_method_when_available():
    name = build_output_dir_name("spatial-domain-identification", "20260329_063000", method="CellCharter")
    assert name == "spatial-domain-identification__cellcharter__20260329_063000"


def test_analysis_notebook_rejects_claim_aliases(tmp_path):
    from omicsclaw.common.notebook_export import write_analysis_notebook
    from omicsclaw.common.output_claim import OUTPUT_CLAIM_FILENAME

    output_dir = tmp_path / "out"
    (output_dir / "figures").mkdir(parents=True)
    (output_dir / "tables").mkdir()
    claim = output_dir / OUTPUT_CLAIM_FILENAME
    claim.write_text("{}\n", encoding="utf-8")
    (output_dir / "processed.h5ad").hardlink_to(claim)
    (output_dir / "figures" / "claim.png").hardlink_to(claim)
    (output_dir / "tables" / "claim.csv").hardlink_to(claim)
    (output_dir / "figures" / "plot.png").write_bytes(b"png")
    (output_dir / "tables" / "table.csv").write_text("a\n1\n", encoding="utf-8")

    notebook_path = write_analysis_notebook(
        output_dir,
        skill_alias="demo-skill",
        result_payload={"summary": {}, "data": {}},
    )
    notebook = nbformat.read(notebook_path, as_version=4)
    rendered = "\n".join(cell.source for cell in notebook.cells)

    assert "processed.h5ad" not in rendered
    assert "claim.png" not in rendered
    assert "claim.csv" not in rendered
    assert "plot.png" in rendered
    assert "table.csv" in rendered


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
