"""Canonical counts and source diagnostics through the public library."""

import anndata as ad
import numpy as np
import pandas as pd
import pytest

from skills._sdk.notebook import load_skill


def test_standardize_uses_counts_and_preserves_the_input():
    api = load_skill("sc-standardize-input")
    counts = np.array([[3, 1], [2, 0]], dtype=np.int32)
    original = ad.AnnData(
        np.log1p(counts), var=pd.DataFrame({"gene_symbols": ["MT-CO1", "RPS3"]},
                                          index=["ENSG1", "ENSG2"]),
    )
    original.layers["counts"] = counts.copy()
    result = api.standardize(original)
    assert result is not original
    np.testing.assert_array_equal(result.X, counts)
    np.testing.assert_array_equal(result.raw.X, counts)
    np.testing.assert_array_equal(original.X, np.log1p(counts))
    assert result.var_names.tolist() == ["MT-CO1", "RPS3"]
    info = api.run_info(result)
    assert info["expression_source"] == "layers.counts"
    assert info["species"] == "human"
    assert api.infer_species(result) == "human"
    assert api.run_info(result, keep=False) == info
    assert api.run_info(result) == {}
