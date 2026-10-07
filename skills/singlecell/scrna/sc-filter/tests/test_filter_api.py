"""Filtering preserves input and records removals."""

import anndata as ad
import numpy as np
import pandas as pd

from skills._sdk.notebook import load_skill


def _counts():
    return ad.AnnData(
        np.array([[2, 0, 1], [1, 2, 0], [3, 1, 0], [2, 2, 0]], dtype=float),
        obs=pd.DataFrame({"outlier": [True, False, False, False],
                          "predicted_doublet": [False, True, False, False]},
                         index=["a", "b", "c", "d"]),
        var=pd.DataFrame(index=["G1", "G2", "G3"]),
    )


def test_outlier_flags_are_reported_without_removing_flagged_cells():
    api = load_skill("sc-filter")
    before = _counts()
    after = api.filter_cells(before, min_genes=1, min_cells=2, max_mt_percent=None)
    assert list(after.obs_names) == ["a", "c", "d"]
    assert list(after.var_names) == ["G1", "G2"]
    stats = api.run_info(after)["summary"]["filter_stats"]
    assert stats["outliers_flagged"] == 1
    assert "outliers_removed" not in stats
    assert stats["doublets_removed"] == 1
    assert before.shape == (4, 3)
    assert "counts" not in before.layers
    assert not before.uns
    state = api.filter_state_table(before, after)
    assert list(state["state"]) == ["Retained", "Removed", "Retained", "Retained"]
    assert api.filter_stats_table(after).set_index("metric").loc["outliers_flagged", "value"] == 1
    assert api.filter_summary(after).set_index("metric").loc["n_cells_after", "value"] == 3
    assert api.run_info(after, keep=False)
    assert api.run_info(after) == {}


def test_doublet_removal_is_optional_and_presets_are_copied():
    api = load_skill("sc-filter")
    before = _counts()
    after = api.filter_cells(before, min_genes=1, min_cells=1, max_mt_percent=None, remove_doublets=False)
    assert after.shape == before.shape
    presets = api.tissue_presets()
    presets["pbmc"]["min_genes"] = -1
    assert api.tissue_presets()["pbmc"]["min_genes"] == 200
