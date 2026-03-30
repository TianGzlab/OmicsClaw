"""
Post-download filtering for ChIP-Atlas Target Genes results.

Filters target genes by binding score, cell type, STRING score, and more.
"""

import numpy as np
import pandas as pd


def filter_targets(
    target_genes_df,
    experiment_df=None,
    min_avg_score=0,
    cell_types=None,
    min_string_score=0,
    top_n=None,
    min_binding_rate=0,
):
    """
    Filter target genes by various criteria.

    Args:
        target_genes_df: Summary DataFrame (gene, avg_score, string_score, etc.)
        experiment_df: Wide-format per-experiment DataFrame (optional, needed for cell_type filter)
        min_avg_score: Minimum average MACS2 binding score (default: 0)
        cell_types: List of cell types to subset (recalculates average from those experiments only)
        min_string_score: Minimum STRING interaction score (default: 0)
        top_n: Keep only top N genes by average score (default: None = all)
        min_binding_rate: Minimum fraction of experiments with binding (0-1, default: 0)

    Returns:
        tuple: (filtered_target_genes_df, filtered_experiment_df or None)
    """
    initial_count = len(target_genes_df)
    df = target_genes_df.copy()
    exp_df = experiment_df.copy() if experiment_df is not None else None

    # Cell-type filtering (must come first — recalculates avg_score)
    if cell_types and exp_df is not None:
        df, exp_df = _filter_by_cell_type(df, exp_df, cell_types)

    # Score filters
    if min_avg_score > 0:
        df = df[df["avg_score"] >= min_avg_score]

    if min_string_score > 0:
        df = df[df["string_score"] >= min_string_score]

    if min_binding_rate > 0:
        df = df[df["binding_rate"] >= min_binding_rate]

    # Top N (applied last, after other filters)
    if top_n is not None and top_n > 0:
        df = df.head(top_n)

    # Sync experiment_df to match filtered genes
    if exp_df is not None:
        exp_df = exp_df[exp_df["gene"].isin(df["gene"])]

    df = df.reset_index(drop=True)
    if exp_df is not None:
        exp_df = exp_df.reset_index(drop=True)

    print(f"  ✓ Filtered: {initial_count} → {len(df)} target genes")
    return df, exp_df


def _filter_by_cell_type(target_genes_df, experiment_df, cell_types):
    """
    Filter to specific cell types and recalculate average scores.

    Args:
        target_genes_df: Summary DataFrame
        experiment_df: Wide-format experiment DataFrame
        cell_types: List of cell type names to keep (case-insensitive)

    Returns:
        tuple: (updated_target_genes_df, filtered_experiment_df)
    """
    cell_types_lower = [ct.lower() for ct in cell_types]

    # Find matching experiment columns
    matching_cols = ["gene"]  # Always keep gene column
    for col in experiment_df.columns:
        if col == "gene":
            continue
        parts = col.split("|", 1)
        if len(parts) == 2 and parts[1].lower() in cell_types_lower:
            matching_cols.append(col)

    n_matching = len(matching_cols) - 1  # Exclude 'gene'
    if n_matching == 0:
        print(f"  WARNING: No experiments found for cell types: {cell_types}")
        print(f"  Available cell types (sample): {_get_sample_cell_types(experiment_df)}")
        return target_genes_df, experiment_df

    print(f"  Cell-type filter: {n_matching} experiments match {cell_types}")

    # Subset experiment DataFrame
    exp_filtered = experiment_df[matching_cols].copy()

    # Recalculate summary statistics from filtered experiments
    exp_cols = [c for c in matching_cols if c != "gene"]
    exp_values = exp_filtered[exp_cols].apply(pd.to_numeric, errors="coerce").fillna(0)

    target_genes_df = target_genes_df.copy()
    target_genes_df["avg_score"] = exp_values.mean(axis=1).values
    target_genes_df["num_experiments"] = n_matching
    target_genes_df["num_bound"] = (exp_values > 0).sum(axis=1).values
    target_genes_df["binding_rate"] = target_genes_df["num_bound"] / max(n_matching, 1)
    target_genes_df["max_score"] = exp_values.max(axis=1).values

    # Re-sort by new average score
    target_genes_df = target_genes_df.sort_values("avg_score", ascending=False).reset_index(drop=True)

    return target_genes_df, exp_filtered


def detect_colocated_genes(target_genes_df, experiment_df):
    """
    Detect co-located genes that share identical binding scores across all experiments.

    Genes at the same genomic locus fall within the same TSS window and receive
    identical ChIP-seq signal, inflating the target gene count. This function
    identifies such groups without removing them.

    Args:
        target_genes_df: Summary DataFrame with 'gene' column
        experiment_df: Wide-format per-experiment DataFrame with 'gene' column

    Returns:
        tuple: (updated_target_genes_df with 'colocated_group' column,
                colocated_info dict with summary statistics)
    """
    df = target_genes_df.copy()

    if experiment_df is None or len(experiment_df) == 0:
        df["colocated_group"] = 0
        return df, {"n_groups": 0, "n_genes_affected": 0, "n_independent_loci": len(df), "groups": []}

    # Get experiment score columns (exclude 'gene')
    exp_cols = [c for c in experiment_df.columns if c != "gene"]
    if not exp_cols:
        df["colocated_group"] = 0
        return df, {"n_groups": 0, "n_genes_affected": 0, "n_independent_loci": len(df), "groups": []}

    # Build score matrix aligned to target_genes_df gene order
    exp_indexed = experiment_df.set_index("gene")
    exp_values = exp_indexed[exp_cols].apply(pd.to_numeric, errors="coerce").fillna(0)

    # Only consider genes present in both DataFrames
    common_genes = df["gene"][df["gene"].isin(exp_values.index)].tolist()
    score_matrix = exp_values.loc[common_genes]

    # Hash each gene's score vector for fast grouping
    # Convert each row to a tuple and group by identical tuples
    row_hashes = {}
    for gene in score_matrix.index:
        row_tuple = tuple(score_matrix.loc[gene].values)
        row_hashes.setdefault(row_tuple, []).append(gene)

    # Assign group IDs (only for groups with 2+ genes)
    gene_to_group = {}
    groups = []
    group_id = 1
    for row_tuple, genes in row_hashes.items():
        if len(genes) >= 2:
            for g in genes:
                gene_to_group[g] = group_id
            groups.append({"group_id": group_id, "genes": genes, "size": len(genes)})
            group_id += 1

    # Add colocated_group column (0 = unique gene, >0 = group ID)
    df["colocated_group"] = df["gene"].map(gene_to_group).fillna(0).astype(int)

    n_genes_affected = sum(g["size"] for g in groups)
    n_independent_loci = len(df) - n_genes_affected + len(groups)

    info = {
        "n_groups": len(groups),
        "n_genes_affected": n_genes_affected,
        "n_independent_loci": n_independent_loci,
        "groups": groups,
    }

    if groups:
        print(f"  Co-located genes: {n_genes_affected} genes in {len(groups)} groups "
              f"({n_independent_loci} independent loci)")
    else:
        print(f"  Co-located genes: none detected (all genes have unique score profiles)")

    return df, info


def _get_sample_cell_types(experiment_df, n=10):
    """Get a sample of available cell types from experiment columns."""
    cell_types = set()
    for col in experiment_df.columns:
        if col == "gene":
            continue
        parts = col.split("|", 1)
        if len(parts) == 2:
            cell_types.add(parts[1])
    return sorted(cell_types)[:n]

