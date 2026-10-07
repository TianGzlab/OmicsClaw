"""Velocity requires splicing counts and returns diagnostics without exiting."""

import anndata as ad
import numpy as np
import pytest
from skills._sdk.notebook import load_skill


def test_velocity_rejects_missing_splicing_layers():
    with pytest.raises(ValueError, match="spliced.*unspliced"):
        load_skill("sc-velocity").velocity(ad.AnnData(np.ones((10, 10))))


@pytest.mark.parametrize("shape", [(4, 6), (6, 4)])
def test_velocity_rejects_tiny_input_without_fabricating_outputs(shape):
    adata = ad.AnnData(np.ones(shape))
    adata.layers["spliced"] = np.ones(adata.shape) * 3
    adata.layers["unspliced"] = np.ones(adata.shape)
    api = load_skill("sc-velocity")
    with pytest.raises(ValueError, match="at least five cells and five genes"):
        api.velocity(adata, mode="dynamical", n_jobs=1)
    assert "velocity" not in adata.layers
    assert "velocity_graph" not in adata.uns
    assert "latent_time" not in adata.obs
    assert api.run_info(adata) == {}


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
    assert api.run_info(result)["placeholder_fallback_used"] is False
    assert api.velocity_diagnostics(result)["fit_validation_performed"] is False
    assert len(api.velocity_cells_table(result)) == 80
    assert len(api.top_velocity_genes(result, n_top=3)) == 3


def test_velocity_graph_failure_raises_instead_of_returning_identity(monkeypatch):
    scv = pytest.importorskip("scvelo")
    adata = scv.datasets.simulation(n_obs=80, n_vars=20, random_seed=0)

    def broken_graph(*args, **kwargs):
        raise ValueError("controlled graph failure")

    api = load_skill("sc-velocity")
    api.velocity(adata, n_jobs=1)
    assert api.run_info(adata)["method"] == "scvelo_stochastic"
    del adata.uns["velocity_graph"]
    monkeypatch.setattr(scv.tl, "velocity_graph", broken_graph)
    with pytest.raises(RuntimeError, match="velocity graph computation failed") as error:
        api.velocity(adata, n_jobs=1)
    assert isinstance(error.value.__cause__, ValueError)
    assert "velocity_graph" not in adata.uns
    assert api.run_info(adata) == {}


def test_latent_time_failure_raises_instead_of_returning_uniform_sequence(monkeypatch):
    scv = pytest.importorskip("scvelo")
    adata = scv.datasets.simulation(n_obs=120, n_vars=40, random_seed=0)

    def broken_latent_time(*args, **kwargs):
        raise ValueError("controlled latent-time failure")

    monkeypatch.setattr(scv.tl, "latent_time", broken_latent_time)
    api = load_skill("sc-velocity")
    with pytest.raises(RuntimeError, match="latent-time computation failed") as error:
        api.velocity(adata, mode="dynamical", n_jobs=1)
    assert isinstance(error.value.__cause__, ValueError)
    assert "latent_time" not in adata.obs
    assert api.run_info(adata) == {}
