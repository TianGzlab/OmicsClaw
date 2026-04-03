from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd

STANDARDIZE_SCRIPT = Path("skills/singlecell/scrna/sc-standardize-input/sc_standardize_input.py").resolve()
QC_SCRIPT = Path("skills/singlecell/scrna/sc-qc/sc_qc.py").resolve()


def _make_nonstandard_h5ad(path: Path) -> None:
    norm_x = np.array(
        [
            [1.1, 0.4, 0.2, 0.1],
            [0.8, 0.2, 0.2, 0.0],
            [1.4, 0.3, 0.1, 0.0],
        ],
        dtype=np.float32,
    )
    counts = np.array(
        [
            [10, 4, 2, 1],
            [8, 2, 2, 0],
            [14, 3, 1, 0],
        ],
        dtype=np.int32,
    )
    adata = ad.AnnData(
        X=norm_x,
        obs=pd.DataFrame(index=["cell1", "cell2", "cell3"]),
        var=pd.DataFrame(
            {"gene_symbols": ["MT-CO1", "RPS3", "GENE3", "GENE4"]},
            index=["ENSG1", "ENSG2", "ENSG3", "ENSG4"],
        ),
    )
    adata.layers["counts"] = counts
    adata.write_h5ad(path)


def test_standardize_input_creates_canonical_contract(tmp_path):
    input_path = tmp_path / "input.h5ad"
    output_dir = tmp_path / "standardized"
    _make_nonstandard_h5ad(input_path)

    result = subprocess.run(
        [sys.executable, str(STANDARDIZE_SCRIPT), "--input", str(input_path), "--output", str(output_dir)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(STANDARDIZE_SCRIPT.parent),
    )

    assert result.returncode == 0, result.stderr
    standardized_path = output_dir / "standardized_input.h5ad"
    assert standardized_path.exists()
    payload = json.loads((output_dir / "result.json").read_text())
    contract = payload["data"]["input_contract"]
    assert contract["standardized"] is True
    assert contract["standardized_by"] == "sc-standardize-input"
    assert contract["expression_source"] == "layers.counts"
    assert contract["gene_name_source"] == "var.gene_symbols"

    standardized = ad.read_h5ad(standardized_path)
    np.testing.assert_allclose(np.asarray(standardized.X), np.asarray(standardized.layers["counts"]))
    assert standardized.var_names.tolist()[0] == "MT-CO1"
    assert standardized.var["feature_id"].tolist()[0] == "ENSG1"


def test_qc_warns_before_standardization_but_not_after(tmp_path):
    input_path = tmp_path / "input.h5ad"
    standardized_dir = tmp_path / "standardized"
    qc_raw_dir = tmp_path / "qc_raw"
    qc_std_dir = tmp_path / "qc_std"
    _make_nonstandard_h5ad(input_path)

    raw_run = subprocess.run(
        [sys.executable, str(QC_SCRIPT), "--input", str(input_path), "--output", str(qc_raw_dir)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(QC_SCRIPT.parent),
    )
    assert raw_run.returncode == 0, raw_run.stderr
    assert "sc-standardize-input" in raw_run.stderr

    std_run = subprocess.run(
        [sys.executable, str(STANDARDIZE_SCRIPT), "--input", str(input_path), "--output", str(standardized_dir)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(STANDARDIZE_SCRIPT.parent),
    )
    assert std_run.returncode == 0, std_run.stderr

    standardized_path = standardized_dir / "standardized_input.h5ad"
    qc_run = subprocess.run(
        [sys.executable, str(QC_SCRIPT), "--input", str(standardized_path), "--output", str(qc_std_dir)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(QC_SCRIPT.parent),
    )
    assert qc_run.returncode == 0, qc_run.stderr
    assert "sc-standardize-input" not in qc_run.stderr
