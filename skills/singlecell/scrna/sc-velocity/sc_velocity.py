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
import shlex
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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    load_result_json,
    write_repro_requirements,
    write_result_json,
    write_standard_run_artifacts,
)
from omicsclaw.common.checksums import sha256_file
from skills.singlecell._lib.adata_utils import (
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad, write_h5ad_aliases
from skills.singlecell._lib.method_config import (
    MethodConfig,
    validate_method_choice,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_velocity
from skills.singlecell._lib import trajectory as sc_traj
from skills.singlecell._lib.viz import (
    plot_latent_time_distribution,
    plot_velocity_magnitude_distribution,
    plot_velocity_top_genes_bar,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-velocity"
SKILL_VERSION = "0.3.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-velocity/sc_velocity.py"

# ---------------------------------------------------------------------------
# Method registry
# ---------------------------------------------------------------------------

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "scvelo_stochastic": MethodConfig(
        name="scvelo_stochastic",
        description="scVelo stochastic velocity estimation",
        dependencies=("scvelo",),
        requires_layers=("spliced", "unspliced"),
    ),
    "scvelo_dynamical": MethodConfig(
        name="scvelo_dynamical",
        description="scVelo dynamical model with latent time",
        dependencies=("scvelo",),
        requires_layers=("spliced", "unspliced"),
    ),
    "scvelo_steady_state": MethodConfig(
        name="scvelo_steady_state",
        description="scVelo steady-state velocity estimation",
        dependencies=("scvelo",),
        requires_layers=("spliced", "unspliced"),
    ),
}

SUPPORTED_METHODS = tuple(METHOD_REGISTRY.keys())

# Mapping from CLI --method value to internal mode for sc_traj.run_velocity_analysis
_CLI_TO_MODE = {
    "scvelo_stochastic": "stochastic",
    "scvelo_dynamical": "dynamical",
    "scvelo_steady_state": "steady_state",
}
_MODE_ALIAS_MAP = {
    "stochastic": "scvelo_stochastic",
    "dynamical": "scvelo_dynamical",
    "steady_state": "scvelo_steady_state",
}

# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------

# Velocity methods all go through sc_traj.run_velocity_analysis with a mode arg;
# _METHOD_DISPATCH kept for structural consistency.
_METHOD_DISPATCH = {
    "scvelo_stochastic": "stochastic",
    "scvelo_dynamical": "dynamical",
    "scvelo_steady_state": "steady_state",
}


def _write_figures_manifest(output_dir: Path, plots: list[dict]) -> None:
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "recipe_id": "standard-sc-velocity-gallery",
        "skill_name": SKILL_NAME,
        "title": "Single-cell RNA velocity gallery",
        "description": "Canonical velocity plots and supporting summaries for scVelo runs.",
        "backend": "python",
        "plots": plots,
    }
    (figures_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _velocity_summary_df(summary: dict, params: dict) -> pd.DataFrame:
    rows = [
        {"metric": "method", "value": params.get("method", "")},
        {"metric": "mode", "value": params.get("mode", "")},
        {"metric": "n_cells", "value": summary.get("n_cells", 0)},
        {"metric": "n_genes", "value": summary.get("n_genes", 0)},
        {"metric": "has_latent_time", "value": bool(summary.get("has_latent_time", False))},
    ]
    if "latent_time_range" in summary:
        rows.append({"metric": "latent_time_min", "value": summary["latent_time_range"][0]})
        rows.append({"metric": "latent_time_max", "value": summary["latent_time_range"][1]})
    return pd.DataFrame(rows)


def _velocity_cell_summary_df(adata) -> pd.DataFrame:
    frame = pd.DataFrame(index=adata.obs_names.astype(str))
    if "X_umap" in adata.obsm:
        frame["umap_1"] = np.asarray(adata.obsm["X_umap"])[:, 0]
        frame["umap_2"] = np.asarray(adata.obsm["X_umap"])[:, 1]
    if "velocity" in adata.layers:
        velocity = adata.layers["velocity"]
        if hasattr(velocity, "toarray"):
            velocity = velocity.toarray()
        velocity = np.asarray(velocity, dtype=np.float32)
        frame["velocity_magnitude"] = np.linalg.norm(velocity, axis=1)
    if "latent_time" in adata.obs.columns:
        frame["latent_time"] = adata.obs["latent_time"].astype(float).to_numpy()
    return frame.reset_index(names="cell_id")


def _velocity_gene_summary_df(adata, n_top: int = 40) -> pd.DataFrame:
    if "velocity" not in adata.layers:
        return pd.DataFrame(columns=["gene", "mean_abs_velocity", "mean_velocity"])
    velocity = np.asarray(adata.layers["velocity"])
    mean_abs = np.mean(np.abs(velocity), axis=0)
    mean_signed = np.mean(velocity, axis=0)
    frame = pd.DataFrame(
        {
            "gene": adata.var_names.astype(str),
            "mean_abs_velocity": mean_abs,
            "mean_velocity": mean_signed,
        }
    )
    return frame.sort_values("mean_abs_velocity", ascending=False).head(n_top).reset_index(drop=True)


def _export_velocity_tables(
    output_dir: Path,
    *,
    summary_df: pd.DataFrame,
    cell_df: pd.DataFrame,
    gene_df: pd.DataFrame,
) -> dict[str, str]:
    tables_dir = output_dir / "tables"
    figure_data_dir = output_dir / "figure_data"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "velocity_summary": "velocity_summary.csv",
        "velocity_cells": "velocity_cells.csv",
        "top_velocity_genes": "top_velocity_genes.csv",
    }
    summary_df.to_csv(tables_dir / files["velocity_summary"], index=False)
    cell_df.to_csv(tables_dir / files["velocity_cells"], index=False)
    gene_df.to_csv(tables_dir / files["top_velocity_genes"], index=False)

    summary_df.to_csv(figure_data_dir / files["velocity_summary"], index=False)
    cell_df.to_csv(figure_data_dir / files["velocity_cells"], index=False)
    gene_df.to_csv(figure_data_dir / files["top_velocity_genes"], index=False)
    _write_figure_data_manifest(
        output_dir,
        {
            "skill": SKILL_NAME,
            "recipe_id": "standard-sc-velocity-gallery",
            "available_files": files,
        },
    )
    return files


def _write_reproducibility(output_dir: Path, params: dict, input_file: str | None, *, demo_mode: bool) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    elif input_file:
        command_parts.extend(["--input", input_file])
    command_parts.extend(["--output", str(output_dir), "--method", params["method"], "--n-jobs", str(params["n_jobs"])])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    write_repro_requirements(output_dir, ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "scvelo"])


def check_scvelo_available() -> bool:
    """Check if scVelo is available."""
    try:
        import scvelo
        return True
    except ImportError:
        return False


def generate_velocity_figures(adata, output_dir: Path, *, cell_df: pd.DataFrame, gene_df: pd.DataFrame) -> list[dict]:
    """Generate velocity visualization figures and return manifest-friendly records."""
    figures: list[dict] = []
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
            figures.append(
                {
                    "plot_id": "velocity_stream",
                    "role": "overview",
                    "backend": "python",
                    "renderer": "plot_velocity_stream",
                    "filename": "velocity_stream.png",
                    "title": "RNA velocity stream",
                    "description": "Velocity stream embedding on the active UMAP basis.",
                    "status": "rendered",
                    "path": str(fig_path),
                }
            )
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
            figures.append(
                {
                    "plot_id": "velocity_magnitude_umap",
                    "role": "diagnostic",
                    "backend": "python",
                    "renderer": "velocity_magnitude_umap",
                    "filename": "velocity_magnitude_umap.png",
                    "title": "Velocity magnitude",
                    "description": "UMAP colored by per-cell velocity magnitude.",
                    "status": "rendered",
                    "path": str(fig_path),
                }
            )
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
            figures.append(
                {
                    "plot_id": "latent_time_umap",
                    "role": "supporting",
                    "backend": "python",
                    "renderer": "latent_time_umap",
                    "filename": "latent_time_umap.png",
                    "title": "Latent time",
                    "description": "UMAP colored by latent time when available.",
                    "status": "rendered",
                    "path": str(fig_path),
                }
            )
            plt.close()
            logger.info(f"  Saved: latent_time_umap.png")
        except Exception as e:
            logger.warning(f"Latent time plot failed: {e}")

    try:
        plot_velocity_top_genes_bar(gene_df, output_dir)
        figures.append(
            {
                "plot_id": "velocity_top_genes",
                "role": "supporting",
                "backend": "python",
                "renderer": "plot_velocity_top_genes_bar",
                "filename": "velocity_top_genes.png",
                "title": "Top genes by velocity magnitude",
                "description": "Genes ranked by mean absolute velocity.",
                "status": "rendered",
                "path": str(output_dir / "figures" / "velocity_top_genes.png"),
            }
        )
    except Exception as e:
        logger.warning(f"Top velocity genes bar plot failed: {e}")

    try:
        plot_velocity_magnitude_distribution(cell_df, output_dir)
        figures.append(
            {
                "plot_id": "velocity_magnitude_distribution",
                "role": "diagnostic",
                "backend": "python",
                "renderer": "plot_velocity_magnitude_distribution",
                "filename": "velocity_magnitude_distribution.png",
                "title": "Velocity magnitude distribution",
                "description": "Histogram of per-cell velocity magnitudes.",
                "status": "rendered",
                "path": str(output_dir / "figures" / "velocity_magnitude_distribution.png"),
            }
        )
    except Exception as e:
        logger.warning(f"Velocity magnitude distribution plot failed: {e}")

    if "latent_time" in cell_df.columns:
        try:
            plot_latent_time_distribution(cell_df, output_dir)
            figures.append(
                {
                    "plot_id": "latent_time_distribution",
                    "role": "supporting",
                    "backend": "python",
                    "renderer": "plot_latent_time_distribution",
                    "filename": "latent_time_distribution.png",
                    "title": "Latent time distribution",
                    "description": "Histogram of latent time values.",
                    "status": "rendered",
                    "path": str(output_dir / "figures" / "latent_time_distribution.png"),
                }
            )
        except Exception as e:
            logger.warning(f"Latent time distribution plot failed: {e}")

    return figures


def write_velocity_report(
    output_dir: Path,
    summary: dict,
    params: dict,
    input_file: str | None,
    *,
    velocity_diagnostics: dict | None = None,
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
        "- `processed.h5ad` — AnnData with velocity results",
        "- `adata_with_velocity.h5ad` — compatibility alias pointing to the same result",
        "- `figures/velocity_stream.png` — Velocity stream plot on UMAP",
        "- `figures/velocity_magnitude_umap.png` — Velocity magnitude on UMAP",
        "- `figures/velocity_magnitude_distribution.png` — Distribution of per-cell velocity magnitude",
        "- `figures/velocity_top_genes.png` — Top genes ranked by mean absolute velocity",
        "- `tables/velocity_summary.csv` — run-level velocity summary",
        "- `tables/velocity_cells.csv` — per-cell velocity summaries",
        "- `tables/top_velocity_genes.csv` — top genes ranked by mean absolute velocity",
        "- `figures/manifest.json` — standard velocity gallery manifest",
        "- `figure_data/manifest.json` — plot-ready data manifest",
    ])

    if summary.get("has_latent_time"):
        body_lines.append("- `figures/latent_time_umap.png` — Latent time on UMAP")
        body_lines.append("- `figures/latent_time_distribution.png` — Distribution of latent time values")

    # Troubleshooting section when degenerate
    if velocity_diagnostics and velocity_diagnostics.get("degenerate"):
        body_lines.extend([
            "",
            "## Troubleshooting: Degenerate Velocity Output\n",
            "The velocity analysis produced results that may not be meaningful.\n",
        ])
        if velocity_diagnostics.get("all_zero_velocity"):
            body_lines.extend([
                "### All velocity vectors are zero",
                "scVelo could not estimate meaningful velocity from the spliced/unspliced layers.",
                "This often happens with synthetic or very noisy data.\n",
                "**Fix**: Use real spliced/unspliced data from `velocyto` or `STARsolo`:",
                "```bash",
                "oc run sc-velocity-prep --input <cellranger_dir> --method velocyto --gtf <genes.gtf> --output <dir>",
                "```\n",
            ])
        if velocity_diagnostics.get("nan_fraction", 0) > 0.5:
            body_lines.extend([
                f"### High NaN fraction ({velocity_diagnostics['nan_fraction']*100:.0f}%)",
                "The velocity fitting failed for many genes. This may indicate insufficient",
                "signal in the spliced/unspliced layers or too few cells.\n",
                "**Fix**: Try the dynamical model which can sometimes recover more signal:",
                "```bash",
                "oc run sc-velocity --input <data.h5ad> --method scvelo_dynamical --output <dir>",
                "```\n",
            ])
        if velocity_diagnostics.get("n_velocity_genes", 0) == 0:
            body_lines.extend([
                "### No genes with non-zero velocity",
                "The spliced/unspliced signal may be too weak for velocity estimation.\n",
                "**Fix**: Ensure proper upstream preprocessing:",
                "```bash",
                "oc run sc-preprocessing --input <data.h5ad> --output <dir>",
                "oc run sc-velocity-prep --input <dir>/processed.h5ad --output <dir2>",
                "```\n",
            ])
        body_lines.extend([
            "### Alternative methods",
            "- `--method scvelo_dynamical`: fits a full splicing kinetics model",
            "- `--method scvelo_stochastic`: faster but may miss weak signal",
            "- `--method scvelo_steady_state`: simplest approximation",
            "",
        ])

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

    logger.info("Generating demo data with spliced/unspliced layers...")
    try:
        adata, demo_path = sc_io.load_repo_demo_data("pbmc3k_raw")
        logger.info("Loaded demo dataset: %s", demo_path or "scanpy-pbmc3k")
        adata = adata.copy()
        if adata.n_obs > 300:
            adata = adata[:300, :].copy()
        if adata.n_vars > 200:
            adata = adata[:, :200].copy()
        if hasattr(adata.X, "toarray"):
            base_counts = adata.X.toarray().astype(np.float32)
        else:
            base_counts = np.asarray(adata.X).astype(np.float32)
        np.random.seed(42)
        spliced = np.maximum(base_counts, 0).astype(np.float32)
        unspliced = np.random.negative_binomial(2, 0.15, size=spliced.shape).astype(np.float32)
        adata.X = spliced
    except Exception:
        np.random.seed(42)
        n_cells = 300
        n_genes = 200
        spliced = np.random.negative_binomial(5, 0.1, size=(n_cells, n_genes)).astype(np.float32)
        unspliced = np.random.negative_binomial(2, 0.15, size=(n_cells, n_genes)).astype(np.float32)
        adata = sc.AnnData(
            X=spliced,
            obs=pd.DataFrame(index=[f"cell_{i}" for i in range(n_cells)]),
            var=pd.DataFrame(index=[f"gene_{i}" for i in range(n_genes)]),
        )

    # Add layers
    adata.layers["counts"] = spliced.copy()
    adata.layers["spliced"] = spliced
    adata.layers["unspliced"] = unspliced
    adata.raw = adata.copy()

    # Basic preprocessing
    sc.pp.filter_genes(adata, min_cells=10)
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, n_top_genes=min(200, adata.n_vars))
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
    parser.add_argument(
        "--method",
        "--mode",
        dest="method",
        default="scvelo_stochastic",
        choices=list(METHOD_REGISTRY.keys()) + list(_MODE_ALIAS_MAP.keys()),
        help="Velocity method; accepts full backend ids or shorthand modes such as 'dynamical'",
    )
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
        adata = sc_io.smart_load(input_path, skill_name=SKILL_NAME)
        input_file = str(input_path)

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    # Check for spliced/unspliced layers
    if "spliced" not in adata.layers or "unspliced" not in adata.layers:
        logger.error("Input data must have 'spliced' and 'unspliced' layers")
        logger.info("Available layers: " + str(list(adata.layers.keys())))
        print("\n" + "="*70)
        print("ERROR: spliced/unspliced layers required for RNA velocity analysis")
        print("="*70)
        print("\nPrepare a velocity-ready object first, then rerun this skill:")
        print("\n1. Cell Ranger output -> OmicsClaw velocity prep:")
        print("   oc run sc-velocity-prep --input <cellranger_run_dir> --method velocyto --gtf <genes.gtf> --output <dir>")
        print("\n2. STARsolo Velocyto output -> OmicsClaw velocity prep:")
        print("   oc run sc-velocity-prep --input <starsolo_run_dir> --method starsolo --output <dir>")
        print("\n3. Existing loom file -> OmicsClaw velocity prep:")
        print("   oc run sc-velocity-prep --input <sample.loom> --method velocyto --output <dir>")
        print("\n4. For demo mode, use: --demo")
        print("="*70)
        sys.exit(1)

    # Validate method & check dependencies
    requested_method = _MODE_ALIAS_MAP.get(args.method, args.method)
    method = validate_method_choice(requested_method, METHOD_REGISTRY)
    mode = _CLI_TO_MODE[method]
    apply_preflight(
        preflight_sc_velocity(
            adata,
            method=method,
            source_path=input_file,
        ),
        logger,
        demo_mode=args.demo,
    )

    # Parameters
    params = {
        "mode": mode,
        "method": method,
        "n_jobs": args.n_jobs,
    }

    # Run velocity analysis
    logger.info(f"Running velocity analysis (mode={mode})...")
    velocity_result = sc_traj.run_velocity_analysis(
        adata,
        mode=mode,
        n_jobs=args.n_jobs,
    )

    if velocity_result is None:
        logger.error("Velocity analysis failed")
        sys.exit(1)

    # ---------------------------------------------------------------------------
    # Degenerate output detection
    # ---------------------------------------------------------------------------
    velocity_diagnostics: dict = {}
    is_degenerate = False

    if "velocity" in adata.layers:
        vel = adata.layers["velocity"]
        if hasattr(vel, "toarray"):
            vel = vel.toarray()
        vel = np.asarray(vel, dtype=np.float32)

        all_zero = np.allclose(vel, 0)
        nan_frac = float(np.isnan(vel).sum()) / max(vel.size, 1)
        n_velocity_genes = int((np.abs(vel).sum(axis=0) > 0).sum())

        velocity_diagnostics["all_zero_velocity"] = bool(all_zero)
        velocity_diagnostics["nan_fraction"] = round(nan_frac, 4)
        velocity_diagnostics["n_velocity_genes"] = n_velocity_genes
        velocity_diagnostics["n_total_genes"] = int(adata.n_vars)

        if all_zero or nan_frac > 0.5 or n_velocity_genes == 0:
            is_degenerate = True
            velocity_diagnostics["degenerate"] = True
            velocity_diagnostics["suggested_actions"] = [
                "Check that spliced/unspliced layers contain real count data (not all zeros)",
                "Try dynamical mode: --method scvelo_dynamical",
                "Ensure input has been preprocessed: sc-preprocessing -> sc-velocity-prep -> sc-velocity",
                "Re-run sc-velocity-prep with real BAM/loom data instead of synthetic layers",
            ]
            logger.warning("Degenerate velocity output detected (all_zero=%s, nan_frac=%.2f, velocity_genes=%d)",
                           all_zero, nan_frac, n_velocity_genes)
            print()
            print("  *** WARNING: Velocity output appears degenerate. ***")
            if all_zero:
                print("  All velocity vectors are zero — scVelo could not estimate meaningful velocity.")
            if nan_frac > 0.5:
                print(f"  {nan_frac*100:.0f}% of velocity values are NaN — fitting may have failed.")
            if n_velocity_genes == 0:
                print("  No genes have non-zero velocity — the spliced/unspliced signal may be too weak.")
            print()
            print("  How to fix:")
            print("    Option 1 — Use real spliced/unspliced data from velocyto or STARsolo:")
            print("      oc run sc-velocity-prep --input <cellranger_dir> --method velocyto --gtf <genes.gtf> --output <dir>")
            print("    Option 2 — Try the dynamical model which may recover more signal:")
            print("      oc run sc-velocity --input <data.h5ad> --method scvelo_dynamical --output <dir>")
            print("    Option 3 — Check upstream preprocessing (normalize, HVG, PCA, neighbors):")
            print("      oc run sc-preprocessing --input <data.h5ad> --output <dir>")
            print()
        else:
            velocity_diagnostics["degenerate"] = False
    else:
        is_degenerate = True
        velocity_diagnostics = {
            "degenerate": True,
            "all_zero_velocity": True,
            "nan_fraction": 1.0,
            "n_velocity_genes": 0,
            "n_total_genes": int(adata.n_vars),
            "suggested_actions": [
                "Velocity layer was not created — check scVelo logs above for errors",
                "Ensure spliced/unspliced layers have sufficient signal",
            ],
        }

    # Summary
    has_latent_time = "latent_time" in adata.obs.columns
    summary = {
        "n_cells": adata.n_obs,
        "n_genes": adata.n_vars,
        "mode": mode,
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

    summary_df = _velocity_summary_df(summary, params)
    cell_df = _velocity_cell_summary_df(adata)
    gene_df = _velocity_gene_summary_df(adata)
    figures = generate_velocity_figures(adata, output_dir, cell_df=cell_df, gene_df=gene_df)
    _write_figures_manifest(output_dir, figures)
    table_files = _export_velocity_tables(output_dir, summary_df=summary_df, cell_df=cell_df, gene_df=gene_df)

    # Write report
    logger.info("Writing report...")
    write_velocity_report(output_dir, summary, params, input_file, velocity_diagnostics=velocity_diagnostics)

    # Save data
    if "counts" not in adata.layers:
        adata.layers["counts"] = adata.X.copy()
    if adata.raw is None:
        adata.raw = adata.copy()
    store_analysis_metadata(adata, SKILL_NAME, method, params)
    _, matrix_contract = propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind="normalized_expression",
        raw_kind="raw_counts_snapshot",
    )
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)
    alias_paths = write_h5ad_aliases(output_h5ad, [output_dir / "adata_with_velocity.h5ad"])
    logger.info(f"Saved: {output_h5ad}")

    # Reproducibility
    _write_reproducibility(output_dir, params, input_file, demo_mode=args.demo)

    # Result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "method": method,
        "params": params,
        "input_contract": adata.uns.get("omicsclaw_input_contract", {}),
        "matrix_contract": matrix_contract,
        "output_h5ad": "processed.h5ad",
        "velocity_diagnostics": velocity_diagnostics,
        "visualization": {
            "recipe_id": "standard-sc-velocity-gallery",
            "available_figure_data": table_files,
        },
        "output_files": {
            "processed_h5ad": str(output_h5ad),
            "compatibility_aliases": [str(path) for path in alias_paths],
        },
    }
    result_data["next_steps"] = []
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }
    write_standard_run_artifacts(
        output_dir,
        skill_alias=SKILL_NAME,
        description="RNA velocity analysis for single-cell RNA-seq with scVelo.",
        result_payload=result_payload,
        preferred_method=summary.get("mode", "stochastic"),
        script_path=Path(__file__).resolve(),
        actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
    )

    # Summary
    print(f"\n{'='*60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'='*60}")
    print(f"  Mode: {mode}")
    print(f"  Cells: {adata.n_obs}")
    print(f"  Latent time: {'Yes' if has_latent_time else 'No'}")
    print(f"  Output: {output_dir}")

    # --- Next-step guidance ---
    print()
    print("▶ Analysis complete. Further exploration:")
    print(f"  • sc-pseudotime: python omicsclaw.py run sc-pseudotime --input {output_dir}/processed.h5ad --output <dir>")
    print(f"  • sc-cytotrace:  python omicsclaw.py run sc-cytotrace --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()
    # TensorFlow (loaded transitively) spawns hundreds of threads that block
    # on futex during interpreter shutdown, and loky workers inherit pipe FDs
    # that prevent the parent subprocess.run from seeing EOF.  Kill the
    # entire process group to force a clean exit.
    import os, sys, signal
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        os.killpg(os.getpgid(os.getpid()), signal.SIGKILL)
    except Exception:
        os._exit(0)
