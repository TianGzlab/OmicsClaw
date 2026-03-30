#!/usr/bin/env python3
"""Spatial Deconv — cell type deconvolution for spatial transcriptomics.

Supported methods:
  flashdeconv   Ultra-fast sketching-based deconvolution
  cell2location Bayesian deep learning with spatial priors (default)
  rctd          Robust Cell Type Decomposition (R / spacexr)
  destvi        Multi-resolution VAE deconvolution (scvi-tools)
  stereoscope   Two-stage probabilistic deconvolution (scvi-tools)
  tangram       Deep learning cell-to-spot mapping (tangram-sc)
  spotlight     NMF-based deconvolution (R / SPOTlight)
  card          Conditional AutoRegressive Deconvolution (R / CARD)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import shlex
import sys
import warnings
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.runtime_env import ensure_runtime_cache_dirs

ensure_runtime_cache_dirs("omicsclaw")

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from skills.spatial._lib.adata_utils import get_spatial_key, store_analysis_metadata
from skills.spatial._lib.deconvolution import (
    COUNT_BASED_METHODS,
    DEFAULT_METHOD,
    FLEXIBLE_INPUT_METHODS,
    METHOD_DISPATCH,
    METHOD_PARAM_DEFAULTS,
    METHOD_REGISTRY,
    NONNEGATIVE_EXPRESSION_METHODS,
    SUPPORTED_METHODS,
    VALID_RCTD_MODES,
    VALID_SPOTLIGHT_MODELS,
    VALID_TANGRAM_MODES,
)
from skills.spatial._lib.viz import (
    PlotSpec,
    VisualizationRecipe,
    VizParams,
    plot_deconvolution,
    plot_features,
    render_plot_specs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-deconv"
SKILL_VERSION = "0.4.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-deconv/spatial_deconv.py"


def _parse_float_or_auto(value: str) -> float | str:
    if value.lower() == "auto":
        return "auto"
    return float(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Spatial Deconv — multi-method cell type deconvolution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(
            [f"  {m:<14} {METHOD_REGISTRY[m].description}" for m in SUPPORTED_METHODS]
        ),
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method",
        choices=list(SUPPORTED_METHODS),
        default=DEFAULT_METHOD,
        help=f"Deconvolution method (default: {DEFAULT_METHOD})",
    )
    parser.add_argument("--reference", default=None, help="Reference scRNA-seq h5ad")
    parser.add_argument(
        "--cell-type-key",
        default="cell_type",
        help="Cell type column in reference obs (default: cell_type)",
    )
    parser.add_argument(
        "--no-gpu",
        "--cpu",
        action="store_true",
        help="Force CPU even when GPU is available for GPU-capable methods",
    )
    parser.add_argument(
        "--use-gpu",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--flashdeconv-sketch-dim",
        type=int,
        default=METHOD_PARAM_DEFAULTS["flashdeconv"]["sketch_dim"],
    )
    parser.add_argument(
        "--flashdeconv-lambda-spatial",
        type=_parse_float_or_auto,
        default=METHOD_PARAM_DEFAULTS["flashdeconv"]["lambda_spatial"],
    )
    parser.add_argument(
        "--flashdeconv-n-hvg",
        type=int,
        default=METHOD_PARAM_DEFAULTS["flashdeconv"]["n_hvg"],
    )
    parser.add_argument(
        "--flashdeconv-n-markers-per-type",
        type=int,
        default=METHOD_PARAM_DEFAULTS["flashdeconv"]["n_markers_per_type"],
    )

    parser.add_argument(
        "--cell2location-n-epochs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["cell2location"]["n_epochs"],
    )
    parser.add_argument(
        "--cell2location-n-cells-per-spot",
        type=int,
        default=METHOD_PARAM_DEFAULTS["cell2location"]["n_cells_per_spot"],
    )
    parser.add_argument(
        "--cell2location-detection-alpha",
        type=float,
        default=METHOD_PARAM_DEFAULTS["cell2location"]["detection_alpha"],
    )

    parser.add_argument(
        "--rctd-mode",
        choices=[*VALID_RCTD_MODES, "single"],
        default=METHOD_PARAM_DEFAULTS["rctd"]["mode"],
    )

    parser.add_argument(
        "--destvi-n-epochs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["destvi"]["n_epochs"],
    )
    parser.add_argument(
        "--destvi-condscvi-epochs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["destvi"]["condscvi_epochs"],
    )
    parser.add_argument(
        "--destvi-n-hidden",
        type=int,
        default=METHOD_PARAM_DEFAULTS["destvi"]["n_hidden"],
    )
    parser.add_argument(
        "--destvi-n-latent",
        type=int,
        default=METHOD_PARAM_DEFAULTS["destvi"]["n_latent"],
    )
    parser.add_argument(
        "--destvi-n-layers",
        type=int,
        default=METHOD_PARAM_DEFAULTS["destvi"]["n_layers"],
    )
    parser.add_argument(
        "--destvi-dropout-rate",
        type=float,
        default=METHOD_PARAM_DEFAULTS["destvi"]["dropout_rate"],
    )
    parser.add_argument(
        "--destvi-vamp-prior-p",
        type=int,
        default=METHOD_PARAM_DEFAULTS["destvi"]["vamp_prior_p"],
    )

    parser.add_argument(
        "--stereoscope-rna-epochs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["stereoscope"]["rna_epochs"],
    )
    parser.add_argument(
        "--stereoscope-spatial-epochs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["stereoscope"]["spatial_epochs"],
    )
    parser.add_argument(
        "--stereoscope-learning-rate",
        type=float,
        default=METHOD_PARAM_DEFAULTS["stereoscope"]["learning_rate"],
    )
    parser.add_argument(
        "--stereoscope-batch-size",
        type=int,
        default=METHOD_PARAM_DEFAULTS["stereoscope"]["batch_size"],
    )

    parser.add_argument(
        "--tangram-n-epochs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["tangram"]["n_epochs"],
    )
    parser.add_argument(
        "--tangram-learning-rate",
        type=float,
        default=METHOD_PARAM_DEFAULTS["tangram"]["learning_rate"],
    )
    parser.add_argument(
        "--tangram-mode",
        choices=list(VALID_TANGRAM_MODES),
        default=METHOD_PARAM_DEFAULTS["tangram"]["mode"],
    )

    parser.add_argument(
        "--spotlight-n-top",
        type=int,
        default=METHOD_PARAM_DEFAULTS["spotlight"]["n_top"],
    )
    parser.add_argument(
        "--spotlight-weight-id",
        default=METHOD_PARAM_DEFAULTS["spotlight"]["weight_id"],
    )
    parser.add_argument(
        "--spotlight-model",
        choices=list(VALID_SPOTLIGHT_MODELS),
        default=METHOD_PARAM_DEFAULTS["spotlight"]["nmf_model"],
    )
    parser.add_argument(
        "--spotlight-min-prop",
        type=float,
        default=METHOD_PARAM_DEFAULTS["spotlight"]["min_prop"],
    )
    parser.add_argument(
        "--spotlight-scale",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["spotlight"]["scale"],
    )

    parser.add_argument(
        "--card-sample-key",
        default=METHOD_PARAM_DEFAULTS["card"]["sample_key"],
    )
    parser.add_argument(
        "--card-min-count-gene",
        type=int,
        default=METHOD_PARAM_DEFAULTS["card"]["min_count_gene"],
    )
    parser.add_argument(
        "--card-min-count-spot",
        type=int,
        default=METHOD_PARAM_DEFAULTS["card"]["min_count_spot"],
    )
    parser.add_argument(
        "--card-imputation",
        action="store_true",
        default=METHOD_PARAM_DEFAULTS["card"]["imputation"],
    )
    parser.add_argument(
        "--card-num-grids",
        type=int,
        default=METHOD_PARAM_DEFAULTS["card"]["num_grids"],
    )
    parser.add_argument(
        "--card-ineibor",
        type=int,
        default=METHOD_PARAM_DEFAULTS["card"]["ineibor"],
    )

    parser.add_argument("--n-epochs", type=int, default=None, help=argparse.SUPPRESS)
    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.demo:
        return
    if not args.input_path:
        parser.error("Provide --input or --demo")
    if args.input_path and not Path(args.input_path).exists():
        parser.error(f"Input file not found: {args.input_path}")

    cfg = METHOD_REGISTRY[args.method]
    if cfg.requires_reference and not args.reference:
        parser.error(f"--reference is required for method '{args.method}'")
    if args.reference and not Path(args.reference).exists():
        parser.error(f"Reference file not found: {args.reference}")

    positive_int_fields = (
        "flashdeconv_sketch_dim",
        "flashdeconv_n_hvg",
        "flashdeconv_n_markers_per_type",
        "cell2location_n_epochs",
        "cell2location_n_cells_per_spot",
        "destvi_n_epochs",
        "destvi_condscvi_epochs",
        "destvi_n_hidden",
        "destvi_n_latent",
        "destvi_n_layers",
        "destvi_vamp_prior_p",
        "stereoscope_rna_epochs",
        "stereoscope_spatial_epochs",
        "stereoscope_batch_size",
        "tangram_n_epochs",
        "spotlight_n_top",
        "card_min_count_gene",
        "card_min_count_spot",
        "card_num_grids",
        "card_ineibor",
    )
    for field in positive_int_fields:
        value = getattr(args, field, None)
        if value is not None and value <= 0:
            parser.error(f"{field.replace('_', '-')} must be > 0")

    if args.flashdeconv_lambda_spatial != "auto" and args.flashdeconv_lambda_spatial <= 0:
        parser.error("--flashdeconv-lambda-spatial must be > 0 or 'auto'")
    if args.cell2location_detection_alpha <= 0:
        parser.error("--cell2location-detection-alpha must be > 0")
    if not 0 <= args.destvi_dropout_rate < 1:
        parser.error("--destvi-dropout-rate must be in [0, 1)")
    if args.stereoscope_learning_rate <= 0:
        parser.error("--stereoscope-learning-rate must be > 0")
    if args.tangram_learning_rate <= 0:
        parser.error("--tangram-learning-rate must be > 0")
    if not 0 <= args.spotlight_min_prop <= 1:
        parser.error("--spotlight-min-prop must be in [0, 1]")
    if not str(args.spotlight_weight_id).strip():
        parser.error("--spotlight-weight-id cannot be empty")


def _resolve_legacy_epoch_overrides(args: argparse.Namespace) -> None:
    """Keep direct-script backward compatibility for the old generic --n-epochs flag."""
    if args.n_epochs is None:
        return

    logger.warning(
        "Generic --n-epochs is deprecated for spatial-deconv. Prefer method-specific flags."
    )
    if args.method == "cell2location":
        args.cell2location_n_epochs = args.n_epochs
    elif args.method == "destvi":
        args.destvi_n_epochs = args.n_epochs
    elif args.method == "tangram":
        args.tangram_n_epochs = args.n_epochs
    elif args.method == "stereoscope":
        args.stereoscope_rna_epochs = max(1, args.n_epochs // 2)
        args.stereoscope_spatial_epochs = max(1, args.n_epochs - args.stereoscope_rna_epochs)


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    params: dict[str, Any] = {
        "method": args.method,
        "reference": args.reference,
        "cell_type_key": args.cell_type_key,
    }
    method_kwargs: dict[str, Any] = {
        "reference_path": args.reference,
        "cell_type_key": args.cell_type_key,
    }

    if args.method == "flashdeconv":
        params.update(
            {
                "flashdeconv_sketch_dim": args.flashdeconv_sketch_dim,
                "flashdeconv_lambda_spatial": args.flashdeconv_lambda_spatial,
                "flashdeconv_n_hvg": args.flashdeconv_n_hvg,
                "flashdeconv_n_markers_per_type": args.flashdeconv_n_markers_per_type,
            }
        )
        method_kwargs.update(
            {
                "sketch_dim": args.flashdeconv_sketch_dim,
                "lambda_spatial": args.flashdeconv_lambda_spatial,
                "n_hvg": args.flashdeconv_n_hvg,
                "n_markers_per_type": args.flashdeconv_n_markers_per_type,
            }
        )
    elif args.method == "cell2location":
        params.update(
            {
                "cell2location_n_epochs": args.cell2location_n_epochs,
                "cell2location_n_cells_per_spot": args.cell2location_n_cells_per_spot,
                "cell2location_detection_alpha": args.cell2location_detection_alpha,
                "no_gpu": args.no_gpu,
            }
        )
        method_kwargs.update(
            {
                "n_epochs": args.cell2location_n_epochs,
                "n_cells_per_spot": args.cell2location_n_cells_per_spot,
                "detection_alpha": args.cell2location_detection_alpha,
                "use_gpu": not args.no_gpu,
            }
        )
    elif args.method == "rctd":
        params["rctd_mode"] = args.rctd_mode
        method_kwargs["mode"] = args.rctd_mode
    elif args.method == "destvi":
        params.update(
            {
                "destvi_n_epochs": args.destvi_n_epochs,
                "destvi_condscvi_epochs": args.destvi_condscvi_epochs,
                "destvi_n_hidden": args.destvi_n_hidden,
                "destvi_n_latent": args.destvi_n_latent,
                "destvi_n_layers": args.destvi_n_layers,
                "destvi_dropout_rate": args.destvi_dropout_rate,
                "destvi_vamp_prior_p": args.destvi_vamp_prior_p,
                "no_gpu": args.no_gpu,
            }
        )
        method_kwargs.update(
            {
                "n_epochs": args.destvi_n_epochs,
                "condscvi_epochs": args.destvi_condscvi_epochs,
                "n_hidden": args.destvi_n_hidden,
                "n_latent": args.destvi_n_latent,
                "n_layers": args.destvi_n_layers,
                "dropout_rate": args.destvi_dropout_rate,
                "vamp_prior_p": args.destvi_vamp_prior_p,
                "use_gpu": not args.no_gpu,
            }
        )
    elif args.method == "stereoscope":
        params.update(
            {
                "stereoscope_rna_epochs": args.stereoscope_rna_epochs,
                "stereoscope_spatial_epochs": args.stereoscope_spatial_epochs,
                "stereoscope_learning_rate": args.stereoscope_learning_rate,
                "stereoscope_batch_size": args.stereoscope_batch_size,
                "no_gpu": args.no_gpu,
            }
        )
        method_kwargs.update(
            {
                "rna_epochs": args.stereoscope_rna_epochs,
                "spatial_epochs": args.stereoscope_spatial_epochs,
                "learning_rate": args.stereoscope_learning_rate,
                "batch_size": args.stereoscope_batch_size,
                "use_gpu": not args.no_gpu,
            }
        )
    elif args.method == "tangram":
        params.update(
            {
                "tangram_n_epochs": args.tangram_n_epochs,
                "tangram_learning_rate": args.tangram_learning_rate,
                "tangram_mode": args.tangram_mode,
                "no_gpu": args.no_gpu,
            }
        )
        method_kwargs.update(
            {
                "n_epochs": args.tangram_n_epochs,
                "learning_rate": args.tangram_learning_rate,
                "mode": args.tangram_mode,
                "use_gpu": not args.no_gpu,
            }
        )
    elif args.method == "spotlight":
        params.update(
            {
                "spotlight_n_top": args.spotlight_n_top,
                "spotlight_weight_id": args.spotlight_weight_id,
                "spotlight_model": args.spotlight_model,
                "spotlight_min_prop": args.spotlight_min_prop,
                "spotlight_scale": args.spotlight_scale,
            }
        )
        method_kwargs.update(
            {
                "n_top": args.spotlight_n_top,
                "weight_id": args.spotlight_weight_id,
                "nmf_model": args.spotlight_model,
                "min_prop": args.spotlight_min_prop,
                "scale": args.spotlight_scale,
            }
        )
    else:
        params.update(
            {
                "card_sample_key": args.card_sample_key,
                "card_min_count_gene": args.card_min_count_gene,
                "card_min_count_spot": args.card_min_count_spot,
                "card_imputation": args.card_imputation,
                "card_num_grids": args.card_num_grids,
                "card_ineibor": args.card_ineibor,
            }
        )
        method_kwargs.update(
            {
                "sample_key": args.card_sample_key,
                "min_count_gene": args.card_min_count_gene,
                "min_count_spot": args.card_min_count_spot,
                "imputation": args.card_imputation,
                "num_grids": args.card_num_grids,
                "ineibor": args.card_ineibor,
            }
        )

    return params, method_kwargs


# ---------------------------------------------------------------------------
# Gallery helpers
# ---------------------------------------------------------------------------


def _prepare_deconv_plot_state(adata) -> str | None:
    """Ensure deconvolution outputs share the standard spatial aliases."""
    spatial_key = get_spatial_key(adata)
    if spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = adata.obsm["spatial"].copy()
    elif spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm["X_spatial"].copy()
    return get_spatial_key(adata)


def _ensure_umap_for_gallery(adata) -> None:
    """Compute a fallback UMAP so the standard gallery can expose an embedding view."""
    if "X_umap" in adata.obsm or adata.n_obs < 3:
        return

    try:
        if "connectivities" not in adata.obsp:
            n_neighbors = max(2, min(15, adata.n_obs - 1))
            if "X_pca" in adata.obsm:
                sc.pp.neighbors(adata, use_rep="X_pca", n_neighbors=n_neighbors)
            else:
                sc.pp.neighbors(adata, n_neighbors=n_neighbors)
        sc.tl.umap(adata)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Could not compute UMAP for deconvolution gallery: %s", exc)


def _align_proportions_to_obs(adata, prop_df: pd.DataFrame) -> pd.DataFrame:
    """Align a deconvolution proportion matrix to ``adata.obs_names``."""
    aligned = prop_df.copy()
    aligned.index = aligned.index.astype(str)
    aligned.columns = aligned.columns.astype(str)
    obs_names = pd.Index(adata.obs_names.astype(str))

    if aligned.index.equals(obs_names):
        return aligned

    if not obs_names.isin(aligned.index).all():
        missing = obs_names[~obs_names.isin(aligned.index)].tolist()[:5]
        raise ValueError(
            "Deconvolution proportions do not cover all observations in AnnData. "
            f"Missing examples: {missing}"
        )

    return aligned.loc[obs_names].copy()


def _extract_proportions_from_adata(adata, method: str | None) -> pd.DataFrame:
    """Reconstruct the stored deconvolution proportion matrix from ``adata``."""
    available_methods = [
        str(key)[len("deconvolution_"):]
        for key in adata.obsm.keys()
        if str(key).startswith("deconvolution_")
    ]
    if method is None:
        if len(available_methods) != 1:
            raise ValueError(
                "Could not infer deconvolution method from AnnData. "
                f"Available stored results: {available_methods}"
            )
        method = available_methods[0]

    prop_key = f"deconvolution_{method}"
    if prop_key not in adata.obsm:
        raise ValueError(f"Stored deconvolution matrix '{prop_key}' not found in adata.obsm")

    cell_types = adata.uns.get(f"{prop_key}_cell_types")
    if cell_types is None:
        n_cell_types = int(np.asarray(adata.obsm[prop_key]).shape[1])
        cell_types = [f"CellType_{idx}" for idx in range(n_cell_types)]

    return pd.DataFrame(
        np.asarray(adata.obsm[prop_key]),
        index=adata.obs_names.astype(str),
        columns=[str(cell_type) for cell_type in cell_types],
    )


def _build_spot_metrics_table(prop_df: pd.DataFrame) -> pd.DataFrame:
    """Derive dominant-type and uncertainty summaries from per-spot proportions."""
    columns = [
        "spot",
        "dominant_cell_type",
        "dominant_proportion",
        "second_cell_type",
        "second_proportion",
        "assignment_margin",
        "shannon_entropy",
        "normalized_entropy",
    ]
    if prop_df.empty:
        return pd.DataFrame(columns=columns)

    value_matrix = np.nan_to_num(prop_df.to_numpy(dtype=float), nan=0.0)
    value_matrix = np.clip(value_matrix, a_min=0.0, a_max=None)
    cell_types = prop_df.columns.to_numpy(dtype=object)
    n_spots = value_matrix.shape[0]

    dominant_idx = value_matrix.argmax(axis=1)
    dominant_type = cell_types[dominant_idx]
    dominant_prop = value_matrix[np.arange(n_spots), dominant_idx]

    if value_matrix.shape[1] > 1:
        rank_idx = np.argsort(value_matrix, axis=1)
        second_idx = rank_idx[:, -2]
        second_type = cell_types[second_idx]
        second_prop = value_matrix[np.arange(n_spots), second_idx]

        row_sums = value_matrix.sum(axis=1, keepdims=True)
        normalized = np.divide(
            value_matrix,
            row_sums,
            out=np.zeros_like(value_matrix),
            where=row_sums > 0,
        )
        entropy_input = np.clip(normalized, 1e-10, None)
        shannon_entropy = -(entropy_input * np.log2(entropy_input)).sum(axis=1)
        normalized_entropy = shannon_entropy / math.log2(value_matrix.shape[1])
    else:
        second_type = np.repeat("", n_spots)
        second_prop = np.zeros(n_spots)
        shannon_entropy = np.zeros(n_spots)
        normalized_entropy = np.zeros(n_spots)

    return pd.DataFrame(
        {
            "spot": prop_df.index.astype(str),
            "dominant_cell_type": dominant_type,
            "dominant_proportion": dominant_prop,
            "second_cell_type": second_type,
            "second_proportion": second_prop,
            "assignment_margin": dominant_prop - second_prop,
            "shannon_entropy": shannon_entropy,
            "normalized_entropy": normalized_entropy,
        }
    )


def _build_dominant_counts_table(spot_metrics_df: pd.DataFrame) -> pd.DataFrame:
    if spot_metrics_df.empty:
        return pd.DataFrame(columns=["dominant_cell_type", "n_spots", "proportion_percent"])

    counts = spot_metrics_df["dominant_cell_type"].astype(str).value_counts()
    total = max(int(counts.sum()), 1)
    return pd.DataFrame(
        [
            {
                "dominant_cell_type": cell_type,
                "n_spots": int(count),
                "proportion_percent": round(count / total * 100.0, 2),
            }
            for cell_type, count in counts.items()
        ]
    )


def _annotate_deconv_metrics_to_obs(
    adata,
    method: str,
    spot_metrics_df: pd.DataFrame,
) -> dict[str, str]:
    """Write deconvolution-derived metrics back to ``adata.obs`` for plotting/export."""
    prefix = f"deconv_{method}"
    obs_names = pd.Index(adata.obs_names.astype(str))
    indexed = spot_metrics_df.set_index("spot").reindex(obs_names)

    mapping = {
        "dominant_label_col": ("dominant_cell_type", f"{prefix}_dominant_cell_type"),
        "dominant_proportion_col": ("dominant_proportion", f"{prefix}_dominant_proportion"),
        "second_label_col": ("second_cell_type", f"{prefix}_second_cell_type"),
        "second_proportion_col": ("second_proportion", f"{prefix}_second_proportion"),
        "assignment_margin_col": ("assignment_margin", f"{prefix}_assignment_margin"),
        "entropy_col": ("shannon_entropy", f"{prefix}_shannon_entropy"),
        "normalized_entropy_col": ("normalized_entropy", f"{prefix}_normalized_entropy"),
    }

    resolved: dict[str, str] = {}
    for context_key, (source_col, obs_col) in mapping.items():
        if source_col not in indexed.columns:
            continue
        series = indexed[source_col]
        if "cell_type" in source_col:
            adata.obs[obs_col] = pd.Categorical(series.fillna("unassigned").astype(str))
        else:
            adata.obs[obs_col] = pd.to_numeric(series, errors="coerce").fillna(0.0)
        resolved[context_key] = obs_col

    return resolved


def _build_run_summary_table(summary: dict[str, Any], context: dict[str, Any]) -> pd.DataFrame:
    spot_metrics_df = context.get("spot_metrics_df", pd.DataFrame())
    mean_margin = (
        float(pd.to_numeric(spot_metrics_df["assignment_margin"], errors="coerce").mean())
        if not spot_metrics_df.empty
        else 0.0
    )
    mean_entropy = (
        float(pd.to_numeric(spot_metrics_df["normalized_entropy"], errors="coerce").mean())
        if not spot_metrics_df.empty
        else 0.0
    )

    rows = [
        {"metric": "method", "value": summary.get("method")},
        {"metric": "reference", "value": summary.get("reference")},
        {"metric": "cell_type_key", "value": summary.get("cell_type_key")},
        {"metric": "n_spots", "value": summary.get("n_spots")},
        {"metric": "n_cell_types", "value": summary.get("n_cell_types")},
        {"metric": "n_common_genes", "value": summary.get("n_common_genes")},
        {"metric": "device", "value": summary.get("device")},
        {"metric": "prop_key", "value": context.get("prop_key")},
        {"metric": "dominant_label_column", "value": context.get("dominant_label_col")},
        {"metric": "dominant_proportion_column", "value": context.get("dominant_proportion_col")},
        {"metric": "normalized_entropy_column", "value": context.get("normalized_entropy_col")},
        {"metric": "assignment_margin_column", "value": context.get("assignment_margin_col")},
        {"metric": "mean_assignment_margin", "value": mean_margin},
        {"metric": "mean_normalized_entropy", "value": mean_entropy},
    ]
    return pd.DataFrame(rows)


def _build_projection_export_table(adata, basis: str, context: dict[str, Any]) -> pd.DataFrame | None:
    if basis == "spatial":
        if "spatial" not in adata.obsm:
            return None
        coords = np.asarray(adata.obsm["spatial"])
        df = pd.DataFrame(
            {
                "observation": adata.obs_names.astype(str),
                "x": coords[:, 0],
                "y": coords[:, 1],
            }
        )
    elif basis == "umap":
        if "X_umap" not in adata.obsm:
            return None
        coords = np.asarray(adata.obsm["X_umap"])
        if coords.shape[1] < 2:
            return None
        df = pd.DataFrame(
            {
                "observation": adata.obs_names.astype(str),
                "umap_1": coords[:, 0],
                "umap_2": coords[:, 1],
            }
        )
    else:
        raise ValueError(f"Unsupported basis '{basis}'")

    for column in (
        context.get("dominant_label_col"),
        context.get("dominant_proportion_col"),
        context.get("second_label_col"),
        context.get("second_proportion_col"),
        context.get("assignment_margin_col"),
        context.get("entropy_col"),
        context.get("normalized_entropy_col"),
    ):
        if column and column in adata.obs.columns:
            series = adata.obs[column]
            if pd.api.types.is_numeric_dtype(series):
                df[column] = pd.to_numeric(series, errors="coerce").fillna(0.0).to_numpy()
            else:
                df[column] = series.astype(str).to_numpy()
    return df


def _prepare_deconv_gallery_context(
    adata,
    prop_df: pd.DataFrame,
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Prepare shared state for the standard Python deconvolution gallery."""
    aligned_prop_df = _align_proportions_to_obs(adata, prop_df)
    spatial_key = _prepare_deconv_plot_state(adata)
    _ensure_umap_for_gallery(adata)

    aux_tables = _build_aux_tables(aligned_prop_df)
    spot_metrics_df = _build_spot_metrics_table(aligned_prop_df)
    dominant_counts_df = _build_dominant_counts_table(spot_metrics_df)
    prop_key = f"deconvolution_{summary.get('method')}"

    summary.setdefault("n_spots", int(aligned_prop_df.shape[0]))
    summary.setdefault("n_cell_types", int(aligned_prop_df.shape[1]))
    summary.setdefault("cell_types", list(aligned_prop_df.columns))
    if "dominant_types" not in summary:
        summary["dominant_types"] = {
            row["dominant_cell_type"]: int(row["n_spots"])
            for row in dominant_counts_df.to_dict(orient="records")
        }

    context: dict[str, Any] = {
        "method": summary.get("method"),
        "reference": summary.get("reference"),
        "cell_type_key": summary.get("cell_type_key"),
        "spatial_key": spatial_key,
        "prop_key": prop_key,
        "cell_types_key": f"{prop_key}_cell_types",
        "prop_df": aligned_prop_df,
        "spot_metrics_df": spot_metrics_df,
        "dominant_counts_df": dominant_counts_df,
        "aux_tables": aux_tables,
        "mean_proportions_df": aux_tables["mean_proportions.csv"],
    }
    context.update(_annotate_deconv_metrics_to_obs(adata, str(summary.get("method")), spot_metrics_df))
    return context


def _build_deconv_visualization_recipe(
    adata,
    summary: dict[str, Any],
    context: dict[str, Any],
) -> VisualizationRecipe:
    plots: list[PlotSpec] = [
        PlotSpec(
            plot_id="deconv_spatial_proportions",
            role="overview",
            renderer="deconvolution_plot",
            filename="spatial_proportions.png",
            title="Spatial Cell Type Proportions",
            description="Canonical multi-panel tissue map of per-cell-type deconvolution proportions.",
            params={
                "subtype": "spatial_multi",
                "colormap": "viridis",
                "figure_size": (13, 9),
            },
            required_obsm=[context["prop_key"], "spatial"],
            required_uns=[context["cell_types_key"]],
        ),
        PlotSpec(
            plot_id="deconv_dominant_celltype",
            role="overview",
            renderer="deconvolution_plot",
            filename="dominant_celltype.png",
            title="Dominant Cell Type per Spot",
            description="Argmax cell type label at each spatial location.",
            params={
                "subtype": "dominant",
                "colormap": "tab20",
                "figure_size": (10, 8),
            },
            required_obsm=[context["prop_key"], "spatial"],
            required_uns=[context["cell_types_key"]],
        ),
        PlotSpec(
            plot_id="deconv_diversity_spatial",
            role="diagnostic",
            renderer="deconvolution_plot",
            filename="celltype_diversity.png",
            title="Cell Type Diversity on Tissue",
            description="Normalized Shannon entropy of the proportion vector at each spot.",
            params={
                "subtype": "diversity",
                "colormap": "magma",
                "figure_size": (10, 8),
            },
            required_obsm=[context["prop_key"], "spatial"],
            required_uns=[context["cell_types_key"]],
        ),
    ]

    if "X_umap" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="deconv_umap_proportions",
                role="diagnostic",
                renderer="deconvolution_plot",
                filename="umap_proportions.png",
                title="Deconvolution Proportions on UMAP",
                description="Embedding view of the deconvolution composition for cross-spot comparison.",
                params={
                    "subtype": "umap",
                    "figure_size": (12, 9),
                },
                required_obsm=[context["prop_key"], "X_umap"],
                required_uns=[context["cell_types_key"]],
            )
        )

    if context.get("assignment_margin_col") and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="deconv_assignment_margin_spatial",
                role="uncertainty",
                renderer="feature_map",
                filename="assignment_margin_spatial.png",
                title="Assignment Margin on Tissue",
                description="Top1 minus top2 proportion, highlighting ambiguous spatial spots.",
                params={
                    "feature": context["assignment_margin_col"],
                    "basis": "spatial",
                    "colormap": "magma",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (10, 8),
                },
                required_obs=[context["assignment_margin_col"]],
                required_obsm=["spatial"],
            )
        )

    if not context["mean_proportions_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="deconv_mean_proportions",
                role="supporting",
                renderer="mean_proportions_barplot",
                filename="mean_proportions.png",
                title="Average Cell Type Proportions",
                description="Mean contribution of each inferred cell type across all spatial spots.",
            )
        )

    if not context["dominant_counts_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="deconv_dominant_distribution",
                role="supporting",
                renderer="dominant_counts_barplot",
                filename="dominant_celltype_distribution.png",
                title="Dominant Cell Type Distribution",
                description="Number of spots for which each cell type is the dominant assignment.",
            )
        )

    if context.get("assignment_margin_col"):
        plots.append(
            PlotSpec(
                plot_id="deconv_assignment_margin_histogram",
                role="uncertainty",
                renderer="assignment_margin_histogram",
                filename="assignment_margin_distribution.png",
                title="Assignment Margin Distribution",
                description="Distribution of deconvolution confidence measured as top1 minus top2 proportion.",
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-deconv-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Deconvolution Standard Gallery",
        description=(
            "Default OmicsClaw deconvolution story plots: proportion overviews, "
            "diagnostic diversity and embedding views, supporting composition "
            "summaries, and uncertainty panels based on assignment confidence."
        ),
        plots=plots,
    )


def _render_deconvolution_plot(adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    params = dict(spec.params)
    params.setdefault("title", spec.title)
    subtype = params.pop("subtype", None)
    return plot_deconvolution(
        adata,
        VizParams(**params),
        subtype=subtype,
        method=context.get("method"),
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict[str, Any]) -> object:
    params = dict(spec.params)
    params.setdefault("title", spec.title)
    return plot_features(adata, VizParams(**params))


def _render_mean_proportions_barplot(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    import matplotlib.pyplot as plt

    mean_df = context.get("mean_proportions_df", pd.DataFrame())
    if mean_df.empty:
        return None

    plot_df = mean_df.sort_values("mean_proportion", ascending=True).copy()
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.5, max(4.5, len(plot_df) * 0.42))),
        dpi=int(spec.params.get("dpi", 200)),
    )
    ax.barh(plot_df["cell_type"], plot_df["mean_proportion"], color="#e34a33")
    ax.set_xlabel("Mean proportion")
    ax.set_title(spec.title or "Average Cell Type Proportions")
    fig.tight_layout()
    return fig


def _render_dominant_counts_barplot(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    import matplotlib.pyplot as plt

    counts_df = context.get("dominant_counts_df", pd.DataFrame())
    if counts_df.empty:
        return None

    plot_df = counts_df.sort_values("n_spots", ascending=True).copy()
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.5, max(4.5, len(plot_df) * 0.42))),
        dpi=int(spec.params.get("dpi", 200)),
    )
    ax.barh(plot_df["dominant_cell_type"], plot_df["n_spots"], color="#3182bd")
    ax.set_xlabel("Number of spots")
    ax.set_title(spec.title or "Dominant Cell Type Distribution")
    fig.tight_layout()
    return fig


def _render_assignment_margin_histogram(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    import matplotlib.pyplot as plt

    spot_metrics_df = context.get("spot_metrics_df", pd.DataFrame())
    if spot_metrics_df.empty:
        return None

    margins = pd.to_numeric(spot_metrics_df["assignment_margin"], errors="coerce").fillna(0.0)
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8, 5)),
        dpi=int(spec.params.get("dpi", 200)),
    )
    ax.hist(margins, bins=24, color="#756bb1", edgecolor="white")
    ax.axvline(float(margins.median()), color="black", linestyle="--", linewidth=1.1)
    ax.set_xlabel("Top1 - Top2 proportion")
    ax.set_ylabel("Number of spots")
    ax.set_title(spec.title or "Assignment Margin Distribution")
    fig.tight_layout()
    return fig


DECONV_GALLERY_RENDERERS = {
    "deconvolution_plot": _render_deconvolution_plot,
    "feature_map": _render_feature_map,
    "mean_proportions_barplot": _render_mean_proportions_barplot,
    "dominant_counts_barplot": _render_dominant_counts_barplot,
    "assignment_margin_histogram": _render_assignment_margin_histogram,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict[str, Any]) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def _export_figure_data(
    adata,
    output_dir: Path,
    summary: dict[str, Any],
    recipe: VisualizationRecipe,
    artifacts: list,
    context: dict[str, Any],
) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    prop_df = context["prop_df"]
    spot_metrics_df = context["spot_metrics_df"]
    dominant_counts_df = context["dominant_counts_df"]
    aux_tables = context["aux_tables"]
    mean_df = context["mean_proportions_df"]

    export_prop_df = prop_df.copy()
    export_prop_df.insert(0, "spot", prop_df.index.astype(str))
    export_prop_df.to_csv(figure_data_dir / "proportions.csv", index=False)

    spot_metrics_df.to_csv(figure_data_dir / "deconv_spot_metrics.csv", index=False)
    dominant_counts_df.to_csv(figure_data_dir / "dominant_celltype_counts.csv", index=False)
    aux_tables["dominant_celltype.csv"].to_csv(figure_data_dir / "dominant_celltype.csv", index=False)
    aux_tables["celltype_diversity.csv"].to_csv(figure_data_dir / "celltype_diversity.csv", index=False)
    mean_df.to_csv(figure_data_dir / "mean_proportions.csv", index=False)
    _build_run_summary_table(summary, context).to_csv(figure_data_dir / "deconv_run_summary.csv", index=False)

    spatial_file = None
    spatial_df = _build_projection_export_table(adata, "spatial", context)
    if spatial_df is not None:
        spatial_file = "deconv_spatial_points.csv"
        spatial_df.to_csv(figure_data_dir / spatial_file, index=False)

    umap_file = None
    umap_df = _build_projection_export_table(adata, "umap", context)
    if umap_df is not None:
        umap_file = "deconv_umap_points.csv"
        umap_df.to_csv(figure_data_dir / umap_file, index=False)

    extra_tables = summary.get("extra_tables", {})
    extra_table_name_map = {
        "card_refined_proportions": "card_refined_proportions.csv",
    }
    exported_extra_files: dict[str, str] = {}
    for key, df in extra_tables.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            filename = extra_table_name_map.get(key, f"{key}.csv")
            df.to_csv(figure_data_dir / filename)
            exported_extra_files[key] = filename

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary.get("method"),
        "reference": summary.get("reference"),
        "cell_type_key": summary.get("cell_type_key"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": list(dict.fromkeys(spec.role for spec in recipe.plots)),
        "prop_key": context.get("prop_key"),
        "available_files": {
            "proportions": "proportions.csv",
            "deconv_spot_metrics": "deconv_spot_metrics.csv",
            "dominant_celltype": "dominant_celltype.csv",
            "celltype_diversity": "celltype_diversity.csv",
            "mean_proportions": "mean_proportions.csv",
            "dominant_celltype_counts": "dominant_celltype_counts.csv",
            "deconv_run_summary": "deconv_run_summary.csv",
            "deconv_spatial_points": spatial_file,
            "deconv_umap_points": umap_file,
            **exported_extra_files,
        },
        "gallery_outputs": [
            {
                "plot_id": artifact.plot_id,
                "role": artifact.role,
                "filename": artifact.filename,
                "status": artifact.status,
            }
            for artifact in artifacts
        ],
    }
    _write_figure_data_manifest(output_dir, contract)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(
    adata,
    output_dir: Path,
    summary: dict[str, Any],
    *,
    gallery_context: dict[str, Any] | None = None,
) -> list[str]:
    """Render the standard deconvolution gallery and export figure-ready data."""
    if gallery_context is None:
        prop_df = _extract_proportions_from_adata(adata, summary.get("method"))
        context = _prepare_deconv_gallery_context(adata, prop_df, summary)
    else:
        context = gallery_context
    recipe = _build_deconv_visualization_recipe(adata, summary, context)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        DECONV_GALLERY_RENDERERS,
        context=runtime_context,
    )
    _export_figure_data(adata, output_dir, summary, recipe, artifacts, context)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


def _build_aux_tables(prop_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    spot_metrics_df = _build_spot_metrics_table(prop_df)
    return {
        "dominant_celltype.csv": spot_metrics_df.loc[
            :,
            ["spot", "dominant_cell_type", "dominant_proportion"],
        ].copy(),
        "celltype_diversity.csv": spot_metrics_df.loc[
            :,
            ["spot", "shannon_entropy", "normalized_entropy"],
        ].copy(),
        "mean_proportions.csv": pd.DataFrame(
            {
                "cell_type": prop_df.columns.astype(str),
                "mean_proportion": prop_df.mean(axis=0).to_numpy(),
            }
        ),
    }


def _append_cli_flag(command: str, key: str, value: Any) -> str:
    if key == "no_gpu":
        return f"{command} --no-gpu" if value else command
    if key == "spotlight_scale":
        return f"{command} {'--spotlight-scale' if value else '--no-spotlight-scale'}"
    flag = f"--{key.replace('_', '-')}"
    if isinstance(value, bool):
        return f"{command} {flag}" if value else command
    if value in (None, ""):
        return command
    return f"{command} {flag} {shlex.quote(str(value))}"


def export_tables(
    output_dir: Path,
    summary: dict[str, Any],
    context: dict[str, Any],
) -> list[str]:
    """Write stable tabular outputs for downstream analysis and reproducibility."""
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    exported: list[str] = []
    prop_df = context["prop_df"]
    export_prop_df = prop_df.copy()
    export_prop_df.insert(0, "spot", prop_df.index.astype(str))
    prop_path = tables_dir / "proportions.csv"
    export_prop_df.to_csv(prop_path, index=False)
    exported.append(str(prop_path))

    for filename, df in context["aux_tables"].items():
        path = tables_dir / filename
        df.to_csv(path, index=False)
        exported.append(str(path))

    spot_metrics_path = tables_dir / "deconv_spot_metrics.csv"
    context["spot_metrics_df"].to_csv(spot_metrics_path, index=False)
    exported.append(str(spot_metrics_path))

    dominant_counts_path = tables_dir / "dominant_celltype_counts.csv"
    context["dominant_counts_df"].to_csv(dominant_counts_path, index=False)
    exported.append(str(dominant_counts_path))

    extra_tables = summary.get("extra_tables", {})
    extra_table_name_map = {
        "card_refined_proportions": "card_refined_proportions.csv",
    }
    for key, df in extra_tables.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            path = tables_dir / extra_table_name_map.get(key, f"{key}.csv")
            df.to_csv(path)
            exported.append(str(path))

    return exported


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-deconv"
        / "r_visualization"
        / "deconv_publication_template.R"
    )
    cmd = f"Rscript {shlex.quote(str(r_template))} {shlex.quote(str(output_dir))}"
    (repro_dir / "r_visualization.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def write_report(
    output_dir: Path,
    summary: dict[str, Any],
    input_file: str | None,
    params: dict[str, Any],
    *,
    gallery_context: dict[str, Any] | None = None,
) -> None:
    header = generate_report_header(
        title="Spatial Deconvolution Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", ""),
            "Reference": params.get("reference", ""),
            "Cell type key": params.get("cell_type_key", ""),
            "Device": summary.get("device", ""),
        },
    )

    lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Spots**: {summary['n_spots']}",
        f"- **Cell types**: {summary['n_cell_types']}",
        f"- **Common genes**: {summary.get('n_common_genes', 'n/a')}",
        f"- **Device**: {summary.get('device', 'cpu')}",
    ]

    if gallery_context and gallery_context.get("prop_key"):
        lines.append(f"- **Stored proportion matrix**: `{gallery_context['prop_key']}`")
    if gallery_context and gallery_context.get("assignment_margin_col"):
        lines.append(f"- **Assignment margin column**: `{gallery_context['assignment_margin_col']}`")
    if gallery_context and gallery_context.get("normalized_entropy_col"):
        lines.append(f"- **Normalized entropy column**: `{gallery_context['normalized_entropy_col']}`")

    dominant_types = summary.get("dominant_types", {})
    if dominant_types:
        lines.extend(["", "### Dominant Cell Type Distribution\n"])
        for cell_type, n_spots in sorted(dominant_types.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- **{cell_type}**: {n_spots} spots")

    lines.extend(["", "## Parameters\n"])
    for key, value in params.items():
        lines.append(f"- `{key}`: {value}")

    effective_params = summary.get("effective_params", {})
    if effective_params:
        lines.extend(["", "### Effective Method Parameters\n"])
        for key, value in effective_params.items():
            lines.append(f"- `{key}`: {value}")

    extra_tables = summary.get("extra_tables", {})
    if extra_tables:
        lines.extend(["", "### Method-Specific Extra Outputs\n"])
        for key in sorted(extra_tables):
            lines.append(f"- `{key}`")

    lines.extend(["", "## Interpretation Notes\n"])
    lines.extend(
        [
            "- Dominant cell type is the argmax of the exported per-spot proportion vector.",
            "- Normalized entropy near 0 indicates a sharper single-type assignment; values near 1 indicate diffuse mixtures.",
            "- Assignment margin (`top1 - top2`) is the standard OmicsClaw uncertainty proxy for ambiguous spots.",
        ]
    )
    if summary.get("method") in COUNT_BASED_METHODS:
        lines.append("- This backend is count-based; interpret outputs in the context of raw-count fidelity and reference quality.")
    elif summary.get("method") in NONNEGATIVE_EXPRESSION_METHODS:
        lines.append("- This backend assumes non-negative normalized expression, so preprocessing choices directly affect the inferred fractions.")

    lines.extend(
        [
            "",
            "## Visualization Outputs\n",
            "- `figures/manifest.json`: Standard Python gallery manifest",
            "- `figure_data/`: Figure-ready CSV exports for downstream customization",
            "- `reproducibility/r_visualization.sh`: Optional R visualization entrypoint",
        ]
    )

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(lines) + "\n" + footer)

    summary_for_json = {
        key: value
        for key, value in summary.items()
        if key not in {"extra_tables", "proportions_df"}
    }
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data: dict[str, Any] = {
        "params": params,
        "effective_params": effective_params,
    }
    if gallery_context:
        result_data["visualization"] = {
            "recipe_id": "standard-spatial-deconv-gallery",
            "prop_key": gallery_context.get("prop_key"),
            "dominant_label_column": gallery_context.get("dominant_label_col"),
            "dominant_proportion_column": gallery_context.get("dominant_proportion_col"),
            "normalized_entropy_column": gallery_context.get("normalized_entropy_col"),
            "assignment_margin_column": gallery_context.get("assignment_margin_col"),
        }
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary_for_json,
        data=result_data,
        input_checksum=checksum,
    )

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    command = (
        f"python {SCRIPT_REL_PATH} --input <input.h5ad> "
        f"--output {shlex.quote(str(output_dir))}"
    )
    for key, value in params.items():
        command = _append_cli_flag(command, key, value)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n")

    try:
        from importlib.metadata import version as get_version
    except ImportError:
        from importlib_metadata import version as get_version  # type: ignore

    env_lines: list[str] = []
    for pkg in ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "scipy"]:
        try:
            env_lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            pass
        except Exception:
            pass

    optional_by_method = {
        "flashdeconv": ["flashdeconv"],
        "cell2location": ["cell2location", "scvi-tools", "torch"],
        "destvi": ["scvi-tools", "torch"],
        "stereoscope": ["scvi-tools", "torch"],
        "tangram": ["tangram-sc", "torch"],
        "rctd": [],
        "spotlight": [],
        "card": [],
    }
    for pkg in optional_by_method.get(params["method"], []):
        try:
            env_lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            pass
        except Exception:
            pass

    if params["method"] in {"rctd", "spotlight", "card"}:
        env_lines.append(
            "# R method used; record spacexr/SPOTlight/CARD package versions in the runtime R environment if needed."
        )

    (repro_dir / "environment.txt").write_text("\n".join(env_lines) + ("\n" if env_lines else ""))
    _write_r_visualization_helper(output_dir)


def _log_input_convention(method: str) -> None:
    if method in COUNT_BASED_METHODS:
        logger.info(
            "Method '%s' expects raw counts in `.X`, `layers['counts']`, or `adata.raw`.",
            method,
        )
    elif method in NONNEGATIVE_EXPRESSION_METHODS:
        logger.info(
            "Method '%s' expects normalized, non-negative expression matrices.",
            method,
        )
    elif method in FLEXIBLE_INPUT_METHODS:
        logger.info(
            "Method '%s' accepts a more flexible expression representation in the current wrapper.",
            method,
        )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.use_gpu and not args.no_gpu:
        logger.warning(
            "--use-gpu is deprecated. GPU is already the default for capable methods."
        )

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

    _resolve_legacy_epoch_overrides(args)
    _validate_args(parser, args)

    adata = sc.read_h5ad(args.input_path)
    params, method_kwargs = _collect_run_configuration(args)
    run_fn = METHOD_DISPATCH[args.method]

    logger.info("Running deconvolution: method=%s", args.method)
    _log_input_convention(args.method)

    prop_df, stats = run_fn(adata, **method_kwargs)
    stats.setdefault("method", args.method)
    prop_df = _align_proportions_to_obs(adata, prop_df)
    stats.setdefault("cell_type_key", args.cell_type_key)
    stats.setdefault("reference", args.reference)

    prop_key = f"deconvolution_{args.method}"
    adata.obsm[prop_key] = prop_df.to_numpy()
    adata.uns[f"{prop_key}_cell_types"] = list(prop_df.columns)
    adata.uns[f"{prop_key}_metadata"] = {
        "method": args.method,
        "reference": args.reference,
        "cell_type_key": args.cell_type_key,
        "effective_params": stats.get("effective_params", {}),
    }

    store_analysis_metadata(adata, SKILL_NAME, stats["method"], params=params)

    gallery_context = _prepare_deconv_gallery_context(adata, prop_df, stats)
    generate_figures(adata, output_dir, stats, gallery_context=gallery_context)
    export_tables(output_dir, stats, gallery_context)
    write_report(
        output_dir,
        stats,
        args.input_path,
        params,
        gallery_context=gallery_context,
    )

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved: %s", h5ad_path)

    print(
        f"Deconvolution complete: {stats['n_cell_types']} cell types via {stats['method']}"
    )


if __name__ == "__main__":
    main()
