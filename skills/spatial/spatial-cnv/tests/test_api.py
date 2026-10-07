"""Copy-number inference through load_skill."""

import numpy as np
import pytest
from skills._sdk.notebook import load_demo, load_skill


def test_missing_gene_positions_are_rejected_before_inference():
    with pytest.raises(ValueError, match="genomic"):
        load_skill("spatial-cnv").cnv(load_demo("spatial_synthetic"))


def test_numbat_does_not_treat_log_expression_as_counts():
    with pytest.raises(ValueError, match="raw integer"):
        load_skill("spatial-cnv").cnv(load_demo("spatial_synthetic"), method="numbat")


def test_reference_categories_require_an_annotation_key():
    with pytest.raises(ValueError, match="reference_key"):
        load_skill("spatial-cnv").cnv(load_demo("spatial_synthetic"), reference_cat=["Normal"])


def test_missing_backend_names_the_install_action():
    import sys
    import subprocess

    code = """
import sys
from skills._sdk.notebook import load_demo, load_skill
data = load_demo('spatial_synthetic')
data.var['chromosome'] = 'chr1'
data.var['start'] = 0
data.var['end'] = 1
sys.modules['infercnvpy'] = None
try:
    load_skill('spatial-cnv').cnv(data)
except ImportError as exc:
    assert 'infercnvpy' in str(exc) and 'install_skill_deps' in str(exc)
else:
    raise AssertionError('Missing backend was not reported')
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_numbat_exchanges_gene_by_cell_matrix_and_long_alleles(monkeypatch):
    import anndata as ad
    import pandas as pd
    import subprocess
    from pathlib import Path
    from scipy.io import mmread

    data = ad.AnnData(np.zeros((2, 3)), obs=pd.DataFrame({"kind": ["Normal", "Tumor"]}, index=["a", "b"]))
    data.var_names = ["G1", "G2", "G3"]
    data.layers["counts"] = np.array([[1, 2, 3], [4, 5, 6]])
    alleles = pd.DataFrame({"cell": ["a", "a", "b", "b"], "snp_id": ["v1", "v2", "v1", "v2"],
                           "CHROM": "1", "POS": [10, 20, 10, 20], "AD": 1, "DP": 2, "GT": "0|1", "gene": "G1"})
    temporary_inputs = []

    def r_process(command, **kwargs):
        if len(command) > 1 and str(command[1]).endswith("/numbat.R"):
            folder, output = Path(command[2]), Path(command[3])
            temporary_inputs.append(folder)
            np.testing.assert_array_equal(mmread(folder / "counts.mtx").toarray(), [[1, 4], [2, 5], [3, 6]])
            assert (folder / "barcodes.tsv").read_text().splitlines() == ["a", "b"]
            assert (folder / "features.tsv").read_text().splitlines() == ["G1", "G2", "G3"]
            assert pd.read_csv(folder / "obs.csv")["kind"].tolist() == ["Normal", "Tumor"]
            assert len(pd.read_csv(folder / "allele_counts.csv")) == 4
            assert command[-1] == "13"
            pd.DataFrame({"cell": ["b"], "segment": ["chr1"]}).to_csv(output / "numbat_results.csv", index=False)
            pd.DataFrame({"cell": ["b", "a"], "p_cnv": [0.8, 0.1]}).to_csv(output / "numbat_clone_post.csv", index=False)
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, "numbat:TRUE\nMatrix:TRUE\n", "")

    monkeypatch.setattr(subprocess, "run", r_process)
    library = load_skill("spatial-cnv")
    assert library.cnv(data, method="numbat", reference_key="kind", reference_cat=["Normal"],
                       allele_counts=alleles, random_state=13) is data
    np.testing.assert_allclose(library.scores(data)["numbat_p_cnv"], [0.1, 0.8])
    assert temporary_inputs and all(not folder.exists() for folder in temporary_inputs)


def test_infercnv_returns_scores_in_observation_order():
    import scanpy as sc

    pytest.importorskip("infercnvpy")
    data = load_demo("spatial_synthetic")
    data.var["chromosome"] = "chr1"
    data.var["start"] = np.arange(data.n_vars) * 10000
    data.var["end"] = data.var["start"] + 1000
    sc.pp.normalize_total(data, target_sum=10000)
    sc.pp.log1p(data)
    library = load_skill("spatial-cnv")
    assert library.cnv(data, window_size=20, step=2) is data
    table = library.scores(data)
    assert table.index.equals(data.obs_names)
    assert np.isfinite(table["cnv_score"]).all()
    assert library.run_info(data)["method"] == "infercnvpy"
