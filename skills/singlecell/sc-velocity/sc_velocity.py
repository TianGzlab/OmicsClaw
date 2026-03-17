#!/usr/bin/env python3
"""Single-Cell RNA Velocity Analysis - scVelo velocity and latent time.

Usage:
    python sc_velocity.py --input <data.h5ad> --output <dir>
    python sc_velocity.py --demo --output <dir>

This skill requires spliced/unspliced layers in the AnnData object.
It performs RNA velocity analysis using scVelo:
- Velocity estimation (stochastic or dynamical mode)
- Velocity graph construction
- Velocity embedding visualization
- Latent time computation (dynamical mode only)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

# Fix for anndata >= 0.11 with StringArray
try:
    import anndata
    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json
from omicsclaw.common.checksums import sha256_file
from omicsclaw.singlecell.viz_utils import save_figure
from omicsclaw.singlecell import io as sc_io
from omicsclaw.singlecell import trajectory as sc_traj

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "singlecell-velocity"
SKILL_VERSION = "0.1.0"


def check_scvelo_available() -> bool:
    """Check if scVelo is available."""
    try:
        import scvelo
        return True
    except ImportError:
        return False


def generate_velocity_figures(adata, output_dir: Path) -> list[str]:
    """Generate velocity visualization figures."""
    figures = []
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Velocity stream plot
    try:
        logger.info("Generating velocity stream plot...")
        fig_path = sc_traj.plot_velocity_stream(
            adata,
            output_dir=figures_dir,
            basis="umap",
            title="RNA Velocity",
        )
        if fig_path:
            figures.append(fig_path)
    except Exception as e:
        logger.warning(f"Velocity stream plot failed: {e}")

    # Velocity UMAP
    try:
        import scanpy as sc
        import matplotlib.pyplot as plt

        logger.info("Generating velocity embedding UMAP...")
        fig, ax = plt.subplots(figsize=(10, 8))

        # Plot UMAP colored by velocity magnitude
        if "velocity" in adata.layers:
            velocity_magnitude = np.linalg.norm(adata.layers["velocity"], axis=1)
            adata.obs["velocity_magnitude"] = velocity_magnitude

            sc.pl.umap(
                adata,
                color="velocity_magnitude",
                ax=ax,
                show=False,
                cmap="viridis",
            )
            ax.set_title("Velocity Magnitude", fontsize=14, fontweight="bold")

            fig.tight_layout()
            fig_path = figures_dir / "velocity_magnitude_umap.png"
            fig.savefig(fig_path, dpi=300, bbox_inches="tight")
            figures.append(str(fig_path))
            plt.close()
            logger.info(f"  Saved: velocity_magnitude_umap.png")

            del adata.obs["velocity_magnitude"]
    except Exception as e:
        logger.warning(f"Velocity magnitude plot failed: {e}")

    # Latent time UMAP (if available)
    if "latent_time" in adata.obs.columns:
        try:
            import scanpy as sc
            import matplotlib.pyplot as plt

            logger.info("Generating latent time UMAP...")
            fig, ax = plt.subplots(figsize=(10, 8))
            sc.pl.umap(
                adata,
                color="latent_time",
                ax=ax,
                show=False,
                cmap="viridis",
            )
            ax.set_title("Latent Time", fontsize=14, fontweight="bold")

            fig.tight_layout()
            fig_path = figures_dir / "latent_time_umap.png"
            fig.savefig(fig_path, dpi=300, bbox_inches="tight")
            figures.append(str(fig_path))
            plt.close()
            logger.info(f"  Saved: latent_time_umap.png")
        except Exception as e:
            logger.warning(f"Latent time plot failed: {e}")

    return figures


def write_velocity_report(
    output_dir: Path,
    summary: dict,
    params: dict,
    input_file: str | None,
) -> None:
    """Write velocity analysis report."""
    header = generate_report_header(
        title="Single-Cell RNA Velocity Analysis Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Mode": params.get("mode", "stochastic"),
            "Has Latent Time": str(summary.get("has_latent_time", False)),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Velocity mode**: {params.get('mode', 'stochastic')}",
        f"- **Cells analyzed**: {summary.get('n_cells', 'N/A')}",
        f"- **Genes used**: {summary.get('n_genes', 'N/A')}",
        f"- **Latent time computed**: {'Yes' if summary.get('has_latent_time') else 'No'}",
        "",
        "## Methods\n",
        "### RNA Velocity",
        "RNA velocity estimates the future state of cells by comparing spliced",
        "and unspliced mRNA counts. High velocity indicates active transcription.\n",
    ]

    if params.get("mode") == "dynamical":
        body_lines.extend([
            "### Dynamical Model",
            "The dynamical mode fits a full splicing kinetics model, enabling",
            "computation of latent time (a global, transcriptome-wide pseudotime).\n",
        ])

    body_lines.extend([
        "## Parameters\n",
        f"- `--mode`: {params.get('mode', 'stochastic')}",
        f"- `--n-jobs`: {params.get('n_jobs', 4)}",
        "",
        "## Output Files\n",
        "- `adata_with_velocity.h5ad` — AnnData with velocity results",
        "- `figures/velocity_stream.png` — Velocity stream plot on UMAP",
        "- `figures/velocity_magnitude_umap.png` — Velocity magnitude on UMAP",
    ])

    if summary.get("has_latent_time"):
        body_lines.append("- `figures/latent_time_umap.png` — Latent time on UMAP")

    body_lines.extend([
        "",
        "## Requirements\n",
        "This skill requires:",
        "- **scVelo** package installed",
        "- **Spliced/unspliced layers** in the input AnnData",
        "",
        "To generate spliced/unspliced data with Cell Ranger, use `velocyto` or `kb-python`.\n",
        "",
    ])

    footer = generate_report_footer()
    report = header + "\n" + "\n".join(body_lines) + "\n" + footer

    (output_dir / "report.md").write_text(report)


def generate_demo_data():
    """Generate demo data with spliced/unspliced layers.

    Note: For real velocity analysis, use velocyto or kb-python to generate
    spliced/unspliced counts from FASTQ files.
    """
    import scanpy as sc

    logger.info("Generating synthetic demo data with spliced/unspliced layers...")

    np.random.seed(42)
    n_cells = 500
    n_genes = 500

    # Generate synthetic counts
    spliced = np.random.negative_binomial(5, 0.1, size=(n_cells, n_genes)).astype(np.float32)
    unspliced = np.random.negative_binomial(2, 0.15, size=(n_cells, n_genes)).astype(np.float32)

    adata = sc.AnnData(
        X=spliced,
        obs=pd.DataFrame(index=[f"cell_{i}" for i in range(n_cells)]),
        var=pd.DataFrame(index=[f"gene_{i}" for i in range(n_genes)]),
    )

    # Add layers
    adata.layers["spliced"] = spliced
    adata.layers["unspliced"] = unspliced

    # Basic preprocessing
    sc.pp.filter_genes(adata, min_cells=10)
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, n_top_genes=500)
    sc.pp.pca(adata)
    sc.pp.neighbors(adata)

    # Clustering
    try:
        sc.tl.leiden(adata, resolution=0.8)
    except ImportError:
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
        adata.obs['leiden'] = pd.Categorical(
            kmeans.fit_predict(adata.obsm['X_pca'][:, :30]).astype(str)
        )

    # UMAP
    sc.tl.umap(adata)

    logger.info(f"Generated: {adata.n_obs} cells x {adata.n_vars} genes")
    logger.info("  - Added synthetic spliced/unspliced layers")

    return adata


def main():
    parser = argparse.ArgumentParser(description="Single-Cell RNA Velocity Analysis")
    parser.add_argument("--input", dest="input_path", help="Input AnnData file (.h5ad)")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with demo data")
    parser.add_argument("--mode", default="stochastic",
                        choices=["stochastic", "dynamical", "steady_state"],
                        help="Velocity mode (default: stochastic)")
    parser.add_argument("--n-jobs", type=int, default=4, help="Number of parallel jobs")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check scVelo availability
    if not check_scvelo_available():
        logger.error("scVelo is not installed. Install with: pip install scvelo")
        print("\nERROR: scVelo package required for velocity analysis.")
        print("Install with: pip install scvelo")
        sys.exit(1)

    # Load data
    if args.demo:
        adata = generate_demo_data()
        input_file = None
    else:
        if not args.input_path:
            parser.error("--input required when not using --demo")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        logger.info(f"Loading: {input_path}")
        adata = sc_io.smart_load(input_path)
        input_file = str(input_path)

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    # Check for spliced/unspliced layers
    if "spliced" not in adata.layers or "unspliced" not in adata.layers:
        logger.error("Input data must have 'spliced' and 'unspliced' layers")
        logger.info("Available layers: " + str(list(adata.layers.keys())))
        print("\n" + "="*70)
        print("ERROR: spliced/unspliced layers required for RNA velocity analysis")
        print("="*70)
        print("\nTo generate spliced/unspliced counts, use one of these tools:")
        print("\n1. velocyto (recommended for Cell Ranger output):")
        print("   pip install velocyto")
        print("   velocyto run10x <cellranger_output_dir> <gtf_file>")
        print("\n2. kb-python (kallisto|bustools):")
        print("   pip install kb-python")
        print("   kb ref -i transcriptome.idx -g t2g.txt -f1 transcripts.fa <fasta> <gtf>")
        print("   kb count -i transcriptome.idx -g t2g.txt -x 10xv2 -o output <fastqs>")
        print("\n3. For demo mode, use: --demo")
        print("="*70)
        sys.exit(1)

    # Parameters
    params = {
        "mode": args.mode,
        "n_jobs": args.n_jobs,
    }

    # Run velocity analysis
    logger.info(f"Running velocity analysis (mode={args.mode})...")
    velocity_result = sc_traj.run_velocity_analysis(
        adata,
        mode=args.mode,
        n_jobs=args.n_jobs,
    )

    if velocity_result is None:
        logger.error("Velocity analysis failed")
        sys.exit(1)

    # Summary
    has_latent_time = "latent_time" in adata.obs.columns
    summary = {
        "n_cells": adata.n_obs,
        "n_genes": adata.n_vars,
        "mode": args.mode,
        "has_latent_time": has_latent_time,
    }

    if has_latent_time:
        summary["latent_time_range"] = [
            float(adata.obs["latent_time"].min()),
            float(adata.obs["latent_time"].max()),
        ]

    # Generate figures
    logger.info("Generating figures...")

    # Ensure UMAP is computed
    import scanpy as sc
    if "X_umap" not in adata.obsm:
        sc.tl.umap(adata)

    figures = generate_velocity_figures(adata, output_dir)

    # Write report
    logger.info("Writing report...")
    write_velocity_report(output_dir, summary, params, input_file)

    # Save data
    output_h5ad = output_dir / "adata_with_velocity.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info(f"Saved: {output_h5ad}")

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    cmd = f"python sc_velocity.py --output {output_dir} --mode {args.mode} --n-jobs {args.n_jobs}"
    if input_file:
        cmd += f" --input {input_file}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    # Result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    # Summary
    print(f"\n{'='*60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'='*60}")
    print(f"  Mode: {args.mode}")
    print(f"  Cells: {adata.n_obs}")
    print(f"  Latent time: {'Yes' if has_latent_time else 'No'}")
    print(f"  Output: {output_dir}")


if __name__ == "__main__":
    main()
