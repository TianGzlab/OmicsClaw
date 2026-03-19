#!/usr/bin/env python3
"""bulkrna-survival — Expression-based survival analysis.

Kaplan-Meier curves, log-rank tests, and Cox proportional hazards
for bulk RNA-seq expression data with clinical outcome metadata.

Usage:
    python bulkrna_survival.py --input expr.csv --clinical clinical.csv --genes TP53,BRCA1 --output results/
    python bulkrna_survival.py --demo --output /tmp/survival_demo
"""
from __future__ import annotations

import argparse
import json
import logging
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as sp_stats

import sys, os
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    write_result_json,
)

logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-survival"
SKILL_VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def _generate_demo_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate synthetic expression + clinical data."""
    np.random.seed(42)
    n_patients = 80
    genes = ["TP53", "BRCA1", "ERBB2", "KRAS", "MYC", "PTEN", "EGFR", "CDK4"]
    samples = [f"patient_{i:03d}" for i in range(1, n_patients + 1)]

    # Expression (lognormal, some genes correlated with outcome)
    expr = np.random.lognormal(5.0, 1.5, size=(len(genes), n_patients))
    expr_df = pd.DataFrame(expr, index=genes, columns=samples)

    # Clinical data
    # Make TP53 high expression → worse survival (prognostic)
    tp53_expr = expr_df.loc["TP53"].values
    tp53_high = tp53_expr > np.median(tp53_expr)

    # Survival times: exponential with TP53-dependent hazard
    base_hazard = 0.02
    times = np.zeros(n_patients)
    events = np.zeros(n_patients, dtype=int)
    for i in range(n_patients):
        hazard = base_hazard * (2.0 if tp53_high[i] else 1.0)
        t = np.random.exponential(1.0 / hazard)
        censor_time = np.random.uniform(20, 60)
        if t < censor_time:
            times[i] = t
            events[i] = 1
        else:
            times[i] = censor_time
            events[i] = 0

    clinical_df = pd.DataFrame({
        "sample": samples,
        "time": np.round(times, 2),
        "event": events,
    })
    return expr_df, clinical_df


def get_demo_data() -> tuple[pd.DataFrame, pd.DataFrame, Path]:
    project_root = Path(__file__).resolve().parents[3]
    demo_expr = project_root / "examples" / "demo_bulkrna_survival_expr.csv"
    demo_clin = project_root / "examples" / "demo_bulkrna_survival_clinical.csv"

    if demo_expr.exists() and demo_clin.exists():
        return pd.read_csv(demo_expr, index_col=0), pd.read_csv(demo_clin), demo_expr

    expr_df, clinical_df = _generate_demo_data()
    demo_expr.parent.mkdir(parents=True, exist_ok=True)
    expr_df.to_csv(demo_expr)
    clinical_df.to_csv(demo_clin, index=False)
    return expr_df, clinical_df, demo_expr


# ---------------------------------------------------------------------------
# Kaplan-Meier estimation (built-in)
# ---------------------------------------------------------------------------

def _kaplan_meier(time: np.ndarray, event: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute Kaplan-Meier survival curve.

    Returns: (times, survival_prob, se)
    """
    order = np.argsort(time)
    t_sorted = time[order]
    e_sorted = event[order]

    unique_times = np.unique(t_sorted[e_sorted == 1])
    km_times = [0.0]
    km_surv = [1.0]
    km_se = [0.0]

    n_at_risk = len(time)
    surv = 1.0
    var_sum = 0.0

    for t in unique_times:
        # Number of events at this time
        d = int(np.sum((t_sorted == t) & (e_sorted == 1)))
        # Number censored before this time
        censored = int(np.sum((t_sorted < t) & (e_sorted == 0) &
                              (t_sorted > (km_times[-1] if km_times else 0))))
        n_at_risk -= censored

        if n_at_risk <= 0:
            break

        surv *= (1 - d / n_at_risk)
        var_sum += d / (n_at_risk * max(n_at_risk - d, 1))  # Greenwood
        se = surv * np.sqrt(var_sum)

        km_times.append(float(t))
        km_surv.append(surv)
        km_se.append(se)

        n_at_risk -= d

    return np.array(km_times), np.array(km_surv), np.array(km_se)


def _log_rank_test(time1: np.ndarray, event1: np.ndarray,
                   time2: np.ndarray, event2: np.ndarray) -> tuple[float, float]:
    """Two-sample log-rank test.

    Returns: (chi2_statistic, p_value)
    """
    all_times = np.unique(np.concatenate([time1[event1 == 1], time2[event2 == 1]]))

    observed1 = 0
    expected1 = 0.0

    for t in all_times:
        d1 = np.sum((time1 == t) & (event1 == 1))
        d2 = np.sum((time2 == t) & (event2 == 1))
        n1 = np.sum(time1 >= t)
        n2 = np.sum(time2 >= t)
        d_total = d1 + d2
        n_total = n1 + n2

        if n_total == 0:
            continue

        observed1 += d1
        expected1 += d_total * n1 / n_total

    if expected1 == 0:
        return 0.0, 1.0

    # Variance (Greenwood-type)
    variance = 0.0
    for t in all_times:
        d1 = np.sum((time1 == t) & (event1 == 1))
        d2 = np.sum((time2 == t) & (event2 == 1))
        n1 = np.sum(time1 >= t)
        n2 = np.sum(time2 >= t)
        d_total = d1 + d2
        n_total = n1 + n2

        if n_total <= 1:
            continue

        variance += (d_total * n1 * n2 * (n_total - d_total)) / \
                    (n_total * n_total * (n_total - 1))

    if variance <= 0:
        return 0.0, 1.0

    chi2 = (observed1 - expected1) ** 2 / variance
    pval = float(1 - sp_stats.chi2.cdf(chi2, df=1))
    return float(chi2), pval


# ---------------------------------------------------------------------------
# Survival analysis per gene
# ---------------------------------------------------------------------------

def analyze_gene(gene: str, expression: np.ndarray, time: np.ndarray,
                 event: np.ndarray, cutoff_method: str = "median") -> dict:
    """Run survival analysis for a single gene."""
    if cutoff_method == "median":
        cutoff = float(np.median(expression))
    else:
        # Optimal cutoff: maximize log-rank chi2
        sorted_expr = np.sort(np.unique(expression))
        best_chi2 = 0.0
        best_cut = float(np.median(expression))
        for c in sorted_expr[1:-1]:
            mask_high = expression >= c
            if mask_high.sum() < 5 or (~mask_high).sum() < 5:
                continue
            chi2, _ = _log_rank_test(time[mask_high], event[mask_high],
                                     time[~mask_high], event[~mask_high])
            if chi2 > best_chi2:
                best_chi2 = chi2
                best_cut = float(c)
        cutoff = best_cut

    high_mask = expression >= cutoff
    low_mask = ~high_mask

    n_high = int(high_mask.sum())
    n_low = int(low_mask.sum())

    if n_high < 2 or n_low < 2:
        return {"gene": gene, "status": "insufficient_samples",
                "n_high": n_high, "n_low": n_low}

    chi2, pval = _log_rank_test(time[high_mask], event[high_mask],
                                time[low_mask], event[low_mask])

    # Median survival per group
    km_high_t, km_high_s, _ = _kaplan_meier(time[high_mask], event[high_mask])
    km_low_t, km_low_s, _ = _kaplan_meier(time[low_mask], event[low_mask])

    median_high = _median_survival(km_high_t, km_high_s)
    median_low = _median_survival(km_low_t, km_low_s)

    # Simple hazard ratio estimate (events/time ratio)
    events_high = event[high_mask].sum()
    events_low = event[low_mask].sum()
    time_high = time[high_mask].sum()
    time_low = time[low_mask].sum()
    hr = (events_high / max(time_high, 1)) / max(events_low / max(time_low, 1), 1e-10)

    return {
        "gene": gene,
        "status": "ok",
        "cutoff": round(cutoff, 4),
        "n_high": n_high,
        "n_low": n_low,
        "log_rank_chi2": round(chi2, 4),
        "log_rank_pval": pval,
        "median_survival_high": median_high,
        "median_survival_low": median_low,
        "hazard_ratio": round(hr, 4),
        "km_high": (km_high_t, km_high_s),
        "km_low": (km_low_t, km_low_s),
    }


def _median_survival(km_times: np.ndarray, km_surv: np.ndarray) -> float | None:
    """Find median survival time (time where S(t) <= 0.5)."""
    below = np.where(km_surv <= 0.5)[0]
    if len(below) == 0:
        return None
    return float(km_times[below[0]])


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def generate_figures(output_dir: Path, results: list[dict]) -> list[str]:
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    # KM plots per gene
    for res in results:
        if res["status"] != "ok":
            continue
        gene = res["gene"]
        km_high_t, km_high_s = res["km_high"]
        km_low_t, km_low_s = res["km_low"]

        fig, ax = plt.subplots(figsize=(7, 5))
        ax.step(km_high_t, km_high_s, where="post", label=f"High ({res['n_high']})",
                color="#E84D60", linewidth=2)
        ax.step(km_low_t, km_low_s, where="post", label=f"Low ({res['n_low']})",
                color="#4878CF", linewidth=2)
        ax.set_xlabel("Time", fontsize=11)
        ax.set_ylabel("Survival Probability", fontsize=11)
        pval_str = f"{res['log_rank_pval']:.2e}" if res['log_rank_pval'] < 0.001 else f"{res['log_rank_pval']:.4f}"
        ax.set_title(f"{gene} — Kaplan-Meier (log-rank p={pval_str})", fontsize=12)
        ax.legend(fontsize=10)
        ax.set_ylim(0, 1.05)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()
        p = fig_dir / f"km_{gene}.png"
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

    # Forest plot of hazard ratios
    ok_results = [r for r in results if r["status"] == "ok"]
    if len(ok_results) >= 2:
        fig, ax = plt.subplots(figsize=(8, max(3, len(ok_results) * 0.5)))
        genes_plot = [r["gene"] for r in ok_results]
        hrs = [r["hazard_ratio"] for r in ok_results]
        pvals = [r["log_rank_pval"] for r in ok_results]

        y_pos = range(len(ok_results))
        colors = ["#E84D60" if hr > 1 else "#4878CF" for hr in hrs]
        ax.scatter(hrs, y_pos, c=colors, s=80, zorder=3, edgecolors="white", linewidth=0.5)
        ax.axvline(1.0, color="black", ls="--", lw=0.8, alpha=0.5)
        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(genes_plot, fontsize=9)
        ax.set_xlabel("Hazard Ratio (high/low expression)")
        ax.set_title("Forest Plot — Hazard Ratios")
        ax.invert_yaxis()
        fig.tight_layout()
        p = fig_dir / "forest_plot.png"
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

    return paths


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, results: list[dict], params: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    header = generate_report_header(
        title="Bulk RNA-seq Survival Analysis Report", skill_name=SKILL_NAME,
    )

    body_lines = [
        "## Summary\n",
        f"- **Genes analyzed**: {len(results)}",
        f"- **Cutoff method**: {params.get('cutoff_method', 'median')}",
        "",
        "## Results\n",
        "| Gene | Cutoff | n_High | n_Low | HR | Log-rank χ² | p-value | Median (High) | Median (Low) |",
        "|------|--------|--------|-------|-----|------------|---------|---------------|--------------|",
    ]
    for r in results:
        if r["status"] != "ok":
            body_lines.append(f"| {r['gene']} | — | {r.get('n_high','—')} | {r.get('n_low','—')} | — | — | — | — | — |")
            continue
        pval_str = f"{r['log_rank_pval']:.2e}" if r['log_rank_pval'] < 0.001 else f"{r['log_rank_pval']:.4f}"
        med_h = f"{r['median_survival_high']:.1f}" if r['median_survival_high'] is not None else "NR"
        med_l = f"{r['median_survival_low']:.1f}" if r['median_survival_low'] is not None else "NR"
        body_lines.append(
            f"| {r['gene']} | {r['cutoff']:.2f} | {r['n_high']} | {r['n_low']} | "
            f"{r['hazard_ratio']:.2f} | {r['log_rank_chi2']:.2f} | {pval_str} | {med_h} | {med_l} |"
        )

    sig_genes = [r["gene"] for r in results if r.get("log_rank_pval", 1) < 0.05]
    if sig_genes:
        body_lines.extend(["", f"### Significant genes (p < 0.05): {', '.join(sig_genes)}", ""])

    body_lines.extend(["", "## Figures\n"])
    for r in results:
        if r["status"] == "ok":
            body_lines.append(f"- `figures/km_{r['gene']}.png` — Kaplan-Meier for {r['gene']}")
    if len([r for r in results if r["status"] == "ok"]) >= 2:
        body_lines.append("- `figures/forest_plot.png` — Hazard ratio forest plot")
    body_lines.append("")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(
        "\n".join([header, "\n".join(body_lines), footer]), encoding="utf-8")

    # JSON summary (strip KM curves)
    json_results = []
    for r in results:
        jr = {k: v for k, v in r.items() if k not in ("km_high", "km_low")}
        json_results.append(jr)
    summary = {"n_genes": len(results), "results": json_results}
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, params)

    # Tables
    table_records = []
    for r in results:
        if r["status"] == "ok":
            table_records.append({
                "gene": r["gene"], "cutoff": r["cutoff"],
                "n_high": r["n_high"], "n_low": r["n_low"],
                "hazard_ratio": r["hazard_ratio"],
                "log_rank_chi2": r["log_rank_chi2"],
                "log_rank_pval": r["log_rank_pval"],
                "median_survival_high": r["median_survival_high"],
                "median_survival_low": r["median_survival_low"],
            })
    pd.DataFrame(table_records).to_csv(tables_dir / "survival_results.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    (repro_dir / "commands.sh").write_text(
        f"#!/usr/bin/env bash\npython bulkrna_survival.py "
        f"--input {params.get('input', '<INPUT>')} "
        f"--clinical {params.get('clinical', '<CLINICAL>')} "
        f"--genes {params.get('genes', '<GENES>')} "
        f"--output {params.get('output', '<OUTPUT>')}\n", encoding="utf-8")
    logger.info("Report written to %s", output_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(description=f"{SKILL_NAME} v{SKILL_VERSION}")
    ap.add_argument("--input", type=str, help="Expression matrix CSV")
    ap.add_argument("--clinical", type=str, help="Clinical data CSV")
    ap.add_argument("--genes", type=str, help="Comma-separated gene list")
    ap.add_argument("--cutoff-method", default="median", choices=["median", "optimal"])
    ap.add_argument("--output", type=str, required=True)
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    output_dir = Path(args.output)

    if args.demo:
        expr_df, clinical_df, input_path = get_demo_data()
        gene_list = list(expr_df.index[:8])  # First 8 genes
    else:
        if not args.input or not args.clinical or not args.genes:
            ap.error("--input, --clinical, and --genes required (or use --demo)")
        expr_df = pd.read_csv(args.input, index_col=0)
        clinical_df = pd.read_csv(args.clinical)
        input_path = Path(args.input)
        gene_list = [g.strip() for g in args.genes.split(",")]

    # Align samples
    clinical_df = clinical_df.set_index("sample")
    shared_samples = sorted(set(expr_df.columns) & set(clinical_df.index))
    expr_df = expr_df[shared_samples]
    clinical_df = clinical_df.loc[shared_samples]

    time_arr = clinical_df["time"].values.astype(float)
    event_arr = clinical_df["event"].values.astype(int)

    # Run survival analysis per gene
    results = []
    for gene in gene_list:
        if gene not in expr_df.index:
            logger.warning("Gene %s not found in expression matrix — skipping", gene)
            results.append({"gene": gene, "status": "not_found"})
            continue
        expression = expr_df.loc[gene].values.astype(float)
        res = analyze_gene(gene, expression, time_arr, event_arr, args.cutoff_method)
        results.append(res)
        if res["status"] == "ok":
            logger.info("  %s: HR=%.2f, p=%.4e", gene, res["hazard_ratio"],
                        res["log_rank_pval"])

    params = {
        "input": str(input_path),
        "clinical": args.clinical or "demo",
        "genes": ",".join(gene_list),
        "cutoff_method": args.cutoff_method,
        "output": str(output_dir),
    }

    generate_figures(output_dir, results)
    write_report(output_dir, results, params)
    logger.info("✓ Survival analysis complete → %s", output_dir)


if __name__ == "__main__":
    main()
