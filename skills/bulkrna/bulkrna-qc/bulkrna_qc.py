#!/usr/bin/env python3
"""Bulk RNA-seq Count Matrix QC — library size, gene detection, sample correlation.

Usage:
    python bulkrna_qc.py --input <counts.csv> --output <dir>
    python bulkrna_qc.py --demo --output <dir>
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

SKILL_NAME = "bulkrna-qc"
SKILL_VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def _generate_demo_counts(n_genes: int = 200, n_ctrl: int = 3, n_treat: int = 3) -> pd.DataFrame:
    """Generate synthetic bulk RNA-seq count data for demo mode."""
    np.random.seed(42)
    genes = [f"GENE_{i:03d}" for i in range(1, n_genes + 1)]
    samples_ctrl = [f"ctrl_{i}" for i in range(1, n_ctrl + 1)]
    samples_treat = [f"treat_{i}" for i in range(1, n_treat + 1)]
    samples = samples_ctrl + samples_treat

    # Base expression: negative binomial (realistic RNA-seq-like distribution)
    mu = np.random.lognormal(mean=3.0, sigma=2.0, size=n_genes)
    counts = np.zeros((n_genes, len(samples)), dtype=int)
    for j, samp in enumerate(samples):
        lib_factor = np.random.uniform(0.8, 1.2)
        for i in range(n_genes):
            counts[i, j] = max(0, int(np.random.negative_binomial(
                n=max(1, int(mu[i] * 0.3)),
                p=0.3 / (0.3 + mu[i] * lib_factor),
            )))

    # Add DE signal: first 50 genes upregulated, next 50 downregulated in treatment
    for j in range(n_ctrl, len(samples)):
        counts[0:50, j] = (counts[0:50, j] * np.random.uniform(2.0, 4.0, size=50)).astype(int)
        counts[50:100, j] = (counts[50:100, j] * np.random.uniform(0.1, 0.4, size=50)).astype(int)

    df = pd.DataFrame(counts, index=genes, columns=samples)
    return df


def get_demo_data() -> tuple[pd.DataFrame, Path]:
    """Load the demo bulk RNA-seq count matrix from examples/.

    Falls back to generating synthetic data if the demo CSV does not exist.
    """
    demo_path = _PROJECT_ROOT / "examples" / "demo_bulkrna_counts.csv"
    if demo_path.exists():
        df = pd.read_csv(demo_path, index_col=0)
        logger.info("Loaded demo data: %d genes x %d samples from %s",
                    df.shape[0], df.shape[1], demo_path)
        return df, demo_path

    logger.info("Demo CSV not found at %s — generating synthetic data.", demo_path)
    df = _generate_demo_counts()
    demo_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(demo_path)
    logger.info("Wrote synthetic demo data: %d genes x %d samples to %s",
                df.shape[0], df.shape[1], demo_path)
    return df, demo_path


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def _detect_sample_groups(sample_names: list[str]) -> dict[str, str]:
    """Auto-detect sample groups from common prefix patterns.

    Returns a mapping of sample_name -> group_label.
    """
    # Try common prefix patterns
    groups: dict[str, str] = {}
    for name in sample_names:
        parts = name.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            groups[name] = parts[0]
        else:
            groups[name] = name
    return groups


def core_analysis(counts: pd.DataFrame) -> dict:
    """Compute library size QC, gene detection rates, sample correlation,
    and outlier flagging.

    Parameters
    ----------
    counts : DataFrame
        Gene-by-sample count matrix (genes as rows, samples as columns).

    Returns
    -------
    dict with summary statistics.
    """
    n_genes, n_samples = counts.shape
    sample_names = list(counts.columns)

    # Library sizes
    lib_sizes = counts.sum(axis=0)
    library_sizes = {s: int(v) for s, v in lib_sizes.items()}
    mean_lib = float(lib_sizes.mean())
    median_lib = float(lib_sizes.median())
    cv_lib = float(lib_sizes.std() / lib_sizes.mean()) if mean_lib > 0 else 0.0

    # Gene detection: how many samples detect each gene (count > 0)
    gene_detection = (counts > 0).sum(axis=1)
    n_zero_genes = int((gene_detection == 0).sum())

    # CPM (Counts Per Million)
    cpm = counts.div(lib_sizes, axis=1) * 1e6

    # Per-sample stats
    per_sample_stats = {}
    for sample in sample_names:
        total = int(counts[sample].sum())
        n_detected = int((counts[sample] > 0).sum())
        pct_detected = round(100.0 * n_detected / n_genes, 2) if n_genes > 0 else 0.0
        per_sample_stats[sample] = {
            "total_counts": total,
            "n_detected_genes": n_detected,
            "pct_detected": pct_detected,
        }

    # Sample correlation matrix (Pearson on log-CPM)
    log_cpm = np.log2(cpm + 1)
    corr_matrix = log_cpm.astype(float).corr(method="pearson")
    corr_list = corr_matrix.values.tolist()

    # Outlier detection: flag samples with mean correlation < median - 2*MAD
    mean_corrs = corr_matrix.mean(axis=0)
    median_corr = float(mean_corrs.median())
    mad_corr = float((mean_corrs - median_corr).abs().median()) * 1.4826
    outlier_threshold = median_corr - 2.0 * mad_corr
    outlier_samples = [s for s in sample_names
                       if float(mean_corrs[s]) < outlier_threshold]

    # Auto-detect groups
    sample_groups = _detect_sample_groups(sample_names)

    summary = {
        "n_genes": n_genes,
        "n_samples": n_samples,
        "sample_names": sample_names,
        "sample_groups": sample_groups,
        "library_sizes": library_sizes,
        "mean_library_size": round(mean_lib, 1),
        "median_library_size": round(median_lib, 1),
        "cv_library_size": round(cv_lib, 4),
        "gene_detection": {g: int(v) for g, v in gene_detection.items()},
        "n_zero_genes": n_zero_genes,
        "per_sample_stats": per_sample_stats,
        "sample_correlation_matrix": corr_list,
        "outlier_samples": outlier_samples,
        "cpm": cpm,
    }
    return summary


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def generate_figures(output_dir: Path, summary: dict) -> list[str]:
    """Generate QC figures and return list of figure paths."""
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    sample_names = summary["sample_names"]
    lib_sizes = summary["library_sizes"]
    sample_groups = summary.get("sample_groups", {})

    # Auto-generate group colors
    from matplotlib.patches import Patch
    unique_groups = sorted(set(sample_groups.values()))
    group_palette = {}
    base_colors = ["#4878CF", "#E8A02F", "#5BA05B", "#E84D60", "#8C564B",
                   "#9467BD", "#BCBD22", "#17BECF"]
    for i, grp in enumerate(unique_groups):
        group_palette[grp] = base_colors[i % len(base_colors)]

    # 1. Library sizes bar chart
    fig, ax = plt.subplots(figsize=(max(6, len(sample_names) * 0.6), 4))
    colors = [group_palette.get(sample_groups.get(s, "unknown"), "grey")
              for s in sample_names]
    sizes = [lib_sizes[s] for s in sample_names]
    ax.bar(range(len(sample_names)), sizes, color=colors,
           edgecolor="white", linewidth=0.5)
    ax.set_xticks(range(len(sample_names)))
    ax.set_xticklabels(sample_names, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Total counts")
    ax.set_title("Library Sizes per Sample")
    # Highlight outliers
    outliers = summary.get("outlier_samples", [])
    for i, s in enumerate(sample_names):
        if s in outliers:
            ax.get_children()[i].set_edgecolor("red")
            ax.get_children()[i].set_linewidth(2.5)
    # Legend
    legend_elements = [Patch(facecolor=c, label=g) for g, c in group_palette.items()]
    if outliers:
        legend_elements.append(Patch(facecolor="white", edgecolor="red",
                                     linewidth=2, label="outlier"))
    ax.legend(handles=legend_elements, loc="upper right", fontsize=8)
    fig.tight_layout()
    p = fig_dir / "library_sizes.png"
    fig.savefig(p, dpi=150)
    plt.close("all")
    paths.append(str(p))

    # 2. Gene detection histogram
    detection_values = list(summary["gene_detection"].values())
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(detection_values, bins=range(0, summary["n_samples"] + 2),
            color="#5BA05B", edgecolor="white", linewidth=0.5, align="left")
    ax.set_xlabel("Number of samples detecting gene")
    ax.set_ylabel("Number of genes")
    ax.set_title("Gene Detection Rate Distribution")
    fig.tight_layout()
    p = fig_dir / "gene_detection.png"
    fig.savefig(p, dpi=150)
    plt.close("all")
    paths.append(str(p))

    # 3. Sample correlation heatmap (computed on log-CPM)
    corr = np.array(summary["sample_correlation_matrix"])
    fig, ax = plt.subplots(figsize=(max(6, len(sample_names) * 0.55),
                                    max(5, len(sample_names) * 0.45)))
    im = ax.imshow(corr, cmap="RdYlBu_r", vmin=0.8, vmax=1.0, aspect="auto")
    ax.set_xticks(range(len(sample_names)))
    ax.set_yticks(range(len(sample_names)))
    ax.set_xticklabels(sample_names, rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels(sample_names, fontsize=7)
    ax.set_title("Sample Pearson Correlation (log-CPM)")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    p = fig_dir / "sample_correlation.png"
    fig.savefig(p, dpi=150)
    plt.close("all")
    paths.append(str(p))

    # 4. Log-CPM density plot
    cpm = summary.get("cpm")
    if cpm is not None:
        fig, ax = plt.subplots(figsize=(8, 5))
        for i, sample in enumerate(sample_names):
            log_vals = np.log2(cpm[sample].values + 1)
            log_vals = log_vals[log_vals > 0]  # exclude zero-count genes
            if len(log_vals) > 0:
                from scipy.stats import gaussian_kde
                try:
                    kde = gaussian_kde(log_vals, bw_method=0.3)
                    x_grid = np.linspace(0, log_vals.max() + 1, 200)
                    ax.plot(x_grid, kde(x_grid),
                            color=colors[i], alpha=0.8, label=sample, linewidth=1.2)
                except np.linalg.LinAlgError:
                    ax.hist(log_vals, bins=50, density=True, alpha=0.3,
                            color=colors[i], label=sample)
        ax.set_xlabel("log2(CPM + 1)")
        ax.set_ylabel("Density")
        ax.set_title("Expression Density (log-CPM)")
        ax.legend(fontsize=7, loc="upper right")
        fig.tight_layout()
        p = fig_dir / "expression_density.png"
        fig.savefig(p, dpi=150)
        plt.close("all")
        paths.append(str(p))

    logger.info("Generated %d figures in %s", len(paths), fig_dir)
    return paths


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write markdown report, result.json, tables, and reproducibility info."""
    # --- report.md ---
    header = generate_report_header(
        title="Bulk RNA-seq Count Matrix QC Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Genes": str(summary["n_genes"]),
            "Samples": str(summary["n_samples"]),
        },
    )

    outlier_samples = summary.get("outlier_samples", [])
    body_lines = [
        "## Summary\n",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Samples**: {summary['n_samples']}",
        f"- **Mean library size**: {summary['mean_library_size']:,.1f}",
        f"- **Median library size**: {summary['median_library_size']:,.1f}",
        f"- **CV of library sizes**: {summary['cv_library_size']:.4f}",
        f"- **Genes with zero counts across all samples**: {summary['n_zero_genes']}",
    ]
    if outlier_samples:
        body_lines.append(f"- **⚠ Outlier samples** (low mean correlation): {', '.join(outlier_samples)}")
    else:
        body_lines.append("- **Outlier samples**: none detected")

    body_lines.extend([
        "",
        "## Per-Sample Statistics\n",
        "| Sample | Group | Total Counts | Detected Genes | % Detected | Flag |",
        "|--------|-------|-------------|----------------|------------|------|",
    ])
    sample_groups = summary.get("sample_groups", {})
    for sample, stats in summary["per_sample_stats"].items():
        flag = "⚠ outlier" if sample in outlier_samples else "✓"
        group = sample_groups.get(sample, "—")
        body_lines.append(
            f"| {sample} | {group} | {stats['total_counts']:,} | "
            f"{stats['n_detected_genes']} | {stats['pct_detected']:.1f}% | {flag} |"
        )

    body_lines.extend(["", "## Figures\n",
                        "- `figures/library_sizes.png` — Library size bar chart",
                        "- `figures/gene_detection.png` — Gene detection histogram",
                        "- `figures/sample_correlation.png` — Sample correlation heatmap (log-CPM Pearson)",
                        "- `figures/expression_density.png` — Log-CPM expression density plot",
                        ""])

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(
        header + "\n".join(body_lines) + "\n" + footer
    )

    # --- result.json ---
    # Strip large fields for JSON envelope
    json_summary = {k: v for k, v in summary.items()
                    if k not in ("gene_detection", "sample_correlation_matrix", "cpm")}
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, json_summary, params)

    # --- tables ---
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    # tables/cpm.csv
    cpm = summary.get("cpm")
    if cpm is not None:
        cpm.to_csv(tables_dir / "cpm_normalized.csv")

    # tables/sample_stats.csv
    rows = []
    for sample, stats in summary["per_sample_stats"].items():
        rows.append({"sample": sample, **stats})
    pd.DataFrame(rows).to_csv(tables_dir / "sample_stats.csv", index=False)

    # --- reproducibility/commands.sh ---
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    input_arg = f"--input {input_file}" if input_file else "--demo"
    cmd = (
        "#!/usr/bin/env bash\n"
        f"# Reproduce this analysis\n"
        f"python skills/bulkrna/bulkrna-qc/bulkrna_qc.py "
        f"{input_arg} --output {output_dir}\n"
    )
    (repro_dir / "commands.sh").write_text(cmd)

    logger.info("Report written to %s", output_dir / "report.md")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Bulk RNA-seq Count Matrix QC — library size, gene detection, correlation"
    )
    parser.add_argument("--input", dest="input_path",
                        help="Input CSV count matrix (genes as rows, samples as columns)")
    parser.add_argument("--output", dest="output_dir", required=True,
                        help="Output directory")
    parser.add_argument("--demo", action="store_true",
                        help="Run with built-in demo data")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        counts, demo_path = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input is required when not using --demo")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        counts = pd.read_csv(input_path, index_col=0)
        input_file = args.input_path

    logger.info("Analysing count matrix: %d genes x %d samples", *counts.shape)

    summary = core_analysis(counts)
    generate_figures(output_dir, summary)
    write_report(output_dir, summary, input_file, {"mode": "demo" if args.demo else "file"})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Bulk RNA-seq QC complete: {summary['n_genes']} genes, "
          f"{summary['n_samples']} samples, "
          f"mean library size {summary['mean_library_size']:,.0f}")


if __name__ == "__main__":
    main()
