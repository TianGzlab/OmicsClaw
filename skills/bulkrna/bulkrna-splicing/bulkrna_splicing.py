#!/usr/bin/env python3
"""Bulk RNA-seq Alternative Splicing Analysis — PSI quantification, splicing event summary.

Usage:
    python bulkrna_splicing.py --input <counts.csv> --output <dir>
    python bulkrna_splicing.py --demo --output <dir>
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
from scipy import stats

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

SKILL_NAME = "bulkrna-splicing"
SKILL_VERSION = "0.3.0"
EVENT_TYPES = ("SE", "A5SS", "A3SS", "MXE", "RI")


# ---------------------------------------------------------------------------
# Benjamini-Hochberg FDR correction
# ---------------------------------------------------------------------------

def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Manual Benjamini-Hochberg FDR correction."""
    pv = np.asarray(pvalues, dtype=float)
    n = len(pv)
    if n == 0:
        return pv
    order = np.argsort(pv)
    sorted_p = pv[order]

    adjusted = np.empty(n, dtype=float)
    adjusted[-1] = sorted_p[-1]
    for i in range(n - 2, -1, -1):
        rank = i + 1
        adjusted[i] = min(sorted_p[i] * n / rank, adjusted[i + 1])
    adjusted = np.clip(adjusted, 0.0, 1.0)

    result = np.empty(n, dtype=float)
    result[order] = adjusted
    return result


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def _generate_demo_splicing_data(n_events: int = 100) -> pd.DataFrame:
    """Generate synthetic splicing event data.

    Creates a DataFrame with columns: event_id, event_type, gene, psi_ctrl,
    psi_treat, delta_psi, pvalue, padj.  Approximately 20% of events are
    simulated as differentially spliced (shifted PSI by +/-0.2).
    """
    np.random.seed(42)

    event_types = np.random.choice(EVENT_TYPES, size=n_events)
    genes = [f"GENE_{np.random.randint(1, 51):03d}" for _ in range(n_events)]
    event_ids = [
        f"{et}_{gene}_{i + 1}" for i, (et, gene) in enumerate(zip(event_types, genes))
    ]

    # Base PSI values for control (mean around 0.2-0.8)
    psi_ctrl = np.random.uniform(0.2, 0.8, size=n_events)

    # Treatment PSI: ~20% of events get a shift of +/-0.2
    psi_treat = psi_ctrl.copy()
    n_diff = int(n_events * 0.2)
    diff_indices = np.random.choice(n_events, size=n_diff, replace=False)
    shifts = np.random.choice([-0.2, 0.2], size=n_diff)
    psi_treat[diff_indices] += shifts
    psi_treat = np.clip(psi_treat, 0.0, 1.0)

    # Add small noise to non-differential events
    noise = np.random.normal(0, 0.02, size=n_events)
    non_diff_mask = np.ones(n_events, dtype=bool)
    non_diff_mask[diff_indices] = False
    psi_treat[non_diff_mask] += noise[non_diff_mask]
    psi_treat = np.clip(psi_treat, 0.0, 1.0)

    delta_psi = psi_treat - psi_ctrl

    # Compute p-values from synthetic replicates (3 per condition)
    pvalues = np.ones(n_events)
    for i in range(n_events):
        ctrl_reps = np.random.normal(psi_ctrl[i], 0.03, size=3)
        treat_reps = np.random.normal(psi_treat[i], 0.03, size=3)
        ctrl_reps = np.clip(ctrl_reps, 0.0, 1.0)
        treat_reps = np.clip(treat_reps, 0.0, 1.0)
        _, pval = stats.ttest_ind(ctrl_reps, treat_reps, equal_var=False)
        pvalues[i] = pval if not np.isnan(pval) else 1.0

    padj = _benjamini_hochberg(pvalues)

    df = pd.DataFrame({
        "event_id": event_ids,
        "event_type": event_types,
        "gene": genes,
        "psi_ctrl": np.round(psi_ctrl, 4),
        "psi_treat": np.round(psi_treat, 4),
        "delta_psi": np.round(delta_psi, 4),
        "pvalue": pvalues,
        "padj": padj,
    })

    logger.info("Generated %d synthetic splicing events (%d differential).", n_events, n_diff)
    return df


def get_demo_data() -> tuple[pd.DataFrame, None]:
    """Return synthetic splicing event data for demo mode."""
    return _generate_demo_splicing_data(), None


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def core_analysis(
    events_df: pd.DataFrame,
    *,
    dpsi_cutoff: float = 0.1,
    padj_cutoff: float = 0.05,
) -> dict:
    """Analyse splicing events and return a summary dict.

    Parameters
    ----------
    events_df : pd.DataFrame
        Must contain columns: event_type, gene, delta_psi, padj.
    dpsi_cutoff : float
        Minimum |delta_psi| for significance.
    padj_cutoff : float
        Maximum adjusted p-value for significance.

    Returns
    -------
    dict with keys: n_events, n_genes_affected, event_type_counts,
        n_significant, n_up, n_down, significant_events_df, top_events.
    """
    n_events = len(events_df)
    n_genes_affected = events_df["gene"].nunique()

    event_type_counts = events_df["event_type"].value_counts().to_dict()

    sig_mask = (events_df["delta_psi"].abs() > dpsi_cutoff) & (events_df["padj"] < padj_cutoff)
    sig_df = events_df[sig_mask].copy()

    n_significant = len(sig_df)
    n_up = int((sig_df["delta_psi"] > 0).sum())
    n_down = int((sig_df["delta_psi"] < 0).sum())

    top_events = (
        events_df
        .assign(_abs_dpsi=events_df["delta_psi"].abs())
        .nlargest(20, "_abs_dpsi")
        .drop(columns=["_abs_dpsi"])
    )

    return {
        "n_events": n_events,
        "n_genes_affected": n_genes_affected,
        "event_type_counts": event_type_counts,
        "n_significant": n_significant,
        "n_up": n_up,
        "n_down": n_down,
        "dpsi_cutoff": dpsi_cutoff,
        "padj_cutoff": padj_cutoff,
        "significant_events_df": sig_df,
        "top_events": top_events,
        "events_df": events_df,
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def generate_figures(
    output_dir: Path,
    summary: dict,
    events_df: pd.DataFrame,
) -> list[str]:
    """Create splicing analysis figures. Return list of file paths."""
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    # --- Event type distribution (pie chart) ---
    fig, ax = plt.subplots(figsize=(7, 7))
    counts = summary["event_type_counts"]
    labels = list(counts.keys())
    sizes = list(counts.values())
    colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6"][:len(labels)]
    ax.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%", startangle=140)
    ax.set_title("Splicing Event Type Distribution")
    plt.tight_layout()
    path = fig_dir / "event_type_distribution.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    created.append(str(path))

    # --- Delta-PSI distribution (histogram) ---
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(events_df["delta_psi"], bins=40, color="steelblue", edgecolor="white", alpha=0.85)
    ax.axvline(0, color="black", ls="-", lw=0.8)
    ax.axvline(-summary["dpsi_cutoff"], color="red", ls="--", lw=0.8, label=f'-{summary["dpsi_cutoff"]}')
    ax.axvline(summary["dpsi_cutoff"], color="red", ls="--", lw=0.8, label=f'+{summary["dpsi_cutoff"]}')
    ax.set_xlabel("Delta PSI (treatment - control)")
    ax.set_ylabel("Number of events")
    ax.set_title("Delta-PSI Distribution")
    ax.legend()
    plt.tight_layout()
    path = fig_dir / "dpsi_distribution.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    created.append(str(path))

    # --- Volcano plot (delta_psi vs -log10 pvalue) ---
    fig, ax = plt.subplots(figsize=(8, 6))
    neg_log10p = -np.log10(events_df["pvalue"].clip(lower=1e-300))
    dpsi = events_df["delta_psi"]
    is_sig = (dpsi.abs() > summary["dpsi_cutoff"]) & (events_df["padj"] < summary["padj_cutoff"])
    colours = np.where(is_sig, np.where(dpsi > 0, "firebrick", "steelblue"), "grey")

    ax.scatter(dpsi, neg_log10p, c=colours, s=14, alpha=0.7, edgecolors="none")
    ax.axvline(-summary["dpsi_cutoff"], color="black", ls="--", lw=0.8)
    ax.axvline(summary["dpsi_cutoff"], color="black", ls="--", lw=0.8)
    ax.set_xlabel("Delta PSI")
    ax.set_ylabel("-log10(p-value)")
    ax.set_title("Splicing Volcano Plot")
    plt.tight_layout()
    path = fig_dir / "volcano_splicing.png"
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
        title="Bulk RNA-seq Alternative Splicing Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Significant events": str(summary["n_significant"]),
        },
    )
    body_lines = [
        "## Summary\n",
        f"- **Total splicing events**: {summary['n_events']}",
        f"- **Genes affected**: {summary['n_genes_affected']}",
        f"- **Significant events (|dPSI| > {summary['dpsi_cutoff']}, padj < {summary['padj_cutoff']})**: {summary['n_significant']}",
        f"  - Increased inclusion: {summary['n_up']}",
        f"  - Decreased inclusion: {summary['n_down']}",
        "",
        "### Event Type Breakdown\n",
    ]
    for et, count in summary["event_type_counts"].items():
        body_lines.append(f"- **{et}**: {count}")

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
        if k not in ("significant_events_df", "top_events", "events_df")
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, json_summary, {"params": params})

    # --- Tables ---
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    summary["events_df"].to_csv(tables_dir / "splicing_events.csv", index=False)
    summary["significant_events_df"].to_csv(tables_dir / "significant_events.csv", index=False)

    # --- Reproducibility ---
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    cmd_parts = [
        "python bulkrna_splicing.py",
        f"--dpsi-cutoff {params.get('dpsi_cutoff', 0.1)}",
        f"--padj-cutoff {params.get('padj_cutoff', 0.05)}",
    ]
    if params.get("input_file"):
        cmd_parts.insert(1, f"--input {params['input_file']}")
    else:
        cmd_parts.insert(1, "--demo")
    cmd_parts.append(f"--output {output_dir}")
    (repro_dir / "commands.sh").write_text("#!/bin/bash\n" + " \\\n  ".join(cmd_parts) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Bulk RNA-seq Alternative Splicing Analysis",
    )
    parser.add_argument("--input", dest="input_path",
                        help="Path to splicing events CSV")
    parser.add_argument("--output", dest="output_dir", required=True,
                        help="Output directory")
    parser.add_argument("--demo", action="store_true",
                        help="Run with synthetic demo data")
    parser.add_argument("--dpsi-cutoff", type=float, default=0.1,
                        help="Absolute delta-PSI significance threshold (default: 0.1)")
    parser.add_argument("--padj-cutoff", type=float, default=0.05,
                        help="Adjusted p-value significance threshold (default: 0.05)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        events_df, _ = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            parser.error("--input is required when not using --demo")
        data_path = Path(args.input_path)
        if not data_path.exists():
            raise FileNotFoundError(f"Input file not found: {data_path}")
        events_df = pd.read_csv(data_path)
        input_file = str(data_path)

    summary = core_analysis(
        events_df,
        dpsi_cutoff=args.dpsi_cutoff,
        padj_cutoff=args.padj_cutoff,
    )

    figures = generate_figures(output_dir, summary, events_df)
    logger.info("Generated %d figures.", len(figures))

    params = {
        "dpsi_cutoff": args.dpsi_cutoff,
        "padj_cutoff": args.padj_cutoff,
        "input_file": args.input_path if not args.demo else None,
    }
    write_report(output_dir, summary, input_file, params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"  Total events: {summary['n_events']}")
    print(f"  Significant: {summary['n_significant']} (up={summary['n_up']}, down={summary['n_down']})")


if __name__ == "__main__":
    main()
