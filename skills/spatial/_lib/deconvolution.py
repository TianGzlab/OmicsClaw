"""Spatial deconvolution core methods.

Estimates cell type proportions per spatial spot using a reference
scRNA-seq dataset.

Usage::

    from skills.spatial._lib.deconvolution import METHOD_DISPATCH, SUPPORTED_METHODS, DEFAULT_METHOD
"""

from __future__ import annotations

import gc
import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import sparse

from omicsclaw.common.runtime_env import ensure_runtime_cache_dirs

ensure_runtime_cache_dirs("omicsclaw")

import scanpy as sc

from .adata_utils import get_spatial_key, require_spatial_coords
from .dependency_manager import require

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Method registry
# ---------------------------------------------------------------------------


@dataclass
class MethodConfig:
    name: str
    description: str
    requires_reference: bool = True
    dependencies: tuple[str, ...] = ()
    supports_gpu: bool = False


METHOD_REGISTRY: dict[str, MethodConfig] = {
    "flashdeconv": MethodConfig(
        name="flashdeconv",
        description="Ultra-fast O(N) sketching deconvolution (CPU, no GPU needed)",
        dependencies=("flashdeconv",),
    ),
    "cell2location": MethodConfig(
        name="cell2location",
        description="Bayesian deep learning with spatial priors",
        dependencies=("scvi", "cell2location", "torch"),
        supports_gpu=True,
    ),
    "rctd": MethodConfig(
        name="rctd",
        description="Robust Cell Type Decomposition (R / spacexr)",
        dependencies=(),
    ),
    "destvi": MethodConfig(
        name="destvi",
        description="Multi-resolution VAE deconvolution (scvi-tools DestVI)",
        dependencies=("scvi", "torch"),
        supports_gpu=True,
    ),
    "stereoscope": MethodConfig(
        name="stereoscope",
        description="Two-stage probabilistic deconvolution (scvi-tools Stereoscope)",
        dependencies=("scvi", "torch"),
        supports_gpu=True,
    ),
    "tangram": MethodConfig(
        name="tangram",
        description="Deep learning cell-to-spot mapping (tangram-sc)",
        dependencies=("tangram",),
        supports_gpu=True,
    ),
    "spotlight": MethodConfig(
        name="spotlight",
        description="NMF-based deconvolution (R / SPOTlight)",
        dependencies=(),
    ),
    "card": MethodConfig(
        name="card",
        description="Conditional AutoRegressive Deconvolution (R / CARD)",
        dependencies=(),
    ),
}

SUPPORTED_METHODS = tuple(METHOD_REGISTRY.keys())
DEFAULT_METHOD = "cell2location"

COUNT_BASED_METHODS = ("cell2location", "rctd", "destvi", "stereoscope", "card")
NONNEGATIVE_EXPRESSION_METHODS = ("tangram", "spotlight")
FLEXIBLE_INPUT_METHODS = ("flashdeconv",)
VALID_RCTD_MODES = ("full", "doublet", "multi")
VALID_TANGRAM_MODES = ("auto", "cells", "clusters")
VALID_SPOTLIGHT_MODELS = ("ns", "std")

METHOD_PARAM_DEFAULTS = {
    "flashdeconv": {
        "sketch_dim": 512,
        "lambda_spatial": 5000.0,
        "n_hvg": 2000,
        "n_markers_per_type": 50,
    },
    "cell2location": {
        "n_epochs": 30000,
        "n_cells_per_spot": 30,
        "detection_alpha": 20.0,
    },
    "rctd": {
        "mode": "full",
    },
    "destvi": {
        "n_epochs": 2500,
        "condscvi_epochs": 300,
        "n_hidden": 128,
        "n_latent": 5,
        "n_layers": 2,
        "dropout_rate": 0.05,
        "vamp_prior_p": 15,
    },
    "stereoscope": {
        "rna_epochs": 400,
        "spatial_epochs": 400,
        "learning_rate": 0.01,
        "batch_size": 128,
    },
    "tangram": {
        "n_epochs": 1000,
        "learning_rate": 0.1,
        "mode": "auto",
    },
    "spotlight": {
        "n_top": 50,
        "nmf_model": "ns",
        "min_prop": 0.01,
        "scale": True,
        "weight_id": "weight",
    },
    "card": {
        "sample_key": None,
        "min_count_gene": 100,
        "min_count_spot": 5,
        "imputation": False,
        "num_grids": 2000,
        "ineibor": 10,
    },
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _to_dense(X) -> np.ndarray:
    if sparse.issparse(X):
        return np.asarray(X.toarray())
    return np.asarray(X)


def _restore_counts(adata, method_name: str = "Unknown") -> "sc.AnnData":
    """Return AnnData with raw integer counts in .X (priority: counts layer > raw > X)."""
    if "counts" in adata.layers:
        logger.info(f"[{method_name}] Using raw counts from adata.layers['counts']")
        result = adata.copy()
        result.X = adata.layers["counts"].copy()
        return result
    if adata.raw is not None:
        logger.info(f"[{method_name}] Using raw counts from adata.raw.X")
        result = adata.raw.to_adata()
        for key in adata.obsm:
            result.obsm[key] = adata.obsm[key].copy()
        return result
    
    logger.warning(
        f"[{method_name}] No 'counts' layer or .raw found! "
        "Falling back to .X. WARNING: Count-based models expect raw counts."
    )
    return adata.copy()


def _load_reference(reference_path: str, cell_type_key: str) -> "sc.AnnData":
    logger.info("Loading reference: %s", reference_path)
    adata_ref = sc.read_h5ad(reference_path)
    if cell_type_key not in adata_ref.obs.columns:
        cat_cols = [
            c for c in adata_ref.obs.columns
            if adata_ref.obs[c].dtype.name in ("object", "category")
        ]
        raise ValueError(
            f"Cell type key '{cell_type_key}' not found in reference obs.\n"
            f"Available categorical columns: {cat_cols}"
        )
    return adata_ref


def _common_genes(adata_sp, adata_ref) -> list[str]:
    common = list(set(adata_sp.var_names) & set(adata_ref.var_names))
    if len(common) < 50:
        raise ValueError(
            f"Only {len(common)} genes shared between spatial and reference data. "
            "Minimum 50 required. Check that both use the same gene ID format."
        )
    logger.info("Common genes: %d", len(common))
    return common


def _get_accelerator(prefer_gpu: bool = True) -> str:
    """Return 'gpu' if CUDA is available and preferred, else 'cpu'."""
    if not prefer_gpu:
        return "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            logger.info("GPU detected: %s", torch.cuda.get_device_name(0))
            return "gpu"
    except ImportError:
        pass
    return "cpu"


def _prefixed_params(prefix: str, **values) -> dict[str, Any]:
    """Return CLI-style parameter names for reportable effective params."""
    result: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        result[f"{prefix}_{key}"] = value
    return result


def _normalize_rctd_mode(mode: str) -> str:
    """Keep backward compatibility for legacy `single` while using public modes."""
    if mode == "single":
        logger.warning(
            "RCTD mode 'single' is deprecated in OmicsClaw; mapping it to 'doublet'. "
            "Public spacexr documentation uses 'doublet', 'multi', or 'full'."
        )
        return "doublet"
    return mode


def _deconv_stats(
    prop_df: pd.DataFrame,
    common_genes: list[str],
    method: str,
    device: str = "cpu",
    effective_params: dict[str, Any] | None = None,
    **extra,
) -> dict:
    stats: dict = {
        "method": method,
        "device": device,
        "n_spots": len(prop_df),
        "n_cell_types": prop_df.shape[1],
        "cell_types": list(prop_df.columns),
        "n_common_genes": len(common_genes),
        "mean_proportions": prop_df.mean().to_dict(),
        "dominant_types": prop_df.idxmax(axis=1).value_counts().to_dict(),
    }
    stats.update(extra)
    if effective_params:
        stats["effective_params"] = effective_params
    return stats


# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------


def deconvolve_flashdeconv(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    sketch_dim: int = METHOD_PARAM_DEFAULTS["flashdeconv"]["sketch_dim"],
    lambda_spatial: float | str = METHOD_PARAM_DEFAULTS["flashdeconv"]["lambda_spatial"],
    n_hvg: int = METHOD_PARAM_DEFAULTS["flashdeconv"]["n_hvg"],
    n_markers_per_type: int = METHOD_PARAM_DEFAULTS["flashdeconv"]["n_markers_per_type"],
) -> tuple[pd.DataFrame, dict]:
    require("flashdeconv", feature="FlashDeconv deconvolution")
    import flashdeconv as fd

    adata_ref = _load_reference(reference_path, cell_type_key)
    
    # FlashDeconv format is flexible (TBD), do not force raw counts
    adata_sp = adata.copy()
    adata_ref = adata_ref.copy()

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref_sub = adata_ref[:, common].copy()

    fd.tl.deconvolve(
        adata_sp, adata_ref_sub, cell_type_key=cell_type_key,
        sketch_dim=sketch_dim, lambda_spatial=lambda_spatial,
        n_hvg=n_hvg, n_markers_per_type=n_markers_per_type,
    )

    if "flashdeconv" not in adata_sp.obsm:
        raise RuntimeError("FlashDeconv produced no output in adata.obsm['flashdeconv']")

    proportions = adata_sp.obsm["flashdeconv"]
    cell_types = list(adata_ref.obs[cell_type_key].astype("category").cat.categories)
    if not isinstance(proportions, pd.DataFrame):
        proportions = pd.DataFrame(proportions, index=adata.obs_names, columns=cell_types)
    else:
        proportions.index = adata.obs_names

    effective_params = _prefixed_params(
        "flashdeconv",
        sketch_dim=sketch_dim,
        lambda_spatial=lambda_spatial,
        n_hvg=n_hvg,
        n_markers_per_type=n_markers_per_type,
    )
    return proportions, _deconv_stats(
        proportions,
        common,
        "flashdeconv",
        sketch_dim=sketch_dim,
        lambda_spatial=lambda_spatial,
        n_hvg=n_hvg,
        n_markers_per_type=n_markers_per_type,
        effective_params=effective_params,
    )


def deconvolve_cell2location(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    n_epochs: int = METHOD_PARAM_DEFAULTS["cell2location"]["n_epochs"],
    n_cells_per_spot: int = METHOD_PARAM_DEFAULTS["cell2location"]["n_cells_per_spot"],
    use_gpu: bool = True,
    detection_alpha: float = METHOD_PARAM_DEFAULTS["cell2location"]["detection_alpha"],
) -> tuple[pd.DataFrame, dict]:
    require("scvi", feature="Cell2Location deconvolution")
    require("cell2location", feature="Cell2Location deconvolution")

    import cell2location
    from cell2location.models import RegressionModel

    logger.info("Initializing Cell2Location pipeline (detection_alpha=%.1f)...", detection_alpha)
    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata, "cell2location")
    adata_ref = _restore_counts(adata_ref, "cell2location")

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref_sub = adata_ref[:, common].copy()

    if "counts" not in adata_ref_sub.layers:
        adata_ref_sub.layers["counts"] = adata_ref_sub.X.copy()
    if "counts" not in adata_sp.layers:
        adata_sp.layers["counts"] = adata_sp.X.copy()

    accelerator = _get_accelerator(use_gpu)
    logger.info("Cell2Location accelerator: %s", accelerator)

    # 1. Reference Signature Model
    try:
        RegressionModel.setup_anndata(adata_ref_sub, layer="counts", labels_key=cell_type_key)
    except Exception as e:
        raise RuntimeError(f"Failed to setup AnnData for RegressionModel: {e}")

    ref_model = RegressionModel(adata_ref_sub)
    
    # Adaptive batch size to prevent OOM
    batch_size = 2500 if adata_ref_sub.n_obs > 10000 else None
    ref_train_kwargs = {"max_epochs": min(250, n_epochs // 10), "accelerator": accelerator}
    if batch_size:
        ref_train_kwargs["batch_size"] = batch_size
        
    logger.info("Training reference regression model...")
    ref_model.train(**ref_train_kwargs)

    logger.info("Exporting reference posterior...")
    inf_aver = ref_model.export_posterior(adata_ref_sub, sample_kwargs={"num_samples": 1000})

    if "means_per_cluster_mu_fg" in inf_aver.varm:
        mat = inf_aver.varm["means_per_cluster_mu_fg"]
        inf_aver_df = (
            mat if isinstance(mat, pd.DataFrame)
            else pd.DataFrame(mat, index=inf_aver.var_names, columns=inf_aver.uns["mod"]["factor_names"])
        )
    else:
        inf_aver_df = inf_aver.var.filter(like="means_per_cluster_mu_fg", axis=1)

    if inf_aver_df.shape[1] == 0:
        raise ValueError("Cell2location reference export returned an empty cell state matrix. Check cell type labels.")

    inf_aver_df = inf_aver_df.clip(lower=1e-6).loc[adata_sp.var_names]

    # 2. Spatial Mapping Model
    try:
        cell2location.models.Cell2location.setup_anndata(adata_sp, layer="counts")
    except Exception as e:
        raise RuntimeError(f"Failed to setup spatial AnnData for Cell2location: {e}")

    model = cell2location.models.Cell2location(
        adata_sp,
        cell_state_df=inf_aver_df,
        N_cells_per_location=n_cells_per_spot,
        detection_alpha=detection_alpha,
    )
    
    sp_batch_size = None if adata_sp.n_obs < 15000 else min(adata_sp.n_obs // 10, 2048)
    sp_train_kwargs = {"max_epochs": n_epochs, "accelerator": accelerator}
    if sp_batch_size:
        sp_train_kwargs["batch_size"] = sp_batch_size
        
    logger.info("Training spatial mapping model (epochs=%d)...", n_epochs)
    model.train(**sp_train_kwargs)

    logger.info("Exporting spatial posterior...")
    adata_sp = model.export_posterior(adata_sp)
    
    if "q05_cell_abundance_w_sf" not in adata_sp.obsm:
        raise KeyError("'q05_cell_abundance_w_sf' not found in spatial obsm. Model export failed.")
        
    q05 = adata_sp.obsm["q05_cell_abundance_w_sf"]

    if isinstance(q05, pd.DataFrame):
        cols = q05.columns.str.replace(r"^q05cell_abundance_w_sf_means_per_cluster_mu_fg_", "", regex=True)
        prop_df = q05.copy()
        prop_df.columns = cols
    else:
        cell_types = list(inf_aver_df.columns)
        prop_df = pd.DataFrame(q05, index=adata.obs_names, columns=cell_types)

    # Convert abundances strictly to proportions summing to 1
    # Adding safe division to avoid NaNs if abundant spots are 0
    row_sums = prop_df.sum(axis=1).replace(0, 1e-10)
    prop_df = prop_df.div(row_sums, axis=0)

    effective_params = _prefixed_params(
        "cell2location",
        n_epochs=n_epochs,
        n_cells_per_spot=n_cells_per_spot,
        detection_alpha=detection_alpha,
        use_gpu=accelerator == "gpu",
    )
    return prop_df, _deconv_stats(
        prop_df,
        common,
        "cell2location",
        device=accelerator,
        n_epochs=n_epochs,
        n_cells_per_spot=n_cells_per_spot,
        detection_alpha=detection_alpha,
        effective_params=effective_params,
    )


def deconvolve_rctd(
    adata,
    *,
    reference_path: str,
    cell_type_key: str = "cell_type",
    mode: str = METHOD_PARAM_DEFAULTS["rctd"]["mode"],
) -> tuple[pd.DataFrame, dict]:
    import tempfile
    from pathlib import Path
    from omicsclaw.core.dependency_manager import validate_r_environment
    from omicsclaw.core.r_script_runner import RScriptRunner
    from omicsclaw.core.r_utils import read_r_result_csv

    validate_r_environment(required_r_packages=["spacexr"])

    mode = _normalize_rctd_mode(mode)
    logger.info("Initializing RCTD pipeline (mode=%s)...", mode)
    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata, "rctd")
    adata_ref_raw = _restore_counts(adata_ref, "rctd")

    # RCTD strictly requires >= 25 cells per reference cell type to build the profile
    type_counts = adata_ref_raw.obs[cell_type_key].value_counts()
    min_cells = 25
    dropped_types = type_counts[type_counts < min_cells].index.tolist()
    if dropped_types:
        logger.warning(
            "RCTD requires >= %d cells per cell type. Dropping %d sparse cell types: %s",
            min_cells, len(dropped_types), dropped_types
        )
        mask = ~adata_ref_raw.obs[cell_type_key].isin(dropped_types)
        adata_ref_raw = adata_ref_raw[mask].copy()
        
    if adata_ref_raw.n_obs == 0:
        raise ValueError("RCTD failed: No cell types left in the reference after filtering for minimum cell count.")

    # Filter out empty spots / cells which will crash colSums in R
    sp_sums = np.array(adata_sp.X.sum(axis=1)).flatten()
    if np.any(sp_sums == 0):
        n_empty = int(np.sum(sp_sums == 0))
        logger.warning("Found %d empty spatial spots (0 total counts). Filtering out to prevent R crash...", n_empty)
        adata_sp = adata_sp[sp_sums > 0].copy()

    common = _common_genes(adata_sp, adata_ref_raw)
    adata_sp = adata_sp[:, common].copy()
    adata_ref_raw = adata_ref_raw[:, common].copy()

    spatial_key = require_spatial_coords(adata_sp)
    coords = adata_sp.obsm[spatial_key][:, :2]

    scripts_dir = Path(__file__).resolve().parents[3] / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_rctd_") as tmpdir:
        tmpdir = Path(tmpdir)
        
        logger.info("Exporting matrices to temporary RCTD sandbox...")
        
        # Round before int casting to prevent float truncation of perfectly valid pre-normalized sets
        sp_mat = np.round(_to_dense(adata_sp.X)).T.astype(np.int32)
        sp_counts = pd.DataFrame(sp_mat, index=adata_sp.var_names, columns=adata_sp.obs_names)
        sp_counts.to_csv(tmpdir / "spatial_counts.csv")

        # Write spatial coordinates
        coords_df = pd.DataFrame(coords, index=adata_sp.obs_names, columns=["x", "y"])
        coords_df.to_csv(tmpdir / "spatial_coords.csv")

        # Write reference counts (genes x cells)
        ref_mat = np.round(_to_dense(adata_ref_raw.X)).T.astype(np.int32)
        ref_counts = pd.DataFrame(ref_mat, index=adata_ref_raw.var_names, columns=adata_ref_raw.obs_names)
        ref_counts.to_csv(tmpdir / "ref_counts.csv")

        # Write reference cell types
        ref_types = pd.DataFrame({
            "cell": adata_ref_raw.obs_names,
            "cell_type": adata_ref_raw.obs[cell_type_key].astype(str).values,
        })
        ref_types.to_csv(tmpdir / "ref_celltypes.csv", index=False)

        output_dir = tmpdir / "output"
        output_dir.mkdir()

        logger.info("Triggering background RScriptRunner for RCTD...")
        runner.run_script(
            "sp_rctd.R",
            args=[
                str(tmpdir / "spatial_counts.csv"), str(tmpdir / "spatial_coords.csv"),
                str(tmpdir / "ref_counts.csv"), str(tmpdir / "ref_celltypes.csv"),
                str(output_dir), mode,
            ],
            expected_outputs=["rctd_proportions.csv"],
            output_dir=output_dir,
        )

        prop_df = read_r_result_csv(output_dir / "rctd_proportions.csv")
        
        # Ensure the spatial spots dropped due to 0 counts get 0s in the final proportion df
        if len(prop_df) < adata.n_obs:
            missing = list(set(adata.obs_names) - set(prop_df.index))
            empty_df = pd.DataFrame(0.0, index=missing, columns=prop_df.columns)
            prop_df = pd.concat([prop_df, empty_df]).loc[adata.obs_names]

    effective_params = _prefixed_params("rctd", mode=mode)
    return prop_df, _deconv_stats(
        prop_df,
        common,
        "rctd",
        rctd_mode=mode,
        effective_params=effective_params,
    )


def deconvolve_destvi(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    n_epochs: int = METHOD_PARAM_DEFAULTS["destvi"]["n_epochs"],
    condscvi_epochs: int = METHOD_PARAM_DEFAULTS["destvi"]["condscvi_epochs"],
    n_hidden: int = METHOD_PARAM_DEFAULTS["destvi"]["n_hidden"],
    n_latent: int = METHOD_PARAM_DEFAULTS["destvi"]["n_latent"],
    n_layers: int = METHOD_PARAM_DEFAULTS["destvi"]["n_layers"],
    dropout_rate: float = METHOD_PARAM_DEFAULTS["destvi"]["dropout_rate"],
    vamp_prior_p: int = METHOD_PARAM_DEFAULTS["destvi"]["vamp_prior_p"],
    use_gpu: bool = True,
) -> tuple[pd.DataFrame, dict]:
    require("scvi", feature="DestVI deconvolution")

    import scvi
    from scvi.model import CondSCVI, DestVI

    logger.info("Initializing DestVI pipeline...")
    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata, "destvi")
    adata_ref = _restore_counts(adata_ref, "destvi")

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref = adata_ref[:, common].copy()

    # CondSCVI requires labels to be strictly categorical
    adata_ref.obs[cell_type_key] = adata_ref.obs[cell_type_key].astype("category")

    accelerator = _get_accelerator(use_gpu)

    # 1. Train Conditional scVI on Reference
    sc_layer = "counts" if "counts" in adata_ref.layers else None
    try:
        CondSCVI.setup_anndata(adata_ref, labels_key=cell_type_key, **({"layer": sc_layer} if sc_layer else {}))
    except Exception as e:
        raise RuntimeError(f"Failed to setup reference AnnData for CondSCVI (Check layer/labels): {e}")

    condscvi_model = CondSCVI(
        adata_ref, n_hidden=n_hidden, n_latent=n_latent, n_layers=n_layers,
        dropout_rate=dropout_rate, weight_obs=False, prior="mog", num_classes_mog=vamp_prior_p,
    )

    logger.info("Training CondSCVI reference model (epochs=%d)...", condscvi_epochs)
    ref_batch_size = 2500 if adata_ref.n_obs > 15000 else None
    c_kwargs = {"max_epochs": condscvi_epochs, "accelerator": accelerator}
    if ref_batch_size:
        c_kwargs["batch_size"] = ref_batch_size
    condscvi_model.train(**c_kwargs)

    # 2. Train DestVI on Spatial
    st_layer = "counts" if "counts" in adata_sp.layers else None
    try:
        DestVI.setup_anndata(adata_sp, **({"layer": st_layer} if st_layer else {}))
    except Exception as e:
        raise RuntimeError(f"Failed to setup spatial AnnData for DestVI: {e}")

    destvi_model = DestVI.from_rna_model(adata_sp, condscvi_model, vamp_prior_p=vamp_prior_p)
    
    logger.info("Training DestVI spatial model (epochs=%d)...", n_epochs)
    sp_batch_size = 2048 if adata_sp.n_obs > 15000 else None
    d_kwargs = {"max_epochs": n_epochs, "accelerator": accelerator}
    if sp_batch_size:
        d_kwargs["batch_size"] = sp_batch_size
    destvi_model.train(**d_kwargs)

    logger.info("Extracting DestVI proportions...")
    prop_df = destvi_model.get_proportions()
    prop_df.index = adata_sp.obs_names

    # Convert abundances strictly to proportions summing to 1 (safety bound)
    row_sums = prop_df.sum(axis=1).replace(0, 1e-10)
    prop_df = prop_df.div(row_sums, axis=0)

    # Free heavy VAE models from RAM/VRAM
    del destvi_model, condscvi_model
    gc.collect()

    effective_params = _prefixed_params(
        "destvi",
        n_epochs=n_epochs,
        condscvi_epochs=condscvi_epochs,
        n_hidden=n_hidden,
        n_latent=n_latent,
        n_layers=n_layers,
        dropout_rate=dropout_rate,
        vamp_prior_p=vamp_prior_p,
        use_gpu=accelerator == "gpu",
    )
    return prop_df, _deconv_stats(
        prop_df,
        common,
        "destvi",
        device=accelerator,
        n_epochs=n_epochs,
        condscvi_epochs=condscvi_epochs,
        prior="mog",
        effective_params=effective_params,
    )


def deconvolve_stereoscope(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    rna_epochs: int = METHOD_PARAM_DEFAULTS["stereoscope"]["rna_epochs"],
    spatial_epochs: int = METHOD_PARAM_DEFAULTS["stereoscope"]["spatial_epochs"],
    learning_rate: float = METHOD_PARAM_DEFAULTS["stereoscope"]["learning_rate"],
    batch_size: int = METHOD_PARAM_DEFAULTS["stereoscope"]["batch_size"],
    use_gpu: bool = True,
) -> tuple[pd.DataFrame, dict]:
    require("scvi", feature="Stereoscope deconvolution")

    from scvi.external import RNAStereoscope, SpatialStereoscope

    logger.info("Initializing Stereoscope pipeline...")
    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata, "stereoscope")
    adata_ref = _restore_counts(adata_ref, "stereoscope")

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref = adata_ref[:, common].copy()

    adata_ref.obs[cell_type_key] = adata_ref.obs[cell_type_key].astype("category")
    cell_types = list(adata_ref.obs[cell_type_key].cat.categories)

    accelerator = _get_accelerator(use_gpu)
    plan_kwargs = {"lr": learning_rate}

    # 1. Train RNA Stereoscope Model
    sc_layer = "counts" if "counts" in adata_ref.layers else None
    try:
        RNAStereoscope.setup_anndata(adata_ref, labels_key=cell_type_key, **({"layer": sc_layer} if sc_layer else {}))
    except Exception as e:
        raise RuntimeError(f"Failed to setup reference AnnData for RNAStereoscope: {e}")

    rna_model = RNAStereoscope(adata_ref)
    
    # Dynamic batch size to accelerate massive datasets (scvi default 128 is too slow for 100k cells)
    ref_batch_size = max(batch_size, 1024) if adata_ref.n_obs > 15000 else batch_size
    train_kwargs: dict = {"max_epochs": rna_epochs, "batch_size": ref_batch_size, "plan_kwargs": plan_kwargs}
    if accelerator:
        train_kwargs["accelerator"] = accelerator
        
    logger.info("Training RNAStereoscope reference model (epochs=%d, batch_size=%d)...", rna_epochs, ref_batch_size)
    rna_model.train(**train_kwargs)

    # 2. Train Spatial Stereoscope Model
    st_layer = "counts" if "counts" in adata_sp.layers else None
    try:
        SpatialStereoscope.setup_anndata(adata_sp, **({"layer": st_layer} if st_layer else {}))
    except Exception as e:
        raise RuntimeError(f"Failed to setup spatial AnnData for SpatialStereoscope: {e}")

    spatial_model = SpatialStereoscope.from_rna_model(adata_sp, rna_model)
    
    sp_batch_size = max(batch_size, 1024) if adata_sp.n_obs > 10000 else batch_size
    train_kwargs["max_epochs"] = spatial_epochs
    train_kwargs["batch_size"] = sp_batch_size
    
    logger.info("Training SpatialStereoscope mapping model (epochs=%d, batch_size=%d)...", spatial_epochs, sp_batch_size)
    spatial_model.train(**train_kwargs)

    logger.info("Extracting Stereoscope proportions...")
    prop_df = pd.DataFrame(spatial_model.get_proportions(), index=adata_sp.obs_names, columns=cell_types)

    # Convert abundances strictly to proportions summing to 1 (safety bound)
    row_sums = prop_df.sum(axis=1).replace(0, 1e-10)
    prop_df = prop_df.div(row_sums, axis=0)

    # Free heavy models from memory
    del spatial_model, rna_model
    gc.collect()

    effective_params = _prefixed_params(
        "stereoscope",
        rna_epochs=rna_epochs,
        spatial_epochs=spatial_epochs,
        learning_rate=learning_rate,
        batch_size=batch_size,
        use_gpu=accelerator == "gpu",
    )
    return prop_df, _deconv_stats(
        prop_df,
        common,
        "stereoscope",
        device=accelerator,
        n_epochs=rna_epochs + spatial_epochs,
        rna_epochs=rna_epochs,
        spatial_epochs=spatial_epochs,
        learning_rate=learning_rate,
        batch_size=batch_size,
        effective_params=effective_params,
    )


def deconvolve_tangram(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    n_epochs: int = METHOD_PARAM_DEFAULTS["tangram"]["n_epochs"],
    learning_rate: float = METHOD_PARAM_DEFAULTS["tangram"]["learning_rate"],
    mode: str = METHOD_PARAM_DEFAULTS["tangram"]["mode"],
    use_gpu: bool = True,
) -> tuple[pd.DataFrame, dict]:
    require("tangram", feature="Tangram deconvolution")
    import tangram as tg

    logger.info("Initializing Tangram pipeline...")
    adata_ref = _load_reference(reference_path, cell_type_key)
    # Tangram expects normalized, non-negative expression data
    adata_sp = adata.copy()

    # Hard validation: Tangram uses cosine similarity internally — negative values are mathematically invalid
    sp_sample = _to_dense(adata_sp.X[:min(1000, adata_sp.n_obs)])
    ref_sample = _to_dense(adata_ref.X[:min(1000, adata_ref.n_obs)])
    if np.any(sp_sample < 0) or np.any(ref_sample < 0):
        raise ValueError(
            "Tangram requires non-negative expression matrices (normalized, NOT z-scored/scaled). "
            "Found negative values in input. Please supply log-normalized or CPM data."
        )

    common = _common_genes(adata_sp, adata_ref)

    # Robust HVG selection with sensible fallback
    if "highly_variable" not in adata_ref.var.columns:
        n_hvg = min(2000, adata_ref.n_vars)
        logger.info("Computing %d highly variable genes for Tangram training...", n_hvg)
        sc.pp.highly_variable_genes(adata_ref, n_top_genes=n_hvg)
    genes = list(adata_ref.var_names[adata_ref.var["highly_variable"]])
    if len(genes) == 0:
        logger.warning("No HVGs found. Falling back to all %d common genes.", len(common))
        genes = common

    spatial_key = get_spatial_key(adata)
    if spatial_key and spatial_key not in adata_sp.obsm:
        adata_sp.obsm[spatial_key] = adata.obsm[spatial_key].copy()

    tg.pp_adatas(adata_ref, adata_sp, genes=genes)
    training_genes = adata_sp.uns.get("training_genes", common)

    # Auto-select mapping mode: 'clusters' averages cells per type → faster & lower memory for large refs
    if mode == "auto":
        if adata_ref.n_obs > 20000:
            mode = "clusters"
            logger.info("Reference has %d cells (>20k). Using 'clusters' mode for memory efficiency.", adata_ref.n_obs)
        else:
            mode = "cells"
            logger.info("Reference has %d cells. Using 'cells' mode for full resolution.", adata_ref.n_obs)

    device = "cuda" if _get_accelerator(use_gpu) == "gpu" else "cpu"
    logger.info("Training Tangram mapping (mode=%s, epochs=%d, device=%s)...", mode, n_epochs, device)

    map_kwargs: dict = {
        "mode": mode,
        "num_epochs": n_epochs,
        "learning_rate": learning_rate,
        "device": device,
    }
    if mode == "clusters":
        map_kwargs["cluster_label"] = cell_type_key

    ad_map = tg.map_cells_to_space(adata_ref, adata_sp, **map_kwargs)
    tg.project_cell_annotations(ad_map, adata_sp, annotation=cell_type_key)

    if "tangram_ct_pred" not in adata_sp.obsm:
        raise RuntimeError("Tangram did not produce 'tangram_ct_pred' in adata.obsm. Mapping may have failed.")

    ct_pred = adata_sp.obsm["tangram_ct_pred"]
    # Strict normalization with zero-division safety
    row_sums = ct_pred.sum(axis=1).replace(0, 1e-10)
    prop_df = ct_pred.div(row_sums, axis=0)

    effective_params = _prefixed_params(
        "tangram",
        n_epochs=n_epochs,
        learning_rate=learning_rate,
        mode=mode,
        use_gpu=device == "cuda",
    )
    return prop_df, _deconv_stats(
        prop_df,
        training_genes,
        "tangram",
        device=device,
        n_epochs=n_epochs,
        learning_rate=learning_rate,
        mode=mode,
        effective_params=effective_params,
    )


def deconvolve_spotlight(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    n_top: int | None = METHOD_PARAM_DEFAULTS["spotlight"]["n_top"],
    nmf_model: str = METHOD_PARAM_DEFAULTS["spotlight"]["nmf_model"],
    min_prop: float = METHOD_PARAM_DEFAULTS["spotlight"]["min_prop"],
    scale: bool = METHOD_PARAM_DEFAULTS["spotlight"]["scale"],
    weight_id: str = METHOD_PARAM_DEFAULTS["spotlight"]["weight_id"],
) -> tuple[pd.DataFrame, dict]:
    import tempfile
    from pathlib import Path
    from omicsclaw.core.dependency_manager import validate_r_environment
    from omicsclaw.core.r_script_runner import RScriptRunner
    from omicsclaw.core.r_utils import read_r_result_csv

    validate_r_environment(required_r_packages=["SPOTlight", "SingleCellExperiment", "SpatialExperiment", "scran", "scuttle"])

    adata_ref = _load_reference(reference_path, cell_type_key)
    # SPOTlight uses counts-derived or normalized matrix flexibly
    adata_sp = adata.copy()
    adata_ref = adata_ref.copy()

    if np.any(_to_dense(adata_sp.X[:1000]) < 0) or np.any(_to_dense(adata_ref.X[:1000]) < 0):
        logger.warning("SPOTlight input contains negative values. It expects non-negative matrices.")

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref = adata_ref[:, common].copy()

    spatial_key = get_spatial_key(adata)
    if spatial_key is None:
        raise ValueError("SPOTlight requires spatial coordinates (obsm['spatial']).")
    coords = adata.obsm[spatial_key][:, :2].astype(np.float64)

    scripts_dir = Path(__file__).resolve().parents[3] / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_spotlight_") as tmpdir:
        tmpdir = Path(tmpdir)

        sp_counts = pd.DataFrame(
            _to_dense(adata_sp.X).T.astype(np.float64), index=common, columns=adata_sp.obs_names)
        sp_counts.to_csv(tmpdir / "spatial_counts.csv")

        coords_df = pd.DataFrame(coords, index=adata_sp.obs_names, columns=["x", "y"])
        coords_df.to_csv(tmpdir / "spatial_coords.csv")

        ref_counts = pd.DataFrame(
            _to_dense(adata_ref.X).T.astype(np.float64), index=common, columns=adata_ref.obs_names)
        ref_counts.to_csv(tmpdir / "ref_counts.csv")

        cell_type_series = adata_ref.obs[cell_type_key].astype(str).str.replace("/", "_", regex=False).str.replace(" ", "_", regex=False)
        ref_types = pd.DataFrame({"cell": adata_ref.obs_names, "cell_type": cell_type_series.values})
        ref_types.to_csv(tmpdir / "ref_celltypes.csv", index=False)

        output_dir = tmpdir / "output"
        output_dir.mkdir()

        runner.run_script(
            "sp_spotlight.R",
            args=[
                str(tmpdir / "spatial_counts.csv"), str(tmpdir / "spatial_coords.csv"),
                str(tmpdir / "ref_counts.csv"), str(tmpdir / "ref_celltypes.csv"),
                str(output_dir),
                str(n_top) if n_top is not None else "",
                weight_id,
                nmf_model,
                str(min_prop),
                str(scale).upper(),
            ],
            expected_outputs=["spotlight_proportions.csv"],
            output_dir=output_dir,
        )

        prop_df = read_r_result_csv(output_dir / "spotlight_proportions.csv")

    effective_params = _prefixed_params(
        "spotlight",
        n_top=n_top,
        weight_id=weight_id,
        nmf_model=nmf_model,
        min_prop=min_prop,
        scale=scale,
    )
    return prop_df, _deconv_stats(
        prop_df,
        common,
        "spotlight",
        n_top=n_top,
        weight_id=weight_id,
        nmf_model=nmf_model,
        min_prop=min_prop,
        scale=scale,
        effective_params=effective_params,
    )


def deconvolve_card(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    sample_key: str | None = METHOD_PARAM_DEFAULTS["card"]["sample_key"],
    min_count_gene: int = METHOD_PARAM_DEFAULTS["card"]["min_count_gene"],
    min_count_spot: int = METHOD_PARAM_DEFAULTS["card"]["min_count_spot"],
    imputation: bool = METHOD_PARAM_DEFAULTS["card"]["imputation"],
    num_grids: int = METHOD_PARAM_DEFAULTS["card"]["num_grids"],
    ineibor: int = METHOD_PARAM_DEFAULTS["card"]["ineibor"],
) -> tuple[pd.DataFrame, dict]:
    import tempfile
    from pathlib import Path
    from omicsclaw.core.dependency_manager import validate_r_environment
    from omicsclaw.core.r_script_runner import RScriptRunner
    from omicsclaw.core.r_utils import read_r_result_csv

    validate_r_environment(required_r_packages=["CARD"])

    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata, "card")
    adata_ref = _restore_counts(adata_ref, "card")

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref = adata_ref[:, common].copy()

    spatial_key = require_spatial_coords(adata_sp)
    coords = pd.DataFrame(
        adata_sp.obsm[spatial_key][:, :2],
        index=adata_sp.obs_names,
        columns=["x", "y"],
    )

    sc_meta = adata_ref.obs[[cell_type_key]].copy()
    sc_meta.columns = ["cellType"]
    if sample_key and sample_key in adata_ref.obs.columns:
        sc_meta["sampleInfo"] = adata_ref.obs[sample_key].values
    else:
        sc_meta["sampleInfo"] = "sample1"

    scripts_dir = Path(__file__).resolve().parents[3] / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_card_") as tmpdir:
        tmpdir = Path(tmpdir)

        sp_counts = pd.DataFrame(
            _to_dense(adata_sp.X).T.astype(np.float64), index=adata_sp.var_names, columns=adata_sp.obs_names)
        sp_counts.to_csv(tmpdir / "spatial_counts.csv")

        coords.to_csv(tmpdir / "spatial_coords.csv")

        ref_counts = pd.DataFrame(
            _to_dense(adata_ref.X).T.astype(np.float64), index=adata_ref.var_names, columns=adata_ref.obs_names)
        ref_counts.to_csv(tmpdir / "ref_counts.csv")

        sc_meta.to_csv(tmpdir / "ref_meta.csv")

        output_dir = tmpdir / "output"
        output_dir.mkdir()

        runner.run_script(
            "sp_card.R",
            args=[
                str(tmpdir / "spatial_counts.csv"), str(tmpdir / "spatial_coords.csv"),
                str(tmpdir / "ref_counts.csv"), str(tmpdir / "ref_meta.csv"),
                str(output_dir),
                str(min_count_gene),
                str(min_count_spot),
                str(imputation).upper(),
                str(num_grids),
                str(ineibor),
            ],
            expected_outputs=["card_proportions.csv"],
            output_dir=output_dir,
        )

        prop_df = read_r_result_csv(output_dir / "card_proportions.csv")
        extra_tables: dict[str, pd.DataFrame] = {}
        refined_path = output_dir / "card_refined_proportions.csv"
        if refined_path.exists():
            extra_tables["card_refined_proportions"] = read_r_result_csv(refined_path)

    effective_params = _prefixed_params(
        "card",
        sample_key=sample_key,
        min_count_gene=min_count_gene,
        min_count_spot=min_count_spot,
        imputation=imputation,
        num_grids=num_grids if imputation else None,
        ineibor=ineibor if imputation else None,
    )
    return prop_df, _deconv_stats(
        prop_df,
        common,
        "card",
        min_count_gene=min_count_gene,
        min_count_spot=min_count_spot,
        imputation=imputation,
        num_grids=num_grids if imputation else None,
        ineibor=ineibor if imputation else None,
        extra_tables=extra_tables,
        effective_params=effective_params,
    )


METHOD_DISPATCH: dict[str, Any] = {
    "flashdeconv":   deconvolve_flashdeconv,
    "cell2location": deconvolve_cell2location,
    "rctd":          deconvolve_rctd,
    "destvi":        deconvolve_destvi,
    "stereoscope":   deconvolve_stereoscope,
    "tangram":       deconvolve_tangram,
    "spotlight":     deconvolve_spotlight,
    "card":          deconvolve_card,
}
