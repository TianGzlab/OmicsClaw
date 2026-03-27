#!/usr/bin/env python3
"""Spatial Statistics — comprehensive spatial analysis toolkit.

Core computations are in skills.spatial._lib.statistics.

Usage:
    oc run spatial-statistics --input <adata.h5ad> --output <dir> --analysis-type moran
    oc run spatial-statistics --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

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
    require_spatial_coords,
    store_analysis_metadata,
)
from skills.spatial._lib.statistics import (
    ANALYSIS_REGISTRY,
    CLUSTER_ANALYSES,
    VALID_ANALYSIS_TYPES,
)
from skills.spatial._lib.viz_utils import save_figure
from skills.spatial._lib.viz import VizParams, plot_spatial_stats

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-statistics"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Generate spatial statistics figures using the SpatialClaw viz library."""
    figures: list[str] = []
    analysis_type = summary.get("analysis_type", "")
    cluster_key = summary.get("cluster_key")

    viz_subtype_map = {
        "neighborhood_enrichment": ("neighborhood", "nhood_enrichment.png"),
        "co_occurrence": ("co_occurrence", "co_occurrence.png"),
        "ripley": ("ripley", "ripley.png"),
        "moran": ("moran", "moran_ranking.png"),
        "spatial_centrality": ("centrality", "centrality_scores.png"),
    }

    if analysis_type in viz_subtype_map:
        subtype, fname = viz_subtype_map[analysis_type]
        try:
            fig = plot_spatial_stats(
                adata,
                VizParams(cluster_key=cluster_key),
                subtype=subtype,
            )
            p = save_figure(fig, output_dir, fname)
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate %s figure: %s", analysis_type, exc)
    else:
        # Generic: try Moran ranking if available
        if "moranI" in adata.uns:
            try:
                fig = plot_spatial_stats(adata, subtype="moran")
                p = save_figure(fig, output_dir, "moran_ranking.png")
                figures.append(str(p))
            except Exception as exc:
                logger.warning("Could not generate Moran ranking: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write report.md, result.json, tables, reproducibility."""

    analysis_label = summary["analysis_type"].replace("_", " ").title()
    cluster_key = summary.get("cluster_key")
    extra_meta = {"Analysis": summary["analysis_type"]}
    if cluster_key:
        extra_meta["Cluster key"] = cluster_key
    header = generate_report_header(
        title=f"Spatial Statistics — {analysis_label}",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata=extra_meta,
    )

    body_lines = ["## Summary\n", f"- **Analysis**: {analysis_label}"]
    if cluster_key:
        body_lines.append(f"- **Cluster key**: `{cluster_key}`")
    if "n_clusters" in summary:
        body_lines.append(f"- **Clusters**: {summary['n_clusters']}")
    if "categories" in summary:
        body_lines.append(f"- **Categories**: {', '.join(str(c) for c in summary['categories'])}")

    if summary["analysis_type"] == "neighborhood_enrichment":
        body_lines.extend([
            "",
            "### Neighborhood Enrichment\n",
            f"- **Mean z-score**: {summary['mean_zscore']:.3f}",
            f"- **Max z-score**: {summary['max_zscore']:.3f}",
            f"- **Min z-score**: {summary['min_zscore']:.3f}",
            "",
            "Positive z-scores indicate spatial co-localisation (enrichment); "
            "negative z-scores indicate avoidance (depletion).",
            "",
            "See `tables/enrichment_zscore.csv` for the full z-score matrix.",
        ])

    elif summary["analysis_type"] == "ripley":
        body_lines.extend([
            "",
            "### Ripley's L Function\n",
            "L(r) > r indicates spatial clustering at distance r; "
            "L(r) < r indicates regularity/dispersion.",
        ])
        if summary.get("ripley_df") is not None:
            body_lines.append(f"- Results table rows: {len(summary['ripley_df'])}")

    elif summary["analysis_type"] == "co_occurrence":
        body_lines.extend([
            "",
            "### Co-occurrence\n",
            "Pairwise cluster co-occurrence ratios across spatial distance intervals.",
        ])

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer

    report_path = output_dir / "report.md"
    report_path.write_text(report)
    logger.info("Wrote %s", report_path)

    # result.json — exclude large non-serialisable objects
    serialisable = {
        k: v for k, v in summary.items()
        if k not in ("zscore_df", "ripley_df", "co_occ", "interval")
    }
    checksum = (
        sha256_file(input_file)
        if input_file and Path(input_file).exists()
        else ""
    )
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=serialisable,
        data={"params": params, **serialisable},
        input_checksum=checksum,
    )

    # tables/
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    if summary["analysis_type"] == "neighborhood_enrichment":
        summary["zscore_df"].to_csv(tables_dir / "enrichment_zscore.csv")
        logger.info("Wrote %s", tables_dir / "enrichment_zscore.csv")

    if summary["analysis_type"] == "ripley" and summary.get("ripley_df") is not None:
        summary["ripley_df"].to_csv(tables_dir / "ripley_L.csv", index=False)
        logger.info("Wrote %s", tables_dir / "ripley_L.csv")

    # reproducibility/
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd_parts: list[str] = [f"oc run spatial-statistics --input <input.h5ad> --output {output_dir}"]
    for k, v in params.items():
        if v is not None and not isinstance(v, bool):
            cmd_parts.append(f"--{str(k).replace('_', '-')} {v}")
        elif isinstance(v, bool) and v:
            cmd_parts.append(f"--{str(k).replace('_', '-')}")
            
    cmd_str = " ".join(cmd_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd_str}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore
    env_lines = []
    for pkg in ["squidpy", "scanpy", "anndata", "numpy", "pandas", "matplotlib", "scipy", "esda", "libpysal", "networkx"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            pass
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data — runs spatial-preprocess --demo via subprocess
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Run spatial-preprocess --demo to generate a preprocessed h5ad."""
    main_runner = _PROJECT_ROOT / "omicsclaw.py"

    if not main_runner.exists():
        raise FileNotFoundError(
            f"OmicsClaw runner not found at {main_runner}. "
            "Run from the OmicsClaw project root."
        )

    with tempfile.TemporaryDirectory(prefix="spatialstats_demo_") as demo_dir:
        demo_dir = Path(demo_dir)
        logger.info("Running spatial-preprocess --demo -> %s", demo_dir)

        result = subprocess.run(
            [sys.executable, str(main_runner), "run", "spatial-preprocess", "--demo", "--output", str(demo_dir)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            logger.error("spatial-preprocess failed:\n%s", result.stderr)
            raise RuntimeError(f"spatial-preprocess --demo failed (exit {result.returncode})")

        processed_path = demo_dir / "processed.h5ad"
        if not processed_path.exists():
            raise FileNotFoundError(
                f"Expected processed.h5ad at {processed_path} after spatial-preprocess"
            )

        adata = sc.read_h5ad(processed_path)
        return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Statistics — comprehensive spatial analysis toolkit",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--analysis-type",
        default="neighborhood_enrichment",
        choices=list(VALID_ANALYSIS_TYPES),
        help=f"Analysis type (default: neighborhood_enrichment). Options: {', '.join(VALID_ANALYSIS_TYPES)}",
    )
    parser.add_argument(
        "--cluster-key",
        default="leiden",
        help="obs column with cluster labels (default: leiden)",
    )
    parser.add_argument(
        "--genes",
        default=None,
        help="Comma-separated gene names for gene-level analyses (e.g. 'EPCAM,VIM')",
    )
    parser.add_argument(
        "--n-top-genes",
        type=int,
        default=20,
        help="Number of top genes to analyze if --genes not specified (default: 20)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        input_path = Path(args.input_path)
        if not input_path.exists():
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    require_spatial_coords(adata)

    analysis_type = args.analysis_type
    cluster_key = args.cluster_key

    if analysis_type in CLUSTER_ANALYSES and cluster_key not in adata.obs.columns:
        logger.error(
            "Cluster key '%s' not found in adata.obs for %s. Available: %s",
            cluster_key, analysis_type, list(adata.obs.columns),
        )
        sys.exit(1)

    gene_list = None
    if args.genes:
        gene_list = [g.strip() for g in args.genes.split(",") if g.strip()]

    params = {
        "analysis_type": analysis_type,
        "cluster_key": cluster_key,
        "genes": args.genes,
        "n_top_genes": args.n_top_genes,
    }

    run_fn = ANALYSIS_REGISTRY.get(analysis_type)
    if run_fn is None:
        print(f"ERROR: Unknown analysis type '{analysis_type}'", file=sys.stderr)
        sys.exit(1)

    summary = run_fn(
        adata,
        cluster_key=cluster_key,
        genes=gene_list,
        n_top_genes=args.n_top_genes,
    )

    store_analysis_metadata(
        adata, SKILL_NAME, analysis_type, params=params,
    )

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    analysis_label = analysis_type.replace("_", " ")
    print(f"Spatial statistics complete: {analysis_label}")


if __name__ == "__main__":
    main()
