"""MAST reads the exact X and requested obs column through Matrix Market."""

import anndata as ad
import numpy as np
import pandas as pd

from skills._sdk.notebook import load_skill
from skills._sdk.r_script_runner import RScriptRunner


def test_mast_receives_expression_and_groups_without_h5ad(monkeypatch):
    from scipy.io import mmread
    from pathlib import Path

    expression = np.array([[1.2, 0.], [0.3, 2.5], [4., 0.8], [1., 1.5]])
    adata = ad.AnnData(expression, obs=pd.DataFrame({"group": ["A", "A", "B", "B"]},
                                                  index=["c1", "c2", "c3", "c4"]),
                        var=pd.DataFrame(index=["g1", "g2"]))

    def run_script(self, script_name, *, args, expected_outputs, output_dir):
        folder = Path(args[0])
        assert folder.is_dir()
        np.testing.assert_allclose(mmread(folder / "matrix.mtx").toarray(), expression.T)
        metadata = pd.read_csv(folder / "obs.csv", index_col=0)
        assert metadata.index.tolist() == adata.obs_names.tolist()
        assert list(metadata) == ["group"]
        assert args[2:] == ["group", "A", "B"]
        assert not list(folder.parent.glob("*.h5ad"))
        pd.DataFrame({"gene": ["g1"], "group": ["A"], "pvalue": [0.2], "padj": [0.2],
                      "logFC": [1.]}).to_csv(output_dir / "mast_results.csv", index=False)

    monkeypatch.setattr(RScriptRunner, "run_script", run_script)
    table = load_skill("sc-de").rank_genes(adata, method="mast", groupby="group", group1="A", group2="B")
    assert table["gene"].tolist() == ["g1"]
