"""
Export results for ChIP-Atlas Target Genes analysis.

Saves analysis object (pickle), CSV files, and markdown summary report.
"""

import os
import pickle
from datetime import datetime


def export_all(results, output_dir="target_genes_results"):
    """
    Export all target genes results to files.

    Args:
        results: Results dict from run_target_genes_workflow()
        output_dir: Output directory (default: "target_genes_results")

    Exports:
        - analysis_object.pkl (complete results for downstream skills)
        - target_genes_all.csv (all target genes with summary scores)
        - target_genes_top50.csv (top 50 by average score)
        - target_genes_with_string.csv (genes with STRING score > 0, conditional)
        - experiment_scores_top50.csv (wide-format per-experiment for top 50)
        - summary_report.md (human-readable report)
    """
    os.makedirs(output_dir, exist_ok=True)

    target_genes = results["target_genes"]
    experiment_data = results["experiment_data"]
    protein = results["protein"]
    metadata = results["metadata"]
    parameters = results["parameters"]

    print(f"\n  Exporting results to: {output_dir}/")

    # 1. Analysis object (pickle)
    pkl_path = os.path.join(output_dir, "analysis_object.pkl")
    export_data = {
        "target_genes": target_genes,
        "experiment_data": experiment_data,
        "cell_types": results["cell_types"],
        "protein": protein,
        "parameters": parameters,
        "metadata": metadata,
        "exported_at": datetime.now().isoformat(),
    }
    with open(pkl_path, "wb") as f:
        pickle.dump(export_data, f)
    print(f"    Saved: analysis_object.pkl")
    print(f"    (Load with: import pickle; obj = pickle.load(open('{pkl_path}', 'rb')))")

    # 2. All target genes CSV
    all_csv_path = os.path.join(output_dir, "target_genes_all.csv")
    target_genes.to_csv(all_csv_path, index=False)
    print(f"    Saved: target_genes_all.csv ({len(target_genes)} genes)")

    # 3. Top 50 target genes CSV
    top50 = target_genes.head(50)
    top50_path = os.path.join(output_dir, "target_genes_top50.csv")
    top50.to_csv(top50_path, index=False)
    print(f"    Saved: target_genes_top50.csv ({len(top50)} genes)")

    # 4. Genes with STRING interactions (conditional)
    with_string = target_genes[target_genes["string_score"] > 0]
    if len(with_string) > 0:
        string_path = os.path.join(output_dir, "target_genes_with_string.csv")
        with_string.to_csv(string_path, index=False)
        print(f"    Saved: target_genes_with_string.csv ({len(with_string)} genes)")

    # 5. Wide-format experiment scores for top 50 genes
    if experiment_data is not None:
        top50_genes = top50["gene"].tolist()
        exp_top50 = experiment_data[experiment_data["gene"].isin(top50_genes)]
        exp_path = os.path.join(output_dir, "experiment_scores_top50.csv")
        exp_top50.to_csv(exp_path, index=False)
        print(f"    Saved: experiment_scores_top50.csv ({len(exp_top50)} genes)")

    # 6. Summary report
    report_path = os.path.join(output_dir, "summary_report.md")
    _write_summary_report(report_path, results)
    print(f"    Saved: summary_report.md")

    print(f"\n  === Export Complete ===")
    print(f"  Files saved to: {output_dir}/")


def _write_summary_report(report_path, results):
    """Write a human-readable markdown summary report."""
    target_genes = results["target_genes"]
    protein = results["protein"]
    metadata = results["metadata"]
    parameters = results["parameters"]

    top10 = target_genes.head(10)

    with open(report_path, "w") as f:
        f.write(f"# {protein} Target Genes Analysis Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("**Data source:** ChIP-Atlas — Zou Z et al. (2024) ChIP-Atlas 3.0: "
                "a data-mining suite to explore chromosome architecture together with large-scale "
                "regulome data. *Nucleic Acids Research*. "
                "[doi:10.1093/nar/gkad884](https://doi.org/10.1093/nar/gkad884)\n\n")

        # Parameters
        f.write("## Analysis Parameters\n\n")
        f.write(f"| Parameter | Value |\n")
        f.write(f"|-----------|-------|\n")
        f.write(f"| Protein | {protein} |\n")
        f.write(f"| Genome | {metadata['genome']} |\n")
        f.write(f"| Distance from TSS | ±{metadata['distance_kb']}kb |\n")
        f.write(f"| Total genes (before filter) | {metadata['total_genes_before_filter']} |\n")
        f.write(f"| Total genes (after filter) | {metadata['total_genes_after_filter']} |\n")
        colocated_info = metadata.get("colocated_info", {})
        n_independent = colocated_info.get("n_independent_loci", metadata['total_genes_after_filter'])
        if colocated_info.get("n_groups", 0) > 0:
            f.write(f"| Independent loci | {n_independent} "
                    f"({colocated_info['n_genes_affected']} genes in "
                    f"{colocated_info['n_groups']} co-located groups) |\n")
        f.write(f"| Total experiments | {metadata['total_experiments']} |\n")
        f.write(f"| Unique cell types | {metadata['unique_cell_types']} |\n")
        f.write("\n")

        # Summary statistics
        f.write("## Summary Statistics\n\n")
        avg_scores = target_genes["avg_score"]
        f.write(f"- **Median binding score:** {avg_scores.median():.1f}\n")
        f.write(f"- **Mean binding score:** {avg_scores.mean():.1f}\n")
        f.write(f"- **Max binding score:** {avg_scores.max():.1f}\n")

        # Score threshold counts (exact numbers to prevent hallucination)
        n_gte500 = (avg_scores >= 500).sum()
        n_gte200 = (avg_scores >= 200).sum()
        n_gte100 = (avg_scores >= 100).sum()
        n_gte50 = (avg_scores >= 50).sum()
        f.write(f"- **Genes with score ≥500 (Q ≤ 1e-50):** {n_gte500}\n")
        f.write(f"- **Genes with score ≥200 (Q ≤ 1e-20):** {n_gte200}\n")
        f.write(f"- **Genes with score ≥100 (Q ≤ 1e-10):** {n_gte100}\n")
        f.write(f"- **Genes with score ≥50 (Q ≤ 1e-5):** {n_gte50}\n")
        n_lt50 = len(avg_scores) - n_gte50
        if n_lt50 > 0:
            pct_weak = 100 * n_lt50 / len(avg_scores)
            f.write(f"- **Genes with score <50 (weak evidence):** {n_lt50} ({pct_weak:.0f}% of returned genes)\n")

        # Binding rate context for score interpretation
        top10_rate = top10["binding_rate"].median()
        f.write(f"\n> **Note:** Average scores include zeros from experiments with no binding. "
                f"The top 10 genes are bound in a median of {top10_rate:.1%} of experiments — "
                f"the remaining ~{100 - top10_rate * 100:.1f}% are zeros that dilute the average. "
                f"See `binding_rate` and `max_score` for complementary views.\n\n")

        n_string = (target_genes["string_score"] > 0).sum()
        n_total = len(target_genes)
        if n_string > 0:
            pct_string = 100 * n_string / n_total
            min_nonzero = target_genes.loc[target_genes["string_score"] > 0, "string_score"].min()
            f.write(f"- **Genes with STRING interactions:** {n_string}/{n_total} ({pct_string:.0f}%) — "
                    f"STRING scores are pre-embedded in the ChIP-Atlas data (not queried separately). "
                    f"Coverage is sparse (lowest non-zero score: {min_nonzero:.0f}); "
                    f"canonical targets like BBC3/PUMA (for TP53) can have STRING=0 "
                    f"because ChIP-Atlas applies a combined-score threshold that excludes "
                    f"lower-confidence interactions. STRING=0 does NOT mean 'not a target.'\n")
        else:
            f.write(f"- **Genes with STRING interactions:** 0/{n_total} — "
                    f"no STRING data available for {protein} in ChIP-Atlas "
                    f"(STRING scores are pre-embedded, not queried separately)\n")

        # Filtering cutoff (report what score threshold the top-N filter produced)
        total_before = metadata.get("total_genes_before_filter", len(target_genes))
        total_after = metadata.get("total_genes_after_filter", len(target_genes))
        if total_after < total_before:
            cutoff_score = avg_scores.iloc[-1] if len(avg_scores) > 0 else 0
            f.write(f"- **Filtering cutoff:** top {total_after} genes selected "
                    f"(lowest included score: {cutoff_score:.1f})\n")
        f.write("\n")

        # Top 10 target genes
        f.write("## Top 10 Target Genes\n\n")
        f.write("> **⚠️ Rankings are data-derived.** When summarizing results, present these "
                "exact genes, ranks, and scores. Do not substitute genes based on biological "
                "fame or general knowledge.\n\n")
        total_exp = metadata['total_experiments']
        f.write("| Rank | Gene | Avg Score | Max Score | Binding Rate (n/N) | STRING |\n")
        f.write("|------|------|-----------|-----------|-------------------|--------|\n")
        for i, (_, row) in enumerate(top10.iterrows(), 1):
            coloc_flag = ""
            if "colocated_group" in row and row["colocated_group"] > 0:
                coloc_flag = " *"
            n_bound = int(row['num_bound'])
            f.write(
                f"| {i} | {row['gene']}{coloc_flag} | {row['avg_score']:.1f} | "
                f"{row['max_score']:.0f} | {row['binding_rate']:.1%} ({n_bound}/{total_exp}) | "
                f"{row['string_score']:.0f} |\n"
            )
        f.write("\n")

        # Ranks 11-20 (reduces temptation to fill in from memory)
        top20 = target_genes.head(20)
        if len(top20) > 10:
            f.write("### Ranks 11-20\n\n")
            f.write("| Rank | Gene | Avg Score | Max Score | Binding Rate (n/N) | STRING |\n")
            f.write("|------|------|-----------|-----------|-------------------|--------|\n")
            for i, (_, row) in enumerate(top20.iloc[10:].iterrows(), 11):
                coloc_flag = ""
                if "colocated_group" in row and row["colocated_group"] > 0:
                    coloc_flag = " *"
                n_bound = int(row['num_bound'])
                f.write(
                    f"| {i} | {row['gene']}{coloc_flag} | {row['avg_score']:.1f} | "
                    f"{row['max_score']:.0f} | {row['binding_rate']:.1%} ({n_bound}/{total_exp}) | "
                    f"{row['string_score']:.0f} |\n"
                )
            has_colocated_in_top20 = (
                "colocated_group" in top20.columns
                and (top20["colocated_group"] > 0).any()
            )
            if has_colocated_in_top20:
                f.write("\n\\* Gene is part of a co-located group (see Caveats).\n")
            f.write("\n")

        # Cell-type distribution (experiment composition bias)
        experiment_data = results.get("experiment_data")
        if experiment_data is not None:
            exp_cols = [c for c in experiment_data.columns if c != "gene"]
            if exp_cols:
                cell_type_counts = {}
                for col in exp_cols:
                    parts = col.split("|", 1)
                    ct = parts[1] if len(parts) == 2 else col
                    cell_type_counts[ct] = cell_type_counts.get(ct, 0) + 1
                sorted_cts = sorted(cell_type_counts.items(), key=lambda x: -x[1])
                total_exp = len(exp_cols)
                f.write("## Experiment Composition\n\n")
                f.write(f"**Total experiments:** {total_exp}\n\n")
                f.write("**Top cell types by experiment count:**\n\n")
                f.write("| Cell Type | Experiments | % of Total |\n")
                f.write("|-----------|------------|------------|\n")
                top5_exp_sum = 0
                for ct, count in sorted_cts[:5]:
                    pct = 100 * count / total_exp
                    top5_exp_sum += count
                    f.write(f"| {ct} | {count} | {pct:.1f}% |\n")
                top5_pct = 100 * top5_exp_sum / total_exp
                n_dominant = sum(1 for _, c in sorted_cts if 100 * c / total_exp >= 5)
                n_rare = sum(1 for _, c in sorted_cts if 100 * c / total_exp < 1)
                f.write(f"\n**⚠️ Experiment distribution is uneven:** Top 5 cell types account for "
                        f"**{top5_pct:.0f}%** of all experiments, while **{n_rare}** of {len(sorted_cts)} "
                        f"cell types contribute <1% each. Average binding scores are heavily weighted toward "
                        f"these well-represented cell types.\n")
                f.write(f"- **{n_dominant}** cell types contribute ≥5% of experiments each.\n")
                f.write(f"- **→ To mitigate this bias,** re-run with the `cell_types` parameter "
                        f"to recalculate scores using only experiments from your cell type(s) of interest.\n\n")

        # Interpretation
        f.write("## Interpretation Guide\n\n")
        f.write("**Binding Score (MACS2):** −10 × log10(Q-value). Higher = stronger binding evidence.\n")
        f.write("- Score ≥500: Very strong binding (Q ≤ 1e-50)\n")
        f.write("- Score 100-500: Strong binding\n")
        f.write("- Score 50-100: Moderate binding\n")
        f.write("- Score <50: Weak binding\n\n")
        f.write("**Note:** The Q-value thresholds above apply to **individual experiment** scores. "
                "The average scores in the rankings include zeros from experiments with no binding, "
                "so an average of 500 means the *consensus across all experiments* reaches that level "
                "— not that Q = 1e-50 in every experiment.\n\n")
        f.write("**Binding Rate:** Fraction of experiments with any binding detected. "
                "Higher rates indicate consistent binding across cell types.\n\n")
        f.write("**STRING Score:** Independent evidence of functional association. "
                "STRING scores aggregate multiple evidence types (co-expression, text-mining, "
                "experimental, database) — a high score may reflect protein-protein interaction "
                "or pathway co-membership rather than direct transcriptional regulation. "
                "Genes with both high binding AND high STRING scores are highest-confidence targets. "
                "**Important:** A STRING score of 0 does NOT mean a gene is not a real target — "
                "it means STRING lacks evidence for this specific pair. Even well-characterized targets "
                "(e.g., BBC3/PUMA for TP53) can have STRING score 0.\n\n")

        # Caveats
        f.write("## Caveats\n\n")
        f.write("- **Averaging includes zeros:** The average binding score is computed across ALL "
                "experiments, including those with no binding (score 0). Genes bound in fewer "
                "experiments get diluted averages. Check `max_score` and `binding_rate` columns "
                "for complementary views — a gene with high max_score but low average may have "
                "strong cell-type-specific binding.\n")
        f.write("- **Cell-type bias:** Experiments are not evenly distributed across cell types. "
                "Rankings are weighted toward well-studied cell lines (see Experiment Composition above) "
                "and primarily reflect binding patterns in cancer cell lines, which may not generalize "
                "to normal tissues or other biological contexts. "
                "**→ For cell-type-specific rankings, re-run with the `cell_types` parameter** "
                "(e.g., `cell_types=['MCF-7']`) to recalculate averages using only matching experiments.\n")
        f.write("- **Functional annotations are external:** ChIP-Atlas provides binding data only. "
                "Any biological role descriptions (e.g., gene function, pathway membership) come from "
                "external knowledge, not from this analysis.\n")

        # Co-located genes caveat (if detected)
        colocated_info = metadata.get("colocated_info", {})
        if colocated_info.get("n_groups", 0) > 0:
            n_groups = colocated_info["n_groups"]
            n_affected = colocated_info["n_genes_affected"]
            n_indep = colocated_info["n_independent_loci"]
            total = metadata["total_genes_after_filter"]
            pct = 100 * n_affected / total if total > 0 else 0
            f.write(f"- **Co-located genes:** {n_affected} of {total} genes ({pct:.1f}%) "
                    f"share identical binding scores with at least one other gene because they "
                    f"sit at the same genomic locus within the ±{metadata['distance_kb']}kb TSS window. "
                    f"This means {n_groups} groups of genes receive the same ChIP-seq signal. "
                    f"The effective number of independent loci is **{n_indep}** (not {total}). "
                    f"For pathway enrichment or gene set analyses, consider collapsing co-located "
                    f"groups to avoid double-counting loci — if co-located genes cluster in the same "
                    f"pathway, this can artificially inflate enrichment p-values. Treat pathway hits "
                    f"driven primarily by co-located gene groups with caution. "
                    f"Genes in co-located groups are flagged "
                    f"with `colocated_group > 0` in the CSV output.\n")
            # Show top examples
            groups = colocated_info.get("groups", [])
            examples = sorted(groups, key=lambda g: g["size"], reverse=True)[:3]
            if examples:
                example_strs = []
                for g in examples:
                    gene_list = ", ".join(g["genes"][:4])
                    if g["size"] > 4:
                        gene_list += f", ... ({g['size']} total)"
                    example_strs.append(gene_list)
                f.write(f"  - Largest groups: {'; '.join(example_strs)}\n")

        f.write("\n")

        # Files
        f.write("## Output Files\n\n")
        f.write("| File | Description |\n")
        f.write("|------|-------------|\n")
        f.write("| `analysis_object.pkl` | Complete analysis for downstream skills |\n")
        f.write("| `target_genes_all.csv` | All target genes with summary scores |\n")
        f.write("| `target_genes_top50.csv` | Top 50 target genes |\n")
        f.write("| `target_genes_with_string.csv` | Genes with STRING interaction data |\n")
        f.write("| `experiment_scores_top50.csv` | Per-experiment scores for top 50 genes |\n")
        f.write("| `target_genes_top_targets.png` | Top target genes barplot |\n")
        f.write("| `target_genes_score_distribution.png` | Binding score distribution |\n")
        f.write("| `target_genes_heatmap.png` | Binding heatmap (genes × experiments) |\n")
        f.write("| `target_genes_string_vs_binding.png` | STRING vs binding scatter |\n")
        f.write("| `summary_report.md` | This report |\n")

