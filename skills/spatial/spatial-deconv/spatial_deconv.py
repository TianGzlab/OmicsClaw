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
import logging
import sys
import warnings
from pathlib import Path

import pandas as pd

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
from skills.spatial._lib.adata_utils import (
    get_spatial_key,
    store_analysis_metadata,
)
from skills.spatial._lib.deconvolution import (
    DEFAULT_METHOD,
    METHOD_DISPATCH,
    METHOD_REGISTRY,
    SUPPORTED_METHODS,
)
from skills.spatial._lib.viz import VizParams, plot_deconvolution
from skills.spatial._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-deconv"
SKILL_VERSION = "0.2.0"


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

    run_fn = METHOD_DISPATCH[args.method]

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
