"""
Parse differential region results from ChIP-Atlas Diff Analysis.

The main BED result file (wabi_result.bed) has 8 columns:
  chrom, chromStart, chromEnd, counts_A, counts_B, logFC, pvalue, qvalue

Where counts_A and counts_B are comma-separated normalized read counts
per experiment (e.g., "47.80,31.04,36.33").

The IGV BED file (wabi_result.igv.bed) is BED9+GFF3 for visualization,
with metadata URL-encoded in the name field and itemRgb colors:
  - Orange (222,131,68) = A-enriched (positive logFC)
  - Blue (106,153,208) = B-enriched (negative logFC)
"""

import numpy as np
import pandas as pd

# Column names for the main result BED (8 columns, no header)
RESULT_COLUMNS = [
    "chrom",
    "chromStart",
    "chromEnd",
    "counts_a",
    "counts_b",
    "logFC",
    "pvalue",
    "qvalue",
]


def parse_bed_results(bed_path):
    """
    Parse differential regions from the main BED result file.

    Parameters
    ----------
    bed_path : str
        Path to wabi_result.bed from ChIP-Atlas Diff Analysis

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        - chrom, chromStart, chromEnd: genomic coordinates
        - counts_a, counts_b: raw comma-separated count strings
        - logFC: log2 fold change (positive = A enriched)
        - pvalue: edgeR p-value
        - qvalue: BH-corrected q-value (FDR)
        - region_size: chromEnd - chromStart (bp)
        - direction: 'A_enriched' or 'B_enriched' (from logFC sign)
        - significant: qvalue < 0.05
        - mean_count_a, mean_count_b: mean normalized counts per group
        - score: -log10(qvalue) * 100, capped at 1000 (for BED compatibility)

    Raises
    ------
    RuntimeError
        If the BED file cannot be parsed
    """
    try:
        # Read tab-separated file, no header
        df = pd.read_csv(
            bed_path,
            sep="\t",
            header=None,
            comment="#",
            dtype=str,
        )

        # Skip browser/track lines if present
        mask = ~df.iloc[:, 0].str.startswith(("browser", "track"), na=False)
        df = df[mask].reset_index(drop=True)

        if df.empty:
            raise RuntimeError(f"BED file is empty: {bed_path}")

        n_cols = len(df.columns)

        if n_cols == 8:
            # Standard diff analysis output format
            df.columns = RESULT_COLUMNS
        elif n_cols == 9:
            # BED9 format (IGV bed) - handle differently
            df.columns = [
                "chrom", "chromStart", "chromEnd", "name", "score",
                "strand", "thickStart", "thickEnd", "itemRgb",
            ]
            # For IGV BED, try to extract logFC/pvalue from name field
            return _parse_igv_bed(df)
        else:
            # Unknown format - assign what we can
            cols = RESULT_COLUMNS[:min(n_cols, len(RESULT_COLUMNS))]
            if n_cols > len(RESULT_COLUMNS):
                cols += [f"extra_{i}" for i in range(n_cols - len(RESULT_COLUMNS))]
            df.columns = cols

        # Convert numeric columns
        df["chromStart"] = pd.to_numeric(df["chromStart"], errors="coerce")
        df["chromEnd"] = pd.to_numeric(df["chromEnd"], errors="coerce")
        df["logFC"] = pd.to_numeric(df["logFC"], errors="coerce")
        df["pvalue"] = pd.to_numeric(df["pvalue"], errors="coerce")
        df["qvalue"] = pd.to_numeric(df["qvalue"], errors="coerce")

        # Derived columns
        df["region_size"] = df["chromEnd"] - df["chromStart"]
        df["direction"] = np.where(df["logFC"] > 0, "A_enriched", "B_enriched")
        df["significant"] = df["qvalue"] < 0.05

        # Mean counts per group
        df["mean_count_a"] = df["counts_a"].apply(_mean_counts)
        df["mean_count_b"] = df["counts_b"].apply(_mean_counts)

        # BED-compatible score: -log10(qvalue) * 100, capped at 1000
        df["score"] = np.minimum(
            -np.log10(df["qvalue"].clip(lower=1e-300)) * 100,
            1000
        ).fillna(0).astype(int)

        # Sort by significance (lowest qvalue first, largest effect for ties)
        df["_abs_logFC"] = df["logFC"].abs()
        df = df.sort_values(
            ["qvalue", "_abs_logFC", "chrom", "chromStart"],
            ascending=[True, False, True, True],
        ).reset_index(drop=True)
        df = df.drop(columns=["_abs_logFC"])

        return df

    except pd.errors.ParserError as e:
        raise RuntimeError(f"Failed to parse BED file: {e}")


def _parse_igv_bed(df):
    """Parse IGV BED9+GFF3 format as fallback."""
    df["chromStart"] = pd.to_numeric(df["chromStart"], errors="coerce")
    df["chromEnd"] = pd.to_numeric(df["chromEnd"], errors="coerce")
    df["region_size"] = df["chromEnd"] - df["chromStart"]

    # Parse direction from itemRgb
    if "itemRgb" in df.columns:
        df["direction"] = df["itemRgb"].apply(_parse_direction_from_rgb)
    else:
        df["direction"] = "unknown"

    # Try to extract logFC and qvalue from the URL-encoded name field
    df["logFC"] = df["name"].apply(
        lambda x: _extract_from_name(x, "LogFC")
    )
    df["pvalue"] = df["name"].apply(
        lambda x: _extract_from_name(x, "P-value")
    )
    df["qvalue"] = df["name"].apply(
        lambda x: _extract_from_name(x, "Q-value")
    )

    df["significant"] = df["qvalue"] < 0.05
    df["score"] = pd.to_numeric(df.get("score", 0), errors="coerce").fillna(0)

    return df


def _extract_from_name(name_str, key):
    """Extract a value from URL-encoded GFF3 name field."""
    try:
        from urllib.parse import unquote
        decoded = unquote(str(name_str))
        for part in decoded.split(";"):
            if part.startswith(key + "="):
                return float(part.split("=", 1)[1])
    except (ValueError, IndexError):
        pass
    return np.nan


def _parse_direction_from_rgb(item_rgb):
    """Parse direction from itemRgb color string."""
    try:
        parts = str(item_rgb).split(",")
        if len(parts) < 3:
            return "unknown"
        r, b = int(parts[0]), int(parts[2])
        if r > b:
            return "A_enriched"
        elif b > r:
            return "B_enriched"
        else:
            return "unchanged"
    except (ValueError, IndexError):
        return "unknown"


def _mean_counts(counts_str):
    """Compute mean from comma-separated count string."""
    try:
        values = [float(x) for x in str(counts_str).split(",")]
        return sum(values) / len(values) if values else 0.0
    except (ValueError, TypeError):
        return 0.0


def summarize_regions(df):
    """
    Print a summary of parsed differential regions.

    Parameters
    ----------
    df : pd.DataFrame
        Parsed DataFrame from parse_bed_results()
    """
    n_total = len(df)
    n_a = (df["direction"] == "A_enriched").sum()
    n_b = (df["direction"] == "B_enriched").sum()
    n_sig = df["significant"].sum() if "significant" in df.columns else 0

    print(f"\n   Differential regions summary:")
    print(f"   Total regions: {n_total}")
    print(f"   Enriched in A: {n_a}")
    print(f"   Enriched in B: {n_b}")
    print(f"   Significant (FDR < 0.05): {n_sig}")

    if n_sig > 0 and "direction" in df.columns:
        sig_df = df[df["significant"]]
        n_sig_a = int((sig_df["direction"] == "A_enriched").sum())
        n_sig_b = int((sig_df["direction"] == "B_enriched").sum())
        print(f"   Significant enriched in A: {n_sig_a}")
        print(f"   Significant enriched in B: {n_sig_b}")

    if "region_size" in df.columns and n_total > 0:
        print(f"   Median region size: {df['region_size'].median():.0f} bp")

    if "logFC" in df.columns and n_total > 0:
        print(f"   LogFC range: {df['logFC'].min():.2f} to {df['logFC'].max():.2f}")

    if "qvalue" in df.columns and n_total > 0:
        print(f"   Min Q-value: {df['qvalue'].min():.2e}")

    if n_total > 0:
        top_chroms = df["chrom"].value_counts().head(5)
        print(f"   Top chromosomes: {', '.join(f'{c}({n})' for c, n in top_chroms.items())}")

