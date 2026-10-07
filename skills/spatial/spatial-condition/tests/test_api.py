"""Replicate-aware public condition comparison."""

import anndata as ad
import numpy as np
import pytest

from skills._sdk.notebook import load_skill


def counts():
    rng = np.random.default_rng(4)
    data = ad.AnnData(rng.poisson(20, (48, 20)).astype(float))
    data.layers["counts"] = data.X.copy()
    data.obs["sample_id"] = [f"sample_{i % 6}" for i in range(48)]
    data.obs["condition"] = np.where(np.arange(48) % 6 < 3, "control", "treated")
    data.obs["leiden"] = ["0"] * 48
    return data


def test_wilcoxon_uses_six_samples_not_48_spots():
    library = load_skill("spatial-condition")
    data = counts()
    assert library.compare_conditions(data, method="wilcoxon") is data
    table = library.results(data)
    assert len(table) == 20
    assert table["n_samples_reference"].eq(3).all()
    assert table["n_samples_other"].eq(3).all()
    assert library.run_info(data)["n_samples"] == 6
    assert library.run_info(data, keep=False)["method"] == "wilcoxon"
    assert library.run_info(data) == {}


def test_fractional_counts_are_not_rounded_into_false_pseudobulk():
    data = counts()
    data.layers["counts"] += .1
    with pytest.raises(ValueError, match="integer"):
        load_skill("spatial-condition").compare_conditions(data, method="wilcoxon")


def test_ambiguous_sample_design_is_rejected():
    data = counts()
    data.obs.loc[data.obs_names[0], "condition"] = "treated"
    with pytest.raises(ValueError, match="exactly one condition"):
        load_skill("spatial-condition").compare_conditions(data, method="wilcoxon")
