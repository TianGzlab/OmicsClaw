"""
Export all ChIP-Atlas enrichment results (Step 4).

Exports:
1. analysis_object.pkl - Complete results for downstream use
2. enrichment_results_all.csv - All experiments analyzed
3. enrichment_results_significant.csv - Significant results (q < 0.05)
4. enrichment_results_top20.csv - Top 20 by significance (q-value)
5. failed_genes.txt - Genes that couldn't be mapped
6. summary_report.md - Human-readable summary
"""

import os
import pickle
from datetime import datetime


def export_all(results, output_dir="chipatlas_results"):
    """
    Export all ChIP-Atlas enrichment results with pickle object.

    Parameters:
    -----------
    results : dict
        Results from run_enrichment_workflow()
    output_dir : str
        Output directory

    Returns:
    --------
    None
        Prints export messages and verification

    Verification:
    -------------
    Prints "=== Export Complete ===" when done
    """

    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "="*70)
    print("EXPORTING RESULTS")
    print("="*70 + "\n")

    # 1. Save analysis object as pickle (CRITICAL for downstream skills)
    print("1. Saving analysis objects for downstream use...")

    analysis_object = {
        'enrichment_results': results['enrichment_results'],
        'input_genes': results['input_genes'],
        'input_regions': results['input_regions'],
        'failed_genes': results.get('failed_genes', []),
        'metadata': results['metadata'],
        'parameters': results['parameters'],
        'n_genes': len(results['input_genes']),
        'n_regions': len(results['input_regions']),
        'n_experiments': len(results['enrichment_results']),
        'n_significant': len(results['enrichment_results'][
            results['enrichment_results']['q_value'] < 0.05
        ]),
        'timestamp': datetime.now().isoformat()
    }

    pickle_path = os.path.join(output_dir, "analysis_object.pkl")
    with open(pickle_path, 'wb') as f:
        pickle.dump(analysis_object, f)

    print(f"   Saved: {pickle_path}")
    print(f"   (Load with: import pickle; obj = pickle.load(open('analysis_object.pkl', 'rb')))")

    # 2. Export all results to CSV
    print("\n2. Exporting enrichment results...")

    all_results_path = os.path.join(output_dir, "enrichment_results_all.csv")
    results['enrichment_results'].to_csv(all_results_path, index=False)
    print(f"   Saved: {all_results_path} ({len(results['enrichment_results'])} experiments)")

    # 3. Export significant results (q < 0.05, BH-corrected)
    significant = results['enrichment_results'][
        results['enrichment_results']['q_value'] < 0.05
    ]

    if len(significant) > 0:
        sig_path = os.path.join(output_dir, "enrichment_results_significant.csv")
        significant.to_csv(sig_path, index=False)
        print(f"   Saved: {sig_path} ({len(significant)} significant, q < 0.05)")
    else:
        print(f"   No significant enrichments found (q < 0.05)")

    # 4. Export top 20 by significance (q-value), requiring min 2 gene overlaps
    rankable = results['enrichment_results'][
        results['enrichment_results']['regions_with_overlaps'] >= 2
    ]
    if len(rankable) > 0:
        top20 = rankable.sort_values('q_value').head(20)
    else:
        top20 = results['enrichment_results'].head(20)
    top20_path = os.path.join(output_dir, "enrichment_results_top20.csv")
    top20.to_csv(top20_path, index=False)
    print(f"   Saved: {top20_path} (top 20 by significance, overlap >= 2)")

    # 5. Export failed genes
    if results.get('failed_genes') and len(results['failed_genes']) > 0:
        failed_path = os.path.join(output_dir, "failed_genes.txt")
        with open(failed_path, 'w') as f:
            f.write('\n'.join(results['failed_genes']))
        print(f"   Saved: {failed_path} ({len(results['failed_genes'])} genes failed)")

    # 6. Generate summary report
    print("\n3. Generating summary report...")

    report_path = os.path.join(output_dir, "summary_report.md")
    with open(report_path, 'w') as f:
        f.write("# ChIP-Atlas Peak Enrichment Analysis Summary\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Parameters with threshold explanation
        f.write("## Analysis Parameters\n\n")
        params = results['parameters']
        f.write(f"- **Genome:** {params.get('genome', 'hg38')}\n")
        f.write(f"- **Antigen class:** {params.get('antigen_class', 'TFs and others')}\n")
        f.write(f"- **Cell class:** {params.get('cell_class', 'All cell types')}\n")
        threshold = params.get('threshold', 50)
        threshold_pval = {50: '1e-5', 100: '1e-10', 200: '1e-20', 500: '1e-50'}
        f.write(f"- **Peak threshold:** {threshold} "
                f"(MACS2 -10×log10(p) ≥ {threshold}; approx. p < {threshold_pval.get(threshold, '?')}). "
                f"Higher = fewer but more confident peaks. Default 50 balances sensitivity and specificity.\n")
        f.write(f"- **TSS window:** {params.get('distance_up', 5000)}bp upstream, "
                f"{params.get('distance_down', 5000)}bp downstream\n")
        if params.get('antigen_filter'):
            f.write(f"- **Antigen filter:** {params['antigen_filter']}\n")
        if params.get('cell_type_filter'):
            f.write(f"- **Cell type filter:** {params['cell_type_filter']}\n")

        # Exploratory analysis banner for small gene sets (BEFORE any results)
        n_genes_total = len(results['input_genes'])
        if n_genes_total <= 10:
            pct = 100.0 / n_genes_total
            f.write(f"\n> ⚠️ **EXPLORATORY ANALYSIS (N={n_genes_total} genes):** This is a "
                    f"demonstration-scale analysis, not a statistically powered study. Each gene "
                    f"contributes ~{pct:.0f}% of the signal — a single gene's inclusion/exclusion "
                    f"substantially changes results. **When summarizing to the user, lead with this "
                    f"exploratory framing** (e.g., \"As an exploratory analysis with only "
                    f"{n_genes_total} genes...\") rather than leading with the count of significant "
                    f"enrichments.\n\n")

        # Summary statistics with gene discrepancy check
        f.write("\n## Summary Statistics\n\n")
        f.write(f"- **Input genes:** {len(results['input_genes'])}\n")
        api_total_regions = results.get('api_total_regions', len(results['input_genes']))
        if api_total_regions != len(results['input_genes']):
            f.write(f"- **API regions analyzed:** {api_total_regions} "
                    f"({len(results['input_genes'])} submitted; "
                    f"{len(results['input_genes']) - api_total_regions} dropped by API — "
                    f"possible causes: gene not in RefSeq, unrecognized symbol, or duplicate promoter). "
                    f"The API does not report which specific gene(s) were dropped — do not speculate.\n")
        f.write(f"- **Promoter regions (Ensembl):** {len(results['input_regions'])}\n")
        f.write(f"- **Failed gene mappings:** {len(results.get('failed_genes', []))}\n")

        # Ensembl vs API reconciliation note
        n_ensembl = len(results['input_regions'])
        n_input = len(results['input_genes'])
        if n_ensembl == 0 and n_input > 0:
            f.write(f"\n⚠️ **Ensembl coordinate lookup failed for all {n_input} genes.** ")
            if api_total_regions == n_input:
                f.write(f"However, the API analyzed all {n_input} genes successfully. "
                        f"These are independent systems — the ChIP-Atlas API resolves gene symbols "
                        f"to promoter regions using its own RefSeq annotation, not Ensembl. "
                        f"Enrichment results are valid but lack independent genomic coordinate "
                        f"verification. When reporting to the user, state this clearly — "
                        f"do not dismiss it as merely \"optional.\"\n\n")
            else:
                f.write(f"The ChIP-Atlas API uses its own internal gene-to-region mapping "
                        f"(RefSeq-based), independent of Ensembl. Enrichment results are valid "
                        f"but lack independent coordinate verification. When reporting to the "
                        f"user, state this clearly — do not dismiss it as merely \"optional.\"\n\n")
        elif 0 < n_ensembl < api_total_regions:
            n_diff = api_total_regions - n_ensembl
            f.write(f"\n⚠️ **Ensembl/API region count discrepancy:** Ensembl mapped {n_ensembl} "
                    f"gene(s) to coordinates, while the ChIP-Atlas API analyzed {api_total_regions} "
                    f"region(s). These systems use **different gene databases** (Ensembl vs RefSeq) "
                    f"— a gene may have a failed/timed-out Ensembl lookup or differ in symbol "
                    f"recognition between databases. The {n_diff} gene(s) without Ensembl coordinates "
                    f"lack independent coordinate verification but are still included in enrichment "
                    f"results via the API's own RefSeq mapping. When reporting to the user, state "
                    f"both counts clearly and explain they reflect different database coverage.\n\n")
        f.write(f"- **Experiments analyzed:** {len(results['enrichment_results'])}\n")
        f.write(f"- **Significant enrichments (q < 0.05):** {analysis_object['n_significant']}\n")

        # Top 10 per-experiment table
        f.write("\n## Top 10 Experiments (by significance)\n\n")
        f.write("*Each row is an individual ChIP-seq experiment. The same factor may appear multiple times.*\n\n")
        f.write("| Rank | Factor | Cell Type | Q-value | Fold Enrichment | Overlap | Regions |\n")
        f.write("|------|--------|-----------|---------|-----------------|---------|----------|\n")

        top10_rankable = rankable.head(10) if len(rankable) > 0 else results['enrichment_results'].head(10)
        for rank, (idx, row) in enumerate(top10_rankable.iterrows(), 1):
            fe_display = f"{row['fold_enrichment']:.1f}" if row['fold_enrichment'] < 100000 else ">100,000"
            f.write(
                f"| {rank} | {row['antigen']} | {row['cell_type']} | "
                f"{row['q_value']:.2e} | {fe_display}x | "
                f"{row['overlap_rate']:.0%} | {int(row['regions_with_overlaps'])}/{int(row['total_regions'])} |\n"
            )

        f.write("\n*Ranked by BH-corrected Q-value. Minimum 2 gene overlaps required.*\n")

        # Aggregated by unique factor
        f.write("\n## Top Factors (aggregated by unique factor)\n\n")

        agg_source = rankable if len(rankable) > 0 else results['enrichment_results']
        sig_source = agg_source[agg_source['q_value'] < 0.05]

        # Count total unique significant factors
        n_unique_sig_factors = sig_source['antigen'].nunique() if len(sig_source) > 0 else 0

        if len(agg_source) > 0:
            # Compute per-factor stats from ALL experiments with overlap >= 2
            agg = agg_source.groupby('antigen').agg(
                n_experiments=('experiment_id', 'count'),
                best_qvalue=('q_value', 'min'),
                median_overlap=('overlap_rate', 'median'),
                max_overlap=('overlap_rate', 'max'),
                median_fe=('fold_enrichment', 'median'),
            ).reset_index()

            # Add significant-only metrics per factor
            if len(sig_source) > 0:
                sig_agg = sig_source.groupby('antigen').agg(
                    n_significant=('experiment_id', 'count'),
                    median_fe_sig=('fold_enrichment', 'median'),
                ).reset_index()
                agg = agg.merge(sig_agg, on='antigen', how='left')
                agg['n_significant'] = agg['n_significant'].fillna(0).astype(int)
                agg['median_fe_sig'] = agg['median_fe_sig'].fillna(0)
            else:
                agg['n_significant'] = 0
                agg['median_fe_sig'] = 0.0

            agg = agg.sort_values('best_qvalue').head(10)

            if n_unique_sig_factors > 10:
                f.write(f"*Top 10 of {n_unique_sig_factors} significantly enriched factors "
                        f"(q < 0.05). \"Experiments\" = experiments with ≥2 gene overlaps; "
                        f"\"Sig\" = those reaching q < 0.05. Median FE (Sig) uses only significant "
                        f"experiments — use this column, not Median FE (All), to judge enrichment "
                        f"strength.*\n\n")
            else:
                f.write(f"*{n_unique_sig_factors} significantly enriched factor(s) shown. "
                        f"\"Experiments\" = experiments with ≥2 gene overlaps; "
                        f"\"Sig\" = those reaching q < 0.05. Median FE (Sig) uses only significant "
                        f"experiments — use this column, not Median FE (All), to judge enrichment "
                        f"strength.*\n\n")

            f.write("| Rank | Factor | Experiments | Sig | Best Q-value | Median FE (Sig) | Median FE (All) | Max Overlap |\n")
            f.write("|------|--------|-------------|-----|-------------|-----------------|-----------------|-------------|\n")

            for rank, (idx, row) in enumerate(agg.iterrows(), 1):
                fe_all = f"{row['median_fe']:.1f}" if row['median_fe'] < 100000 else ">100,000"
                if row['n_significant'] > 0:
                    fe_sig = f"{row['median_fe_sig']:.1f}" if row['median_fe_sig'] < 100000 else ">100,000"
                else:
                    fe_sig = "—"
                fe_sig_cell = f"{fe_sig}x" if fe_sig != "—" else "—"
                f.write(
                    f"| {rank} | {row['antigen']} | {int(row['n_experiments'])} | "
                    f"{int(row['n_significant'])} | "
                    f"{row['best_qvalue']:.2e} | "
                    f"{fe_sig_cell} | {fe_all}x | {row['max_overlap']:.0%} |\n"
                )

            # Diluted median FE warning
            f.write(f"\n⚠️ **Use Median FE (Sig), not Median FE (All), to judge enrichment "
                    f"strength.** The \"Median FE (All)\" column averages across all experiments "
                    f"with ≥2 overlaps — including non-significant ones. For factors with many "
                    f"experiments but few significant (e.g., Experiments=137 but Sig=5), this "
                    f"median is diluted by non-significant experiments and will dramatically "
                    f"understate the actual enrichment. **Do not conclude \"weak enrichment\" from "
                    f"a low Median FE (All) when Median FE (Sig) shows strong enrichment.**\n")

            # Multiple testing across factors note
            f.write(f"\n⚠️ **Per-factor multiple testing:** The \"Best Q-value\" column shows "
                    f"each factor's most significant experiment (BH-corrected across experiments, "
                    f"not across factors). Interpreting all {min(len(agg), 10)} top factors as "
                    f"independent discoveries overstates confidence — these Q-values do not account "
                    f"for testing across multiple factors.\n")

            # Additional significant factors note
            if n_unique_sig_factors > 10:
                f.write(f"\n⚠️ **{n_unique_sig_factors - 10} additional significantly enriched "
                        f"factors** (q < 0.05) are not shown in this table. Mention that "
                        f"{n_unique_sig_factors} total factors are significant, not just the top 10 "
                        f"shown here. Consider noting notable omissions from the full significant "
                        f"results CSV.\n")

            # Small gene set warning directly after factor table
            if len(results['input_genes']) <= 10:
                f.write(f"\n⚠️ **SMALL GENE SET (N={api_total_regions} genes):** When discussing "
                        f"factors with moderate fold enrichment (2–10x) from this table, you MUST "
                        f"explicitly note that with only {api_total_regions} input genes, a single "
                        f"gene's inclusion/exclusion could eliminate the signal entirely. Do not "
                        f"present moderate-enrichment factors as reliable findings without this caveat.\n")

        # Overlap rate summary
        f.write("\n## Overlap Rate Summary\n\n")

        sig_df = results['enrichment_results'][results['enrichment_results']['q_value'] < 0.05]
        if len(sig_df) > 0:
            f.write(f"**Across {len(sig_df)} significant experiments (q < 0.05):**\n")
            f.write(f"- Median overlap rate: {sig_df['overlap_rate'].median():.0%}\n")
            f.write(f"- Range: {sig_df['overlap_rate'].min():.0%} – {sig_df['overlap_rate'].max():.0%}\n")
            f.write(f"- Mean: {sig_df['overlap_rate'].mean():.0%}\n\n")

        if len(rankable) > 0:
            top10_data = rankable.head(10)
            f.write(f"**Across top 10 experiments (by q-value, overlap ≥ 2):**\n")
            f.write(f"- Median overlap rate: {top10_data['overlap_rate'].median():.0%}\n")
            f.write(f"- Range: {top10_data['overlap_rate'].min():.0%} – {top10_data['overlap_rate'].max():.0%}\n\n")

        f.write("⚠️ When summarizing, cite the median and range from this section. "
                "Do not round up or generalize overlap rates.\n")

        # Interpretation
        f.write("\n## Interpretation\n\n")
        f.write("**Q-value (BH-corrected, primary ranking):**\n")
        f.write("- q < 0.001: Highly significant after multiple testing correction\n")
        f.write("- q < 0.01: Significant\n")
        f.write("- q < 0.05: Genome-wide significant\n")
        f.write("- q ≥ 0.05: Not significant after correction\n\n")

        f.write("**Fold Enrichment:**\n")
        f.write("- >10x: Very strong enrichment, likely direct regulatory relationship\n")
        f.write("- 5–10x: Strong enrichment, good evidence for regulation\n")
        f.write("- 2–5x: Moderate enrichment, possible regulation\n")
        f.write("- <2x: Weak enrichment, may be background\n")
        f.write("- >100,000x: Likely sentinel value (zero background overlap); interpret with caution\n")

        # Important caveats (promoted to dedicated section)
        f.write("\n## Important Caveats\n\n")
        f.write("**1. Data Availability Bias:** Well-studied transcription factors "
                "(e.g., TP53, RELA, CTCF) have hundreds to thousands of public ChIP-seq experiments, "
                "while less-studied factors may have only a few. A factor appearing in the top results "
                "may partly reflect data availability, not just biological specificity. "
                "Compare the 'Experiments' and 'Sig' columns in the aggregated table: a factor with "
                "many experiments but few significant (e.g., Experiments=137, Sig=5) shows enrichment "
                "only in specific cell types/conditions. **Always use Median FE (Sig) — not "
                "Median FE (All) — to judge enrichment strength.** The 'All' median is diluted by "
                "non-significant experiments and can dramatically understate actual enrichment.\n\n")
        f.write("**2. Redundant Experiments:** The top experiments table shows individual ChIP-seq "
                "datasets. The same factor may appear multiple times from different cell types, labs, "
                "or conditions. The aggregated factor table provides a deduplicated view.\n\n")
        f.write("**3. Validation Required:** Validate key findings with orthogonal methods: "
                "gene expression correlation, perturbation experiments, or motif analysis.\n\n")

        f.write(f"**4. Threshold Sensitivity:** Results were generated at threshold={threshold} "
                f"(approx. p < {threshold_pval.get(threshold, '?')}). "
                f"Lower thresholds include more peaks, potentially inflating overlap rates and significance; "
                f"higher thresholds are more conservative. "
                f"Consider re-running at a different threshold (e.g., 100) to assess robustness.\n")

        n_genes = len(results['input_genes'])
        if n_genes <= 30:
            pct_per_gene = 100.0 / api_total_regions
            if n_genes <= 10:
                f.write(f"\n**5. ⚠️ Small Gene Set — Exploratory Analysis Only:** With only "
                        f"{api_total_regions} input regions, each gene contributes ~{pct_per_gene:.1f}% "
                        f"to overlap rates. This is a demonstration-scale analysis, not a statistically "
                        f"powered study. A single gene's inclusion or exclusion substantially changes "
                        f"overlap percentages and significance rankings. Conclusions should be framed "
                        f"as exploratory — validate any findings with a larger gene set "
                        f"(recommended: 20–100 genes) before drawing biological conclusions.\n")
            else:
                f.write(f"\n**5. Small Gene Set Granularity:** With {api_total_regions} input regions, "
                        f"each gene contributes ~{pct_per_gene:.1f}% to overlap rates. "
                        f"A single gene's inclusion or exclusion substantially changes the overlap percentage. "
                        f"Interpret overlap rates as approximate.\n")

        # Files generated
        f.write("\n## Files Generated\n\n")
        f.write("- `analysis_object.pkl` — Complete results for downstream use\n")
        f.write("- `enrichment_results_all.csv` — All experiments\n")

        if len(significant) > 0:
            f.write("- `enrichment_results_significant.csv` — Significant results (q < 0.05)\n")

        f.write("- `enrichment_results_top20.csv` — Top 20 by significance (q-value, overlap ≥ 2)\n")

        if results.get('failed_genes') and len(results['failed_genes']) > 0:
            f.write(f"- `failed_genes.txt` — {len(results['failed_genes'])} genes that couldn't be mapped\n")

        f.write("- `chipatlas_enrichment.png/.svg` — 4-panel summary plot\n")

        # References
        f.write("\n## References\n\n")
        f.write("- Zou et al. (2024). ChIP-Atlas 3.0: a data-mining suite to explore chromosome "
                "architecture. *Nucleic Acids Research*. doi:10.1093/nar/gkad884\n")
        f.write("- Oki et al. (2018). ChIP-Atlas: a data-mining suite powered by full integration "
                "of public ChIP-seq data. *EMBO Reports* 19(12):e46255. doi:10.15252/embr.201846255\n")
        f.write("- ChIP-Atlas: https://chip-atlas.org\n")

    print(f"   Saved: {report_path}")

    # Final verification message
    print("\n" + "="*70)
    print("=== Export Complete ===")
    print("="*70)
    print(f"\nAll results saved to: {output_dir}/")
    print(f"  - analysis_object.pkl (for downstream analysis)")
    print(f"  - enrichment_results_all.csv ({len(results['enrichment_results'])} experiments)")

    if len(significant) > 0:
        print(f"  - enrichment_results_significant.csv ({len(significant)} significant, q < 0.05)")

    print(f"  - enrichment_results_top20.csv (top 20 by significance)")

    if results.get('failed_genes') and len(results['failed_genes']) > 0:
        print(f"  - failed_genes.txt ({len(results['failed_genes'])} genes failed)")

    print(f"  - summary_report.md (human-readable summary)")
    print()


if __name__ == "__main__":
    # Test with mock data
    import pandas as pd

    mock_results = {
        'enrichment_results': pd.DataFrame({
            'experiment_id': ['SRX000001', 'SRX000002'],
            'antigen': ['TP53', 'MYC'],
            'cell_type': ['HeLa', 'K562'],
            'fold_enrichment': [15.2, 8.3],
            'p_value': [0.0001, 0.001],
            'q_value': [0.001, 0.01],
            'significant': [True, True],
            'overlap_rate': [0.6, 0.4],
            'regions_with_overlaps': [3, 2],
            'total_regions': [5, 5],
            'total_peaks': [1000, 800]
        }),
        'input_genes': ['CDKN1A', 'BAX', 'BBC3', 'GADD45A', 'MDM2'],
        'input_regions': [('chr6', 36651929, 36654929, 'CDKN1A', '+')],
        'failed_genes': [],
        'metadata': pd.DataFrame(),
        'parameters': {
            'genome': 'hg38',
            'upstream': 2000,
            'downstream': 500,
            'peak_threshold': '05',
            'antigen_filter': None,
            'cell_type_filter': None,
            'max_experiments': 50
        }
    }

    export_all(mock_results, output_dir="test_export")
    print("Test completed successfully!")

