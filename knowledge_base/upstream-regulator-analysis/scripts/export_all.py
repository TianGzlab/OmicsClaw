"""
Export all upstream regulator analysis results (Step 4).

Exports:
1. analysis_object.pkl - Complete results for downstream use
2. regulon_scores_all.csv - All scored TFs
3. regulon_scores_top.csv - Top TFs by regulatory score
4. target_overlaps.csv - Per-TF target gene overlap details
5. enrichment_up.csv - Peak enrichment results for upregulated genes
6. enrichment_down.csv - Peak enrichment results for downregulated genes
7. summary_report.md - Human-readable summary
8. analysis_report.pdf - Publication-quality PDF report
"""

import os
import pickle
from datetime import datetime

import pandas as pd


def export_all(results, output_dir="regulator_results"):
    """
    Export all upstream regulator results with pickle object.

    Parameters
    ----------
    results : dict
        Results from run_integration_workflow().
    output_dir : str
        Output directory.

    Verification
    ------------
    Prints "=== Export Complete ===" when done.
    """
    os.makedirs(output_dir, exist_ok=True)

    print("\n--- Exporting results ---")

    regulon_scores = results["regulon_scores"]
    parameters = results["parameters"]
    metadata = results["metadata"]

    # 1. Analysis object (pickle)
    pkl_path = os.path.join(output_dir, "analysis_object.pkl")
    analysis_object = {
        "regulon_scores": regulon_scores,
        "enrichment_results_up": results.get("enrichment_results_up"),
        "enrichment_results_down": results.get("enrichment_results_down"),
        "top_tfs": results.get("top_tfs"),
        "target_gene_data": results.get("target_gene_data"),
        "de_data": results["de_data"],
        "parameters": parameters,
        "metadata": metadata,
        "timestamp": datetime.now().isoformat(),
    }
    with open(pkl_path, "wb") as f:
        pickle.dump(analysis_object, f)
    print(f"   1. {pkl_path}")
    print(f"      (Load with: import pickle; obj = pickle.load(open('{pkl_path}', 'rb')))")

    # 2. All regulon scores
    if len(regulon_scores) > 0:
        csv_all = os.path.join(output_dir, "regulon_scores_all.csv")
        regulon_scores.to_csv(csv_all, index=False)
        print(f"   2. {csv_all} ({len(regulon_scores)} TFs)")

        # 3. Top regulon scores
        top_n = min(20, len(regulon_scores))
        csv_top = os.path.join(output_dir, "regulon_scores_top.csv")
        regulon_scores.head(top_n).to_csv(csv_top, index=False)
        print(f"   3. {csv_top} (top {top_n})")
    else:
        print("   2-3. No regulon scores to export")

    # 4. Target overlaps detail
    _export_target_overlaps(results, output_dir)

    # 5-6. Enrichment results
    for label, key in [("up", "enrichment_results_up"), ("down", "enrichment_results_down")]:
        enrichment = results.get(key)
        if enrichment is not None and "enrichment_results" in enrichment:
            er = enrichment["enrichment_results"]
            if len(er) > 0:
                csv_path = os.path.join(output_dir, f"enrichment_{label}.csv")
                er.to_csv(csv_path, index=False)
                print(f"   {5 if label == 'up' else 6}. {csv_path} ({len(er)} experiments)")

    # 7. Summary report (markdown)
    _write_summary_report(results, output_dir)

    # 8. PDF report (requires reportlab, optional)
    try:
        from generate_report import generate_report
        generate_report(results, output_dir=output_dir)
    except ImportError:
        try:
            from scripts.generate_report import generate_report
            generate_report(results, output_dir=output_dir)
        except ImportError:
            pass
    except Exception as e:
        print(f"   PDF generation skipped: {e}")
        print("   (Markdown report still available)")

    print("\n=== Export Complete ===")


def _export_target_overlaps(results, output_dir):
    """Export per-TF target gene overlap details."""
    regulon_scores = results["regulon_scores"]
    target_gene_data = results.get("target_gene_data", {})
    de_data = results["de_data"]

    if len(regulon_scores) == 0:
        return

    de_up_set = set(de_data["de_up"])
    de_down_set = set(de_data["de_down"])

    rows = []
    for _, tf_row in regulon_scores.iterrows():
        tf_name = tf_row["tf"]
        if tf_name not in target_gene_data:
            continue

        target_df = target_gene_data[tf_name]
        gene_col = "gene" if "gene" in target_df.columns else target_df.columns[0]

        for _, target_row in target_df.iterrows():
            gene = str(target_row[gene_col])
            de_status = "not_de"
            if gene in de_up_set:
                de_status = "up"
            elif gene in de_down_set:
                de_status = "down"

            rows.append({
                "tf": tf_name,
                "target_gene": gene,
                "de_status": de_status,
                "avg_binding_score": target_row.get("avg_score", None),
            })

    if rows:
        overlap_df = (
            pd.DataFrame(rows)
            .query("de_status != 'not_de'")
            .sort_values(["tf", "de_status", "avg_binding_score"], ascending=[True, True, False])
            .reset_index(drop=True)
        )
        csv_path = os.path.join(output_dir, "target_overlaps.csv")
        overlap_df.to_csv(csv_path, index=False)
        print(f"   4. {csv_path} ({len(overlap_df)} TF-target-DE overlaps)")


def _write_summary_report(results, output_dir):
    """Write markdown summary report."""
    regulon_scores = results["regulon_scores"]
    parameters = results["parameters"]
    metadata = results["metadata"]

    report_path = os.path.join(output_dir, "summary_report.md")

    lines = []
    lines.append("# Upstream Regulator Analysis Report\n")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Parameters
    lines.append("## Parameters\n")
    lines.append(f"| Parameter | Value |")
    lines.append(f"|-----------|-------|")
    lines.append(f"| Genome | {parameters['genome']} |")
    lines.append(f"| Antigen class | {parameters['antigen_class']} |")
    lines.append(f"| Cell class | {parameters['cell_class']} |")
    lines.append(f"| Peak threshold | {parameters['threshold']} |")
    lines.append(f"| Target gene distance | \u00b1{parameters['distance_kb']}kb |")
    lines.append(f"| DE padj threshold | {parameters['padj_threshold']} |")
    lines.append(f"| DE log2FC threshold | {parameters['log2fc_threshold']} |")
    lines.append(f"| Max TFs investigated | {parameters['max_tfs']} |")
    lines.append(f"| Min target overlap | {parameters['min_targets_overlap']} |")
    lines.append("")

    # Input summary
    lines.append("## Input DE Summary\n")
    lines.append(f"- **Total genes measured:** {metadata['n_background']}")
    lines.append(f"- **DE genes:** {metadata['n_de_total']} ({metadata['n_de_up']} up, {metadata['n_de_down']} down)")
    lines.append(f"- **TFs enriched in ChIP-Atlas:** {metadata['n_tfs_enriched']}")
    lines.append(f"- **TFs with target gene data:** {metadata['n_tfs_with_targets']}")
    lines.append(f"- **TFs scored:** {metadata['n_tfs_scored']}")
    lines.append("")

    # Top regulators table
    if len(regulon_scores) > 0:
        lines.append("## Top Upstream Regulators\n")
        lines.append("| Rank | TF | Direction | Reg. Score | Fisher P | Concordance | ChIP Q | Targets DE |")
        lines.append("|------|----|-----------|------------|----------|-------------|--------|------------|")

        for i, (_, row) in enumerate(regulon_scores.head(15).iterrows()):
            lines.append(
                f"| {i+1} | **{row['tf']}** | {row['direction']} | "
                f"{row['regulatory_score']:.1f} | {row['fisher_pvalue']:.2e} | "
                f"{row['concordance']:.0%} | {row['chip_best_qvalue']:.2e} | "
                f"{row['n_targets_de_total']} ({row['n_targets_de_up']}\u2191 {row['n_targets_de_down']}\u2193) |"
            )
        lines.append("")

        # Direction summary
        n_act = (regulon_scores["direction"] == "activator").sum()
        n_rep = (regulon_scores["direction"] == "repressor").sum()
        n_mix = (regulon_scores["direction"] == "mixed").sum()
        lines.append(f"**Direction summary:** {n_act} activators, {n_rep} repressors, {n_mix} mixed\n")
    else:
        lines.append("## Results\n")
        lines.append("No TFs passed the scoring thresholds.\n")

    # Interpretation guide
    lines.append("## Interpretation Guide\n")
    lines.append("### Regulatory Score")
    lines.append("Combined evidence metric: `-log10(Fisher P) \u00d7 Concordance \u00d7 -log10(ChIP Q)`\n")
    lines.append("| Score | Evidence Level |")
    lines.append("|-------|---------------|")
    lines.append("| >100 | Very strong |")
    lines.append("| 50-100 | Strong |")
    lines.append("| 20-50 | Moderate |")
    lines.append("| <20 | Weak |")
    lines.append("")
    lines.append("### Direction")
    lines.append("- **Activator:** >60% of TF-bound DE genes are upregulated")
    lines.append("- **Repressor:** >60% of TF-bound DE genes are downregulated")
    lines.append("- **Mixed:** No clear directional bias (<60% in either direction)")
    lines.append("")

    # Caveats
    lines.append("## Important Caveats\n")
    lines.append("1. **ChIP-Atlas bias:** Results biased toward well-studied TFs and cell types")
    lines.append("2. **Correlation, not causation:** Binding enrichment does not prove regulatory causation")
    lines.append("3. **Directional simplification:** Activator/repressor labels assume simple regulation")
    lines.append("4. **Combined score is heuristic:** Not a formal statistical test across all axes")
    lines.append("5. **Validate experimentally:** Confirm key findings with perturbation experiments")
    lines.append("")

    # References
    lines.append("## References\n")
    lines.append("- Zou Z, et al. (2024) ChIP-Atlas 3.0. *Nucleic Acids Res.* 52(W1):W159-W166")
    lines.append("- Oki S, et al. (2018) ChIP-Atlas. *EMBO Rep.* 19(12):e46255")
    lines.append("")

    # Output files
    lines.append("## Output Files\n")
    lines.append("| File | Description |")
    lines.append("|------|-------------|")
    lines.append("| `analysis_object.pkl` | Complete analysis for downstream use |")
    lines.append("| `regulon_scores_all.csv` | All scored TFs |")
    lines.append("| `regulon_scores_top.csv` | Top TFs by regulatory score |")
    lines.append("| `target_overlaps.csv` | Per-TF target gene DE overlap details |")
    lines.append("| `enrichment_up.csv` | ChIP-Atlas enrichment for upregulated genes |")
    lines.append("| `enrichment_down.csv` | ChIP-Atlas enrichment for downregulated genes |")
    lines.append("| `upstream_regulators_*.png/svg` | Visualization panels |")
    lines.append("| `analysis_report.pdf` | Publication-quality PDF report |")
    lines.append("")

    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"   7. {report_path}")

