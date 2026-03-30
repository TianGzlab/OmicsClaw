"""
Quality control checks for ChIP-Atlas diff analysis results.

Runs automated QC after parsing BED results to flag interpretive pitfalls:
- Sex chromosome confounds (chrY/chrX artifacts from mismatched sample sex)
- Non-standard contigs (mapping artifacts on random/unplaced scaffolds)
- Implausibly small regions (< 10bp, likely edge artifacts)
- Low sample size (limited statistical power with small n)
- MA plot asymmetry (significant hits clustering at low counts in one direction)
- Region size distribution (unusually small median region size)

Each check returns a warning dict with severity, issue, details, recommendation.
Warnings are printed to console and stored in results for the summary report.
"""

import numpy as np

try:
    from scripts.filter_regions import get_standard_chroms
except ImportError:
    from filter_regions import get_standard_chroms

SEX_CHROMS = {"chrX", "chrY"}


def run_qc_checks(df, n_samples_a, n_samples_b, analysis_type="diffbind", genome=None):
    """
    Run all QC checks on parsed differential regions.

    Parameters
    ----------
    df : pd.DataFrame
        Parsed DataFrame from parse_bed_results() (unfiltered)
    n_samples_a : int
        Number of experiments in group A
    n_samples_b : int
        Number of experiments in group B
    analysis_type : str
        'diffbind' for ChIP/ATAC/DNase-seq or 'dmr' for Bisulfite-seq
    genome : str or None
        Genome assembly (hg38, mm10, dm6, ce11, sacCer3, etc.)

    Returns
    -------
    list of dict
        QC warnings, each with keys: severity, issue, details, recommendation
    """
    warnings = []

    if len(df) == 0:
        return warnings

    print("\n   Running QC checks...")

    warnings.extend(_check_sex_chromosome_confound(df))
    warnings.extend(_check_sex_chromosome_significant(df))
    warnings.extend(_check_nonstandard_contigs(df, genome=genome))
    warnings.extend(_check_small_regions(df))
    warnings.extend(_check_chrM_enrichment(df, analysis_type))
    warnings.extend(_check_genomic_clusters(df))
    warnings.extend(_check_ma_asymmetry(df))
    warnings.extend(_check_region_size_distribution(df, analysis_type))
    warnings.extend(_check_sample_size(n_samples_a, n_samples_b))

    # Deduplicate: if both all-regions and significant-regions warnings exist
    # for the same chromosome, keep only the more specific significant-regions version
    sig_warned_chroms = set()
    for w in warnings:
        if "significant regions" in w.get("issue", ""):
            chrom = w["issue"].split(" ")[0]
            sig_warned_chroms.add(chrom)

    if sig_warned_chroms:
        warnings = [
            w for w in warnings
            if not (
                "sex chromosome confound" in w.get("issue", "")
                and "significant regions" not in w.get("issue", "")
                and w["issue"].split(" ")[0] in sig_warned_chroms
            )
        ]

    if warnings:
        print(f"\n   ⚠️  {len(warnings)} QC warning(s) detected:")
        for w in warnings:
            icon = "🔴" if w["severity"] == "major" else "🟡"
            print(f"   {icon} [{w['severity'].upper()}] {w['issue']}")
            print(f"      {w['details']}")
            print(f"      → {w['recommendation']}")
    else:
        print("   ✓ No QC issues detected")

    return warnings


def _check_sex_chromosome_confound(df):
    """
    Detect probable sex chromosome artifacts.

    If chrY (or chrX) regions are overwhelmingly one-directional AND the
    depleted group has near-zero counts, this is likely a sex mismatch
    (e.g., male vs female cell lines), not genuine differential binding.
    """
    warnings = []

    for chrom in ["chrY", "chrX"]:
        chrom_df = df[df["chrom"] == chrom]
        if len(chrom_df) < 3:
            continue

        n_a = (chrom_df["direction"] == "A_enriched").sum()
        n_b = (chrom_df["direction"] == "B_enriched").sum()
        n_total = len(chrom_df)

        # Check if >80% one-directional
        dominant_frac = max(n_a, n_b) / n_total
        if dominant_frac < 0.8:
            continue

        # Check if the depleted group has near-zero counts
        if "mean_count_a" in chrom_df.columns and "mean_count_b" in chrom_df.columns:
            if n_a > n_b:
                depleted_col = "mean_count_b"
                enriched_group = "A"
            else:
                depleted_col = "mean_count_a"
                enriched_group = "B"

            depleted_mean = chrom_df[depleted_col].mean()
            enriched_col = "mean_count_a" if enriched_group == "A" else "mean_count_b"
            enriched_mean = chrom_df[enriched_col].mean()

            # Near-zero = depleted mean < 10% of enriched mean
            if enriched_mean > 0 and depleted_mean / enriched_mean < 0.1:
                n_sig = chrom_df["significant"].sum() if "significant" in chrom_df.columns else 0

                warnings.append({
                    "severity": "major",
                    "issue": f"{chrom} sex chromosome confound",
                    "details": (
                        f"{n_total} {chrom} regions are {dominant_frac:.0%} enriched in group "
                        f"{enriched_group} with near-zero counts in the other group "
                        f"(mean {depleted_mean:.1f} vs {enriched_mean:.1f}). "
                        f"{n_sig} of these are statistically significant. "
                        f"This pattern indicates a sex mismatch between groups "
                        f"(e.g., male vs female cell lines), not genuine differential binding."
                    ),
                    "recommendation": (
                        f"Exclude {chrom} regions from biological interpretation. "
                        f"Report {chrom} findings as probable sex-chromosome artifacts, not real differential peaks."
                    ),
                })

    return warnings


def _check_sex_chromosome_significant(df):
    """
    Detect sex chromosome artifacts among SIGNIFICANT regions specifically.

    Supplements _check_sex_chromosome_confound() which checks all regions.
    When most significant regions on chrY/chrX are one-directional with
    near-zero depleted-group counts, this indicates a sex mismatch even
    if the overall directionality (diluted by non-significant noise) is
    below the 80% threshold.
    """
    warnings = []

    if "significant" not in df.columns:
        return warnings

    for chrom in ["chrY", "chrX"]:
        sig_chrom = df[(df["chrom"] == chrom) & (df["significant"])]
        if len(sig_chrom) < 2:
            continue

        n_a = (sig_chrom["direction"] == "A_enriched").sum()
        n_b = (sig_chrom["direction"] == "B_enriched").sum()
        n_sig = len(sig_chrom)

        # 67% threshold (lower than 80% all-regions, appropriate for smaller N)
        dominant_frac = max(n_a, n_b) / n_sig
        if dominant_frac < 0.67:
            continue

        if "mean_count_a" not in sig_chrom.columns or "mean_count_b" not in sig_chrom.columns:
            continue

        if n_a > n_b:
            depleted_col, enriched_col = "mean_count_b", "mean_count_a"
            enriched_group = "A"
        else:
            depleted_col, enriched_col = "mean_count_a", "mean_count_b"
            enriched_group = "B"

        # Focus on the dominant-direction significant regions
        dominant_dir = "A_enriched" if n_a > n_b else "B_enriched"
        dominant_sig = sig_chrom[sig_chrom["direction"] == dominant_dir]

        depleted_mean = dominant_sig[depleted_col].mean()
        enriched_mean = dominant_sig[enriched_col].mean()

        # Near-zero = depleted mean < 10% of enriched mean
        if enriched_mean > 0 and depleted_mean / enriched_mean < 0.1:
            n_dominant = max(n_a, n_b)
            warnings.append({
                "severity": "major",
                "issue": f"{chrom} sex chromosome confound (significant regions)",
                "details": (
                    f"{n_dominant}/{n_sig} significant {chrom} regions are "
                    f"enriched in group {enriched_group} with near-zero counts "
                    f"in the other group (mean {depleted_mean:.1f} vs "
                    f"{enriched_mean:.1f}). These appear in the top results and "
                    f"are likely sex-chromosome artifacts, not genuine differential "
                    f"binding."
                ),
                "recommendation": (
                    f"Exclude significant {chrom} regions from biological "
                    f"interpretation. Consider filtering {chrom} regions entirely "
                    f"when comparing cell lines of different sex."
                ),
            })

    return warnings


def _check_nonstandard_contigs(df, genome=None):
    """Check for regions on non-standard contigs (random, unplaced, chrUn)."""
    warnings = []

    standard_chroms = get_standard_chroms(genome)
    nonstandard_mask = ~df["chrom"].isin(standard_chroms)
    n_nonstandard = nonstandard_mask.sum()

    if n_nonstandard == 0:
        return warnings

    n_sig_nonstandard = 0
    if "significant" in df.columns:
        n_sig_nonstandard = (nonstandard_mask & df["significant"]).sum()

    pct = n_nonstandard / len(df) * 100
    contigs = df.loc[nonstandard_mask, "chrom"].nunique()

    warnings.append({
        "severity": "minor",
        "issue": "Non-standard contigs present",
        "details": (
            f"{n_nonstandard} regions ({pct:.1f}%) are on {contigs} non-standard "
            f"contig(s) (random scaffolds, unplaced sequences, etc.). "
            f"{n_sig_nonstandard} of these are statistically significant. "
            f"Regions on non-standard contigs can represent mapping artifacts."
        ),
        "recommendation": (
            "Default QC filtering removes non-standard contigs. "
            "Unfiltered data is available in diff_regions_unfiltered.csv."
        ),
    })

    return warnings


def _check_small_regions(df):
    """Flag regions smaller than 10bp as biologically implausible."""
    warnings = []

    if "region_size" not in df.columns:
        return warnings

    small_mask = df["region_size"] < 10
    n_small = small_mask.sum()

    if n_small == 0:
        return warnings

    n_sig_small = 0
    if "significant" in df.columns:
        n_sig_small = (small_mask & df["significant"]).sum()

    min_size = int(df.loc[small_mask, "region_size"].min())

    warnings.append({
        "severity": "minor",
        "issue": "Implausibly small regions detected",
        "details": (
            f"{n_small} regions are < 10bp (smallest: {min_size}bp). "
            f"{n_sig_small} of these are statistically significant. "
            f"Regions this small are biologically implausible for transcription factor "
            f"binding sites (~20bp consensus motif) or histone marks (200bp+), "
            f"and likely represent edge artifacts in peak calling or differential analysis."
        ),
        "recommendation": (
            "Default QC filtering removes regions < 10bp. "
            "Unfiltered data is available in diff_regions_unfiltered.csv."
        ),
    })

    return warnings


def _check_chrM_enrichment(df, analysis_type="diffbind"):
    """
    Flag chrM regions as probable contamination in ChIP-seq/ATAC-seq.

    Mitochondrial DNA lacks histones and is not a target for most
    transcription factors. ChIP-seq signal on chrM typically reflects
    non-specific antibody binding to abundant mtDNA or library prep
    artifacts. For Bisulfite-seq (DMR), chrM methylation can be
    biologically meaningful, so this check is skipped.
    """
    warnings = []

    if analysis_type == "dmr":
        return warnings

    chrm_df = df[df["chrom"] == "chrM"]
    if len(chrm_df) < 3:
        return warnings

    n_sig_chrm = int(chrm_df["significant"].sum()) if "significant" in chrm_df.columns else 0
    n_sig_total = int(df["significant"].sum()) if "significant" in df.columns else 0

    if n_sig_chrm == 0:
        return warnings

    pct_of_sig = n_sig_chrm / n_sig_total * 100 if n_sig_total > 0 else 0
    severity = "major" if n_sig_chrm >= 5 or pct_of_sig >= 10 else "minor"

    dir_note = ""
    if "direction" in chrm_df.columns and "significant" in chrm_df.columns:
        sig_chrm = chrm_df[chrm_df["significant"]]
        n_a = int((sig_chrm["direction"] == "A_enriched").sum())
        n_b = int((sig_chrm["direction"] == "B_enriched").sum())
        dir_note = f" ({n_a} A-enriched, {n_b} B-enriched)"

    assay = "ChIP/ATAC/DNase-seq"

    warnings.append({
        "severity": severity,
        "issue": f"chrM enrichment ({n_sig_chrm} significant regions)",
        "details": (
            f"{n_sig_chrm} of {n_sig_total} significant regions ({pct_of_sig:.0f}%) "
            f"are on chrM{dir_note}. Mitochondrial DNA lacks histones and is not a "
            f"target for most transcription factors. {assay} signal on chrM typically "
            f"reflects non-specific antibody binding to abundant mtDNA or library "
            f"preparation artifacts, not genuine differential binding. "
            f"(Note: this is the pre-filter count; some chrM regions may be "
            f"removed by subsequent QC filtering of regions < 10bp.)"
        ),
        "recommendation": (
            "Exclude chrM regions from biological interpretation. Report chrM "
            "findings as probable contamination artifacts. Consider filtering "
            "chrM from the analysis entirely."
        ),
    })

    return warnings


def _check_genomic_clusters(df, min_regions=10, max_window=2_000_000):
    """
    Detect dense clusters of significant regions that may indicate
    copy number amplification or structural variants rather than
    genuine differential binding.

    A cluster is flagged when >= min_regions significant regions fall
    within a window of <= max_window bp on the same chromosome.
    """
    warnings = []

    if "significant" not in df.columns:
        return warnings

    sig_df = df[df["significant"]].copy()
    if len(sig_df) < min_regions:
        return warnings

    for chrom in sig_df["chrom"].unique():
        chrom_sig = sig_df[sig_df["chrom"] == chrom].sort_values("chromStart")
        if len(chrom_sig) < min_regions:
            continue

        # Sliding window: check if any window of max_window bp contains >= min_regions
        starts = chrom_sig["chromStart"].values
        ends = chrom_sig["chromEnd"].values

        best_count = 0
        best_start = 0
        best_end = 0

        # Two-pointer approach
        j = 0
        for i in range(len(starts)):
            while j < len(starts) and starts[j] - starts[i] <= max_window:
                j += 1
            count = j - i
            if count > best_count:
                best_count = count
                best_start = int(starts[i])
                best_end = int(ends[j - 1])

        if best_count < min_regions:
            continue

        window_size = best_end - best_start
        cluster_regions = chrom_sig[
            (chrom_sig["chromStart"] >= best_start)
            & (chrom_sig["chromStart"] <= best_start + max_window)
        ]

        # Check directionality
        n_a = int((cluster_regions["direction"] == "A_enriched").sum())
        n_b = int((cluster_regions["direction"] == "B_enriched").sum())
        dominant_dir = "A" if n_a >= n_b else "B"
        dominant_n = max(n_a, n_b)
        dominant_pct = dominant_n / best_count * 100

        # Check for zero-count pattern (strong CNV signal)
        zero_note = ""
        depleted_col = "mean_count_b" if dominant_dir == "A" else "mean_count_a"
        if depleted_col in cluster_regions.columns:
            depleted_mean = cluster_regions[depleted_col].mean()
            if depleted_mean < 1.0:
                zero_note = (
                    f" The depleted group has near-zero counts (mean {depleted_mean:.1f}), "
                    f"strengthening the case for a copy number difference."
                )

        # Store flagged region coordinates for aggregate impact accounting
        flagged_coords = list(zip(
            cluster_regions["chrom"].values,
            cluster_regions["chromStart"].values.astype(int),
            cluster_regions["chromEnd"].values.astype(int),
        ))

        warnings.append({
            "severity": "minor",
            "issue": f"{chrom} genomic cluster ({best_count} significant regions in {window_size / 1e6:.1f} Mb)",
            "details": (
                f"{best_count} significant regions cluster within "
                f"{chrom}:{best_start:,}-{best_end:,} ({window_size / 1e6:.1f} Mb). "
                f"{dominant_pct:.0f}% are enriched in group {dominant_dir} "
                f"({n_a} A-enriched, {n_b} B-enriched). "
                f"Dense clustering of one-directional regions can indicate a "
                f"copy number amplification or structural variant in one group "
                f"rather than genuine differential binding.{zero_note}"
            ),
            "recommendation": (
                f"Investigate {chrom}:{best_start:,}-{best_end:,} in a genome browser. "
                f"Check for known copy number variants in these cell lines. "
                f"Consider excluding this cluster from biological interpretation "
                f"if a CNV is confirmed."
            ),
            "flagged_regions": flagged_coords,
        })

    return warnings


def _check_ma_asymmetry(df):
    """
    Detect asymmetric distribution of significant hits on the MA plot.

    If one direction's significant hits cluster at substantially lower
    mean counts than the other direction, this suggests the signal may
    be driven by low-count noise or a normalization artifact rather than
    genuine differential binding.
    """
    warnings = []

    if "significant" not in df.columns:
        return warnings
    if "mean_count_a" not in df.columns or "mean_count_b" not in df.columns:
        return warnings

    sig_df = df[df["significant"]].copy()
    if len(sig_df) < 5:
        return warnings

    sig_a = sig_df[sig_df["direction"] == "A_enriched"]
    sig_b = sig_df[sig_df["direction"] == "B_enriched"]

    if len(sig_a) < 3 or len(sig_b) < 3:
        return warnings

    # Compute log2 mean count for each significant region
    def _log2_mean(row):
        mean_expr = (row["mean_count_a"] + row["mean_count_b"]) / 2
        return np.log2(max(mean_expr, 0.1))

    median_a = sig_a.apply(_log2_mean, axis=1).median()
    median_b = sig_b.apply(_log2_mean, axis=1).median()

    diff = abs(median_a - median_b)
    if diff < 1.0:
        return warnings

    # Identify which direction clusters at lower counts
    if median_a < median_b:
        low_group = "A"
        low_median = median_a
        high_median = median_b
        low_n = len(sig_a)
    else:
        low_group = "B"
        low_median = median_b
        high_median = median_a
        low_n = len(sig_b)

    warnings.append({
        "severity": "minor",
        "issue": f"MA plot asymmetry (group {low_group} significant hits at low counts)",
        "details": (
            f"Significant regions enriched in group {low_group} have a median "
            f"log2(mean count) of {low_median:.1f}, compared to {high_median:.1f} "
            f"for the other direction (difference: {diff:.1f} log2 units). "
            f"Group {low_group} has {low_n} significant hits clustering at low "
            f"mean counts. Per MA plot interpretation guidelines, asymmetric "
            f"significant hits at low counts in one direction may indicate a "
            f"normalization artifact or noise-driven signal rather than genuine "
            f"differential binding."
        ),
        "recommendation": (
            f"Examine the MA plot for visual confirmation. Consider whether "
            f"group {low_group}-enriched significant hits at low counts represent "
            f"genuine biology or noise. Low-count regions have less statistical "
            f"power and are more susceptible to technical artifacts. Focus "
            f"biological interpretation on higher-count significant regions."
        ),
    })

    return warnings


def _check_region_size_distribution(df, analysis_type="diffbind"):
    """
    Flag unusually small median region sizes for diffbind analyses.

    For ChIP-seq/ATAC-seq, typical peak sizes are 100-500bp (TF) or
    200bp+ (histone marks). A very small median suggests the differential
    analysis is fragmenting peaks into sub-regions.
    """
    warnings = []

    if analysis_type == "dmr":
        return warnings
    if "region_size" not in df.columns or "significant" not in df.columns:
        return warnings

    sig_df = df[df["significant"]]
    if len(sig_df) < 5:
        return warnings

    median_size = sig_df["region_size"].median()
    if median_size >= 100:
        return warnings

    warnings.append({
        "severity": "minor",
        "issue": f"Unusually small significant regions (median {median_size:.0f}bp)",
        "details": (
            f"The median size of significant differential regions is "
            f"{median_size:.0f}bp, which is smaller than typical transcription "
            f"factor binding sites (100-500bp) or histone marks (200bp+). "
            f"This may indicate the differential analysis is fragmenting "
            f"peaks into sub-regions, which can inflate the region count "
            f"and complicate interpretation."
        ),
        "recommendation": (
            "Examine representative regions in a genome browser to check "
            "whether adjacent small differential sub-regions fall within "
            "larger consensus peaks. Small sub-peaks may still be biologically "
            "meaningful but should be interpreted cautiously."
        ),
    })

    return warnings


def _check_sample_size(n_samples_a, n_samples_b):
    """Warn about limited statistical power with small sample sizes."""
    warnings = []

    min_n = min(n_samples_a, n_samples_b)

    if min_n <= 3:
        warnings.append({
            "severity": "major",
            "issue": f"Very low sample size (n={n_samples_a} vs n={n_samples_b})",
            "details": (
                f"Group A has {n_samples_a} and group B has {n_samples_b} experiments. "
                f"With n ≤ 3 per group, edgeR's dispersion estimates are unreliable — "
                f"FDR values should be treated as approximate rankings, not reliable "
                f"false discovery rates. Many moderate-effect regions may be missed "
                f"or falsely called significant."
            ),
            "recommendation": (
                "Interpret FDR values with caution. Focus on regions with large "
                "effect sizes (|logFC| > 2) and the most extreme q-values. "
                "Validate key findings with orthogonal methods or additional "
                "replicates before drawing biological conclusions."
            ),
        })
    elif min_n < 5:
        warnings.append({
            "severity": "minor",
            "issue": f"Low sample size (n={n_samples_a} vs n={n_samples_b})",
            "details": (
                f"Group A has {n_samples_a} and group B has {n_samples_b} experiments. "
                f"With n < 5 per group, edgeR's FDR estimates can be unstable, "
                f"particularly for regions with moderate effect sizes. "
                f"Statistical power is limited for detecting subtle differences."
            ),
            "recommendation": (
                "Interpret results with caution. Focus on regions with large effect "
                "sizes and highly significant q-values. Validate key findings with "
                "orthogonal methods or additional replicates."
            ),
        })

    return warnings

