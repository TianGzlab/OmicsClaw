"""Potency is a complexity proxy with an explicit expression-layer choice."""

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

from skills._sdk.notebook import load_skill


def test_cytotrace_selects_counts_without_changing_x():
    counts = np.tril(np.ones((6, 6)))
    adata = ad.AnnData(np.ones((6, 6)), obs=pd.DataFrame(index=[f"c{x}" for x in range(6)]))
    adata.layers["counts"] = sparse.csr_matrix(counts)
    adata.uns["neighbors"] = {"connectivities_key": "connectivities"}
    adata.obsp["connectivities"] = sparse.eye(6, format="csr")
    api = load_skill("sc-cytotrace")
    result = api.cytotrace(adata, layer="counts", n_neighbors=2)
    assert result is adata
    np.testing.assert_array_equal(result.X, np.ones((6, 6)))
    np.testing.assert_array_equal(result.obs["cytotrace_gene_count"], np.arange(1, 7))
    np.testing.assert_allclose(result.obs["cytotrace_score"], np.linspace(0, 1, 6))
    assert api.potency_table(result).index.equals(adata.obs_names)
    assert api.potency_composition(result)["n_cells"].sum() == 6
    assert api.run_info(result)["method"] == "cytotrace_simple"
