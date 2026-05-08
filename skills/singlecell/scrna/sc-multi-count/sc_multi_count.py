#!/usr/bin/env python3
"""Merge multiple single-sample scRNA-seq count matrices into one AnnData."""

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

try:
    import anndata

    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_repro_requirements,
    write_result_json,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.export import save_h5ad, write_h5ad_aliases
from skills.singlecell._lib.upstream import standardize_count_adata
from skills.singlecell._lib.viz import (
    plot_barcode_rank,
    plot_count_complexity_scatter,
    plot_count_distributions,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-multi-count"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-multi-count/sc_multi_count.py"


# ---------------------------------------------------------------------------
# Demo helpers
# ---------------------------------------------------------------------------

def _demo_adata():
    """Build a two-sample demo from the repo pbmc3k_raw dataset."""
    import scanpy as sc

    adata, demo_path = sc_io.load_repo_demo_data("pbmc3k_raw")
    # Split into two pseudo-samples
    n = adata.n_obs
    mid = n // 2
    idx_a = list(range(mid))
    idx_b = list(range(mid, n))
    a = adata[idx_a].copy()
    b = adata[idx_b].copy()
    a.obs["sample_id"] = "sample_A"
    b.obs["sample_id"] = "sample_B"
    # Make barcodes unique across samples
    a.obs_names = [f"sampleA_{bc}" for bc in a.obs_names]
    b.obs_names = [f"sampleB_{bc}" for bc in b.obs_names]
    combined = anndata.concat([a, b], join="outer")
    combined.obs["sample_id"] = combined.obs["sample_id"].astype(str)
    return combined, [a, b], str(demo_path) if demo_path else None


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

def _load_and_tag(h5ad_path: Path, sample_id: str | None = None) -> anndata.AnnData:
    """Load one h5ad and tag with sample_id."""
    import scanpy as sc

    adata = sc.read_h5ad(h5ad_path)
    if sample_id is None:
        sample_id = h5ad_path.stem.replace("processed", "").strip("_") or h5ad_path.parent.name
    if "sample_id" not in adata.obs.columns:
        adata.obs["sample_id"] = sample_id
    # Prefix barcodes to avoid collisions
    adata.obs_names = [f"{sample_id}_{bc}" for bc in adata.obs_names]
    adata.obs_names_make_unique()
    return adata


def _merge_samples(adatas: list[anndata.AnnData]) -> anndata.AnnData:
    """Concatenate sample AnnData objects with outer join on genes."""
    combined = anndata.concat(adatas, join="outer")
    combined.obs_names_make_unique()
    # Fill NaN from outer join with zeros (count data)
    if hasattr(combined.X, "toarray"):
        # sparse: NaN not possible, already zero-filled
        pass
    else:
        combined.X = np.nan_to_num(combined.X, nan=0.0)
    combined.obs["sample_id"] = combined.obs["sample_id"].astype(str)
    return combined


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _barcode_metrics_df(adata) -> pd.DataFrame:
    matrix = adata.X
    total_counts = np.asarray(matrix.sum(axis=1)).ravel()
    detected_genes = np.asarray((matrix > 0).sum(axis=1)).ravel()
    return (
        pd.DataFrame(
            {
                "barcode": adata.obs_names.astype(str),
                "sample_id": adata.obs["sample_id"].values,
                "total_counts": total_counts,
                "detected_genes": detected_genes,
            }
        )
        .sort_values("total_counts", ascending=False)
        .reset_index(drop=True)
    )


def _per_sample_summary(barcode_df: pd.DataFrame) -> pd.DataFrame:
    return (
        barcode_df.groupby("sample_id", dropna=False)
        .agg(
            n_cells=("barcode", "count"),
            median_counts=("total_counts", "median"),
            median_genes=("detected_genes", "median"),
            total_umis=("total_counts", "sum"),
        )
        .reset_index()
    )


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _write_figures_manifest(output_dir: Path, plots: list[dict]) -> None:
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "recipe_id": "standard-sc-multi-count-gallery",
        "skill_name": SKILL_NAME,
        "title": "Multi-sample counting gallery",
        "description": "Canonical counting diagnostics across merged samples.",
        "backend": "python",
        "plots": plots,
    }
    (figures_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _plot_sample_composition(per_sample: pd.DataFrame, output_dir: Path) -> None:
    """Bar chart of cell counts per sample."""
    import matplotlib.pyplot as plt
    from skills.singlecell._lib.viz import apply_singlecell_theme, save_figure

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(max(6, len(per_sample) * 0.8), 4))
    bars = ax.bar(per_sample["sample_id"], per_sample["n_cells"], color="#4C72B0", edgecolor="white")
    ax.set_xlabel("Sample")
    ax.set_ylabel("Number of cells")
    ax.set_title("Cell count per sample")
    if len(per_sample) > 6:
        plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    save_figure(fig, output_dir, "sample_composition.png")


def _export_tables(
    output_dir: Path,
    barcode_metrics: pd.DataFrame,
    per_sample: pd.DataFrame,
) -> dict[str, str]:
    tables_dir = output_dir / "tables"
    figure_data_dir = output_dir / "figure_data"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    table_files = {
        "barcode_metrics": "barcode_metrics.csv",
        "per_sample_summary": "per_sample_summary.csv",
    }
    barcode_metrics.to_csv(tables_dir / table_files["barcode_metrics"], index=False)
    per_sample.to_csv(tables_dir / table_files["per_sample_summary"], index=False)

    barcode_metrics.to_csv(figure_data_dir / table_files["barcode_metrics"], index=False)
    per_sample.to_csv(figure_data_dir / table_files["per_sample_summary"], index=False)
    _write_figure_data_manifest(
        output_dir,
        {
            "skill": SKILL_NAME,
            "recipe_id": "standard-sc-multi-count-gallery",
            "available_files": {
                "barcode_metrics": table_files["barcode_metrics"],
                "per_sample_summary": table_files["per_sample_summary"],
            },
        },
    )
    return table_files


def _write_reproducibility(output_dir: Path, args: argparse.Namespace, *, demo_mode: bool) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    elif args.input_paths:
        for p in args.input_paths:
            command_parts.extend(["--input", p])
    if args.sample_ids:
        for s in args.sample_ids:
            command_parts.extend(["--sample-id", s])
    command_parts.extend(["--output", str(output_dir)])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    write_repro_requirements(output_dir, ["scanpy", "anndata", "numpy", "pandas", "matplotlib"])


def _write_report(
    output_dir: Path,
    *,
    summary: dict,
    per_sample: pd.DataFrame,
    diagnostics: dict,
) -> None:
    header = generate_report_header(
        title="Multi-Sample Count Merge Report",
        skill_name=SKILL_NAME,
        extra_metadata={
            "Samples": str(summary["n_samples"]),
            "Total cells": str(summary["n_cells"]),
            "Total genes": str(summary["n_genes"]),
        },
    )
    lines = [
        "## Summary\n",
        f"- **Samples merged**: {summary['n_samples']}",
        f"- **Total cells**: {summary['n_cells']:,}",
        f"- **Total genes (union)**: {summary['n_genes']:,}",
        f"- **Median counts per barcode**: {summary['median_counts']:.1f}",
        f"- **Median detected genes**: {summary['median_genes']:.1f}",
        "",
        "## Per-Sample Breakdown\n",
    ]
    for _, row in per_sample.iterrows():
        lines.extend([
            f"### {row['sample_id']}\n",
            f"- **Cells**: {int(row['n_cells']):,}",
            f"- **Median counts**: {row['median_counts']:.1f}",
            f"- **Median genes**: {row['median_genes']:.1f}",
            f"- **Total UMIs**: {int(row['total_umis']):,}",
            "",
        ])

    if diagnostics.get("degenerate"):
        lines.extend([
            "",
            "## Troubleshooting: Degenerate Output Detected\n",
        ])
        for action in diagnostics.get("suggested_actions", []):
            lines.append(f"- {action}")
        lines.append("")

    lines.extend([
        "",
        "## Output Files\n",
        "- `processed.h5ad` -- merged AnnData with `layers['counts']` and `obs['sample_id']`",
        "- `figures/barcode_rank.png` -- barcode-rank curve for merged cells",
        "- `figures/count_distributions.png` -- total-count and detected-gene distributions",
        "- `figures/count_complexity_scatter.png` -- counts versus detected genes",
        "- `figures/sample_composition.png` -- cell count per sample",
        "- `tables/barcode_metrics.csv` -- per-barcode count summary with sample labels",
        "- `tables/per_sample_summary.csv` -- per-sample summary statistics",
        "",
        "## Recommended Next Step\n",
        "- Continue with `sc-qc` or `sc-preprocessing` on `processed.h5ad`.",
        "- If samples have batch effects, consider `sc-batch-integration` after preprocessing.",
    ])

    (output_dir / "report.md").write_text(
        header + "\n".join(lines) + "\n" + generate_report_footer(), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge multiple single-sample scRNA-seq count matrices into one AnnData."
    )
    parser.add_argument(
        "--input", dest="input_paths", action="append", default=[],
        help="Path to a processed.h5ad from sc-count (repeat for each sample)",
    )
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run built-in demo mode")
    parser.add_argument(
        "--sample-id", dest="sample_ids", action="append", default=[],
        help="Sample ID for the corresponding --input (repeat for each sample, same order)",
    )
    parser.add_argument("--r-enhanced", action="store_true",
        help="(Accepted for CLI consistency; no R Enhanced plots available for this skill.)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        combined, _parts, input_file = _demo_adata()
    else:
        if len(args.input_paths) < 2:
            parser.error("At least two --input paths required when not using --demo.")
        sample_ids = args.sample_ids if args.sample_ids else [None] * len(args.input_paths)
        if len(sample_ids) != len(args.input_paths):
            parser.error(
                f"Number of --sample-id ({len(sample_ids)}) must match "
                f"number of --input ({len(args.input_paths)})."
            )
        adatas = []
        for path_str, sid in zip(args.input_paths, sample_ids):
            path = Path(path_str)
            if not path.exists():
                raise FileNotFoundError(
                    f"Input file not found: {path}\n"
                    "Each --input should point to a processed.h5ad from sc-count.\n"
                    "Example: python omicsclaw.py run sc-multi-count "
                    "--input sample1/processed.h5ad --input sample2/processed.h5ad "
                    "--output merged/"
                )
            adatas.append(_load_and_tag(path, sample_id=sid))
        combined = _merge_samples(adatas)
        input_file = None

    # Standardize
    standardized, contract = standardize_count_adata(
        combined,
        skill_name=SKILL_NAME,
        method="merge",
        source_label="multi_sample_merge",
        warnings=[],
    )

    # Metrics
    barcode_metrics = _barcode_metrics_df(standardized)
    per_sample = _per_sample_summary(barcode_metrics)

    # Tables
    table_files = _export_tables(output_dir, barcode_metrics, per_sample)

    # Figures
    plot_count_distributions(standardized, output_dir)
    raw_counts = np.asarray(standardized.X.sum(axis=1)).ravel()
    plot_barcode_rank(barcode_metrics["total_counts"].to_numpy(), output_dir, raw_counts=raw_counts)
    plot_count_complexity_scatter(barcode_metrics, output_dir)
    _plot_sample_composition(per_sample, output_dir)

    _write_figures_manifest(
        output_dir,
        [
            {
                "plot_id": "barcode_rank",
                "role": "overview",
                "backend": "python",
                "renderer": "plot_barcode_rank",
                "filename": "barcode_rank.png",
                "title": "Barcode rank curve (merged)",
                "description": "Barcode ranks across all merged samples.",
                "status": "rendered",
                "path": str(output_dir / "figures" / "barcode_rank.png"),
            },
            {
                "plot_id": "count_distributions",
                "role": "diagnostic",
                "backend": "python",
                "renderer": "plot_count_distributions",
                "filename": "count_distributions.png",
                "title": "Count distributions (merged)",
                "description": "Total counts and detected genes across merged barcodes.",
                "status": "rendered",
                "path": str(output_dir / "figures" / "count_distributions.png"),
            },
            {
                "plot_id": "count_complexity_scatter",
                "role": "diagnostic",
                "backend": "python",
                "renderer": "plot_count_complexity_scatter",
                "filename": "count_complexity_scatter.png",
                "title": "Count complexity per barcode (merged)",
                "description": "Counts versus detected genes for merged barcodes.",
                "status": "rendered",
                "path": str(output_dir / "figures" / "count_complexity_scatter.png"),
            },
            {
                "plot_id": "sample_composition",
                "role": "overview",
                "backend": "python",
                "renderer": "_plot_sample_composition",
                "filename": "sample_composition.png",
                "title": "Cell count per sample",
                "description": "Bar chart of cells contributed by each sample.",
                "status": "rendered",
                "path": str(output_dir / "figures" / "sample_composition.png"),
            },
        ],
    )

    # Reproducibility
    _write_reproducibility(output_dir, args, demo_mode=args.demo)

    # Save h5ad
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(standardized, output_h5ad)
    alias_paths = write_h5ad_aliases(output_h5ad, [output_dir / "standardized_input.h5ad"])

    # Summary
    summary = {
        "method": "merge",
        "n_samples": int(per_sample.shape[0]),
        "n_cells": int(standardized.n_obs),
        "n_genes": int(standardized.n_vars),
        "median_counts": float(barcode_metrics["total_counts"].median()),
        "median_genes": float(barcode_metrics["detected_genes"].median()),
    }

    # Degenerate output detection
    diagnostics: dict = {"degenerate": False, "suggested_actions": []}
    if summary["n_cells"] == 0:
        diagnostics["degenerate"] = True
        diagnostics["zero_cells"] = True
        diagnostics["suggested_actions"].append(
            "No cells after merge. Check that each input processed.h5ad contains cells."
        )
    if summary["n_samples"] < 2 and not args.demo:
        diagnostics["single_sample"] = True
        diagnostics["suggested_actions"].append(
            "Only one sample detected. Use sc-count for single-sample workflows."
        )
    imbalanced = per_sample[per_sample["n_cells"] < per_sample["n_cells"].median() * 0.1]
    if not imbalanced.empty:
        diagnostics["imbalanced_samples"] = imbalanced["sample_id"].tolist()
        diagnostics["suggested_actions"].append(
            f"Samples {imbalanced['sample_id'].tolist()} have very few cells relative to others. "
            "Consider checking those samples for QC issues before merging."
        )

    _write_report(output_dir, summary=summary, per_sample=per_sample, diagnostics=diagnostics)

    result_data = {
        "method": "merge",
        "params": {
            "input_paths": args.input_paths,
            "sample_ids": args.sample_ids,
        },
        "input_contract": contract,
        "matrix_contract": standardized.uns.get("omicsclaw_matrix_contract", {}),
        "output_h5ad": "processed.h5ad",
        "summary_tables": table_files,
        "visualization": {
            "recipe_id": "standard-sc-multi-count-gallery",
            "available_figure_data": {
                "barcode_metrics": table_files["barcode_metrics"],
                "per_sample_summary": table_files["per_sample_summary"],
            },
        },
        "output_files": {
            "processed_h5ad": str(output_h5ad),
            "compatibility_aliases": [str(p) for p in alias_paths],
        },
        "per_sample_summary": per_sample.to_dict(orient="records"),
        "count_diagnostics": diagnostics,
    }
    result_data["next_steps"] = [
        {"skill": "sc-qc", "reason": "Compute QC metrics on the merged count matrix", "priority": "recommended"},
    ]
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, "")
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME, "summary": summary, "data": result_data,
    }

    # Stdout guidance
    if diagnostics["degenerate"]:
        print()
        print("  *** MERGE WARNING: degenerate output detected ***")
        for action in diagnostics["suggested_actions"]:
            print(f"    - {action}")
        print()

    print(f"\n{'=' * 60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'=' * 60}")
    print(f"  Output directory: {output_dir}")
    print(f"  Samples merged: {summary['n_samples']}")
    print(f"  Total cells: {summary['n_cells']:,}")
    print(f"  Total genes: {summary['n_genes']:,}")
    print(f"  Standardized output: {output_h5ad}")
    print()
    print(">> Next step: Run sc-qc for quality assessment")
    print(f"  python omicsclaw.py run sc-qc --input {output_h5ad} --output <dir>")


if __name__ == "__main__":
    main()
