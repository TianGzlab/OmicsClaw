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
# Methods
# ---------------------------------------------------------------------------


def deconvolve_flashdeconv(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    sketch_dim: int = 512, lambda_spatial: float = 5000.0,
    n_hvg: int = 2000, n_markers_per_type: int = 50,
) -> tuple[pd.DataFrame, dict]:
    require("flashdeconv", feature="FlashDeconv deconvolution")
    import flashdeconv as fd

    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata)
    adata_ref = _restore_counts(adata_ref)

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

    return proportions, _deconv_stats(
        proportions, common, "flashdeconv",
        sketch_dim=sketch_dim, lambda_spatial=lambda_spatial, n_hvg=n_hvg,
    )


def deconvolve_cell2location(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    n_epochs: int = 30000, n_cells_per_spot: int = 30, use_gpu: bool = True,
) -> tuple[pd.DataFrame, dict]:
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
            else pd.DataFrame(mat, index=inf_aver.var_names, columns=inf_aver.uns["mod"]["factor_names"])
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
        cols = q05.columns.str.replace(r"^q05cell_abundance_w_sf_means_per_cluster_mu_fg_", "", regex=True)
        prop_df = q05.copy()
        prop_df.columns = cols
    else:
        cell_types = list(inf_aver_df.columns)
        prop_df = pd.DataFrame(q05, index=adata.obs_names, columns=cell_types)

    prop_df = prop_df.div(prop_df.sum(axis=1), axis=0)

    return prop_df, _deconv_stats(
        prop_df, common, "cell2location", device=accelerator,
        n_epochs=n_epochs, n_cells_per_spot=n_cells_per_spot,
    )


def deconvolve_rctd(
    adata, *, reference_path: str, cell_type_key: str = "cell_type", mode: str = "full",
) -> tuple[pd.DataFrame, dict]:
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
        ro.IntVector(ref_counts.flatten()), nrow=int(ref_counts.shape[0]), ncol=int(ref_counts.shape[1]),
    )
    ro.globalenv["ref_cell_types"] = cell_types_r
    ro.globalenv["ref_genes"] = ro.StrVector(list(adata_ref_raw.var_names))
    ro.globalenv["ref_cells"] = ro.StrVector(list(adata_ref_raw.obs_names))
    ro.globalenv["sp_counts"] = ro.r["matrix"](
        ro.IntVector(sp_counts.flatten()), nrow=int(sp_counts.shape[0]), ncol=int(sp_counts.shape[1]),
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
        weights_df = pd.DataFrame(weights_arr, index=list(adata_sp.obs_names), columns=cell_types_out)
    else:
        weights_df = pandas2ri.rpy2py(weights_r)

    numpy2ri.deactivate()
    pandas2ri.deactivate()

    prop_df = weights_df.div(weights_df.sum(axis=1), axis=0)
    return prop_df, _deconv_stats(prop_df, common, "rctd", rctd_mode=mode)


def deconvolve_destvi(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    n_epochs: int = 2500, n_hidden: int = 128, n_latent: int = 5,
    n_layers: int = 2, dropout_rate: float = 0.05, vamp_prior_p: int = 15,
    use_gpu: bool = True,
) -> tuple[pd.DataFrame, dict]:
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

    sc_layer = "counts" if "counts" in adata_ref.layers else None
    CondSCVI.setup_anndata(adata_ref, labels_key=cell_type_key, **({"layer": sc_layer} if sc_layer else {}))

    condscvi_model = CondSCVI(
        adata_ref, n_hidden=n_hidden, n_latent=n_latent, n_layers=n_layers,
        dropout_rate=dropout_rate, weight_obs=False, prior="mog", num_classes_mog=vamp_prior_p,
    )

    condscvi_epochs = 300
    condscvi_model.train(max_epochs=condscvi_epochs, accelerator=accelerator)

    st_layer = "counts" if "counts" in adata_sp.layers else None
    DestVI.setup_anndata(adata_sp, **({"layer": st_layer} if st_layer else {}))

    destvi_model = DestVI.from_rna_model(adata_sp, condscvi_model, vamp_prior_p=vamp_prior_p)
    destvi_model.train(max_epochs=n_epochs, accelerator=accelerator)

    prop_df = destvi_model.get_proportions()
    prop_df.index = adata_sp.obs_names

    del destvi_model, condscvi_model
    gc.collect()

    return prop_df, _deconv_stats(
        prop_df, common, "destvi", device=accelerator,
        n_epochs=n_epochs, condscvi_epochs=condscvi_epochs, prior="mog",
    )


def deconvolve_stereoscope(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    n_epochs: int = 150000, learning_rate: float = 0.01,
    batch_size: int = 128, use_gpu: bool = True,
) -> tuple[pd.DataFrame, dict]:
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
    train_kwargs: dict = {"max_epochs": rna_epochs, "batch_size": batch_size, "plan_kwargs": plan_kwargs}
    if accelerator == "gpu":
        train_kwargs["accelerator"] = accelerator
    rna_model.train(**train_kwargs)

    SpatialStereoscope.setup_anndata(adata_sp)
    spatial_model = SpatialStereoscope.from_rna_model(adata_sp, rna_model)
    train_kwargs["max_epochs"] = spatial_epochs
    spatial_model.train(**train_kwargs)

    prop_df = pd.DataFrame(spatial_model.get_proportions(), index=adata_sp.obs_names, columns=cell_types)

    del spatial_model, rna_model
    gc.collect()

    return prop_df, _deconv_stats(
        prop_df, common, "stereoscope", device=accelerator,
        n_epochs=n_epochs, rna_epochs=rna_epochs, spatial_epochs=spatial_epochs,
    )


def deconvolve_tangram(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    n_epochs: int = 1000, use_gpu: bool = True,
) -> tuple[pd.DataFrame, dict]:
    require("tangram", feature="Tangram deconvolution")
    import tangram as tg

    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata)

    common = _common_genes(adata_sp, adata_ref)

    if "highly_variable" not in adata_ref.var.columns:
        sc.pp.highly_variable_genes(adata_ref, n_top_genes=2000)
    genes = list(adata_ref.var_names[adata_ref.var["highly_variable"]])

    spatial_key = get_spatial_key(adata)
    if spatial_key and spatial_key not in adata_sp.obsm:
        adata_sp.obsm[spatial_key] = adata.obsm[spatial_key].copy()

    tg.pp_adatas(adata_ref, adata_sp, genes=genes)
    training_genes = adata_sp.uns.get('training_genes', common)

    device = "cuda" if _get_accelerator(use_gpu) == "gpu" else "cpu"
    ad_map = tg.map_cells_to_space(adata_ref, adata_sp, mode="cells", num_epochs=n_epochs, device=device)
    tg.project_cell_annotations(ad_map, adata_sp, annotation=cell_type_key)

    if "tangram_ct_pred" not in adata_sp.obsm:
        raise RuntimeError("Tangram did not produce tangram_ct_pred in adata.obsm")

    ct_pred = adata_sp.obsm["tangram_ct_pred"]
    prop_df = ct_pred.div(ct_pred.sum(axis=1), axis=0)

    return prop_df, _deconv_stats(prop_df, training_genes, "tangram", device=device, n_epochs=n_epochs)


def deconvolve_spotlight(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    n_top_genes: int = 2000, nmf_model: str = "ns", min_prop: float = 0.01,
    scale: bool = True, weight_id: str = "mean.AUC",
) -> tuple[pd.DataFrame, dict]:
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

    cell_type_series = adata_ref.obs[cell_type_key].astype(str).str.replace("/", "_", regex=False).str.replace(" ", "_", regex=False)

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
        sce <- SingleCellExperiment(assays = list(counts = reference_counts), colData = data.frame(cell_type = factor(cell_types), row.names = reference_names))
        rownames(sce) <- gene_names
        sce <- logNormCounts(sce)

        spe <- SpatialExperiment(assays = list(counts = spatial_counts), spatialCoords = spatial_coords, colData = data.frame(row.names = spatial_names))
        rownames(spe) <- gene_names
        colnames(spe) <- spatial_names

        markers <- findMarkers(sce, groups = sce$cell_type, test.type = "wilcox")
        cell_type_names <- names(markers)
        mgs_list <- list()
        for (ct in cell_type_names) {
            ct_markers <- markers[[ct]]
            n_markers <- min(50, nrow(ct_markers))
            top_markers <- head(ct_markers[order(ct_markers$p.value), ], n_markers)
            mgs_list[[ct]] <- data.frame(gene = rownames(top_markers), cluster = ct, mean.AUC = -log10(top_markers$p.value + 1e-10))
        }
        mgs <- do.call(rbind, mgs_list)

        spotlight_result <- SPOTlight(x = sce, y = spe, groups = sce$cell_type, mgs = mgs, weight_id = weight_id, group_id = "cluster", gene_id = "gene", model = nmf_model, min_prop = min_prop, scale = scale_data, verbose = FALSE)
    """)

    with localconverter(ro.default_converter + pandas2ri.converter + numpy2ri.converter):
        proportions_np = np.array(ro.r("spotlight_result$mat"))
        spot_names = list(ro.r("rownames(spotlight_result$mat)"))
        ct_names = list(ro.r("colnames(spotlight_result$mat)"))

    ro.r("""
        rm(list = intersect(c("spatial_counts","reference_counts","spatial_coords","gene_names","spatial_names","reference_names","cell_types","nmf_model","min_prop","scale_data","weight_id","sce","spe","markers","mgs","spotlight_result"), ls(envir=.GlobalEnv)), envir = .GlobalEnv)
        gc()
    """)

    prop_df = pd.DataFrame(proportions_np, index=spot_names, columns=ct_names)
    return prop_df, _deconv_stats(prop_df, common, "spotlight", n_top_genes=n_top_genes, nmf_model=nmf_model, min_prop=min_prop)


def deconvolve_card(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    sample_key: str | None = None, min_count_gene: int = 100,
    min_count_spot: int = 5, imputation: bool = False,
    num_grids: int = 2000, ineibor: int = 10,
) -> tuple[pd.DataFrame, dict]:
    require("rpy2", feature="CARD deconvolution")

    import rpy2.robjects as ro
    from rpy2.robjects import numpy2ri, pandas2ri
    from rpy2.robjects.conversion import localconverter

    _check_r_package("CARD", "devtools::install_github('YMa-lab/CARD')")

    adata_ref = _load_reference(reference_path, cell_type_key)
    adata_sp = _restore_counts(adata)
    adata_ref = _restore_counts(adata_ref)

    common = _common_genes(adata_sp, adata_ref)
    adata_sp = adata_sp[:, common].copy()
    adata_ref = adata_ref[:, common].copy()

    spatial_key = get_spatial_key(adata)
    if spatial_key is not None:
        coords = pd.DataFrame(adata.obsm[spatial_key][:, :2], index=adata_sp.obs_names, columns=["x", "y"])
    else:
        logger.warning("No spatial coordinates found; using dummy coordinates for CARD.")
        coords = pd.DataFrame({"x": range(adata_sp.n_obs), "y": [0] * adata_sp.n_obs}, index=adata_sp.obs_names)

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
        capture.output(CARD_obj <- createCARDObject(sc_count = sc_count, sc_meta = sc_meta, spatial_count = spatial_count, spatial_location = spatial_location, ct.varname = "cellType", ct.select = unique(sc_meta$cellType), sample.varname = "sampleInfo", minCountGene = minCountGene, minCountSpot = minCountSpot), file = "/dev/null")
        capture.output(CARD_obj <- CARD_deconvolution(CARD_object = CARD_obj), file = "/dev/null")
    """)

    with localconverter(ro.default_converter + pandas2ri.converter + numpy2ri.converter):
        row_names = list(ro.r("rownames(CARD_obj@Proportion_CARD)"))
        col_names = list(ro.r("colnames(CARD_obj@Proportion_CARD)"))
        proportions_arr = np.array(ro.r("CARD_obj@Proportion_CARD"))

    prop_df = pd.DataFrame(proportions_arr, index=row_names, columns=col_names)

    extra: dict = {}
    if imputation:
        ro.r(f"""
            capture.output(CARD_impute <- CARD.imputation(CARD_object = CARD_obj, NumGrids = {num_grids}, ineibor = {ineibor}), file = "/dev/null")
        """)
        with localconverter(ro.default_converter + pandas2ri.converter + numpy2ri.converter):
            imp_rows = list(ro.r("rownames(CARD_impute@refined_prop)"))
            imp_cols = list(ro.r("colnames(CARD_impute@refined_prop)"))
            imp_arr = np.array(ro.r("CARD_impute@refined_prop"))
        imp_df = pd.DataFrame(imp_arr, index=imp_rows, columns=imp_cols)
        extra["imputed_n_locations"] = len(imp_df)

    _r_cleanup("sc_count", "spatial_count", "sc_meta", "spatial_location", "minCountGene", "minCountSpot", "CARD_obj", *(["CARD_impute"] if imputation else []))

    return prop_df, _deconv_stats(
        prop_df, common, "card", min_count_gene=min_count_gene, min_count_spot=min_count_spot, imputation=imputation, **extra,
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
