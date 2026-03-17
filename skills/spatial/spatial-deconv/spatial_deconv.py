#!/usr/bin/env python3
"""Spatial Deconv — cell type deconvolution for spatial transcriptomics.

Estimates cell type proportions per spatial spot using a reference
scRNA-seq dataset.

Supported methods (in roughly increasing runtime order):
  flashdeconv   Ultra-fast sketching-based (default, CPU, no GPU needed)
  cell2location Bayesian deep learning with spatial priors (scvi-tools)
  rctd          Robust Cell Type Decomposition (R / spacexr)
  destvi        Multi-resolution VAE deconvolution (scvi-tools DestVI)
  stereoscope   Two-stage probabilistic (scvi-tools Stereoscope)
  tangram       Deep learning cell-to-spot mapping (tangram-sc)
  spotlight     NMF-based (R / SPOTlight)
  card          Conditional AutoRegressive Deconvolution (R / CARD)

Usage:
    python spatial_deconv.py --input <processed.h5ad> \\
        --reference <sc_ref.h5ad> --output <dir>
    python spatial_deconv.py --input <file> --method card \\
        --reference <ref.h5ad> --cell-type-key cellType --output <dir>
"""

from __future__ import annotations

import argparse
import gc
import logging
import subprocess
import sys
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from omicsclaw.spatial.adata_utils import (
    get_spatial_key,
    require_spatial_coords,
    store_analysis_metadata,
)
from omicsclaw.spatial.dependency_manager import require
from omicsclaw.spatial.viz import VizParams, plot_deconvolution
from omicsclaw.spatial.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-deconv"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Method registry
# ---------------------------------------------------------------------------


@dataclass
class MethodConfig:
    name: str
    description: str
    requires_reference: bool = True
    dependencies: tuple[str, ...] = ()
    is_r_based: bool = False
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
        dependencies=("rpy2",),
        is_r_based=True,
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
        dependencies=("rpy2",),
        is_r_based=True,
    ),
    "card": MethodConfig(
        name="card",
        description="Conditional AutoRegressive Deconvolution (R / CARD)",
        dependencies=("rpy2",),
        is_r_based=True,
    ),
}

SUPPORTED_METHODS = tuple(METHOD_REGISTRY.keys())
DEFAULT_METHOD = "flashdeconv"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _to_dense(X) -> np.ndarray:
    if sparse.issparse(X):
        return np.asarray(X.toarray())
    return np.asarray(X)


def _restore_counts(adata) -> "sc.AnnData":
    """Return AnnData with raw integer counts in .X (priority: raw > counts layer > X)."""
    if adata.raw is not None:
        result = adata.raw.to_adata()
        for key in adata.obsm:
            result.obsm[key] = adata.obsm[key].copy()
        return result
    if "counts" in adata.layers:
        result = adata.copy()
        result.X = adata.layers["counts"].copy()
        return result
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


def _deconv_stats(
    prop_df: pd.DataFrame,
    common_genes: list[str],
    method: str,
    device: str = "cpu",
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
    return stats


# ---------------------------------------------------------------------------
# 1. FlashDeconv — default, ultra-fast
# ---------------------------------------------------------------------------


def deconvolve_flashdeconv(
    adata,
    *,
    reference_path: str,
    cell_type_key: str = "cell_type",
    sketch_dim: int = 512,
    lambda_spatial: float = 5000.0,
    n_hvg: int = 2000,
    n_markers_per_type: int = 50,
) -> tuple[pd.DataFrame, dict]:
    """Deconvolve using FlashDeconv (ultra-fast, no GPU needed)."""
    require("flashdeconv", feature="FlashDeconv deconvolution")
    import flashdeconv as fd

    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata)
    adata_ref = _restore_counts(adata_ref)

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref_sub = adata_ref[:, common].copy()

    fd.tl.deconvolve(
        adata_sp,
        adata_ref_sub,
        cell_type_key=cell_type_key,
        sketch_dim=sketch_dim,
        lambda_spatial=lambda_spatial,
        n_hvg=n_hvg,
        n_markers_per_type=n_markers_per_type,
    )

    if "flashdeconv" not in adata_sp.obsm:
        raise RuntimeError(
            "FlashDeconv produced no output in adata.obsm['flashdeconv']"
        )

    proportions = adata_sp.obsm["flashdeconv"]
    cell_types = list(adata_ref.obs[cell_type_key].astype("category").cat.categories)
    if not isinstance(proportions, pd.DataFrame):
        proportions = pd.DataFrame(
            proportions, index=adata.obs_names, columns=cell_types
        )
    else:
        proportions.index = adata.obs_names

    return proportions, _deconv_stats(
        proportions, common, "flashdeconv",
        sketch_dim=sketch_dim,
        lambda_spatial=lambda_spatial,
        n_hvg=n_hvg,
    )


# ---------------------------------------------------------------------------
# 2. Cell2Location — Bayesian deep learning
# ---------------------------------------------------------------------------


def deconvolve_cell2location(
    adata,
    *,
    reference_path: str,
    cell_type_key: str = "cell_type",
    n_epochs: int = 30000,
    n_cells_per_spot: int = 30,
    use_gpu: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Deconvolve using Cell2Location (Bayesian, scvi-tools backend)."""
    require("scvi", feature="Cell2Location deconvolution")
    require("cell2location", feature="Cell2Location deconvolution")

    import cell2location
    from cell2location.models import RegressionModel

    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata)
    adata_ref = _restore_counts(adata_ref)

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref_sub = adata_ref[:, common].copy()

    if "counts" not in adata_ref_sub.layers:
        adata_ref_sub.layers["counts"] = adata_ref_sub.X.copy()
    if "counts" not in adata_sp.layers:
        adata_sp.layers["counts"] = adata_sp.X.copy()

    accelerator = _get_accelerator(use_gpu)
    logger.info("Cell2Location accelerator: %s", accelerator)

    RegressionModel.setup_anndata(adata_ref_sub, layer="counts", labels_key=cell_type_key)
    ref_model = RegressionModel(adata_ref_sub)
    ref_model.train(max_epochs=min(250, n_epochs // 10), accelerator=accelerator)

    inf_aver = ref_model.export_posterior(adata_ref_sub, sample_kwargs={"num_samples": 1000})

    if "means_per_cluster_mu_fg" in inf_aver.varm:
        mat = inf_aver.varm["means_per_cluster_mu_fg"]
        inf_aver_df = (
            mat if isinstance(mat, pd.DataFrame)
            else pd.DataFrame(
                mat,
                index=inf_aver.var_names,
                columns=inf_aver.uns["mod"]["factor_names"],
            )
        )
    else:
        inf_aver_df = inf_aver.var.filter(like="means_per_cluster_mu_fg", axis=1)

    if inf_aver_df.shape[1] == 0:
        raise ValueError("cell2location export_posterior returned an empty cell state matrix.")

    inf_aver_df = inf_aver_df.clip(lower=1e-6).loc[adata_sp.var_names]

    cell2location.models.Cell2location.setup_anndata(adata_sp, layer="counts")
    model = cell2location.models.Cell2location(
        adata_sp, cell_state_df=inf_aver_df, N_cells_per_location=n_cells_per_spot,
    )
    model.train(max_epochs=n_epochs, accelerator=accelerator)

    adata_sp = model.export_posterior(adata_sp)
    q05 = adata_sp.obsm["q05_cell_abundance_w_sf"]

    if isinstance(q05, pd.DataFrame):
        cols = q05.columns.str.replace(
            r"^q05cell_abundance_w_sf_means_per_cluster_mu_fg_", "", regex=True
        )
        prop_df = q05.copy()
        prop_df.columns = cols
    else:
        cell_types = list(inf_aver_df.columns)
        prop_df = pd.DataFrame(q05, index=adata.obs_names, columns=cell_types)

    prop_df = prop_df.div(prop_df.sum(axis=1), axis=0)

    return prop_df, _deconv_stats(
        prop_df, common, "cell2location",
        device=accelerator,
        n_epochs=n_epochs,
        n_cells_per_spot=n_cells_per_spot,
    )


# ---------------------------------------------------------------------------
# 3. RCTD — Robust Cell Type Decomposition (R/spacexr)
# ---------------------------------------------------------------------------


def deconvolve_rctd(
    adata,
    *,
    reference_path: str,
    cell_type_key: str = "cell_type",
    mode: str = "full",
) -> tuple[pd.DataFrame, dict]:
    """Deconvolve using RCTD via rpy2 (R / spacexr)."""
    require("rpy2", feature="RCTD deconvolution")

    import rpy2.robjects as ro
    from rpy2.robjects import numpy2ri, pandas2ri
    from rpy2.robjects.packages import importr

    numpy2ri.activate()
    pandas2ri.activate()

    try:
        importr("spacexr")
    except Exception:
        raise ImportError(
            "R package 'spacexr' not installed.\n"
            "  In R: devtools::install_github('dmcable/spacexr')\n"
            "  Or:   Rscript install_r_dependencies.R"
        )

    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata)
    adata_ref_raw = _restore_counts(adata_ref)

    common = _common_genes(adata_sp, adata_ref_raw)
    adata_sp = adata_sp[:, common].copy()
    adata_ref_raw = adata_ref_raw[:, common].copy()

    spatial_key = require_spatial_coords(adata)
    coords = adata.obsm[spatial_key][:, :2]

    ref_counts = _to_dense(adata_ref_raw.X).T.astype(np.int32)
    sp_counts = _to_dense(adata_sp.X).T.astype(np.int32)
    cell_types_r = ro.StrVector(list(adata_ref_raw.obs[cell_type_key].astype(str)))

    ro.globalenv["ref_counts"] = ro.r["matrix"](
        ro.IntVector(ref_counts.flatten()),
        nrow=int(ref_counts.shape[0]), ncol=int(ref_counts.shape[1]),
    )
    ro.globalenv["ref_cell_types"] = cell_types_r
    ro.globalenv["ref_genes"] = ro.StrVector(list(adata_ref_raw.var_names))
    ro.globalenv["ref_cells"] = ro.StrVector(list(adata_ref_raw.obs_names))
    ro.globalenv["sp_counts"] = ro.r["matrix"](
        ro.IntVector(sp_counts.flatten()),
        nrow=int(sp_counts.shape[0]), ncol=int(sp_counts.shape[1]),
    )
    ro.globalenv["sp_genes"] = ro.StrVector(list(adata_sp.var_names))
    ro.globalenv["sp_spots"] = ro.StrVector(list(adata_sp.obs_names))
    ro.globalenv["sp_coords"] = ro.r["data.frame"](
        x=ro.FloatVector(coords[:, 0].tolist()),
        y=ro.FloatVector(coords[:, 1].tolist()),
    )
    ro.globalenv["rctd_mode"] = mode

    ro.r("""
        library(spacexr)
        rownames(ref_counts) <- ref_genes
        colnames(ref_counts) <- ref_cells
        names(ref_cell_types) <- ref_cells
        ref <- Reference(ref_counts, ref_cell_types)

        rownames(sp_counts) <- sp_genes
        colnames(sp_counts) <- sp_spots
        rownames(sp_coords) <- sp_spots
        puck <- SpatialRNA(sp_coords, sp_counts)

        myRCTD <- create.RCTD(puck, ref, max_cores = 1)
        myRCTD <- run.RCTD(myRCTD, doublet_mode = rctd_mode)
        weights <- myRCTD@results$weights
    """)

    weights_r = ro.r["weights"]
    if hasattr(weights_r, "rx2"):
        weights_arr = np.array(ro.r("as.matrix(weights)"))
        cell_types_out = list(ro.r("colnames(weights)"))
        weights_df = pd.DataFrame(
            weights_arr, index=list(adata_sp.obs_names), columns=cell_types_out
        )
    else:
        weights_df = pandas2ri.rpy2py(weights_r)

    numpy2ri.deactivate()
    pandas2ri.deactivate()

    prop_df = weights_df.div(weights_df.sum(axis=1), axis=0)

    return prop_df, _deconv_stats(prop_df, common, "rctd", rctd_mode=mode)


# ---------------------------------------------------------------------------
# 4. DestVI — multi-resolution VAE (scvi-tools)
# ---------------------------------------------------------------------------


def deconvolve_destvi(
    adata,
    *,
    reference_path: str,
    cell_type_key: str = "cell_type",
    n_epochs: int = 2500,  # Official tutorial uses max_epochs=2500 for DestVI
    n_hidden: int = 128,
    n_latent: int = 5,    # Official CondSCVI default
    n_layers: int = 2,    # Official CondSCVI default
    dropout_rate: float = 0.05,  # Official CondSCVI default
    vamp_prior_p: int = 15,
    use_gpu: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Deconvolve using DestVI (scvi-tools CondSCVI + DestVI).

    Re-implemented following the official scvi-tools 1.4.x tutorial:
    https://docs.scvi-tools.org/en/stable/tutorials/notebooks/spatial/DestVI_tutorial.html

    Key design choices from official tutorial:
      - prior="mog" (Mixture of Gaussians) — avoids mean_vprior type errors
      - weight_obs=False (default) — no cell type abundance reweighting
      - CondSCVI trains with default max_epochs (converges ~300)
      - DestVI trains with user-controlled max_epochs (default 2500)
    """
    require("scvi", feature="DestVI deconvolution")

    import scvi
    from scvi.model import CondSCVI, DestVI

    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata)
    adata_ref = _restore_counts(adata_ref)

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref = adata_ref[:, common].copy()

    adata_ref.obs[cell_type_key] = adata_ref.obs[cell_type_key].astype("category")

    accelerator = _get_accelerator(use_gpu)

    # --- Step 1: CondSCVI on reference (scLVM) ---
    # Determine layer for counts (prefer "counts" layer, fall back to X)
    sc_layer = "counts" if "counts" in adata_ref.layers else None
    CondSCVI.setup_anndata(
        adata_ref,
        labels_key=cell_type_key,
        **({"layer": sc_layer} if sc_layer else {}),
    )

    # Official tutorial: prior="mog" with num_classes_mog, weight_obs=False
    condscvi_model = CondSCVI(
        adata_ref,
        n_hidden=n_hidden,
        n_latent=n_latent,
        n_layers=n_layers,
        dropout_rate=dropout_rate,
        weight_obs=False,
        prior="mog",
        num_classes_mog=vamp_prior_p,
    )

    condscvi_epochs = 300  # Official default, converges quickly
    logger.info(
        "Training CondSCVI (reference model): max_epochs=%d, accelerator=%s",
        condscvi_epochs, accelerator,
    )
    condscvi_model.train(max_epochs=condscvi_epochs, accelerator=accelerator)

    # --- Step 2: DestVI on spatial data (stLVM) ---
    st_layer = "counts" if "counts" in adata_sp.layers else None
    DestVI.setup_anndata(
        adata_sp,
        **({"layer": st_layer} if st_layer else {}),
    )

    destvi_epochs = n_epochs
    logger.info(
        "Training DestVI (spatial model): max_epochs=%d, accelerator=%s",
        destvi_epochs, accelerator,
    )

    destvi_model = DestVI.from_rna_model(
        adata_sp,
        condscvi_model,
        vamp_prior_p=vamp_prior_p,
    )
    destvi_model.train(max_epochs=destvi_epochs, accelerator=accelerator)

    # --- Step 3: Extract proportions ---
    prop_df = destvi_model.get_proportions()
    prop_df.index = adata_sp.obs_names

    del destvi_model, condscvi_model
    gc.collect()

    return prop_df, _deconv_stats(
        prop_df, common, "destvi",
        device=accelerator,
        n_epochs=destvi_epochs,
        condscvi_epochs=condscvi_epochs,
        prior="mog",
    )


# ---------------------------------------------------------------------------
# 5. Stereoscope — two-stage probabilistic (scvi-tools)
# ---------------------------------------------------------------------------


def deconvolve_stereoscope(
    adata,
    *,
    reference_path: str,
    cell_type_key: str = "cell_type",
    n_epochs: int = 150000,
    learning_rate: float = 0.01,
    batch_size: int = 128,
    use_gpu: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Deconvolve using Stereoscope (scvi-tools RNAStereoscope + SpatialStereoscope)."""
    require("scvi", feature="Stereoscope deconvolution")

    from scvi.external import RNAStereoscope, SpatialStereoscope

    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata)
    adata_ref = _restore_counts(adata_ref)

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref = adata_ref[:, common].copy()

    adata_ref.obs[cell_type_key] = adata_ref.obs[cell_type_key].astype("category")
    cell_types = list(adata_ref.obs[cell_type_key].cat.categories)

    rna_epochs = n_epochs // 2
    spatial_epochs = n_epochs - rna_epochs
    accelerator = _get_accelerator(use_gpu)
    plan_kwargs = {"lr": learning_rate}

    RNAStereoscope.setup_anndata(adata_ref, labels_key=cell_type_key)
    rna_model = RNAStereoscope(adata_ref)
    train_kwargs: dict = {
        "max_epochs": rna_epochs,
        "batch_size": batch_size,
        "plan_kwargs": plan_kwargs,
    }
    if accelerator == "gpu":
        train_kwargs["accelerator"] = accelerator
    rna_model.train(**train_kwargs)

    SpatialStereoscope.setup_anndata(adata_sp)
    spatial_model = SpatialStereoscope.from_rna_model(adata_sp, rna_model)
    train_kwargs["max_epochs"] = spatial_epochs
    spatial_model.train(**train_kwargs)

    prop_df = pd.DataFrame(
        spatial_model.get_proportions(),
        index=adata_sp.obs_names,
        columns=cell_types,
    )

    del spatial_model, rna_model
    gc.collect()

    return prop_df, _deconv_stats(
        prop_df, common, "stereoscope",
        device=accelerator,
        n_epochs=n_epochs,
        rna_epochs=rna_epochs,
        spatial_epochs=spatial_epochs,
    )


# ---------------------------------------------------------------------------
# 6. Tangram — deep learning mapping
# ---------------------------------------------------------------------------


def deconvolve_tangram(
    adata,
    *,
    reference_path: str,
    cell_type_key: str = "cell_type",
    n_epochs: int = 1000,
    use_gpu: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Deconvolve using Tangram deep learning mapping."""
    require("tangram", feature="Tangram deconvolution")
    import tangram as tg

    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata)

    # Check common genes first (for early error detection)
    common = _common_genes(adata_sp, adata_ref)

    # Select HVG as training genes
    if "highly_variable" not in adata_ref.var.columns:
        sc.pp.highly_variable_genes(adata_ref, n_top_genes=2000)
    genes = list(adata_ref.var_names[adata_ref.var["highly_variable"]])

    spatial_key = get_spatial_key(adata)
    if spatial_key and spatial_key not in adata_sp.obsm:
        adata_sp.obsm[spatial_key] = adata.obsm[spatial_key].copy()

    # Let tg.pp_adatas handle gene matching internally
    tg.pp_adatas(adata_ref, adata_sp, genes=genes)

    # Get actual training genes used by Tangram
    training_genes = adata_sp.uns.get('training_genes', common)

    device = "cuda" if _get_accelerator(use_gpu) == "gpu" else "cpu"
    logger.info("Tangram mapping (%d epochs, device=%s) ...", n_epochs, device)
    ad_map = tg.map_cells_to_space(
        adata_ref, adata_sp, mode="cells", num_epochs=n_epochs, device=device,
    )
    tg.project_cell_annotations(ad_map, adata_sp, annotation=cell_type_key)

    if "tangram_ct_pred" not in adata_sp.obsm:
        raise RuntimeError("Tangram did not produce tangram_ct_pred in adata.obsm")

    ct_pred = adata_sp.obsm["tangram_ct_pred"]
    prop_df = ct_pred.div(ct_pred.sum(axis=1), axis=0)

    return prop_df, _deconv_stats(
        prop_df, training_genes, "tangram", device=device, n_epochs=n_epochs
    )


# ---------------------------------------------------------------------------
# 7. SPOTlight — NMF-based (R / Bioconductor)
# ---------------------------------------------------------------------------


def deconvolve_spotlight(
    adata,
    *,
    reference_path: str,
    cell_type_key: str = "cell_type",
    n_top_genes: int = 2000,
    nmf_model: str = "ns",
    min_prop: float = 0.01,
    scale: bool = True,
    weight_id: str = "mean.AUC",
) -> tuple[pd.DataFrame, dict]:
    """Deconvolve using SPOTlight (R / Bioconductor)."""
    require("rpy2", feature="SPOTlight deconvolution")

    import rpy2.robjects as ro
    from rpy2.robjects import numpy2ri, pandas2ri
    from rpy2.robjects.conversion import localconverter

    _check_r_package("SPOTlight", "BiocManager::install('SPOTlight')")

    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata)
    adata_ref = _restore_counts(adata_ref)

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref = adata_ref[:, common].copy()

    spatial_key = get_spatial_key(adata)
    if spatial_key is None:
        raise ValueError("SPOTlight requires spatial coordinates (obsm['spatial']).")
    coords = adata.obsm[spatial_key][:, :2].astype(np.float64)

    sp_counts = _to_dense(adata_sp.X).T.astype(np.int32)
    ref_counts = _to_dense(adata_ref.X).T.astype(np.int32)

    # Clean cell type strings for R
    cell_type_series = (
        adata_ref.obs[cell_type_key]
        .astype(str)
        .str.replace("/", "_", regex=False)
        .str.replace(" ", "_", regex=False)
    )

    with localconverter(ro.default_converter + pandas2ri.converter):
        ro.r("library(SPOTlight)")
        ro.r("library(SingleCellExperiment)")
        ro.r("library(SpatialExperiment)")
        ro.r("library(scran)")
        ro.r("library(scuttle)")

    with localconverter(ro.default_converter + numpy2ri.converter):
        ro.globalenv["spatial_counts"] = sp_counts
        ro.globalenv["reference_counts"] = ref_counts

    with localconverter(ro.default_converter + pandas2ri.converter + numpy2ri.converter):
        ro.globalenv["spatial_coords"] = coords
        ro.globalenv["gene_names"] = ro.StrVector(common)
        ro.globalenv["spatial_names"] = ro.StrVector(list(adata_sp.obs_names))
        ro.globalenv["reference_names"] = ro.StrVector(list(adata_ref.obs_names))
        ro.globalenv["cell_types"] = ro.StrVector(cell_type_series.tolist())
        ro.globalenv["nmf_model"] = nmf_model
        ro.globalenv["min_prop"] = min_prop
        ro.globalenv["scale_data"] = scale
        ro.globalenv["weight_id"] = weight_id

    ro.r("""
        sce <- SingleCellExperiment(
            assays = list(counts = reference_counts),
            colData = data.frame(
                cell_type = factor(cell_types),
                row.names = reference_names
            )
        )
        rownames(sce) <- gene_names
        sce <- logNormCounts(sce)

        spe <- SpatialExperiment(
            assays = list(counts = spatial_counts),
            spatialCoords = spatial_coords,
            colData = data.frame(row.names = spatial_names)
        )
        rownames(spe) <- gene_names
        colnames(spe) <- spatial_names

        markers <- findMarkers(sce, groups = sce$cell_type, test.type = "wilcox")
        cell_type_names <- names(markers)
        mgs_list <- list()
        for (ct in cell_type_names) {
            ct_markers <- markers[[ct]]
            n_markers <- min(50, nrow(ct_markers))
            top_markers <- head(ct_markers[order(ct_markers$p.value), ], n_markers)
            mgs_list[[ct]] <- data.frame(
                gene     = rownames(top_markers),
                cluster  = ct,
                mean.AUC = -log10(top_markers$p.value + 1e-10)
            )
        }
        mgs <- do.call(rbind, mgs_list)

        spotlight_result <- SPOTlight(
            x        = sce,
            y        = spe,
            groups   = sce$cell_type,
            mgs      = mgs,
            weight_id = weight_id,
            group_id  = "cluster",
            gene_id   = "gene",
            model     = nmf_model,
            min_prop  = min_prop,
            scale     = scale_data,
            verbose   = FALSE
        )
    """)

    with localconverter(ro.default_converter + pandas2ri.converter + numpy2ri.converter):
        proportions_np = np.array(ro.r("spotlight_result$mat"))
        spot_names = list(ro.r("rownames(spotlight_result$mat)"))
        ct_names = list(ro.r("colnames(spotlight_result$mat)"))

    ro.r("""
        rm(list = intersect(
               c("spatial_counts","reference_counts","spatial_coords",
                 "gene_names","spatial_names","reference_names","cell_types",
                 "nmf_model","min_prop","scale_data","weight_id",
                 "sce","spe","markers","mgs","spotlight_result"),
               ls(envir=.GlobalEnv)),
           envir = .GlobalEnv)
        gc()
    """)

    prop_df = pd.DataFrame(proportions_np, index=spot_names, columns=ct_names)

    return prop_df, _deconv_stats(
        prop_df, common, "spotlight",
        n_top_genes=n_top_genes, nmf_model=nmf_model, min_prop=min_prop,
    )


# ---------------------------------------------------------------------------
# 8. CARD — Conditional AutoRegressive Deconvolution (R)
# ---------------------------------------------------------------------------


def deconvolve_card(
    adata,
    *,
    reference_path: str,
    cell_type_key: str = "cell_type",
    sample_key: str | None = None,
    min_count_gene: int = 100,
    min_count_spot: int = 5,
    imputation: bool = False,
    num_grids: int = 2000,
    ineibor: int = 10,
) -> tuple[pd.DataFrame, dict]:
    """Deconvolve using CARD (R / conditional autoregressive model)."""
    require("rpy2", feature="CARD deconvolution")

    import rpy2.robjects as ro
    from rpy2.robjects import numpy2ri, pandas2ri
    from rpy2.robjects.conversion import localconverter

    _check_r_package(
        "CARD",
        "devtools::install_github('YMa-lab/CARD')",
    )

    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata)
    adata_ref = _restore_counts(adata_ref)

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref = adata_ref[:, common].copy()

    spatial_key = get_spatial_key(adata)
    if spatial_key is not None:
        coords = pd.DataFrame(
            adata.obsm[spatial_key][:, :2],
            index=adata_sp.obs_names,
            columns=["x", "y"],
        )
    else:
        logger.warning("No spatial coordinates found; using dummy coordinates for CARD.")
        coords = pd.DataFrame(
            {"x": range(adata_sp.n_obs), "y": [0] * adata_sp.n_obs},
            index=adata_sp.obs_names,
        )

    sc_meta = adata_ref.obs[[cell_type_key]].copy()
    sc_meta.columns = ["cellType"]
    if sample_key and sample_key in adata_ref.obs.columns:
        sc_meta["sampleInfo"] = adata_ref.obs[sample_key].values
    else:
        sc_meta["sampleInfo"] = "sample1"

    sp_count_mat = _to_dense(adata_sp.X).T.astype(np.float64)
    ref_count_mat = _to_dense(adata_ref.X).T.astype(np.float64)

    with localconverter(ro.default_converter + numpy2ri.converter):
        ro.globalenv["sc_count"] = ref_count_mat
        ro.globalenv["spatial_count"] = sp_count_mat

    with localconverter(ro.default_converter + pandas2ri.converter):
        ro.globalenv["sc_meta"] = ro.conversion.py2rpy(sc_meta)
        ro.globalenv["spatial_location"] = ro.conversion.py2rpy(coords)
        ro.globalenv["minCountGene"] = min_count_gene
        ro.globalenv["minCountSpot"] = min_count_spot

    ro.r(f"""
        rownames(sc_count) <- {_r_str_vec(adata_ref.var_names)}
        colnames(sc_count) <- {_r_str_vec(adata_ref.obs_names)}
        rownames(spatial_count) <- {_r_str_vec(adata_sp.var_names)}
        colnames(spatial_count) <- {_r_str_vec(adata_sp.obs_names)}
    """)

    ro.r("""
        library(CARD)
        capture.output(
            CARD_obj <- createCARDObject(
                sc_count         = sc_count,
                sc_meta          = sc_meta,
                spatial_count    = spatial_count,
                spatial_location = spatial_location,
                ct.varname       = "cellType",
                ct.select        = unique(sc_meta$cellType),
                sample.varname   = "sampleInfo",
                minCountGene     = minCountGene,
                minCountSpot     = minCountSpot
            ),
            file = "/dev/null"
        )
        capture.output(
            CARD_obj <- CARD_deconvolution(CARD_object = CARD_obj),
            file = "/dev/null"
        )
    """)

    with localconverter(ro.default_converter + pandas2ri.converter + numpy2ri.converter):
        row_names = list(ro.r("rownames(CARD_obj@Proportion_CARD)"))
        col_names = list(ro.r("colnames(CARD_obj@Proportion_CARD)"))
        proportions_arr = np.array(ro.r("CARD_obj@Proportion_CARD"))

    prop_df = pd.DataFrame(proportions_arr, index=row_names, columns=col_names)

    extra: dict = {}
    if imputation:
        ro.r(f"""
            capture.output(
                CARD_impute <- CARD.imputation(
                    CARD_object = CARD_obj,
                    NumGrids    = {num_grids},
                    ineibor     = {ineibor}
                ),
                file = "/dev/null"
            )
        """)
        with localconverter(ro.default_converter + pandas2ri.converter + numpy2ri.converter):
            imp_rows = list(ro.r("rownames(CARD_impute@refined_prop)"))
            imp_cols = list(ro.r("colnames(CARD_impute@refined_prop)"))
            imp_arr = np.array(ro.r("CARD_impute@refined_prop"))
        imp_df = pd.DataFrame(imp_arr, index=imp_rows, columns=imp_cols)
        extra["imputed_n_locations"] = len(imp_df)

    # Clean up R env
    _r_cleanup(
        "sc_count", "spatial_count", "sc_meta", "spatial_location",
        "minCountGene", "minCountSpot", "CARD_obj",
        *(["CARD_impute"] if imputation else []),
    )

    return prop_df, _deconv_stats(
        prop_df, common, "card",
        min_count_gene=min_count_gene,
        min_count_spot=min_count_spot,
        imputation=imputation,
        **extra,
    )


# ---------------------------------------------------------------------------
# R helper utilities
# ---------------------------------------------------------------------------


def _check_r_package(pkg: str, install_cmd: str) -> None:
    """Raise ImportError if R package is not installed."""
    try:
        import rpy2.robjects as ro
        ro.r(f'if (!requireNamespace("{pkg}", quietly=TRUE)) stop("not found")')
    except Exception:
        raise ImportError(
            f"R package '{pkg}' is not installed.\n"
            f"  In R: {install_cmd}\n"
            f"  Or:   Rscript install_r_dependencies.R"
        )


def _r_str_vec(names) -> str:
    """Build an R c("a","b",...) string from a list/Index."""
    quoted = ", ".join(f'"{n}"' for n in names)
    return f"c({quoted})"


def _r_cleanup(*var_names: str) -> None:
    """Remove named variables from R global env and call gc()."""
    try:
        import rpy2.robjects as ro
        existing = list(ro.r("ls(envir=.GlobalEnv)"))
        to_rm = [v for v in var_names if v in existing]
        if to_rm:
            rm_str = ", ".join(f'"{v}"' for v in to_rm)
            ro.r(f"rm(list=c({rm_str}), envir=.GlobalEnv); gc()")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------


from typing import Any

_METHOD_DISPATCH: dict[str, Any] = {
    "flashdeconv":   deconvolve_flashdeconv,
    "cell2location": deconvolve_cell2location,
    "rctd":          deconvolve_rctd,
    "destvi":        deconvolve_destvi,
    "stereoscope":   deconvolve_stereoscope,
    "tangram":       deconvolve_tangram,
    "spotlight":     deconvolve_spotlight,
    "card":          deconvolve_card,
}


# ---------------------------------------------------------------------------
# Figure generation
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, prop_df: pd.DataFrame) -> list[str]:
    import matplotlib.pyplot as plt
    figures: list[str] = []
    spatial_key = get_spatial_key(adata)

    # viz library tight coupling on "spatial"
    if spatial_key and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm[spatial_key]

    if spatial_key is not None:
        for subtype, fname in [
            ("spatial_multi", "spatial_proportions.png"),
            ("dominant",      "dominant_celltype.png"),
            ("diversity",     "celltype_diversity.png"),
        ]:
            try:
                fig = plot_deconvolution(adata, VizParams(colormap="Reds"), subtype=subtype)
                figures.append(str(save_figure(fig, output_dir, fname)))
            except Exception as exc:
                logger.warning("Could not generate %s: %s", fname, exc)

    try:
        mean_props = prop_df.mean().sort_values(ascending=True)
        fig, ax = plt.subplots(figsize=(8, max(3, int(len(mean_props) * 0.4))), dpi=200)
        mean_props.plot.barh(ax=ax, color="coral")
        ax.set_xlabel("Mean Proportion")
        ax.set_title("Average Cell Type Proportions")
        fig.tight_layout()
        figures.append(str(save_figure(fig, output_dir, "mean_proportions.png")))
    except Exception as exc:
        logger.warning("Could not generate proportion barplot: %s", exc)

    if "X_umap" in adata.obsm:
        try:
            fig = plot_deconvolution(adata, VizParams(), subtype="umap")
            figures.append(str(save_figure(fig, output_dir, "umap_proportions.png")))
        except Exception as exc:
            logger.warning("Could not generate UMAP proportions: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_report(
    output_dir: Path, stats: dict, input_file: str | None, params: dict
) -> None:
    header = generate_report_header(
        title="Spatial Deconvolution Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Method": stats["method"]},
    )

    lines = [
        "## Summary\n",
        f"- **Method**: {stats['method']}",
        f"- **Spots**: {stats['n_spots']}",
        f"- **Cell types**: {stats['n_cell_types']}",
    ]
    if "n_common_genes" in stats:
        lines.append(f"- **Common genes**: {stats['n_common_genes']}")

    lines += ["", "### Cell types detected\n"]
    for ct in stats.get("cell_types", []):
        lines.append(f"- {ct}")

    lines += ["", "## Parameters\n"]
    for k, v in params.items():
        lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=stats,
        data={"params": params, **stats},
        input_checksum=checksum,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Spatial Deconv — multi-method cell type deconvolution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(
            [f"  {m:<14} {METHOD_REGISTRY[m].description}" for m in SUPPORTED_METHODS]
        ),
    )
    parser.add_argument("--input",  dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo",   action="store_true")
    parser.add_argument(
        "--method",
        choices=list(SUPPORTED_METHODS),
        default=DEFAULT_METHOD,
        help=f"Deconvolution method (default: {DEFAULT_METHOD})",
    )
    parser.add_argument("--reference",      default=None, help="Reference scRNA-seq h5ad")
    parser.add_argument("--cell-type-key",  default="cell_type",
                        help="Cell type column in reference obs (default: cell_type)")
    parser.add_argument("--n-epochs",       type=int, default=None)
    parser.add_argument("--no-gpu", "--cpu", action="store_true",
                        help="Force CPU even when GPU is available")
    parser.add_argument("--use-gpu",        action="store_true",
                        help="(deprecated, GPU is now default for capable methods)")
    parser.add_argument("--rctd-mode",      default="full",
                        choices=["full", "doublet", "single"],
                        help="RCTD mode (default: full)")
    parser.add_argument("--card-imputation", action="store_true",
                        help="Enable CARD spatial imputation")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        print(
            "ERROR: --demo requires a real reference scRNA-seq dataset.\n\n"
            "Example:\n"
            "  python spatial_deconv.py \\\n"
            "      --input spatial.h5ad \\\n"
            "      --reference reference.h5ad \\\n"
            f"      --method {DEFAULT_METHOD} \\\n"
            "      --output results/\n\n"
            f"Available methods: {', '.join(SUPPORTED_METHODS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.input_path:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    adata = sc.read_h5ad(args.input_path)
    input_file = args.input_path

    cfg = METHOD_REGISTRY[args.method]
    if cfg.requires_reference and not args.reference:
        print(f"ERROR: --reference is required for method '{args.method}'", file=sys.stderr)
        sys.exit(1)

    run_fn = _METHOD_DISPATCH[args.method]

    # Build kwargs — start with common ones, add method-specific overrides
    kwargs: dict = {
        "reference_path": args.reference,
        "cell_type_key": args.cell_type_key,
    }
    # Methods that accept n_epochs parameter
    _EPOCH_METHODS = {"cell2location", "destvi", "stereoscope", "tangram"}
    if args.n_epochs is not None:
        if args.method in _EPOCH_METHODS:
            kwargs["n_epochs"] = args.n_epochs
            logger.info("Using user-specified n_epochs=%d", args.n_epochs)
        else:
            logger.warning(
                "Method '%s' does not support --n-epochs (ignored). "
                "Supported: %s", args.method, ", ".join(sorted(_EPOCH_METHODS))
            )
    if cfg.supports_gpu:
        # GPU is default for capable methods; --no-gpu / --cpu opts out
        kwargs["use_gpu"] = not getattr(args, 'no_gpu', False)
    if args.method == "rctd":
        kwargs["mode"] = args.rctd_mode
    if args.method == "card":
        kwargs["imputation"] = args.card_imputation

    logger.info("Running deconvolution: method=%s", args.method)
    prop_df, stats = run_fn(adata, **kwargs)

    prop_key = f"deconvolution_{args.method}"
    adata.obsm[prop_key] = prop_df.values
    adata.uns[f"{prop_key}_cell_types"] = list(prop_df.columns)

    params = {
        "method": args.method,
        "reference": args.reference,
        "cell_type_key": args.cell_type_key,
    }

    store_analysis_metadata(adata, SKILL_NAME, stats["method"], params=params)

    generate_figures(adata, output_dir, prop_df)
    write_report(output_dir, stats, input_file, params)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    prop_df.to_csv(tables_dir / "proportions.csv")

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved: %s", h5ad_path)

    print(
        f"Deconvolution complete: {stats['n_cell_types']} cell types "
        f"via {stats['method']}"
    )


if __name__ == "__main__":
    main()
