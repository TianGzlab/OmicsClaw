"""
Pseudobulk Differential Expression Analysis

This module implements pseudobulk aggregation and differential expression analysis
for single-cell RNA-seq data using DESeq2.

For methodology and best practices, see references/pseudobulk_de_guide.md

Functions:
  - aggregate_to_pseudobulk(): Aggregate counts per sample × cell type
  - run_deseq2_analysis(): Run DESeq2 on pseudobulk data
  - export_de_results(): Export DE results to CSV
  - plot_volcano(): Create volcano plots
  - plot_ma(): Create MA plots
"""

import scanpy as sc
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
import warnings


def aggregate_to_pseudobulk(
    adata: sc.AnnData,
    sample_key: str,
    celltype_key: str,
    min_cells: int = 10,
    min_counts: int = 1,
    layer: Optional[str] = None
) -> Dict[str, pd.DataFrame]:
    """
    Aggregate single-cell counts to pseudobulk (sum per sample × cell type).

    CRITICAL: Use raw counts, not normalized. Use sum aggregation, not mean.

    Parameters
    ----------
    adata : AnnData
        AnnData object with raw counts
    sample_key : str
        Column in adata.obs with sample IDs
    celltype_key : str
        Column in adata.obs with cell type labels
    min_cells : int, optional
        Minimum cells per sample-celltype combination (default: 10)
    min_counts : int, optional
        Minimum total counts per sample-celltype (default: 1)
    layer : str, optional
        Layer to aggregate (default: None uses .X)

    Returns
    -------
    dict
        Dictionary with keys:
        - 'counts': DataFrame of aggregated counts (genes × samples)
        - 'metadata': DataFrame of sample metadata
        - 'n_cells': DataFrame of cell counts per sample-celltype

    Notes
    -----
    Filters out sample-celltype combinations with <min_cells cells.
    """
    print(f"Aggregating to pseudobulk...")
    print(f"  Sample column: {sample_key}")
    print(f"  Cell type column: {celltype_key}")

    # Check required columns
    if sample_key not in adata.obs.columns:
        raise ValueError(f"'{sample_key}' not found in adata.obs")
    if celltype_key not in adata.obs.columns:
        raise ValueError(f"'{celltype_key}' not found in adata.obs")

    # Get counts
    if layer is not None:
        counts = adata.layers[layer]
    else:
        counts = adata.X

    # Convert to dense if sparse
    if hasattr(counts, 'toarray'):
        counts = counts.toarray()

    # Create sample-celltype combinations
    adata.obs['sample_celltype'] = (
        adata.obs[sample_key].astype(str) + '_' +
        adata.obs[celltype_key].astype(str)
    )

    # Aggregate counts
    pseudobulk_counts = {}
    n_cells_dict = {}
    metadata_list = []

    for sample in adata.obs[sample_key].unique():
        for celltype in adata.obs[celltype_key].unique():
            # Select cells
            mask = (
                (adata.obs[sample_key] == sample) &
                (adata.obs[celltype_key] == celltype)
            )
            n_cells = mask.sum()

            # Filter by minimum cells
            if n_cells < min_cells:
                continue

            # Sum counts
            sample_celltype_id = f"{sample}_{celltype}"
            summed_counts = counts[mask, :].sum(axis=0)

            # Filter by minimum counts
            if summed_counts.sum() < min_counts:
                continue

            pseudobulk_counts[sample_celltype_id] = summed_counts
            n_cells_dict[sample_celltype_id] = n_cells

            # Store metadata
            metadata_list.append({
                'sample_celltype': sample_celltype_id,
                'sample': sample,
                'celltype': celltype,
                'n_cells': n_cells
            })

    # Convert to DataFrames
    counts_df = pd.DataFrame(pseudobulk_counts, index=adata.var_names)
    metadata_df = pd.DataFrame(metadata_list).set_index('sample_celltype')

    print(f"\nPseudobulk aggregation complete:")
    print(f"  Total sample-celltype combinations: {counts_df.shape[1]}")
    print(f"  Genes: {counts_df.shape[0]}")
    print(f"  Median cells per combination: {metadata_df['n_cells'].median():.0f}")

    return {
        'counts': counts_df,
        'metadata': metadata_df,
        'n_cells': metadata_df['n_cells']
    }


def validate_pseudobulk_design(
    metadata: pd.DataFrame,
    contrast: List[str],
    min_replicates: int = 2
) -> Dict[str, any]:
    """
    Validate experimental design for pseudobulk DE analysis.

    Checks that each condition in the contrast has sufficient biological
    replicates. DESeq2 requires biological replicates to estimate dispersion;
    N=1 in any group makes DE analysis statistically invalid.

    Parameters
    ----------
    metadata : DataFrame
        Sample-level metadata
    contrast : list of str
        DESeq2 contrast [variable, level1, level2]
    min_replicates : int, optional
        Minimum replicates per condition (default: 2, recommended: 3)

    Returns
    -------
    dict
        Validation result with keys:
        - 'valid': bool, whether design is valid
        - 'condition_counts': dict mapping condition to sample count
        - 'warnings': list of warning messages
        - 'errors': list of error messages
    """
    result = {'valid': True, 'condition_counts': {}, 'warnings': [], 'errors': []}

    contrast_var = contrast[0]
    if contrast_var not in metadata.columns:
        result['valid'] = False
        result['errors'].append(
            f"Contrast variable '{contrast_var}' not found in metadata. "
            f"Available columns: {list(metadata.columns)}"
        )
        return result

    # Count unique samples per condition level
    for level in contrast[1:]:
        level_mask = metadata[contrast_var] == level
        n_samples = metadata.loc[level_mask, 'sample'].nunique() if 'sample' in metadata.columns else level_mask.sum()
        result['condition_counts'][level] = n_samples

    # Check for insufficient replicates
    for level, n in result['condition_counts'].items():
        if n < 1:
            result['valid'] = False
            result['errors'].append(
                f"Condition '{level}' has 0 samples. Cannot run DE."
            )
        elif n == 1:
            result['valid'] = False
            result['errors'].append(
                f"Condition '{level}' has only 1 sample (N=1). "
                f"DESeq2 requires biological replicates to estimate dispersion. "
                f"Pseudobulk DE is not valid with N=1 in any group. "
                f"Options: (1) Add more samples for this condition, "
                f"(2) Use exploratory cell-level DE (Wilcoxon) with appropriate caveats, "
                f"(3) Report descriptive statistics only."
            )
        elif n < min_replicates:
            result['warnings'].append(
                f"Condition '{level}' has only {n} samples. "
                f"Minimum {min_replicates} recommended for reliable DE."
            )
        elif n < 3:
            result['warnings'].append(
                f"Condition '{level}' has {n} samples. "
                f"N≥3 per group recommended for adequate statistical power."
            )

    return result


def run_deseq2_analysis(
    pseudobulk: Dict[str, pd.DataFrame],
    sample_metadata: pd.DataFrame,
    formula: str,
    contrast: List[str],
    celltype_key: str = 'celltype',
    output_dir: Union[str, Path] = "results/pseudobulk_de",
    use_rpy2: bool = True,
    min_replicates: int = 2
) -> Dict[str, pd.DataFrame]:
    """
    Run DESeq2 differential expression analysis for each cell type.

    CRITICAL: Validates that each condition has sufficient biological
    replicates before running. DESeq2 requires ≥2 replicates per group
    to estimate dispersion. Will refuse to run with N=1 in any group.

    Parameters
    ----------
    pseudobulk : dict
        Output from aggregate_to_pseudobulk()
    sample_metadata : DataFrame
        Sample-level metadata with condition, batch, etc.
        Must have 'sample' column matching pseudobulk sample IDs
    formula : str
        DESeq2 design formula (e.g., "~ batch + condition")
    contrast : list of str
        DESeq2 contrast (e.g., ["condition", "treated", "control"])
    celltype_key : str, optional
        Column name for cell types (default: 'celltype')
    output_dir : str or Path
        Directory to save results
    use_rpy2 : bool, optional
        Use R DESeq2 via rpy2 (default: True)
        If False, uses pydeseq2 (pure Python, less tested)
    min_replicates : int, optional
        Minimum replicates per condition (default: 2)
        Set to 3 for standard recommendations.

    Returns
    -------
    dict
        Dictionary mapping cell type to DESeq2 results DataFrame

    Notes
    -----
    Requires R and DESeq2 installed if use_rpy2=True.
    Install in R: BiocManager::install("DESeq2")
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # === VALIDATE EXPERIMENTAL DESIGN ===
    print("\nValidating experimental design for pseudobulk DE...")
    design_check = validate_pseudobulk_design(
        sample_metadata, contrast, min_replicates=min_replicates
    )

    # Report condition counts
    for level, n in design_check['condition_counts'].items():
        print(f"  {contrast[0]}='{level}': {n} samples")

    # Report warnings
    for w in design_check['warnings']:
        print(f"\n  [WARNING] {w}")

    # Block on errors (N=1 etc.)
    if not design_check['valid']:
        for e in design_check['errors']:
            print(f"\n  [ERROR] {e}")
        print("\n  Pseudobulk DE analysis aborted due to invalid design.")
        print("  Use cell-level DE (Wilcoxon) for exploratory analysis only,")
        print("  with clear caveats about pseudoreplication.")
        return {}

    # Get counts and metadata
    counts_df = pseudobulk['counts']
    pb_metadata = pseudobulk['metadata']

    # Merge with sample metadata
    pb_metadata = pb_metadata.merge(
        sample_metadata,
        left_on='sample',
        right_on='sample',
        how='left'
    )

    # Get unique cell types
    celltypes = pb_metadata[celltype_key].unique()
    print(f"\nRunning DESeq2 for {len(celltypes)} cell types...")

    de_results = {}

    for celltype in celltypes:
        print(f"\n  Cell type: {celltype}")

        # Subset to cell type
        celltype_mask = pb_metadata[celltype_key] == celltype
        celltype_counts = counts_df.loc[:, celltype_mask]
        celltype_metadata = pb_metadata[celltype_mask]

        n_samples = celltype_counts.shape[1]
        print(f"    Samples: {n_samples}")

        # Check minimum samples (total for this cell type)
        if n_samples < 3:
            print(f"    Skipping: <3 samples total for this cell type")
            continue

        # Check per-condition replicates for this cell type
        contrast_var = contrast[0]
        if contrast_var in celltype_metadata.columns:
            for level in contrast[1:]:
                n_level = (celltype_metadata[contrast_var] == level).sum()
                if n_level < 2:
                    print(f"    Skipping: '{level}' has only {n_level} sample(s) "
                          f"for {celltype} (need ≥2)")
                    break
            else:
                # All levels have ≥2 — proceed
                pass
            if any((celltype_metadata[contrast_var] == level).sum() < 2
                   for level in contrast[1:]):
                continue

        # Run DESeq2
        if use_rpy2:
            results_df = _run_deseq2_rpy2(
                celltype_counts,
                celltype_metadata,
                formula,
                contrast
            )
        else:
            results_df = _run_deseq2_pydeseq2(
                celltype_counts,
                celltype_metadata,
                formula,
                contrast
            )

        if results_df is not None:
            de_results[celltype] = results_df

            n_sig = (results_df['padj'] < 0.05).sum()
            print(f"    Significant genes (padj<0.05): {n_sig}")

    return de_results


def _run_deseq2_rpy2(
    counts: pd.DataFrame,
    metadata: pd.DataFrame,
    formula: str,
    contrast: List[str]
) -> pd.DataFrame:
    """Run DESeq2 via rpy2."""
    try:
        import rpy2.robjects as ro
        from rpy2.robjects import pandas2ri
        from rpy2.robjects.packages import importr
    except ImportError:
        raise ImportError("rpy2 required. Install with: pip install rpy2")

    # Activate pandas conversion
    pandas2ri.activate()

    # Import R packages
    try:
        deseq2 = importr('DESeq2')
        base = importr('base')
    except Exception as e:
        raise ImportError(f"DESeq2 not found in R. Install with: BiocManager::install('DESeq2')\n{e}")

    # Convert to R objects
    r_counts = pandas2ri.py2rpy(counts.astype(int))
    r_metadata = pandas2ri.py2rpy(metadata)

    # Create DESeqDataSet
    ro.globalenv['counts_matrix'] = r_counts
    ro.globalenv['col_data'] = r_metadata

    ro.r(f'''
    dds <- DESeqDataSetFromMatrix(
        countData = counts_matrix,
        colData = col_data,
        design = {formula}
    )
    ''')

    # Filter low count genes
    ro.r('''
    keep <- rowSums(counts(dds) >= 10) >= 3
    dds <- dds[keep,]
    ''')

    # Run DESeq2
    ro.r('dds <- DESeq(dds, quiet=TRUE)')

    # Extract results
    contrast_str = f"c('{contrast[0]}', '{contrast[1]}', '{contrast[2]}')"
    ro.r(f'res <- results(dds, contrast={contrast_str})')

    # Shrink log2FoldChange
    ro.r(f'''
    res_shrunk <- lfcShrink(dds,
                           contrast={contrast_str},
                           res=res,
                           type="ashr",
                           quiet=TRUE)
    ''')

    # Convert to pandas
    results_df = pandas2ri.rpy2py(ro.r('as.data.frame(res_shrunk)'))
    results_df.index.name = 'gene'
    results_df = results_df.reset_index()

    pandas2ri.deactivate()

    return results_df


def _run_deseq2_pydeseq2(
    counts: pd.DataFrame,
    metadata: pd.DataFrame,
    formula: str,
    contrast: List[str]
) -> pd.DataFrame:
    """Run DESeq2 via pydeseq2 (pure Python)."""
    try:
        from pydeseq2.dds import DeseqDataSet
        from pydeseq2.ds import DeseqStats
    except ImportError:
        raise ImportError("pydeseq2 required. Install with: pip install pydeseq2")

    # Create DESeqDataSet
    dds = DeseqDataSet(
        counts=counts.T.astype(int),
        metadata=metadata,
        design_factors=formula.replace('~', '').strip().split('+')
    )

    # Run DESeq2
    dds.deseq2()

    # Compute statistics
    stat_res = DeseqStats(dds, contrast=contrast)
    stat_res.summary()

    results_df = stat_res.results_df
    results_df.index.name = 'gene'
    results_df = results_df.reset_index()

    return results_df


def export_de_results(
    de_results: Dict[str, pd.DataFrame],
    output_dir: Union[str, Path] = "results/pseudobulk_de",
    padj_threshold: float = 0.05,
    log2fc_threshold: float = 0
):
    """
    Export DE results to CSV files.

    Parameters
    ----------
    de_results : dict
        Dictionary mapping cell type to results DataFrame
    output_dir : str or Path
        Output directory
    padj_threshold : float, optional
        Adjusted p-value threshold (default: 0.05)
    log2fc_threshold : float, optional
        Absolute log2 fold change threshold (default: 0)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nExporting DE results to {output_dir}")

    for celltype, results_df in de_results.items():
        # Export full results
        results_file = output_dir / f"{celltype}_deseq2_results.csv"
        results_df.to_csv(results_file, index=False)

        # Export significant genes
        sig_mask = (
            (results_df['padj'] < padj_threshold) &
            (results_df['log2FoldChange'].abs() > log2fc_threshold)
        )
        sig_df = results_df[sig_mask].sort_values('padj')

        sig_file = output_dir / f"{celltype}_deseq2_sig.csv"
        sig_df.to_csv(sig_file, index=False)

        print(f"  {celltype}: {len(sig_df)} significant genes")


def plot_volcano(
    results_df: pd.DataFrame,
    celltype: str,
    output_dir: Union[str, Path] = "results/pseudobulk_de",
    padj_threshold: float = 0.05,
    log2fc_threshold: float = 0.5,
    top_genes: int = 10
):
    """
    Create volcano plot for DE results.

    Parameters
    ----------
    results_df : DataFrame
        DESeq2 results
    celltype : str
        Cell type name
    output_dir : str or Path
        Output directory
    padj_threshold : float
        Adjusted p-value threshold for significance
    log2fc_threshold : float
        Log2 fold change threshold for significance
    top_genes : int
        Number of top genes to label
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    try:
        from adjustText import adjust_text
        HAS_ADJUSTTEXT = True
    except ImportError:
        HAS_ADJUSTTEXT = False

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Prepare data
    plot_df = results_df.copy()
    plot_df['-log10(padj)'] = -np.log10(plot_df['padj'])

    # Classify genes
    plot_df['significance'] = 'NS'
    sig_mask = (
        (plot_df['padj'] < padj_threshold) &
        (plot_df['log2FoldChange'].abs() > log2fc_threshold)
    )
    plot_df.loc[sig_mask, 'significance'] = 'Significant'

    # Get top genes
    top_df = plot_df.nsmallest(top_genes, 'padj')

    # Create plot
    fig, ax = plt.subplots(figsize=(8, 6))

    color_map = {'NS': '#CCCCCC', 'Significant': '#E31A1C'}
    for sig_type, color in color_map.items():
        mask = plot_df['significance'] == sig_type
        ax.scatter(
            plot_df.loc[mask, 'log2FoldChange'],
            plot_df.loc[mask, '-log10(padj)'],
            c=color, alpha=0.5, s=10, label=sig_type, edgecolors='none'
        )

    ax.axhline(y=-np.log10(padj_threshold), linestyle='--', color='red', linewidth=0.8)
    ax.axvline(x=log2fc_threshold, linestyle='--', color='red', linewidth=0.8)
    ax.axvline(x=-log2fc_threshold, linestyle='--', color='red', linewidth=0.8)

    ax.set_xlabel('log2 Fold Change')
    ax.set_ylabel('-log10(adjusted p-value)')
    ax.set_title(f'Volcano Plot: {celltype}', fontweight='bold')
    ax.legend(frameon=False)
    sns.despine(ax=ax)

    # Add gene labels with adjustText if available
    if HAS_ADJUSTTEXT and len(top_df) > 0:
        texts = [
            ax.text(row['log2FoldChange'], row['-log10(padj)'],
                    row.name if hasattr(row, 'name') else str(i),
                    fontsize=8, alpha=0.9)
            for i, row in top_df.iterrows()
        ]
        adjust_text(
            texts,
            arrowprops=dict(arrowstyle='->', color='gray', lw=0.5, alpha=0.7),
            expand_points=(1.5, 1.5),
            force_text=(0.5, 0.5)
        )

    fig.tight_layout()
    fig.savefig(output_dir / f"{celltype}_volcano.png", dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / f"{celltype}_volcano.svg", dpi=300, bbox_inches='tight')
    plt.close(fig)


def plot_ma(
    results_df: pd.DataFrame,
    celltype: str,
    output_dir: Union[str, Path] = "results/pseudobulk_de",
    padj_threshold: float = 0.05
):
    """
    Create MA plot for DE results.

    Parameters
    ----------
    results_df : DataFrame
        DESeq2 results
    celltype : str
        Cell type name
    output_dir : str or Path
        Output directory
    padj_threshold : float
        Adjusted p-value threshold for significance
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    output_dir = Path(output_dir)

    # Prepare data
    plot_df = results_df.copy()

    # Classify genes
    plot_df['significance'] = 'NS'
    plot_df.loc[plot_df['padj'] < padj_threshold, 'significance'] = 'Significant'

    # Create plot
    fig, ax = plt.subplots(figsize=(8, 6))

    color_map = {'NS': '#CCCCCC', 'Significant': '#E31A1C'}
    for sig_type, color in color_map.items():
        mask = plot_df['significance'] == sig_type
        ax.scatter(
            plot_df.loc[mask, 'baseMean'],
            plot_df.loc[mask, 'log2FoldChange'],
            c=color, alpha=0.5, s=10, label=sig_type, edgecolors='none'
        )

    ax.axhline(y=0, linestyle='--', color='black', linewidth=0.8)
    ax.set_xlabel('Mean Expression (log10)')
    ax.set_ylabel('log2 Fold Change')
    ax.set_title(f'MA Plot: {celltype}', fontweight='bold')
    ax.legend(frameon=False)
    sns.despine(ax=ax)

    fig.tight_layout()
    fig.savefig(output_dir / f"{celltype}_ma.png", dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / f"{celltype}_ma.svg", dpi=300, bbox_inches='tight')
    plt.close(fig)


# Example usage
if __name__ == "__main__":
    # Example workflow
    print("Example pseudobulk DE workflow:")
    print("1. Aggregate counts: pseudobulk = aggregate_to_pseudobulk(adata, 'sample', 'celltype')")
    print("2. Run DESeq2: de_results = run_deseq2_analysis(pseudobulk, metadata, '~ condition', ['condition', 'treated', 'control'])")
    print("3. Export: export_de_results(de_results)")
    print("4. Plot: plot_volcano(de_results['CellType'], 'CellType')")

