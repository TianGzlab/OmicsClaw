"""
Filter ChIP-Atlas differential regions after retrieval.

Provides client-side post-filtering of differential peak/methylation
regions by statistical significance, effect size, region size, direction,
and chromosome.
"""

import pandas as pd

# Genome-specific standard chromosomes for all supported organisms
GENOME_STANDARD_CHROMS = {
    # Human
    "hg38": {f"chr{c}" for c in list(range(1, 23)) + ["X", "Y", "M"]},
    "hg19": {f"chr{c}" for c in list(range(1, 23)) + ["X", "Y", "M"]},
    # Mouse
    "mm10": {f"chr{c}" for c in list(range(1, 20)) + ["X", "Y", "M"]},
    "mm9": {f"chr{c}" for c in list(range(1, 20)) + ["X", "Y", "M"]},
    # Rat
    "rn6": {f"chr{c}" for c in list(range(1, 21)) + ["X", "Y", "M"]},
    # Drosophila
    "dm6": {"chr2L", "chr2R", "chr3L", "chr3R", "chr4", "chrX", "chrY", "chrM"},
    "dm3": {"chr2L", "chr2R", "chr3L", "chr3R", "chr4", "chrX", "chrY", "chrM"},
    # C. elegans
    "ce11": {"chrI", "chrII", "chrIII", "chrIV", "chrV", "chrX", "chrM"},
    "ce10": {"chrI", "chrII", "chrIII", "chrIV", "chrV", "chrX", "chrM"},
    # Yeast
    "sacCer3": {f"chr{r}" for r in [
        "I", "II", "III", "IV", "V", "VI", "VII", "VIII",
        "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "M",
    ]},
}

# Default fallback (human)
STANDARD_CHROMS = GENOME_STANDARD_CHROMS["hg38"]


def get_standard_chroms(genome=None):
    """Get standard chromosome set for a genome. Falls back to human (hg38)."""
    if genome and genome in GENOME_STANDARD_CHROMS:
        return GENOME_STANDARD_CHROMS[genome]
    return STANDARD_CHROMS


def filter_standard_chromosomes(df, genome=None):
    """
    Filter to standard chromosomes for the given genome.

    Removes non-standard contigs (random scaffolds, unplaced sequences)
    that can represent mapping artifacts.

    Parameters
    ----------
    df : pd.DataFrame
        Parsed DataFrame from parse_bed_results()
    genome : str or None
        Genome assembly (hg38, mm10, dm6, ce11, sacCer3, etc.).
        Uses human (hg38) chromosomes if None.

    Returns
    -------
    pd.DataFrame
        Filtered to standard chromosomes only
    """
    standard = get_standard_chroms(genome)
    before = len(df)
    filtered = df[df["chrom"].isin(standard)].copy()
    removed = before - len(filtered)
    if removed > 0:
        print(f"   Removed {removed} regions on non-standard contigs")
    return filtered.reset_index(drop=True)


def filter_min_region_size(df, min_size=10):
    """
    Remove regions smaller than a minimum size.

    Regions < 10bp are biologically implausible for TF binding sites
    (~20bp motif) or histone marks (200bp+) and likely represent
    edge artifacts in peak calling.

    Parameters
    ----------
    df : pd.DataFrame
        Parsed DataFrame from parse_bed_results()
    min_size : int
        Minimum region size in bp (default: 10)

    Returns
    -------
    pd.DataFrame
        Filtered to regions >= min_size bp
    """
    if "region_size" not in df.columns:
        return df

    before = len(df)
    filtered = df[df["region_size"] >= min_size].copy()
    removed = before - len(filtered)
    if removed > 0:
        print(f"   Removed {removed} regions < {min_size}bp")
    return filtered.reset_index(drop=True)


def filter_regions(
    regions_df,
    max_qvalue=None,
    min_logfc=None,
    min_score=0,
    min_region_size=0,
    max_region_size=None,
    direction_filter=None,
    chromosomes=None,
):
    """
    Filter differential regions DataFrame.

    Parameters
    ----------
    regions_df : pd.DataFrame
        Parsed DataFrame from parse_bed_results()
    max_qvalue : float or None
        Maximum Q-value (FDR) threshold (e.g., 0.05). None = no filter.
    min_logfc : float or None
        Minimum absolute logFC threshold (e.g., 1.0). None = no filter.
    min_score : int
        Minimum BED score (0-1000, default: 0)
    min_region_size : int
        Minimum region size in bp (default: 0)
    max_region_size : int or None
        Maximum region size in bp (None = no limit)
    direction_filter : str or None
        Keep only 'A_enriched' or 'B_enriched' (None = all)
    chromosomes : list of str or None
        Specific chromosomes to keep (e.g., ['chr1', 'chr2']). None = all.

    Returns
    -------
    pd.DataFrame
        Filtered regions
    """
    df = regions_df.copy()
    initial_count = len(df)

    if max_qvalue is not None and "qvalue" in df.columns:
        df = df[df["qvalue"] < max_qvalue]
        print(f"   After FDR < {max_qvalue}: {len(df)} regions")

    if min_logfc is not None and "logFC" in df.columns:
        df = df[df["logFC"].abs() >= min_logfc]
        print(f"   After |logFC| >= {min_logfc}: {len(df)} regions")

    if min_score > 0 and "score" in df.columns:
        df = df[df["score"] >= min_score]
        print(f"   After score >= {min_score}: {len(df)} regions")

    if min_region_size > 0 and "region_size" in df.columns:
        df = df[df["region_size"] >= min_region_size]
        print(f"   After region size >= {min_region_size}bp: {len(df)} regions")

    if max_region_size is not None and "region_size" in df.columns:
        df = df[df["region_size"] <= max_region_size]
        print(f"   After region size <= {max_region_size}bp: {len(df)} regions")

    if direction_filter is not None and "direction" in df.columns:
        df = df[df["direction"] == direction_filter]
        print(f"   After direction = '{direction_filter}': {len(df)} regions")

    if chromosomes is not None and len(chromosomes) > 0:
        df = df[df["chrom"].isin(chromosomes)]
        print(f"   After chromosome filter ({chromosomes}): {len(df)} regions")

    if len(df) < initial_count:
        print(f"   Filtered: {initial_count} -> {len(df)} regions")

    return df.reset_index(drop=True)

