"""Tests for the sc-preprocessing skill."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from skills._sdk.r_script_runner import RScriptRunner

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_preprocess.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_preprocess_out"


def test_demo_mode(tmp_output):
    """sc-preprocessing --demo should run without error."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert not (tmp_output / "README.md").exists()
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "tables" / "preprocess_summary.csv").exists()
    assert (tmp_output / "tables" / "qc_metrics_per_cell.csv").exists()
    assert (tmp_output / "tables" / "pca_embedding.csv").exists()
    assert (tmp_output / "processed.h5ad").exists()
    assert not (tmp_output / "reproducibility" / "replay.json").exists()
    assert (tmp_output / "reproducibility" / "requirements.txt").exists()
    assert not (tmp_output / "reproducibility" / "environment.txt").exists()


def test_demo_report_content(tmp_output):
    """Report should contain expected sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Preprocessing" in report or "preprocessing" in report
    assert "Default Gallery" in report
    assert "Disclaimer" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "sc-preprocessing"
    assert "summary" in data
    assert data["data"]["params"]["method"] == "scanpy"
    assert data["data"]["effective_params"]["method"] == "scanpy"
    assert data["data"]["effective_params"]["scanpy_hvg_flavor"] == "seurat"
    assert data["data"]["effective_params"]["normalization_target_sum"] == 10000.0
    assert data["data"]["effective_params"]["raw_available"] is True
    assert data["data"]["visualization"]["recipe_id"] == "standard-sc-preprocessing-gallery"
    assert "pca_embedding" in data["data"]["visualization"]["available_figure_data"]
    command_text = (tmp_output / "reproducibility" / "commands.sh").read_text()
    assert "--method scanpy" in command_text


def _load_api(name: str):
    spec = importlib.util.spec_from_file_location(name, SKILL_SCRIPT.parent / "_api.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_seurat_backend_is_wired_into_the_library():
    """The R-backed Seurat workflows are reachable through ``preprocess``."""
    module = _load_api("sc_preprocess_api")
    assert {"seurat", "sctransform"} <= set(module.METHODS)
    assert hasattr(module, "_run_seurat_preprocessing")


def test_seurat_backend_preflight_requires_rhdf5(monkeypatch):
    """The Python preflight must catch zellkonverter's H5AD dependency."""
    module = _load_api("sc_preprocess_api_r_preflight")

    observed: list[str] = []

    def stop_after_preflight(*, required_r_packages):
        observed.extend(required_r_packages)
        raise RuntimeError("stop after dependency preflight")

    monkeypatch.setattr(module, "validate_r_environment", stop_after_preflight)
    with pytest.raises(RuntimeError, match="stop after dependency preflight"):
        module._run_seurat_preprocessing(object(), workflow="seurat")

    assert "rhdf5" in observed


def test_prepare_input_can_preserve_original_feature_axis():
    import anndata as ad
    import numpy as np
    import pandas as pd

    module = _load_api("sc_preprocess_api_preserve")

    adata = ad.AnnData(
        X=np.array([[3, 1], [2, 1], [1, 0]], dtype=np.int32),
        obs=pd.DataFrame(index=["cell1", "cell2", "cell3"]),
        var=pd.DataFrame(
            {"feature_name": ["MT-CO1", "RPS3"]},
            index=pd.Index(["ENSG1", "ENSG2"], name="gene"),
        ),
    )
    prepared, _summary, _params, contract = module._prepare_input(
        adata,
        effective_params={
            "method": "scanpy",
            "min_genes": 0,
            "min_cells": 0,
            "max_mt_pct": 100.0,
            "remove_doublets": False,
            "preserve_var_names": True,
        },
    )

    assert prepared.var_names.tolist() == ["ENSG1", "ENSG2"]
    assert prepared.var_names.name == "gene"
    assert prepared.var["mt"].tolist() == [True, False]
    assert contract["preserved_var_names"] is True


def _has_seurat_r_stack() -> bool:
    """Probe the same R executable and library paths as production execution."""
    runner = RScriptRunner(verbose=False)
    packages = ["Seurat", "SingleCellExperiment", "zellkonverter", "rhdf5"]
    return runner.check_r_available() and not runner.get_missing_packages(packages)


@pytest.mark.skipif(not _has_seurat_r_stack(), reason="R Seurat preprocessing stack not installed")
def test_demo_mode_seurat(tmp_output):
    """sc-preprocessing --method seurat should run when the R stack is available."""
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--demo",
            "--method",
            "seurat",
            "--output",
            str(tmp_output),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
    )
    if result.returncode != 0:
        bootstrap_markers = [
            "Couldn't connect to server",
            "trying URL",
            "Miniforge",
            "basilisk",
        ]
        if any(marker in result.stderr for marker in bootstrap_markers):
            pytest.skip("R Seurat stack requires basilisk bootstrap that is unavailable in this environment")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["summary"]["method"] == "seurat"
    assert payload["data"]["visualization"]["recipe_id"] == "standard-sc-preprocessing-gallery"
