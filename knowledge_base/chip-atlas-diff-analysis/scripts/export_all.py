"""
Export all ChIP-Atlas diff analysis results (Step 4).

Exports:
1. analysis_object.pkl - Complete results for downstream use
2. diff_regions_all.csv - All differential regions
3. diff_regions_significant.csv - Significant regions (FDR < 0.05)
4. diff_regions_top50.csv - Top 50 by significance
5. summary_report.md - Human-readable summary
"""

import os
import pickle
from datetime import datetime

try:
    try:
        from scripts.annotate_genes import annotate_nearest_genes
    except ImportError:
        from annotate_genes import annotate_nearest_genes
    _HAS_GENE_ANNOTATION = True
except ImportError:
    _HAS_GENE_ANNOTATION = False


def export_all(results, output_dir="diff_analysis_results", qvalue_threshold=0.05):
    """
    Export all ChIP-Atlas diff analysis results with pickle object.

    Parameters
    ----------
    results : dict
        Results from run_diff_workflow()
    output_dir : str
        Output directory
    qvalue_threshold : float
        Maximum Q-value (FDR) for "significant" regions (default: 0.05)

    Verification
    ------------
    Prints "=== Export Complete ===" when done
    """
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("EXPORTING RESULTS")
    print("=" * 70 + "\n")

    df = results["diff_regions"]
    params = results["parameters"]

    qc_warnings = results.get("qc_warnings", [])
    unfiltered_df = results.get("diff_regions_unfiltered", df)

    # 1. Save analysis object as pickle (CRITICAL for downstream skills)
    print("1. Saving analysis objects for downstream use...")

    n_a = (df["direction"] == "A_enriched").sum() if len(df) > 0 else 0
    n_b = (df["direction"] == "B_enriched").sum() if len(df) > 0 else 0

    analysis_object = {
        "diff_regions": df,
        "diff_regions_unfiltered": unfiltered_df,
        "qc_warnings": qc_warnings,
        "experiments_a": results["experiments_a"],
        "experiments_b": results["experiments_b"],
        "raw_files": results.get("raw_files", {}),
        "log_content": results.get("log_content", ""),
        "parameters": params,
        "n_regions_total": len(df),
        "n_regions_unfiltered": len(unfiltered_df),
        "n_regions_a_enriched": int(n_a),
        "n_regions_b_enriched": int(n_b),
        "timestamp": datetime.now().isoformat(),
    }

    pickle_path = os.path.join(output_dir, "analysis_object.pkl")
    with open(pickle_path, "wb") as f:
        pickle.dump(analysis_object, f)

    print(f"   Saved: {pickle_path}")
    print("   (Load with: import pickle; obj = pickle.load(open('analysis_object.pkl', 'rb')))")

    # 2. Export all regions to CSV
    print("\n2. Exporting differential regions...")

    all_path = os.path.join(output_dir, "diff_regions_all.csv")
    df.to_csv(all_path, index=False)
    print(f"   Saved: {all_path} ({len(df)} regions)")

    # 3. Export significant regions (FDR-filtered)
    if "qvalue" in df.columns:
        significant = df[df["qvalue"] < qvalue_threshold]
        if len(significant) > 0:
            sig_path = os.path.join(output_dir, "diff_regions_significant.csv")
            significant.to_csv(sig_path, index=False)
            print(f"   Saved: {sig_path} ({len(significant)} regions with FDR < {qvalue_threshold})")
        else:
            print(f"   No regions with FDR < {qvalue_threshold}")
    elif "score" in df.columns:
        significant = df[df["score"] >= 200]
        if len(significant) > 0:
            sig_path = os.path.join(output_dir, "diff_regions_significant.csv")
            significant.to_csv(sig_path, index=False)
            print(f"   Saved: {sig_path} ({len(significant)} regions with score >= 200)")

    # 4. Export top 50 by significance (with gene annotations if available)
    if "qvalue" in df.columns and "logFC" in df.columns and len(df) > 0:
        _s = df.copy()
        _s["_abs_logFC"] = _s["logFC"].abs()
        top50 = _s.sort_values(
            ["qvalue", "_abs_logFC", "chrom", "chromStart"],
            ascending=[True, False, True, True],
        ).head(50).drop(columns=["_abs_logFC"])
    elif "score" in df.columns and len(df) > 0:
        top50 = df.sort_values("score", ascending=False).head(50)
    else:
        top50 = df.head(50)

    # Annotate top regions with nearest genes
    gene_annotations = None
    if _HAS_GENE_ANNOTATION and len(top50) > 0:
        try:
            genome = params.get("genome", "hg38")
            gene_annotations = annotate_nearest_genes(
                top50, genome=genome, max_regions=50
            )
        except Exception as e:
            print(f"   Warning: Gene annotation failed ({e}). Skipping.")
            gene_annotations = None

    if gene_annotations is not None and len(gene_annotations) > 0:
        top50 = top50.copy()
        top50["nearest_gene"] = gene_annotations.reindex(top50.index).fillna("")

    top50_path = os.path.join(output_dir, "diff_regions_top50.csv")
    top50.to_csv(top50_path, index=False)
    print(f"   Saved: {top50_path} (top {len(top50)} by significance)")

    # 4b. Export unfiltered regions (pre-QC) if different from filtered
    if len(unfiltered_df) != len(df):
        unfiltered_path = os.path.join(output_dir, "diff_regions_unfiltered.csv")
        unfiltered_df.to_csv(unfiltered_path, index=False)
        print(f"   Saved: {unfiltered_path} ({len(unfiltered_df)} regions, pre-QC filter)")

    # 5. Generate summary report
    print("\n3. Generating summary report...")

    desc_a = params.get("description_a", "Group A")
    desc_b = params.get("description_b", "Group B")
    analysis_type = params.get("analysis_type", "diffbind")
    type_label = "Differential Peak Regions" if analysis_type == "diffbind" else "Differentially Methylated Regions"

    report_path = os.path.join(output_dir, "summary_report.md")
    with open(report_path, "w") as f:
        f.write(f"# ChIP-Atlas Diff Analysis Summary\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## Analysis Parameters\n\n")
        f.write(f"- **Analysis type:** {type_label}\n")
        f.write(f"- **Genome:** {params.get('genome', 'N/A')}\n")
        n_a_exp = len(results['experiments_a'])
        n_b_exp = len(results['experiments_b'])
        f.write(f"- **Group A ({desc_a}):** {', '.join(results['experiments_a'])} (n={n_a_exp})\n")
        f.write(f"- **Group B ({desc_b}):** {', '.join(results['experiments_b'])} (n={n_b_exp})\n")

        # Experimental design caveats — placed prominently before QC warnings
        design_caveats = params.get("design_caveats", [])
        if design_caveats:
            f.write("\n## ⚠️ Experimental Design Caveats\n\n")
            for caveat in design_caveats:
                f.write(f"- {caveat}\n")

        # QC Warnings section
        if qc_warnings:
            f.write("\n## QC Warnings\n\n")
            for w in qc_warnings:
                icon = "**MAJOR**" if w["severity"] == "major" else "Minor"
                f.write(f"### {icon}: {w['issue']}\n\n")
                f.write(f"{w['details']}\n\n")
                f.write(f"**Recommendation:** {w['recommendation']}\n\n")

        # Cluster + chrM impact aggregation
        # Collect flagged coordinates (used for both artifact summary and top hits note)
        flagged_coords = set()
        artifact_warnings = [
            w for w in qc_warnings
            if "genomic cluster" in w.get("issue", "")
            or "chrM enrichment" in w.get("issue", "")
        ]
        if artifact_warnings and "significant" in df.columns:
            for w in artifact_warnings:
                for coord in w.get("flagged_regions", []):
                    flagged_coords.add(tuple(coord))

            # chrM enrichment warning flags all significant chrM regions
            if any("chrM enrichment" in w.get("issue", "") for w in artifact_warnings):
                sig_chrm = df[(df["chrom"] == "chrM") & (df["significant"])]
                for _, row in sig_chrm.iterrows():
                    flagged_coords.add((row["chrom"], int(row["chromStart"]), int(row["chromEnd"])))

            artifact_sig = df[df["significant"]]
            n_flagged = sum(
                1 for _, row in artifact_sig.iterrows()
                if (row["chrom"], int(row["chromStart"]), int(row["chromEnd"])) in flagged_coords
            )
            n_sig = len(artifact_sig)

            if n_flagged > 0 and n_sig > 0:
                pct = n_flagged / n_sig * 100
                n_clean = n_sig - n_flagged
                f.write("### Artifact Impact Summary\n\n")
                f.write(
                    f"**{n_flagged} of {n_sig} significant regions ({pct:.0f}%) "
                    f"fall within flagged artifacts** (genomic clusters and/or chrM "
                    f"contamination). After excluding these, **{n_clean} significant "
                    f"regions remain** for biological interpretation.\n\n"
                )

                # Direction breakdown after artifact removal
                if "direction" in artifact_sig.columns and n_clean > 0:
                    clean_sig = artifact_sig[
                        ~artifact_sig.apply(
                            lambda row: (
                                row["chrom"],
                                int(row["chromStart"]),
                                int(row["chromEnd"]),
                            )
                            in flagged_coords,
                            axis=1,
                        )
                    ]
                    n_clean_a = int(
                        (clean_sig["direction"] == "A_enriched").sum()
                    )
                    n_clean_b = int(
                        (clean_sig["direction"] == "B_enriched").sum()
                    )
                    f.write(
                        f"Direction breakdown after artifact removal: "
                        f"**{n_clean_a} {desc_a}-enriched, "
                        f"{n_clean_b} {desc_b}-enriched**"
                    )
                    # Note if balance shifted substantially vs pre-removal
                    pre_a = int((artifact_sig["direction"] == "A_enriched").sum())
                    pre_b = int((artifact_sig["direction"] == "B_enriched").sum())
                    if pre_a > 0 and pre_b > 0 and n_clean_b > 0:
                        orig_ratio = pre_a / pre_b
                        clean_ratio = n_clean_a / n_clean_b
                        ratio_change = max(
                            clean_ratio / orig_ratio,
                            orig_ratio / clean_ratio,
                        )
                        if ratio_change > 2:
                            dominant = (
                                desc_a if n_clean_a > n_clean_b else desc_b
                            )
                            f.write(
                                f" (vs {pre_a}/{pre_b} before removal "
                                f"— artifact removal substantially shifts "
                                f"the direction balance, suggesting genuine "
                                f"differential binding is predominantly "
                                f"{dominant}-enriched)"
                            )
                    f.write(".\n\n")

                if pct >= 50:
                    f.write(
                        "The majority of significant results may reflect copy number "
                        "differences, structural variants, or mitochondrial contamination "
                        "rather than genuine differential binding. Interpret with extreme "
                        "caution and focus on the non-flagged regions.\n\n"
                    )
                elif pct >= 25:
                    f.write(
                        "A notable fraction of significant results may be artifacts. "
                        "Review flagged clusters individually before drawing biological "
                        "conclusions.\n\n"
                    )

        # QC filtering note
        if len(unfiltered_df) != len(df):
            f.write("\n## QC Filtering Applied\n\n")
            f.write(f"- **Before QC filtering:** {len(unfiltered_df)} regions\n")
            f.write(f"- **After QC filtering:** {len(df)} regions\n")
            f.write(f"- **Removed:** {len(unfiltered_df) - len(df)} regions "
                    f"(non-standard contigs and regions < 10bp)\n")
            f.write(f"- **Unfiltered data:** See `diff_regions_unfiltered.csv`\n")

        # Statistical caveats
        f.write("\n## Statistical Caveats\n\n")
        f.write(f"- **Sample size:** n={n_a_exp} (Group A) vs n={n_b_exp} (Group B)\n")
        min_n = min(n_a_exp, n_b_exp)
        if min_n < 5:
            f.write(f"- **Power limitation:** With n < 5 per group, edgeR FDR estimates "
                    f"may be unstable for moderate effect sizes\n")
        f.write("- **Validation:** Key findings should be validated with orthogonal methods "
                "or additional replicates\n")
        f.write("- **Public data:** Results depend on the quality of public ChIP-Atlas data\n")

        f.write("\n## Summary Statistics\n\n")
        f.write(f"- **Total differential regions:** {len(df)}\n")
        f.write(f"- **Enriched in {desc_a}:** {n_a}\n")
        f.write(f"- **Enriched in {desc_b}:** {n_b}\n")

        # Check if low sample size warning exists
        has_low_n = any(
            "sample size" in w.get("issue", "").lower() for w in qc_warnings
        )

        n_sig_a = 0
        n_sig_b = 0
        if "significant" in df.columns and len(df) > 0:
            n_sig = df["significant"].sum()
            if has_low_n:
                f.write(f"- **Significant (FDR < 0.05):** {n_sig} "
                        f"(interpret with caution — see Statistical Caveats)\n")
            else:
                f.write(f"- **Significant (FDR < 0.05):** {n_sig}\n")
            if "direction" in df.columns:
                sig_df = df[df["significant"]]
                n_sig_a = int((sig_df["direction"] == "A_enriched").sum())
                n_sig_b = int((sig_df["direction"] == "B_enriched").sum())
                f.write(f"  - Significant enriched in {desc_a}: {n_sig_a}\n")
                f.write(f"  - Significant enriched in {desc_b}: {n_sig_b}\n")

        if "logFC" in df.columns and len(df) > 0:
            f.write(f"- **LogFC range:** {df['logFC'].min():.2f} to {df['logFC'].max():.2f}\n")
            f.write(f"- **Median |logFC|:** {df['logFC'].abs().median():.2f}\n")

        if "qvalue" in df.columns and len(df) > 0:
            f.write(f"- **Min Q-value:** {df['qvalue'].min():.2e}\n")
            f.write(f"- **Median Q-value:** {df['qvalue'].median():.2e}\n")

        if "region_size" in df.columns and len(df) > 0:
            f.write(f"- **Median region size:** {df['region_size'].median():.0f} bp\n")
            f.write(f"- **Mean region size:** {df['region_size'].mean():.0f} bp\n")

        # Asymmetric binding note
        if n_sig_a > 0 and n_sig_b > 0:
            ratio = max(n_sig_a, n_sig_b) / min(n_sig_a, n_sig_b)
            if ratio >= 1.5:
                more_group = desc_a if n_sig_a > n_sig_b else desc_b
                f.write(f"\n**Note:** Asymmetric binding pattern — {more_group} has "
                        f"{ratio:.1f}x more significant differential regions, "
                        f"suggesting a broader {type_label.lower().rstrip('s')} landscape "
                        f"in this group.\n")
        elif n_sig_a > 0 and n_sig_b == 0:
            f.write(f"\n**Note:** All {n_sig_a} significant regions are enriched in "
                    f"{desc_a} (none in {desc_b}).\n")
        elif n_sig_b > 0 and n_sig_a == 0:
            f.write(f"\n**Note:** All {n_sig_b} significant regions are enriched in "
                    f"{desc_b} (none in {desc_a}).\n")

        # Build set of flagged sex chromosomes from QC warnings
        sex_artifact_chroms = set()
        for w in qc_warnings:
            if "sex chromosome confound" in w.get("issue", ""):
                chrom_name = w["issue"].split(" ")[0]
                sex_artifact_chroms.add(chrom_name)

        # Build gene lookup from annotations
        top10_genes = {}
        if gene_annotations is not None:
            for ann_idx, gene in gene_annotations.items():
                if gene:
                    top10_genes[ann_idx] = gene

        # Top regions table
        if len(df) > 0:
            has_genes = bool(top10_genes)
            f.write("\n## Top 10 Differential Regions (strict ranking by Q-value)\n\n")
            if has_genes:
                f.write("| Rank | Location | Size (bp) | logFC | Q-value | Direction | Nearest Gene |\n")
                f.write("|------|----------|-----------|-------|---------|----------|-------------|\n")
            else:
                f.write("| Rank | Location | Size (bp) | logFC | Q-value | Direction |\n")
                f.write("|------|----------|-----------|-------|---------|----------|\n")

            if "qvalue" in df.columns and "logFC" in df.columns:
                _s = df.copy()
                _s["_abs_logFC"] = _s["logFC"].abs()
                top_display = _s.sort_values(
                    ["qvalue", "_abs_logFC", "chrom", "chromStart"],
                    ascending=[True, False, True, True],
                ).head(10).drop(columns=["_abs_logFC"])
            elif "score" in df.columns:
                top_display = df.sort_values("score", ascending=False).head(10)
            else:
                top_display = df.head(10)
            for rank, (idx, row) in enumerate(top_display.iterrows(), 1):
                loc = f"{row['chrom']}:{int(row['chromStart']):,}-{int(row['chromEnd']):,}"
                size = int(row.get("region_size", row["chromEnd"] - row["chromStart"]))
                logfc = f"{row['logFC']:.2f}" if "logFC" in row else "N/A"
                qval = f"{row['qvalue']:.2e}" if "qvalue" in row else "N/A"
                direction = row.get("direction", "unknown")
                if row["chrom"] in sex_artifact_chroms:
                    direction += " *"
                gene = top10_genes.get(idx, "")
                if has_genes:
                    f.write(f"| {rank} | {loc} | {size:,} | {logfc} | {qval} | {direction} | {gene} |\n")
                else:
                    f.write(f"| {rank} | {loc} | {size:,} | {logfc} | {qval} | {direction} |\n")

            f.write(f"\nRanked strictly by Q-value. Some regions may lack gene "
                    f"annotations — this does not diminish their statistical "
                    f"significance.\n")
            if sex_artifact_chroms:
                f.write(f"\n\\* Probable sex-chromosome artifact "
                        f"({', '.join(sorted(sex_artifact_chroms))}). "
                        f"See QC Warnings above.\n")

            # Note if top hits are dominated by artifacts
            if flagged_coords:
                n_top_flagged = sum(
                    1 for _, row in top_display.iterrows()
                    if (row["chrom"], int(row["chromStart"]), int(row["chromEnd"])) in flagged_coords
                )
                n_top = len(top_display)
                if n_top_flagged > n_top // 2:
                    f.write(
                        f"\n**Note:** {n_top_flagged} of these top {n_top} regions "
                        f"fall within flagged artifact areas (genomic clusters "
                        f"and/or chrM). The strongest statistical signals are "
                        f"largely driven by artifacts rather than genuine "
                        f"differential binding. See non-artifact regions for "
                        f"biologically interpretable results.\n"
                    )
                elif n_top_flagged > 0:
                    f.write(
                        f"\n**Note:** {n_top_flagged} of these top {n_top} regions "
                        f"fall within flagged artifact areas — see Artifact "
                        f"Impact Summary above.\n"
                    )

        # Chromosome distribution
        if len(df) > 0:
            f.write("\n## Chromosome Distribution\n\n")
            chrom_counts = df["chrom"].value_counts().head(10)
            for chrom, count in chrom_counts.items():
                f.write(f"- **{chrom}:** {count} regions\n")

        f.write("\n## Files Generated\n\n")
        f.write("**Analysis Objects:**\n")
        f.write("- `analysis_object.pkl` - Complete results for downstream use\n\n")
        f.write("**Results (CSV):**\n")
        f.write("- `diff_regions_all.csv` - All differential regions (QC-filtered)\n")
        f.write("- `diff_regions_significant.csv` - Significant regions (FDR < 0.05)\n")
        f.write("- `diff_regions_top50.csv` - Top 50 by significance\n")
        if len(unfiltered_df) != len(df):
            f.write("- `diff_regions_unfiltered.csv` - Pre-QC regions (includes non-standard contigs and small regions)\n")
        f.write("\n")
        f.write("**Visualizations (plotnine with Prism theme):**\n")
        f.write("- `volcano_plot.png/.svg` - Volcano plot (logFC vs -log10 Q-value)\n")
        f.write("- `chromosome_distribution.png/.svg` - Differential regions by chromosome\n")
        f.write("- `region_size_distribution.png/.svg` - Region size histogram\n")
        f.write("- `ma_plot.png/.svg` - MA plot (mean counts vs logFC)\n\n")
        f.write("**Raw Results:**\n")
        f.write("- `raw_results/` - Original BED, IGV, and log files from ChIP-Atlas\n")

        f.write("\n## Suggested Next Steps\n\n")
        f.write("1. **Visualize in IGV** — Open the `.igv.bed` file in IGV to inspect "
                "differential regions in their genomic context\n")
        f.write("2. **Motif analysis** — Run HOMER or MEME-ChIP on significant regions "
                "to identify enriched transcription factor motifs\n")
        f.write("3. **Gene ontology / pathway analysis** — Use GREAT or nearby gene "
                "annotations to identify enriched biological processes\n")
        f.write("4. **Integrate with expression data** — Cross-reference differential "
                "peaks with RNA-seq DE results to link regulatory regions to gene "
                "expression changes\n")

    print(f"   Saved: {report_path}")

    # Final verification message
    print("\n" + "=" * 70)
    print("=== Export Complete ===")
    print("=" * 70)
    print(f"\nAll results saved to: {output_dir}/")
    print(f"  - analysis_object.pkl (for downstream analysis)")
    print(f"  - diff_regions_all.csv ({len(df)} regions)")

    if "qvalue" in df.columns:
        n_sig = len(df[df["qvalue"] < qvalue_threshold])
        if n_sig > 0:
            print(f"  - diff_regions_significant.csv ({n_sig} significant regions, FDR < {qvalue_threshold})")
            if "direction" in df.columns:
                sig_df = df[df["qvalue"] < qvalue_threshold]
                n_sig_a = int((sig_df["direction"] == "A_enriched").sum())
                n_sig_b = int((sig_df["direction"] == "B_enriched").sum())
                print(f"    ({desc_a}: {n_sig_a}, {desc_b}: {n_sig_b})")
    elif "score" in df.columns:
        n_sig = len(df[df["score"] >= 200])
        if n_sig > 0:
            print(f"  - diff_regions_significant.csv ({n_sig} high-score regions)")

    print(f"  - diff_regions_top50.csv (top {min(50, len(df))} by significance)")
    print(f"  - summary_report.md (human-readable summary)")
    print()

