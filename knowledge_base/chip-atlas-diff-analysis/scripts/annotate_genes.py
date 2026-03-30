"""
Annotate differential regions with nearest/overlapping genes via UCSC REST API.

Uses the UCSC Genome Browser REST API to find genes overlapping or near
each genomic region. Requires internet (same as ChIP-Atlas API dependency).

Graceful fallback: if UCSC API is unavailable, returns empty annotations
without raising errors.
"""

import pandas as pd
import requests

UCSC_API_URL = "https://api.genome.ucsc.edu/getData/track"
FLANK_BP = 5000


def annotate_nearest_genes(df, genome="hg38", max_regions=50):
    """
    Annotate regions with overlapping/nearest gene symbols via UCSC API.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with chrom, chromStart, chromEnd columns.
        Should be pre-sorted by significance (top regions first).
    genome : str
        UCSC genome assembly (hg38, mm10, etc.)
    max_regions : int
        Maximum number of regions to annotate (default: 50).

    Returns
    -------
    pd.Series
        Gene annotations indexed to match df. Each entry is a string
        like "SBF2" (overlapping) or "SBF2 (+2.1kb)" (nearest within flank).
        Empty string for unannotated regions.
    """
    annotations = pd.Series("", index=df.index)

    regions_to_query = df.head(max_regions)
    if len(regions_to_query) == 0:
        return annotations

    print(f"   Annotating top {len(regions_to_query)} regions with nearest genes (UCSC API)...")

    n_annotated = 0
    n_failed = 0

    for idx, row in regions_to_query.iterrows():
        try:
            gene_str = _query_genes_for_region(
                row["chrom"],
                int(row["chromStart"]),
                int(row["chromEnd"]),
                genome=genome,
            )
            if gene_str:
                annotations.at[idx] = gene_str
                n_annotated += 1
        except Exception:
            n_failed += 1
            if n_failed >= 3:
                print(f"   Warning: UCSC API unavailable ({n_failed} failures). "
                      f"Skipping remaining gene annotations.")
                break

    print(f"   Annotated {n_annotated}/{len(regions_to_query)} regions with gene symbols")
    return annotations


def _query_genes_for_region(chrom, start, end, genome="hg38"):
    """
    Query UCSC REST API for genes overlapping or near a region.

    Returns
    -------
    str
        Gene symbol(s) or empty string.
        Direct overlap: "GENE1, GENE2"
        Nearest within flank: "GENE1 (+2.1kb)"
    """
    # First: check for direct overlap
    genes = _fetch_gene_symbols(chrom, start, end, genome)
    if genes:
        return ", ".join(sorted(genes))

    # Second: expand window and find nearest
    expanded_start = max(0, start - FLANK_BP)
    expanded_end = end + FLANK_BP
    records = _fetch_gene_records(chrom, expanded_start, expanded_end, genome)

    if not records:
        return ""

    # Find the closest gene by distance to region midpoint
    region_mid = (start + end) / 2
    best_gene = None
    best_dist = float("inf")

    for rec in records:
        tx_start = rec.get("txStart", 0)
        tx_end = rec.get("txEnd", 0)
        gene_mid = (tx_start + tx_end) / 2
        dist = abs(region_mid - gene_mid)
        name2 = rec.get("name2", "")
        if name2 and dist < best_dist:
            best_dist = dist
            best_gene = name2

    if best_gene and best_dist > 0:
        dist_kb = best_dist / 1000
        return f"{best_gene} ({dist_kb:+.1f}kb)"
    elif best_gene:
        return best_gene

    return ""


def _fetch_gene_symbols(chrom, start, end, genome):
    """Fetch unique gene symbols overlapping a region."""
    records = _fetch_gene_records(chrom, start, end, genome)
    symbols = set()
    for rec in records:
        name2 = rec.get("name2", "")
        if name2:
            symbols.add(name2)
    return symbols


def _fetch_gene_records(chrom, start, end, genome):
    """Fetch raw gene records from UCSC REST API."""
    url = (
        f"{UCSC_API_URL}?genome={genome};track=ncbiRefSeq;"
        f"chrom={chrom};start={int(start)};end={int(end)}"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("ncbiRefSeq", [])
    except (requests.RequestException, ValueError, KeyError):
        return []

