"""
Download and parse ChIP-Atlas Target Genes pre-computed TSV data.

Core script for the chip-atlas-target-genes skill.
Downloads wide-format TSV from ChIP-Atlas and parses into summary + experiment DataFrames.
"""

import io
import re

import pandas as pd
import requests

# ChIP-Atlas data server base URL
BASE_URL = "https://chip-atlas.dbcls.jp/data"

# Valid genomes
VALID_GENOMES = ["hg38", "hg19", "mm10", "mm9", "rn6", "dm6", "dm3", "ce11", "ce10", "sacCer3"]

# Valid distance values (kb from TSS)
VALID_DISTANCES = [1, 5, 10]


def _build_url(protein, genome, distance):
    """Build the download URL for target genes TSV."""
    return f"{BASE_URL}/{genome}/target/{protein}.{distance}.tsv"


def check_antigen_available(protein, genome="hg38", distance=5):
    """
    Check if target gene data exists for a given protein/antigen.

    Args:
        protein: Protein/TF name (case-sensitive, e.g., "TP53")
        genome: Genome assembly (default: "hg38")
        distance: Distance from TSS in kb (1, 5, or 10)

    Returns:
        bool: True if data is available, False otherwise
    """
    if genome not in VALID_GENOMES:
        print(f"  ERROR: Invalid genome '{genome}'. Valid: {', '.join(VALID_GENOMES)}")
        return False

    if distance not in VALID_DISTANCES:
        print(f"  ERROR: Invalid distance {distance}. Valid: {VALID_DISTANCES}")
        return False

    url = _build_url(protein, genome, distance)

    try:
        resp = requests.head(url, timeout=15, allow_redirects=True)
        if resp.status_code == 200:
            return True
        elif resp.status_code == 404:
            # Provide helpful suggestions
            print(f"  WARNING: No target gene data for '{protein}' ({genome}, ±{distance}kb)")
            print(f"  - Protein names are case-sensitive (e.g., 'TP53' not 'tp53')")
            print(f"  - Histone marks (H3K4me3, etc.) are NOT available in Target Genes")
            print(f"  - Check https://chip-atlas.org/target_genes for available antigens")
            return False
        else:
            print(f"  WARNING: Unexpected HTTP {resp.status_code} for {url}")
            return False
    except requests.RequestException as e:
        print(f"  ERROR: Network error checking antigen availability: {e}")
        return False


def download_target_genes(protein, genome="hg38", distance=5):
    """
    Download and parse ChIP-Atlas target genes TSV data.

    Args:
        protein: Protein/TF name (case-sensitive, e.g., "TP53")
        genome: Genome assembly (default: "hg38")
        distance: Distance from TSS in kb (1, 5, or 10)

    Returns:
        tuple: (summary_df, experiment_df)
            - summary_df: Gene-level summary (gene, avg_score, string_score, etc.)
            - experiment_df: Full wide-format per-experiment scores
    """
    url = _build_url(protein, genome, distance)
    print(f"  Downloading target genes from: {url}")

    # Stream download for large files
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()

    # Read content (stream into memory, then parse)
    content = resp.content.decode("utf-8")
    print(f"  Downloaded {len(content) / 1024 / 1024:.1f} MB")

    # Parse TSV
    df = pd.read_csv(io.StringIO(content), sep="\t")

    if df.empty:
        raise ValueError(f"No target gene data returned for {protein} ({genome}, ±{distance}kb)")

    # Parse into summary and experiment DataFrames
    summary_df, experiment_df = parse_target_genes_tsv(df, protein)

    print(f"  ✓ Downloaded target genes: {len(summary_df)} genes, {len(experiment_df.columns) - 1} experiments")
    return summary_df, experiment_df


def parse_target_genes_tsv(df, protein):
    """
    Parse raw wide-format TSV into summary and experiment DataFrames.

    Args:
        df: Raw DataFrame from TSV download
        protein: Protein name (for identifying the Average column)

    Returns:
        tuple: (summary_df, experiment_df)
    """
    # Identify columns
    gene_col = "Target_genes"
    avg_col = f"{protein}|Average"
    string_col = "STRING"

    # Verify expected columns exist
    if gene_col not in df.columns:
        raise ValueError(f"Expected column '{gene_col}' not found. Columns: {list(df.columns[:5])}")

    # Find the Average column (case-insensitive fallback)
    if avg_col not in df.columns:
        avg_candidates = [c for c in df.columns if c.lower().endswith("|average")]
        if avg_candidates:
            avg_col = avg_candidates[0]
            print(f"  Using average column: {avg_col}")
        else:
            raise ValueError(f"No Average column found. Expected '{avg_col}'. Columns: {list(df.columns[:5])}")

    # Identify experiment columns (SRX/ERX/DRX pattern)
    experiment_cols = [
        c for c in df.columns
        if re.match(r"^[SED]RX\d+\|", c) and c != avg_col
    ]

    # Check for STRING column
    has_string = string_col in df.columns

    # Build experiment DataFrame (gene + per-experiment scores)
    experiment_df = df[[gene_col] + experiment_cols].copy()
    experiment_df = experiment_df.rename(columns={gene_col: "gene"})

    # Build summary DataFrame
    summary_data = {
        "gene": df[gene_col],
        "avg_score": pd.to_numeric(df[avg_col], errors="coerce").fillna(0),
        "string_score": pd.to_numeric(df[string_col], errors="coerce").fillna(0) if has_string else 0,
        "num_experiments": len(experiment_cols),
    }

    # Calculate per-gene binding statistics from experiment columns
    experiment_values = df[experiment_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    summary_data["num_bound"] = (experiment_values > 0).sum(axis=1).values
    summary_data["binding_rate"] = (
        summary_data["num_bound"] / max(len(experiment_cols), 1)
    )
    summary_data["max_score"] = experiment_values.max(axis=1).values

    summary_df = pd.DataFrame(summary_data)

    # Sort by average score descending (should already be sorted, but ensure)
    summary_df = summary_df.sort_values("avg_score", ascending=False).reset_index(drop=True)

    # Extract cell types from experiment column headers
    cell_types = []
    for col in experiment_cols:
        parts = col.split("|", 1)
        if len(parts) == 2:
            cell_types.append(parts[1])
    unique_cell_types = sorted(set(cell_types))

    print(f"  Parsed: {len(summary_df)} genes, {len(experiment_cols)} experiments, {len(unique_cell_types)} cell types")
    return summary_df, experiment_df


def get_cell_types(experiment_df):
    """
    Extract unique cell types from experiment DataFrame column headers.

    Args:
        experiment_df: Wide-format DataFrame with {SRX_ID}|{CellType} columns

    Returns:
        list: Sorted unique cell type names
    """
    cell_types = set()
    for col in experiment_df.columns:
        if col == "gene":
            continue
        parts = col.split("|", 1)
        if len(parts) == 2:
            cell_types.add(parts[1])
    return sorted(cell_types)

