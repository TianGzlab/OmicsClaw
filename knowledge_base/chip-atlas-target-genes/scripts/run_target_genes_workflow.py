"""
Orchestrator for ChIP-Atlas Target Genes workflow.

Coordinates the full 4-step pipeline: validate → download → filter → return results.
"""

from scripts.download_target_genes import (
    check_antigen_available,
    download_target_genes,
    get_cell_types,
)
from scripts.filter_targets import detect_colocated_genes, filter_targets


def run_target_genes_workflow(
    protein,
    genome="hg38",
    distance=5,
    min_score=0,
    top_n=500,
    cell_types=None,
    min_string_score=0,
    min_binding_rate=0,
    output_dir="target_genes_results",
):
    """
    Run the complete target genes analysis workflow.

    Args:
        protein: Protein/TF name (case-sensitive, e.g., "TP53")
        genome: Genome assembly (default: "hg38")
        distance: Distance from TSS in kb (1, 5, or 10; default: 5)
        min_score: Minimum average binding score filter (default: 0)
        top_n: Keep top N genes by average score (default: 500)
        cell_types: List of cell types to filter to (default: None = all)
        min_string_score: Minimum STRING interaction score (default: 0)
        min_binding_rate: Minimum binding rate across experiments (0-1, default: 0)
        output_dir: Output directory for results (default: "target_genes_results")

    Returns:
        dict: Results dictionary with keys:
            - target_genes: pd.DataFrame (gene-level summary)
            - experiment_data: pd.DataFrame (wide-format per-experiment scores)
            - cell_types: list (unique cell types found)
            - protein: str
            - parameters: dict
            - metadata: dict
    """
    print(f"\n{'='*60}")
    print(f"ChIP-Atlas Target Genes Analysis")
    print(f"{'='*60}")
    print(f"  Protein: {protein}")
    print(f"  Genome: {genome}")
    print(f"  Distance: ±{distance}kb from TSS")
    print()

    # Step 1: Validate antigen availability
    print("Step 1: Validating antigen availability...")
    if not check_antigen_available(protein, genome, distance):
        raise ValueError(
            f"No target gene data available for '{protein}' ({genome}, ±{distance}kb). "
            f"Check spelling (case-sensitive) and that this is a non-histone antigen."
        )
    print(f"  ✓ Antigen '{protein}' data confirmed available")
    print()

    # Step 2: Download and parse target genes
    print("Step 2: Downloading target genes data...")
    summary_df, experiment_df = download_target_genes(protein, genome, distance)
    all_cell_types = get_cell_types(experiment_df)
    total_genes = len(summary_df)
    total_experiments = len(experiment_df.columns) - 1  # Exclude 'gene' column
    print()

    # Step 3: Apply filters
    print("Step 3: Applying filters...")
    has_filters = (
        min_score > 0
        or cell_types is not None
        or min_string_score > 0
        or min_binding_rate > 0
        or top_n is not None
    )

    if has_filters:
        summary_df, experiment_df = filter_targets(
            summary_df,
            experiment_df,
            min_avg_score=min_score,
            cell_types=cell_types,
            min_string_score=min_string_score,
            top_n=top_n,
            min_binding_rate=min_binding_rate,
        )
    else:
        print("  No filters applied (showing all genes)")

    # Detect co-located genes (identical score vectors = same genomic locus)
    summary_df, colocated_info = detect_colocated_genes(summary_df, experiment_df)
    print()

    # Build results dictionary
    parameters = {
        "protein": protein,
        "genome": genome,
        "distance_kb": distance,
        "min_score": min_score,
        "top_n": top_n,
        "cell_types": cell_types,
        "min_string_score": min_string_score,
        "min_binding_rate": min_binding_rate,
        "output_dir": output_dir,
    }

    metadata = {
        "total_genes_before_filter": total_genes,
        "total_genes_after_filter": len(summary_df),
        "total_experiments": total_experiments,
        "genome": genome,
        "distance_kb": distance,
        "unique_cell_types": len(all_cell_types),
        "colocated_info": colocated_info,
    }

    results = {
        "target_genes": summary_df,
        "experiment_data": experiment_df,
        "cell_types": all_cell_types,
        "protein": protein,
        "parameters": parameters,
        "metadata": metadata,
    }

    print(f"{'='*60}")
    print(f"  ✓ Target genes analysis completed successfully!")
    print(f"    {metadata['total_genes_after_filter']} target genes")
    print(f"    {metadata['total_experiments']} experiments")
    print(f"    {metadata['unique_cell_types']} cell types")
    print(f"{'='*60}")

    return results

