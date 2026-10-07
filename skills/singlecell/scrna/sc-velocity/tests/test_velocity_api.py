"""Velocity requires splicing counts and returns diagnostics without exiting."""

import anndata as ad
import numpy as np
import pytest
from skills._sdk.notebook import load_skill


def test_velocity_rejects_missing_splicing_layers():
    with pytest.raises(ValueError, match="spliced.*unspliced"):
        load_skill("sc-velocity").velocity(ad.AnnData(np.ones((10, 10))))


def test_velocity_runs_on_kinetic_simulation():
    scv = pytest.importorskip("scvelo")
    adata = scv.datasets.simulation(n_obs=80, n_vars=20, random_seed=0)
    api = load_skill("sc-velocity")
    result = api.velocity(adata, mode="stochastic", n_jobs=1, random_state=8)
    assert result is adata
    assert result.n_obs == 80
    assert "velocity" in result.layers
    assert np.isfinite(result.layers["velocity"]).all()
    assert api.velocity_diagnostics(result)["n_velocity_genes"] > 0
    assert result.uns["neighbors"]["params"]["random_state"] == 8
    assert len(api.velocity_cells_table(result)) == 80
    assert len(api.top_velocity_genes(result, n_top=3)) == 3
