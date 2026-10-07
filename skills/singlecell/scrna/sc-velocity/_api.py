"""scVelo analysis and output objects without CLI process cleanup."""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
from skills.singlecell._lib import trajectory

__all__ = ["velocity", "run_info", "velocity_diagnostics", "velocity_summary",
           "velocity_cells_table", "top_velocity_genes", "stream_figure"]
_RUN_KEY = "omicsclaw_sc_velocity_run"


def velocity(adata, *, mode: str = "stochastic", n_jobs: int = 4, random_state: int = 0):
    """Compute scVelo velocity in place, including its gene filtering.

    Both spliced and unspliced count layers are required. The shared method
    filters/normalizes expression, explicitly constructs seeded neighbors,
    computes moments, velocity and its graph, plus latent time in
    dynamical mode. Fewer than five cells or genes, graph failures and
    latent-time failures raise errors; no placeholder outputs are created.
    Gene filtering modifies every aligned matrix. A failed call can leave
    partial preprocessing, so retry from a fresh input copy.

    :param mode: stochastic (default), steady_state or dynamical.
    :param n_jobs: Dynamics worker budget, default 4; the shared small-data
        branch uses one worker. Graph workers follow scVelo's own settings.
    :param random_state: Neighbor seed, default 0.
    :returns: The same AnnData. Inspect velocity_diagnostics before interpretation.
    :raises ValueError: Layers, mode, worker budget or input dimensions are invalid.
    :raises RuntimeError: Velocity graph or dynamical latent-time computation fails.
    :raises ImportError: scvelo is unavailable.
    """
    adata.uns.pop(_RUN_KEY, None)
    if not {"spliced", "unspliced"} <= set(adata.layers):
        raise ValueError("velocity requires spliced and unspliced count layers")
    if mode not in {"stochastic", "steady_state", "dynamical"} or n_jobs < 1:
        raise ValueError("invalid velocity mode or n_jobs")
    import scvelo  # noqa: F401
    result = trajectory.run_velocity_analysis(adata, mode=mode, n_jobs=n_jobs,
                                             random_state=random_state, strict=True)
    if result is None:
        raise RuntimeError("scVelo did not return a velocity result")
    adata.uns[_RUN_KEY] = json.dumps({"mode": mode, "method": f"scvelo_{mode}",
                                     "n_jobs": n_jobs, "random_state": random_state,
                                     "placeholder_fallback_used": False,
                                     "fit_validation_performed": False})
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read the completed run's mode, seed and placeholder policy; empty after failure.

    Completion does not establish biological fit validity. keep=False removes
    the record from uns.
    """
    value = adata.uns.get(_RUN_KEY, "{}") if keep else adata.uns.pop(_RUN_KEY, "{}")
    return json.loads(value)


def velocity_diagnostics(adata) -> dict:
    """Return zero/NaN and expressed-velocity-gene checks, not fit validation.

    The API rejects placeholder fallbacks. For objects without a completed
    API run record, placeholder_fallback_used is unknown (None). These
    numerical checks do not establish biological fit validity.
    """
    checks = {"placeholder_fallback_used": run_info(adata).get("placeholder_fallback_used"),
              "fit_validation_performed": False}
    if "velocity" not in adata.layers:
        return {**checks, "degenerate": True, "all_zero_velocity": True, "nan_fraction": 1.0,
                "n_velocity_genes": 0, "n_total_genes": int(adata.n_vars),
                "suggested_actions": ["Velocity layer was not created — check scVelo logs above for errors",
                                      "Ensure spliced/unspliced layers have sufficient signal"]}
    values = adata.layers["velocity"]
    values = np.asarray(values.toarray() if hasattr(values, "toarray") else values, dtype=np.float32)
    all_zero = bool(np.allclose(values, 0))
    nan_frac = float(np.isnan(values).sum()) / max(values.size, 1)
    genes = int((np.abs(values).sum(axis=0) > 0).sum())
    result = {**checks, "all_zero_velocity": all_zero, "nan_fraction": round(nan_frac, 4),
              "n_velocity_genes": genes, "n_total_genes": int(adata.n_vars),
              "degenerate": all_zero or nan_frac > 0.5 or genes == 0}
    if result["degenerate"]:
        result["suggested_actions"] = [
            "Check that spliced/unspliced layers contain real count data (not all zeros)",
            "Try dynamical mode: --method scvelo_dynamical",
            "Ensure input has been preprocessed: sc-preprocessing -> sc-velocity-prep -> sc-velocity",
            "Re-run sc-velocity-prep with real BAM/loom data instead of synthetic layers",
        ]
    return result


def velocity_summary(adata) -> pd.DataFrame:
    """Return method, dimensions and latent-time availability as metric/value rows."""
    info = run_info(adata)
    rows = [("method", info["method"]), ("mode", info["mode"]), ("n_cells", adata.n_obs),
            ("n_genes", adata.n_vars), ("has_latent_time", "latent_time" in adata.obs)]
    if "latent_time" in adata.obs:
        rows += [("latent_time_min", float(adata.obs["latent_time"].min())),
                 ("latent_time_max", float(adata.obs["latent_time"].max()))]
    return pd.DataFrame(rows, columns=["metric", "value"])


def velocity_cells_table(adata) -> pd.DataFrame:
    """Return cell_id, optional UMAP coordinates, velocity magnitude and latent time."""
    frame = pd.DataFrame(index=adata.obs_names.astype(str))
    if "X_umap" in adata.obsm:
        frame["umap_1"] = np.asarray(adata.obsm["X_umap"])[:, 0]
        frame["umap_2"] = np.asarray(adata.obsm["X_umap"])[:, 1]
    if "velocity" in adata.layers:
        values = adata.layers["velocity"]
        values = np.asarray(values.toarray() if hasattr(values, "toarray") else values, dtype=np.float32)
        frame["velocity_magnitude"] = np.linalg.norm(values, axis=1)
    if "latent_time" in adata.obs:
        frame["latent_time"] = adata.obs["latent_time"].astype(float).to_numpy()
    return frame.reset_index(names="cell_id")


def top_velocity_genes(adata, *, n_top: int = 40) -> pd.DataFrame:
    """Rank genes by mean absolute velocity and retain their signed mean."""
    if "velocity" not in adata.layers:
        return pd.DataFrame(columns=["gene", "mean_abs_velocity", "mean_velocity"])
    values = adata.layers["velocity"]
    values = np.asarray(values.toarray() if hasattr(values, "toarray") else values)
    frame = pd.DataFrame({"gene": adata.var_names.astype(str), "mean_abs_velocity": np.mean(np.abs(values), axis=0),
                          "mean_velocity": np.mean(values, axis=0)})
    return frame.sort_values("mean_abs_velocity", ascending=False).head(n_top).reset_index(drop=True)


def stream_figure(adata, *, basis: str = "umap"):
    """Return a scVelo stream Figure; X_<basis> must already be present."""
    import scvelo as scv
    from matplotlib import pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 5))
    scv.pl.velocity_embedding_stream(adata, basis=basis, ax=ax, show=False)
    return fig
