#!/usr/bin/env python3
"""Bulk RNA-seq Co-expression Network Analysis -- WGCNA-style module detection.

Usage:
    python bulkrna_coexpression.py --input <counts.csv> --output <dir>
    python bulkrna_coexpression.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))
from skills._sdk import REPO_ROOT as _PROJECT_ROOT  # noqa: E402

from skills._sdk.report import (
    generate_report_footer,
    generate_report_header,
)
from skills._sdk.result import write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-coexpression"
SKILL_VERSION = "0.3.0"
SUPPORTED_METHODS = ("python", "wgcna")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def get_demo_data() -> tuple[pd.DataFrame, Path]:
    """Load the bundled demo count matrix.

    Returns (DataFrame, path-to-csv).
    """
    demo_path = _PROJECT_ROOT / "examples" / "demo_bulkrna_counts.csv"
    if not demo_path.exists():
        raise FileNotFoundError(
            f"Demo data not found at {demo_path}. "
            "Please ensure examples/demo_bulkrna_counts.csv exists."
        )
    df = pd.read_csv(demo_path)
    logger.info(
        "Loaded demo data: %s (%d genes, %d columns)",
        demo_path, len(df), len(df.columns),
    )
    return df, demo_path


# ---------------------------------------------------------------------------
# R WGCNA integration
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Module detection
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Hub gene detection
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def generate_figures(output_dir: Path, summary: dict) -> list[str]:
    """Create diagnostic figures. Return list of created file paths."""
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    fit_df = summary["threshold_fit_df"]
    module_sizes = summary["module_sizes"]
    chosen_power = summary["soft_power"]

    # --- Scale-free topology fit ---
    fig, ax1 = plt.subplots(figsize=(8, 5))

    color_r2 = "tab:blue"
    ax1.set_xlabel("Soft Threshold (power)")
    ax1.set_ylabel("Scale-Free Topology Fit (R^2)", color=color_r2)
    ax1.plot(
        fit_df["power"], fit_df["r_squared"],
        "o-", color=color_r2, linewidth=1.5, markersize=6,
    )
    ax1.axhline(0.8, color="grey", linestyle="--", linewidth=0.8, alpha=0.7)
    # Mark the chosen power
    chosen_row = fit_df[fit_df["power"] == chosen_power]
    if len(chosen_row) > 0:
        ax1.plot(
            chosen_power, chosen_row["r_squared"].iloc[0],
            "D", color="red", markersize=10, zorder=5,
        )
    ax1.tick_params(axis="y", labelcolor=color_r2)

    color_k = "tab:orange"
    ax2 = ax1.twinx()
    ax2.set_ylabel("Mean Connectivity", color=color_k)
    ax2.plot(
        fit_df["power"], fit_df["mean_connectivity"],
        "s--", color=color_k, linewidth=1.2, markersize=5, alpha=0.8,
    )
    ax2.tick_params(axis="y", labelcolor=color_k)

    fig.suptitle("Scale-Free Topology Fit", fontsize=13)
    plt.tight_layout()
    path = fig_dir / "scale_free_fit.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    created.append(str(path))

    # --- Module sizes bar chart ---
    fig, ax = plt.subplots(figsize=(8, 5))
    mod_ids = sorted(module_sizes.keys())
    labels = [str(m) for m in mod_ids]
    sizes = [module_sizes[m] for m in mod_ids]

    # Color palette: grey for unassigned, tab colours for the rest
    n_colored = len([m for m in mod_ids if m != "grey"])
    cmap = matplotlib.colormaps["tab20"].resampled(max(n_colored, 1))
    colors = []
    color_idx = 0
    for m in mod_ids:
        if m == "grey":
            colors.append("lightgrey")
        else:
            colors.append(cmap(color_idx % 20))
            color_idx += 1

    bars = ax.bar(labels, sizes, color=colors, edgecolor="black", linewidth=0.5)
    ax.set_xlabel("Module")
    ax.set_ylabel("Number of Genes")
    ax.set_title("Co-expression Module Sizes")
    for i, v in enumerate(sizes):
        ax.text(i, v + max(sizes) * 0.01, str(v), ha="center", fontsize=9)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    path = fig_dir / "module_sizes.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    created.append(str(path))

    # --- Module assignment overview (colour-coded bar) ---
    fig, ax = plt.subplots(figsize=(10, 2))
    assignments = summary["module_assignments"]
    gene_order = sorted(assignments.keys(), key=lambda g: assignments[g])
    color_codes = {color: number + 1 for number, color in enumerate(sorted(set(assignments.values()) - {"grey"}))}
    color_codes["grey"] = 0
    mod_values = [color_codes[assignments[g]] for g in gene_order]

    cmap_full = matplotlib.colormaps["tab20"].resampled(max(summary["n_modules"] + 1, 2))
    color_array = []
    for v in mod_values:
        if v == 0:
            color_array.append([0.85, 0.85, 0.85, 1.0])
        else:
            color_array.append(list(cmap_full((v - 1) % 20)))

    color_array = np.array(color_array)
    ax.imshow(
        color_array[np.newaxis, :, :],
        aspect="auto",
        interpolation="nearest",
    )
    ax.set_yticks([])
    ax.set_xlabel("Genes (sorted by module)")
    ax.set_title("Module Assignments")
    plt.tight_layout()
    path = fig_dir / "module_dendrogram.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    created.append(str(path))

    return created


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write markdown report, result.json, tables, and reproducibility script."""
    # --- Markdown report ---
    header = generate_report_header(
        title="Bulk RNA-seq Co-expression Network Analysis Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Soft power": str(summary["soft_power"]),
            "Modules detected": str(summary["n_modules"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Genes used**: {summary['n_genes_used']}",
        f"- **Samples**: {summary['n_samples']}",
        f"- **Soft-thresholding power**: {summary['soft_power']}",
        f"- **Modules detected**: {summary['n_modules']}",
        "",
        "### Module Sizes\n",
        "| Module | Size |",
        "|--------|------|",
    ]
    for mod_id in sorted(summary["module_sizes"].keys()):
        label = str(mod_id)
        body_lines.append(f"| {label} | {summary['module_sizes'][mod_id]} |")

    body_lines.extend(["", "### Hub Genes\n"])
    for mod_id in sorted(summary["hub_genes"].keys()):
        genes = ", ".join(summary["hub_genes"][mod_id])
        body_lines.append(f"- **Module {mod_id}**: {genes}")

    body_lines.extend([
        "",
        "## Parameters\n",
    ])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    # --- result.json ---
    json_summary = {
        k: v for k, v in summary.items()
        if k not in ("threshold_fit_df", "module_assignments")
    }
    # Convert module_assignments to counts only for JSON (full table in CSV)
    json_summary["module_assignment_count"] = len(summary["module_assignments"])
    write_result_json(
        output_dir, SKILL_NAME, SKILL_VERSION, json_summary, {"params": params},
    )

    # --- Tables ---
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    # Module assignments
    assign_df = pd.DataFrame([
        {"gene": gene, "module": mod}
        for gene, mod in summary["module_assignments"].items()
    ])
    assign_df = assign_df.sort_values(["module", "gene"]).reset_index(drop=True)
    assign_df.to_csv(tables_dir / "module_assignments.csv", index=False)

    # Hub genes
    hub_records = []
    for mod_id, genes in summary["hub_genes"].items():
        for rank, gene in enumerate(genes, 1):
            hub_records.append({"module": mod_id, "rank": rank, "gene": gene})
    hub_df = pd.DataFrame(hub_records, columns=["module", "rank", "gene"])
    hub_df.to_csv(tables_dir / "hub_genes.csv", index=False)

    # Threshold fit
    summary["threshold_fit_df"].to_csv(
        tables_dir / "threshold_fit.csv", index=False,
    )

    # --- Reproducibility ---
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    cmd_parts = ["python bulkrna_coexpression.py"]
    if params.get("input_file"):
        cmd_parts.append(f"--input {params['input_file']}")
    if params.get("power") is not None:
        cmd_parts.append(f"--power {params['power']}")
    cmd_parts.append(f"--min-module-size {params.get('min_module_size', 10)}")
    cmd_parts.append(f"--output {output_dir}")
    (repro_dir / "commands.sh").write_text(
        "#!/bin/bash\n" + " \\\n  ".join(cmd_parts) + "\n"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Bulk RNA-seq Co-expression Network Analysis (WGCNA-style)",
    )
    parser.add_argument(
        "--input", dest="input_path",
        help="Path to counts CSV (gene x sample)",
    )
    parser.add_argument(
        "--output", dest="output_dir", required=True,
        help="Output directory",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run with bundled demo data",
    )
    parser.add_argument(
        "--power", type=int, default=None,
        help="Soft-thresholding power (auto-selected if omitted)",
    )
    parser.add_argument(
        "--min-module-size", type=int, default=10,
        help="Minimum genes per module (default: 10)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        counts, data_path = get_demo_data()
        input_file = str(data_path)
    else:
        if not args.input_path:
            parser.error("--input is required when not using --demo")
        data_path = Path(args.input_path)
        if not data_path.exists():
            raise FileNotFoundError(f"Input file not found: {data_path}")
        counts = pd.read_csv(data_path)
        input_file = str(data_path)

    from skills._sdk.notebook import load_skill
    api = load_skill(SKILL_NAME)
    table = api.analyze(counts.set_index(counts.columns[0]), power=args.power, min_module_size=args.min_module_size)
    diagnostics = api.run_info(table, keep=False)
    summary = diagnostics.pop("summary")
    summary["threshold_fit_df"] = api.threshold_fit(table)

    figures = generate_figures(output_dir, summary)
    logger.info("Generated %d figures.", len(figures))

    params = {
        "power": args.power,
        "min_module_size": args.min_module_size,
        "input_file": input_file,
        "run_info": diagnostics,
    }
    write_report(
        output_dir, summary,
        input_file if not args.demo else None,
        params,
    )

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"  Soft power: {summary['soft_power']}")
    print(f"  Modules: {summary['n_modules']}")
    print(f"  Genes used: {summary['n_genes_used']}")
    for mod_id, hubs in sorted(summary["hub_genes"].items()):
        print(f"  Module {mod_id} hubs: {', '.join(hubs)}")


if __name__ == "__main__":
    main()
