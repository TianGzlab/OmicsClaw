from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd

AMBIENT_SCRIPT = Path("skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py").resolve()


def _run_skill(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AMBIENT_SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(cwd),
    )


def test_simple_uses_counts_layer_when_x_is_not_count_like(tmp_path):
    input_path = tmp_path / "normalized_with_counts.h5ad"
    output_dir = tmp_path / "ambient_out"

    norm_x = np.array(
        [
            [1.1, 0.4, 0.2],
            [0.8, 0.2, 0.1],
        ],
        dtype=np.float32,
    )
    counts = np.array(
        [
            [11, 4, 2],
            [8, 2, 1],
        ],
        dtype=np.int32,
    )
    adata = ad.AnnData(
        X=norm_x,
        obs=pd.DataFrame(index=["cell1", "cell2"]),
        var=pd.DataFrame(index=["GENE1", "GENE2", "GENE3"]),
    )
    adata.layers["counts"] = counts
    adata.write_h5ad(input_path)

    result = _run_skill(
        ["--input", str(input_path), "--output", str(output_dir), "--method", "simple"],
        cwd=AMBIENT_SCRIPT.parent,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((output_dir / "result.json").read_text())
    assert payload["data"]["params"]["simple_expression_source"] == "layers.counts"
    assert any(
        "layers.counts" in warning for warning in payload["data"]["input_preparation"]["warnings"]
    )

    corrected = ad.read_h5ad(output_dir / "corrected.h5ad")
    np.testing.assert_allclose(np.asarray(corrected.layers["counts"]), counts)


def test_simple_uses_adata_raw_when_no_counts_layer(tmp_path):
    input_path = tmp_path / "normalized_with_raw.h5ad"
    output_dir = tmp_path / "ambient_out"

    norm_x = np.array(
        [
            [1.2, 0.5, 0.1],
            [0.7, 0.3, 0.2],
        ],
        dtype=np.float32,
    )
    raw_counts = np.array(
        [
            [12, 5, 1],
            [7, 3, 2],
        ],
        dtype=np.int32,
    )
    adata = ad.AnnData(
        X=norm_x,
        obs=pd.DataFrame(index=["cell1", "cell2"]),
        var=pd.DataFrame(index=["GENE1", "GENE2", "GENE3"]),
    )
    adata.raw = ad.AnnData(
        X=raw_counts,
        obs=adata.obs.copy(),
        var=adata.var.copy(),
    )
    adata.write_h5ad(input_path)

    result = _run_skill(
        ["--input", str(input_path), "--output", str(output_dir), "--method", "simple"],
        cwd=AMBIENT_SCRIPT.parent,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((output_dir / "result.json").read_text())
    assert payload["data"]["params"]["simple_expression_source"] == "adata.raw"

    corrected = ad.read_h5ad(output_dir / "corrected.h5ad")
    np.testing.assert_allclose(np.asarray(corrected.layers["counts"]), raw_counts)


def test_cellbender_without_input_requires_expected_cells(tmp_path):
    raw_h5 = tmp_path / "fake_raw.h5"
    raw_h5.write_bytes(b"placeholder")
    output_dir = tmp_path / "ambient_out"

    result = _run_skill(
        ["--method", "cellbender", "--raw-h5", str(raw_h5), "--output", str(output_dir)],
        cwd=AMBIENT_SCRIPT.parent,
    )

    assert result.returncode != 0
    assert "--expected-cells" in result.stderr
