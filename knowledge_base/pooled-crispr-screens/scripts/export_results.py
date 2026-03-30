"""
Export Results and Hit Lists

Export summary tables, hit lists, and processed data for downstream analysis.
"""

import os
import pickle
import pandas as pd
import anndata as ad
from typing import Dict, List, Optional


def export_all_results(
    adata: ad.AnnData,
    perturbation_summary: pd.DataFrame,
    de_results: Optional[Dict[str, pd.DataFrame]] = None,
    outlier_cells: Optional[List[str]] = None,
    output_dir: str = 'results/',
    export_formats: List[str] = ['csv', 'h5ad', 'excel']
) -> None:
    """
    Export all analysis results to various formats.

    Parameters
    ----------
    adata : AnnData
        Processed AnnData object
    perturbation_summary : DataFrame
        Summary from detect_perturbed_cells
    de_results : dict, optional
        DE results from run_de_analysis
    outlier_cells : list, optional
        List of outlier cell barcodes
    output_dir : str, default='results/'
        Directory to save results
    export_formats : list of str
        Formats to export: 'csv', 'h5ad', 'excel'

    Example
    -------
    >>> export_all_results(
    ...     adata,
    ...     results['perturbation_summary'],
    ...     de_results=de_results,
    ...     outlier_cells=results['outlier_cells'],
    ...     output_dir='results/'
    ... )
    """
    os.makedirs(output_dir, exist_ok=True)

    print(f"Exporting results to: {output_dir}")

    # 1. Export hit summary
    if perturbation_summary is not None and 'csv' in export_formats:
        hit_summary_path = os.path.join(output_dir, 'hit_summary.csv')
        perturbation_summary.to_csv(hit_summary_path, index=False)
        print(f"  Saved: hit_summary.csv")

    # 2. Export per-perturbation stats
    if perturbation_summary is not None and 'csv' in export_formats:
        stats_path = os.path.join(output_dir, 'per_perturbation_stats.csv')
        perturbation_summary.to_csv(stats_path, index=False)
        print(f"  Saved: per_perturbation_stats.csv")

    # 3. Export top DE genes per perturbation
    if de_results is not None and 'excel' in export_formats:
        excel_path = os.path.join(output_dir, 'top_de_genes_per_perturbation.xlsx')

        try:
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                for gene, de_df in de_results.items():
                    # Top 50 genes
                    top_genes = de_df.head(50)
                    sheet_name = gene[:31]  # Excel sheet name limit
                    top_genes.to_excel(writer, sheet_name=sheet_name, index=False)

            print(f"  Saved: top_de_genes_per_perturbation.xlsx ({len(de_results)} sheets)")
        except ImportError:
            print(f"  (Skipped Excel export - install openpyxl: pip install openpyxl)")

    # 4. Export outlier cell list
    if outlier_cells is not None and 'csv' in export_formats:
        outlier_df = pd.DataFrame({'cell_barcode': outlier_cells})
        outlier_path = os.path.join(output_dir, 'outlier_cells.csv')
        outlier_df.to_csv(outlier_path, index=False)
        print(f"  Saved: outlier_cells.csv ({len(outlier_cells)} cells)")

    # 5. Export processed AnnData
    if 'h5ad' in export_formats:
        adata_path = os.path.join(output_dir, 'adata_processed.h5ad')
        adata.write(adata_path)
        print(f"  Saved: adata_processed.h5ad")

    # 6. Export hit list (genes only)
    if perturbation_summary is not None and 'csv' in export_formats and 'is_hit' in perturbation_summary.columns:
        hits = perturbation_summary[perturbation_summary['is_hit']]
        hit_list_path = os.path.join(output_dir, 'hit_list.csv')

        # Select available columns dynamically
        available_cols = []
        for col in ['perturbation', 'gene', 'n_outliers', 'outlier_fraction', 'n_de_genes']:
            if col in hits.columns:
                available_cols.append(col)

        if len(available_cols) > 0:
            hits[available_cols].to_csv(hit_list_path, index=False)
            print(f"  Saved: hit_list.csv ({len(hits)} hits)")

    # 7. Save analysis objects as pickle (for downstream skills)
    analysis_objects = {
        'perturbation_summary': perturbation_summary,
        'de_results': de_results,
        'outlier_cells': outlier_cells,
    }
    pkl_path = os.path.join(output_dir, 'analysis_objects.pkl')
    with open(pkl_path, 'wb') as f:
        pickle.dump(analysis_objects, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"  Saved: analysis_objects.pkl")
    print(f"    (Load with: import pickle; objs = pickle.load(open('{pkl_path}', 'rb')))")

    # 8. Generate PDF report
    try:
        from scripts.generate_report import generate_report
        generate_report(
            adata=adata,
            perturbation_summary=perturbation_summary,
            de_results=de_results,
            output_dir=output_dir,
        )
    except Exception as e:
        print(f"   PDF generation skipped: {e}")
        print(f"   (Install reportlab for PDF: pip install reportlab)")

    print("\n=== Export Complete ===")


def export_hit_list(
    perturbation_summary: pd.DataFrame,
    output_path: str = 'results/hit_list.txt',
    sort_by: str = 'outlier_fraction'
) -> None:
    """
    Export simple hit list (gene names only) for downstream analysis.

    Parameters
    ----------
    perturbation_summary : DataFrame
        Summary from detect_perturbed_cells
    output_path : str
        Path to save hit list
    sort_by : str, default='outlier_fraction'
        Column to sort by

    Example
    -------
    >>> export_hit_list(
    ...     results['perturbation_summary'],
    ...     output_path='results/hit_list.txt'
    ... )
    """
    hits = perturbation_summary[perturbation_summary['is_hit']].sort_values(
        sort_by,
        ascending=False
    )

    with open(output_path, 'w') as f:
        for gene in hits['gene']:
            f.write(f"{gene}\n")

    print(f"Hit list exported: {output_path} ({len(hits)} genes)")


def create_summary_report(
    adata: ad.AnnData,
    perturbation_summary: pd.DataFrame,
    de_results: Optional[Dict] = None,
    output_path: str = 'results/analysis_report.txt'
) -> None:
    """
    Create a human-readable summary report.

    Parameters
    ----------
    adata : AnnData
        Processed AnnData
    perturbation_summary : DataFrame
        Summary from detect_perturbed_cells
    de_results : dict, optional
        DE results
    output_path : str
        Path to save report

    Example
    -------
    >>> create_summary_report(
    ...     adata,
    ...     results['perturbation_summary'],
    ...     de_results=de_results
    ... )
    """
    with open(output_path, 'w') as f:
        f.write("=" * 60 + "\n")
        f.write("POOLED CRISPR SCREEN ANALYSIS REPORT\n")
        f.write("=" * 60 + "\n\n")

        # Dataset summary
        f.write("DATASET SUMMARY\n")
        f.write("-" * 60 + "\n")
        f.write(f"Total cells: {adata.n_obs:,}\n")
        f.write(f"Total genes: {adata.n_vars:,}\n")

        if 'gene' in adata.obs.columns:
            f.write(f"Unique perturbations: {adata.obs['gene'].nunique()}\n")
            f.write(f"Unique sgRNAs: {adata.obs['sgRNA'].nunique()}\n")

            cells_per_pert = adata.obs.groupby('gene').size()
            f.write(f"Mean cells per perturbation: {cells_per_pert.mean():.1f}\n")
            f.write(f"Median cells per perturbation: {cells_per_pert.median():.1f}\n")

        f.write("\n")

        # Hit summary
        f.write("HIT CALLING SUMMARY\n")
        f.write("-" * 60 + "\n")
        n_hits = perturbation_summary['is_hit'].sum()
        n_tested = len(perturbation_summary)
        hit_rate = n_hits / n_tested * 100

        f.write(f"Perturbations tested: {n_tested}\n")
        f.write(f"Hits detected: {n_hits} ({hit_rate:.1f}%)\n")
        f.write(f"Total outlier cells: {perturbation_summary['n_outliers'].sum()}\n")
        f.write("\n")

        # Top 10 hits
        f.write("TOP 10 HITS (by outlier fraction)\n")
        f.write("-" * 60 + "\n")
        top_hits = perturbation_summary.nlargest(10, 'outlier_fraction')

        for idx, row in top_hits.iterrows():
            f.write(
                f"{row['gene']:20s} | "
                f"Outliers: {row['n_outliers']:4.0f} ({row['outlier_fraction']:.1%}) | "
                f"DE genes: {row['n_de_genes']:4.0f}\n"
            )

        f.write("\n")

        # DE summary (if available)
        if de_results is not None:
            f.write("DIFFERENTIAL EXPRESSION SUMMARY\n")
            f.write("-" * 60 + "\n")

            de_counts = [len(df[df['pval'] < 0.05]) for df in de_results.values()]
            f.write(f"Mean DE genes per perturbation: {sum(de_counts)/len(de_counts):.1f}\n")
            f.write(f"Median DE genes per perturbation: {sorted(de_counts)[len(de_counts)//2]:.1f}\n")

        f.write("\n")
        f.write("=" * 60 + "\n")

    print(f"Summary report saved: {output_path}")

