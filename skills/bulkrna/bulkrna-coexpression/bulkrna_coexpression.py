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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-coexpression"
SKILL_VERSION = "0.3.0"


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
# Soft threshold selection
# ---------------------------------------------------------------------------

def _select_soft_threshold(
    cor_matrix: np.ndarray,
    powers: list[int] | None = None,
) -> tuple[int, pd.DataFrame]:
    """Test soft-thresholding powers and pick the best one.

    For each candidate power, compute the adjacency matrix |cor|^power,
    derive connectivity, and evaluate the scale-free topology fit (R^2 of
    log(k) vs log(p(k))).

    Parameters
    ----------
    cor_matrix : np.ndarray
        Square gene-gene Pearson correlation matrix.
    powers : list[int] | None
        Candidate powers to evaluate.  Defaults to a standard WGCNA range.

    Returns
    -------
    best_power : int
        First power where R^2 > 0.8, or the power with the highest R^2.
    fit_df : pd.DataFrame
        Columns: power, r_squared, mean_connectivity.
    """
    if powers is None:
        powers = [1, 2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20]

    n_genes = cor_matrix.shape[0]
    abs_cor = np.abs(cor_matrix)
    records: list[dict] = []

    for power in powers:
        adjacency = abs_cor ** power
        np.fill_diagonal(adjacency, 0.0)
        connectivity = adjacency.sum(axis=0)
        mean_k = float(np.mean(connectivity))

        # Scale-free fit: R^2 of log10(k) vs log10(p(k))
        k_vals = connectivity[connectivity > 0]
        if len(k_vals) < 10:
            records.append({
                "power": power,
                "r_squared": 0.0,
                "mean_connectivity": round(mean_k, 4),
            })
            continue

        # Bin connectivity into a histogram for p(k)
        n_bins = max(10, int(np.sqrt(len(k_vals))))
        hist, bin_edges = np.histogram(k_vals, bins=n_bins)
        bin_centres = (bin_edges[:-1] + bin_edges[1:]) / 2.0

        # Keep only bins with non-zero counts
        mask = hist > 0
        if mask.sum() < 3:
            records.append({
                "power": power,
                "r_squared": 0.0,
                "mean_connectivity": round(mean_k, 4),
            })
            continue

        log_k = np.log10(bin_centres[mask])
        log_pk = np.log10(hist[mask] / hist[mask].sum())

        # Linear regression: R^2
        if np.std(log_k) == 0:
            r_sq = 0.0
        else:
            correlation = np.corrcoef(log_k, log_pk)[0, 1]
            r_sq = float(correlation ** 2) if not np.isnan(correlation) else 0.0

        records.append({
            "power": power,
            "r_squared": round(r_sq, 4),
            "mean_connectivity": round(mean_k, 4),
        })

    fit_df = pd.DataFrame(records)

    # Pick first power with R^2 > 0.8, otherwise the maximum
    above = fit_df[fit_df["r_squared"] > 0.8]
    if len(above) > 0:
        best_power = int(above.iloc[0]["power"])
    else:
        best_power = int(fit_df.loc[fit_df["r_squared"].idxmax(), "power"])

    logger.info(
        "Selected soft-threshold power=%d (R^2=%.3f, mean_k=%.1f)",
        best_power,
        float(fit_df.loc[fit_df["power"] == best_power, "r_squared"].iloc[0]),
        float(fit_df.loc[fit_df["power"] == best_power, "mean_connectivity"].iloc[0]),
    )
    return best_power, fit_df


# ---------------------------------------------------------------------------
# Module detection
# ---------------------------------------------------------------------------

def _detect_modules(
    cor_matrix: np.ndarray,
    power: int,
    min_module_size: int = 10,
) -> np.ndarray:
    """Detect co-expression modules using TOM-based hierarchical clustering.

    Parameters
    ----------
    cor_matrix : np.ndarray
        Square gene-gene Pearson correlation matrix.
    power : int
        Soft-thresholding power.
    min_module_size : int
        Minimum genes per module; smaller clusters go to module 0 (unassigned).

    Returns
    -------
    np.ndarray
        Integer module labels (0 = unassigned).
    """
    n = cor_matrix.shape[0]
    abs_cor = np.abs(cor_matrix)
    adjacency = abs_cor ** power
    np.fill_diagonal(adjacency, 0.0)

    # Connectivity per gene
    k = adjacency.sum(axis=0)

    # Topological Overlap Matrix (TOM)
    # TOM_ij = (sum_u(a_iu * a_uj) + a_ij) / (min(k_i, k_j) + 1 - a_ij)
    numerator = adjacency @ adjacency + adjacency
    min_k = np.minimum(k[:, None], k[None, :])
    denominator = min_k + 1.0 - adjacency

    # Avoid division by zero
    denominator[denominator < 1e-12] = 1e-12
    tom = numerator / denominator
    np.fill_diagonal(tom, 1.0)

    # Clip to [0, 1] for numerical safety
    tom = np.clip(tom, 0.0, 1.0)

    # TOM-based dissimilarity
    dist_matrix = 1.0 - tom
    np.fill_diagonal(dist_matrix, 0.0)

    # Convert to condensed distance for scipy
    dist_condensed = squareform(dist_matrix, checks=False)

    # Hierarchical clustering (average linkage, as in WGCNA)
    Z = linkage(dist_condensed, method="average")

    # Dynamic tree cut: use a fixed height threshold
    # Pick a threshold that gives reasonable module count
    # Try multiple thresholds and pick one giving between 2 and 30 modules
    best_labels = None
    best_n_modules = 0

    for threshold in np.arange(0.80, 0.99, 0.02):
        labels = fcluster(Z, t=threshold, criterion="distance")
        # Count modules meeting min size
        unique, counts = np.unique(labels, return_counts=True)
        n_valid = int((counts >= min_module_size).sum())
        if 2 <= n_valid <= 30:
            best_labels = labels
            best_n_modules = n_valid
            break

    if best_labels is None:
        # Fallback: use a moderate threshold
        best_labels = fcluster(Z, t=0.90, criterion="distance")

    # Relabel: assign small modules to 0 (unassigned), renumber the rest from 1
    unique, counts = np.unique(best_labels, return_counts=True)
    module_map: dict[int, int] = {}
    next_id = 1
    for label, count in sorted(zip(unique, counts), key=lambda x: -x[1]):
        if count >= min_module_size:
            module_map[label] = next_id
            next_id += 1
        else:
            module_map[label] = 0

    modules = np.array([module_map[lbl] for lbl in best_labels])
    n_assigned = int((modules > 0).sum())
    n_unassigned = int((modules == 0).sum())
    n_modules = len(set(modules)) - (1 if 0 in modules else 0)
    logger.info(
        "Detected %d modules (%d genes assigned, %d unassigned)",
        n_modules, n_assigned, n_unassigned,
    )
    return modules


# ---------------------------------------------------------------------------
# Hub gene detection
# ---------------------------------------------------------------------------

def _find_hub_genes(
    cor_matrix: np.ndarray,
    modules: np.ndarray,
    gene_names: list[str],
    power: int,
    n_hubs: int = 5,
) -> dict:
    """Identify hub genes per module by intra-module connectivity.

    For each module, compute the mean adjacency of each gene to all other
    genes in the same module (approximation of kME).

    Parameters
    ----------
    cor_matrix : np.ndarray
        Gene-gene Pearson correlation matrix.
    modules : np.ndarray
        Module labels (0 = unassigned).
    gene_names : list[str]
        Gene names in the same order as the correlation matrix.
    power : int
        Soft-thresholding power.
    n_hubs : int
        Number of top hub genes to return per module.

    Returns
    -------
    dict
        Mapping of module_id -> list of top hub gene names.
    """
    abs_cor = np.abs(cor_matrix)
    adjacency = abs_cor ** power
    np.fill_diagonal(adjacency, 0.0)

    hub_genes: dict[int, list[str]] = {}
    unique_modules = sorted(set(modules))

    for mod_id in unique_modules:
        if mod_id == 0:
            continue
        indices = np.where(modules == mod_id)[0]
        if len(indices) < 2:
            hub_genes[mod_id] = [gene_names[i] for i in indices]
            continue

        # Intra-module connectivity: mean adjacency to other module members
        sub_adj = adjacency[np.ix_(indices, indices)]
        intra_k = sub_adj.mean(axis=1)

        # Sort by descending connectivity, take top n_hubs
        top_idx = np.argsort(-intra_k)[: min(n_hubs, len(indices))]
        hub_genes[mod_id] = [gene_names[indices[i]] for i in top_idx]

    return hub_genes


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def core_analysis(
    counts: pd.DataFrame,
    *,
    power: int | None = None,
    min_module_size: int = 10,
) -> dict:
    """Run WGCNA-style co-expression analysis.

    Parameters
    ----------
    counts : pd.DataFrame
        Genes-by-samples count matrix.  First column is gene identifiers,
        remaining columns are sample counts.
    power : int | None
        Soft-thresholding power.  Auto-selected if None.
    min_module_size : int
        Minimum genes per module.

    Returns
    -------
    dict
        Summary with keys: n_genes_used, n_samples, soft_power, n_modules,
        module_sizes, hub_genes, module_assignments, threshold_fit_df.
    """
    gene_col = counts.columns[0]
    sample_cols = [c for c in counts.columns if c != gene_col]
    gene_names = counts[gene_col].tolist()

    n_samples = len(sample_cols)
    logger.info("Input: %d genes, %d samples", len(gene_names), n_samples)

    # Log2 transform
    expr = counts[sample_cols].values.astype(float)
    expr = np.log2(expr + 1)

    # Filter low-variance genes (keep top 80%)
    variances = np.var(expr, axis=1)
    threshold = np.percentile(variances, 20)
    keep_mask = variances >= threshold
    expr_filt = expr[keep_mask]
    gene_names_filt = [g for g, m in zip(gene_names, keep_mask) if m]

    n_genes_used = len(gene_names_filt)
    logger.info("After variance filter: %d genes retained", n_genes_used)

    # Pearson correlation matrix
    cor_matrix = np.corrcoef(expr_filt)
    # Handle NaN from constant rows (shouldn't happen after variance filter)
    cor_matrix = np.nan_to_num(cor_matrix, nan=0.0)

    # Soft threshold selection
    if power is None:
        best_power, fit_df = _select_soft_threshold(cor_matrix)
    else:
        best_power = power
        _, fit_df = _select_soft_threshold(cor_matrix)
        logger.info("Using user-specified power=%d", best_power)

    # Module detection
    modules = _detect_modules(cor_matrix, best_power, min_module_size)

    # Module sizes
    unique_mods, mod_counts = np.unique(modules, return_counts=True)
    module_sizes: dict[int, int] = {}
    for mod_id, count in zip(unique_mods, mod_counts):
        module_sizes[int(mod_id)] = int(count)

    n_modules = len([m for m in unique_mods if m > 0])

    # Hub genes
    hub_genes = _find_hub_genes(
        cor_matrix, modules, gene_names_filt, best_power, n_hubs=5,
    )

    # Module assignments as dict
    module_assignments = {
        gene: int(mod) for gene, mod in zip(gene_names_filt, modules)
    }

    return {
        "n_genes_used": n_genes_used,
        "n_samples": n_samples,
        "soft_power": best_power,
        "n_modules": n_modules,
        "module_sizes": module_sizes,
        "hub_genes": {int(k): v for k, v in hub_genes.items()},
        "module_assignments": module_assignments,
        "threshold_fit_df": fit_df,
    }


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
    labels = [f"M{m}" if m > 0 else "Unassigned" for m in mod_ids]
    sizes = [module_sizes[m] for m in mod_ids]

    # Color palette: grey for unassigned, tab colours for the rest
    n_colored = len([m for m in mod_ids if m > 0])
    cmap = plt.cm.get_cmap("tab20", max(n_colored, 1))
    colors = []
    color_idx = 0
    for m in mod_ids:
        if m == 0:
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
    mod_values = [assignments[g] for g in gene_order]

    cmap_full = plt.cm.get_cmap("tab20", max(summary["n_modules"] + 1, 2))
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
        label = f"M{mod_id}" if mod_id > 0 else "Unassigned"
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
    hub_df = pd.DataFrame(hub_records)
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

    summary = core_analysis(
        counts,
        power=args.power,
        min_module_size=args.min_module_size,
    )

    figures = generate_figures(output_dir, summary)
    logger.info("Generated %d figures.", len(figures))

    params = {
        "power": args.power,
        "min_module_size": args.min_module_size,
        "input_file": input_file,
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
