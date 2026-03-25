#!/usr/bin/env python3
"""Spatial Integrate — multi-sample integration and batch correction.

Usage:
    python spatial_integrate.py --input <merged.h5ad> --output <dir> --batch-key batch
    python spatial_integrate.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
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
from skills.spatial._lib.adata_utils import store_analysis_metadata
from skills.spatial._lib.dependency_manager import is_available
from skills.spatial._lib.integration import run_integration, SUPPORTED_METHODS
from skills.spatial._lib.viz_utils import save_figure
from skills.spatial._lib.viz import VizParams, plot_integration

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-integrate"
SKILL_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Generate integration quality figures using the SpatialClaw viz library."""
    figures: list[str] = []
    method = summary.get("method", "harmony")

    # Auto-detect batch key
    batch_key = None
    for cand in ("batch", "sample_id", "batch_key", "sample"):
        if cand in adata.obs.columns:
            batch_key = cand
            break

    # 1. UMAP coloured by batch (mixing quality)
    if "X_umap" in adata.obsm and batch_key:
        try:
            fig = plot_integration(
                adata,
                VizParams(batch_key=batch_key, title=f"UMAP by Batch — After {method}"),
                subtype="batch",
            )
            p = save_figure(fig, output_dir, "umap_by_batch.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate batch UMAP: %s", exc)

    # 2. UMAP coloured by cluster (bio-structure preservation)
    if "X_umap" in adata.obsm:
        try:
            fig = plot_integration(
                adata,
                VizParams(title=f"UMAP by Cluster — After {method}"),
                subtype="cluster",
            )
            p = save_figure(fig, output_dir, "umap_by_cluster.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate cluster UMAP: %s", exc)

    # 3. Per-batch highlight panels
    if "X_umap" in adata.obsm and batch_key:
        try:
            fig = plot_integration(
                adata,
                VizParams(batch_key=batch_key, title="Per-Batch Distribution"),
                subtype="highlight",
            )
            p = save_figure(fig, output_dir, "batch_highlight.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate batch highlight: %s", exc)

    # 4. Batch mixing entropy bar chart (lightweight, no extra deps)
    try:
        import matplotlib.pyplot as plt
        vals = [summary.get("batch_mixing_before", 0), summary.get("batch_mixing_after", 0)]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(["Before", "After"], vals,
               color=["#d9534f", "#5cb85c"], edgecolor="black", width=0.5)
        ax.set_ylabel("Batch Mixing Entropy (normalised)")
        ax.set_title("Integration Quality")
        ax.set_ylim(0, 1.05)
        for i, v in enumerate(vals):
            ax.text(i, v + 0.02, f"{v:.3f}", ha="center", fontsize=10)
        fig.tight_layout()
        p = save_figure(fig, output_dir, "batch_mixing.png")
        figures.append(str(p))
        plt.close('all')
    except Exception as exc:
        logger.warning("Could not generate batch mixing plot: %s", exc)

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

    header = generate_report_header(
        title="Spatial Multi-Sample Integration Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Batch key": params.get("batch_key", "batch"),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Batches**: {summary['n_batches']}",
        f"- **Method**: {summary['method']}",
        f"- **Embedding**: `{summary['embedding_key']}`",
        "",
        "### Batch Sizes\n",
        "| Batch | Cells |",
        "|-------|-------|",
    ]
    for b, n in summary["batch_sizes"].items():
        body_lines.append(f"| {b} | {n} |")

    body_lines.extend([
        "",
        "### Integration Quality\n",
        f"- **Batch mixing (before)**: {summary['batch_mixing_before']:.4f}",
        f"- **Batch mixing (after)**: {summary['batch_mixing_after']:.4f}",
        "",
        "Higher mixing entropy (0–1) indicates better batch mixing. "
        "A value of 1.0 means perfect mixing.",
    ])

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)
    logger.info("Wrote %s", output_dir / "report.md")

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
        summary=summary, data={"params": params, **summary},
        input_checksum=checksum,
    )

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    pd.DataFrame([{
        "metric": "batch_mixing_before", "value": summary["batch_mixing_before"],
    }, {
        "metric": "batch_mixing_after", "value": summary["batch_mixing_after"],
    }, {
        "metric": "method", "value": summary["method"],
    }, {
        "metric": "n_batches", "value": summary["n_batches"],
    }]).to_csv(tables_dir / "integration_metrics.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd_parts: list[str] = [f"python spatial_integrate.py --input <input.h5ad> --output {output_dir}"]
    for k, v in params.items():
        if v is not None:
            cmd_parts.append(f"--{str(k).replace('_', '-')} {v}")
    
    cmd_str = " ".join(cmd_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd_str}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore
    env_lines: list[str] = []
    for pkg in ["scanpy", "anndata", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    for opt in ["harmonypy", "bbknn", "scanorama"]:
        if is_available(opt):
            try:
                env_lines.append(f"{opt}=={_get_version(opt)}")
            except Exception:
                pass
    (repro_dir / "environment.yml").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data — create synthetic multi-batch data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Generate synthetic multi-batch data from preprocess demo."""
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_int_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Running spatial-preprocess --demo into %s", tmp_path)
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"spatial-preprocess --demo failed (exit {result.returncode}):\n{result.stderr}"
            )
        processed = tmp_path / "processed.h5ad"
        if not processed.exists():
            raise FileNotFoundError(f"Expected {processed}")
        adata = sc.read_h5ad(processed)

    rng = np.random.default_rng(42)
    adata.obs["batch"] = rng.choice(["batch_A", "batch_B", "batch_C"], size=adata.n_obs)
    adata.obs["batch"] = pd.Categorical(adata.obs["batch"])

    logger.info("Demo: %d cells, batches=%s", adata.n_obs, adata.obs["batch"].cat.categories.tolist())
    return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Integrate — multi-sample batch integration",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method", default="harmony",
        choices=["harmony", "bbknn", "scanorama"],
    )
    parser.add_argument("--batch-key", default="batch")
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

    params = {"method": args.method, "batch_key": args.batch_key}

    summary = run_integration(adata, method=args.method, batch_key=args.batch_key)

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    store_analysis_metadata(
        adata, SKILL_NAME, summary["method"],
        params=params,
    )

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(
        f"Integration complete ({summary['method']}): "
        f"{summary['n_batches']} batches, "
        f"mixing {summary['batch_mixing_before']:.3f} → {summary['batch_mixing_after']:.3f}"
    )


if __name__ == "__main__":
    main()
