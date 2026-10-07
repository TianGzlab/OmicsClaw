"""Ambient correction preserves the selected original counts."""

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from scipy import sparse
from scipy.io import mmread
from pathlib import Path

from skills._sdk.notebook import load_skill
from skills._sdk import deps
from skills._sdk.r_script_runner import RScriptRunner


@pytest.mark.parametrize("sparse_input", [False, True])
def test_simple_subtraction_uses_counts_and_clips_at_zero(sparse_input):
    counts = np.array([[10., 0.], [0., 10.]], dtype=np.float32)
    matrix = sparse.csr_matrix(counts) if sparse_input else counts
    adata = ad.AnnData(np.log1p(counts), var=pd.DataFrame(index=["A", "B"]))
    adata.layers["counts"] = matrix.copy()
    api = load_skill("sc-ambient-removal")
    result = api.remove_ambient(adata, contamination=0.1)
    assert result is adata
    actual = result.X.toarray() if sparse.issparse(result.X) else result.X
    np.testing.assert_allclose(actual, [[9.5, 0.], [0., 9.5]])
    original = result.layers["counts"].toarray() if sparse_input else result.layers["counts"]
    np.testing.assert_array_equal(original, counts)
    assert api.run_info(adata)["expression_source"] == "layers.counts"
    assert api.counts_comparison_table(adata)["counts_before"].tolist() == [10., 10.]
    assert api.ambient_profile_table(adata)["fraction"].tolist() == [0.5, 0.5]
    assert api.correction_summary(adata)["reduction_pct"].iloc[0] == pytest.approx(5.)


def test_soupx_exchanges_selected_counts_and_aligns_reordered_output(monkeypatch):
    api = load_skill("sc-ambient-removal")
    adata = ad.AnnData(np.ones((2, 2)), obs=pd.DataFrame(index=["c1", "c2"]),
                      var=pd.DataFrame(index=["A", "B"]))
    adata.layers["counts"] = np.array([[10., 2.], [3., 20.]])
    raw = ad.AnnData(np.array([[10., 2.], [3., 20.], [1., 1.]]),
                    obs=pd.DataFrame(index=["c1", "c2", "empty"]), var=adata.var.copy())
    folders = []

    def run_script(self, script_name, *, args, expected_outputs, output_dir):
        assert script_name == "sc_soupx.R"
        raw_dir, filtered_dir, output = map(Path, args)
        folders.append(raw_dir.parent)
        np.testing.assert_array_equal(mmread(raw_dir / "matrix.mtx.gz").toarray(), raw.X.T)
        np.testing.assert_array_equal(mmread(filtered_dir / "matrix.mtx.gz").toarray(), adata.layers["counts"].T)
        assert pd.read_csv(filtered_dir / "barcodes.tsv.gz", header=None)[0].tolist() == ["c1", "c2"]
        pd.DataFrame([[18., 1.], [2., 9.]], index=["B", "A"], columns=["c2", "c1"]).to_csv(output / "corrected_counts.csv")
        pd.DataFrame({"cell": ["c2", "c1"]}).to_csv(output / "cells.csv", index=False)
        pd.DataFrame({"gene": ["B", "A"]}).to_csv(output / "genes.csv", index=False)
        (output / "contamination.json").write_text('{"contamination": 0.1}')

    monkeypatch.setattr(deps, "validate_r_environment", lambda **kwargs: None)
    monkeypatch.setattr(RScriptRunner, "run_script", run_script)
    result = api.remove_ambient_soupx(adata, raw=raw)
    assert result is not adata
    np.testing.assert_array_equal(result.X, [[9., 1.], [2., 18.]])
    np.testing.assert_array_equal(result.layers["counts"], adata.layers["counts"])
    np.testing.assert_array_equal(adata.X, np.ones((2, 2)))
    assert api.run_info(result)["executed_method"] == "soupx"
    assert all(not folder.exists() for folder in folders)


@pytest.mark.requires_r
def test_temporary_exchange_is_readable_by_seurat(tmp_path):
    import shutil
    import subprocess
    from skills.singlecell._lib.r_exchange import write_matrix_exchange
    rscript = shutil.which("Rscript")
    if rscript is None:
        pytest.skip("Rscript is unavailable")
    matrix = ad.AnnData(np.array([[10., 2.], [3., 20.]]),
                        obs=pd.DataFrame(index=["c1", "c2"]), var=pd.DataFrame(index=["A", "B"]))
    folder = write_matrix_exchange(matrix, tmp_path / "tenx", obs_columns=[], compressed=True)
    completed = subprocess.run([rscript, "-e", 'suppressPackageStartupMessages(library(Seurat)); x <- Read10X(commandArgs(TRUE)[1]); stopifnot(identical(dim(x), c(2L, 2L)), identical(colnames(x), c("c1", "c2")), x[1, 1] == 10)', str(folder)], capture_output=True, text=True)
    if "there is no package called" in completed.stderr:
        pytest.skip(completed.stderr)
    assert completed.returncode == 0, completed.stdout + completed.stderr
