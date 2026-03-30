"""
Filter ChIP-Atlas enrichment results after API retrieval.

Provides client-side post-filtering since the API's antigenClass and
cellClass parameters are broad categories. This module enables fine-grained
filtering by specific antigens, cell types, significance thresholds, etc.
"""

import pandas as pd


def filter_experiments(
    results_df,
    antigen_filter=None,
    cell_type_filter=None,
    min_fold_enrichment=1.0,
    max_qvalue=None,
    max_pvalue=None,
    min_overlap=0,
):
    """
    Filter enrichment results DataFrame.

    Parameters:
    -----------
    results_df : pd.DataFrame
        Enrichment results from parse_api_results()
    antigen_filter : list of str or None
        Specific antigens to keep (None = all)
    cell_type_filter : list of str or None
        Specific cell types to keep (None = all)
    min_fold_enrichment : float
        Minimum fold enrichment (default: 1.0, no filter)
    max_qvalue : float or None
        Maximum Q-value threshold (e.g., 0.05)
    max_pvalue : float or None
        Maximum P-value threshold (e.g., 0.05)
    min_overlap : int
        Minimum number of overlapping regions (default: 0)

    Returns:
    --------
    pd.DataFrame: Filtered results
    """

    df = results_df.copy()
    initial_count = len(df)

    # Filter by specific antigens
    if antigen_filter is not None and len(antigen_filter) > 0:
        mask = df["antigen"].str.lower().isin([a.lower() for a in antigen_filter])
        df = df[mask]
        print(f"   After antigen filter ({antigen_filter}): {len(df)} experiments")

    # Filter by specific cell types
    if cell_type_filter is not None and len(cell_type_filter) > 0:
        mask = df["cell_type"].str.lower().isin([c.lower() for c in cell_type_filter])
        df = df[mask]
        print(f"   After cell type filter ({cell_type_filter}): {len(df)} experiments")

    # Filter by fold enrichment
    if min_fold_enrichment > 1.0:
        df = df[df["fold_enrichment"] >= min_fold_enrichment]
        print(f"   After fold enrichment >= {min_fold_enrichment}: {len(df)} experiments")

    # Filter by Q-value
    if max_qvalue is not None and "q_value" in df.columns:
        df = df[df["q_value"] <= max_qvalue]
        print(f"   After Q-value <= {max_qvalue}: {len(df)} experiments")

    # Filter by P-value
    if max_pvalue is not None:
        df = df[df["p_value"] <= max_pvalue]
        print(f"   After P-value <= {max_pvalue}: {len(df)} experiments")

    # Filter by minimum overlap count
    if min_overlap > 0:
        df = df[df["regions_with_overlaps"] >= min_overlap]
        print(f"   After overlap >= {min_overlap}: {len(df)} experiments")

    if len(df) < initial_count:
        print(f"   Filtered: {initial_count} -> {len(df)} experiments")

    return df.reset_index(drop=True)


if __name__ == "__main__":
    # Test with mock data
    mock_df = pd.DataFrame(
        {
            "experiment_id": [f"SRX{i:06d}" for i in range(20)],
            "antigen": ["TP53"] * 5 + ["MYC"] * 5 + ["H3K27ac"] * 5 + ["CTCF"] * 5,
            "cell_type": ["HeLa", "K562"] * 10,
            "fold_enrichment": list(range(20, 0, -1)),
            "p_value": [0.001] * 10 + [0.1] * 10,
            "q_value": [0.005] * 10 + [0.2] * 10,
            "significant": [True] * 10 + [False] * 10,
            "overlap_rate": [0.5] * 20,
            "regions_with_overlaps": [3] * 10 + [1] * 10,
            "total_regions": [5] * 20,
            "total_peaks": [1000] * 20,
        }
    )

    print("Testing filter_experiments...")
    print(f"Starting with {len(mock_df)} experiments\n")

    filtered = filter_experiments(
        mock_df,
        antigen_filter=["TP53", "MYC"],
        min_fold_enrichment=5.0,
        max_qvalue=0.05,
    )

    print(f"\nFiltered to {len(filtered)} experiments")
    print(filtered[["experiment_id", "antigen", "cell_type", "fold_enrichment", "q_value"]].head())

