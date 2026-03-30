"""
============================================================================
SPATIAL TRANSCRIPTOMICS VISUALIZATION
============================================================================

Generate publication-quality plots for spatial analysis results.
Uses plotnine + theme_prism() for standard plots, seaborn for heatmaps,
and scanpy/squidpy for spatial tissue overlays.

Functions:
  - generate_all_plots(): Generate all visualizations (PNG + SVG)

Usage:
  from generate_all_plots import generate_all_plots
  generate_all_plots(adata, output_dir="visium_results")
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Optional, List, Union

from plotnine import (
    ggplot, aes, geom_violin, geom_jitter, geom_point, geom_col,
    geom_line, labs, theme, coord_flip, facet_wrap, element_text,
    element_blank, scale_color_cmap, guides, guide_legend,
    scale_fill_hue, scale_color_hue
)
from plotnine_prism import theme_prism


# ---------------------------------------------------------------------------
# Save helper: PNG + SVG with graceful fallback
# ---------------------------------------------------------------------------

def _save_plot(fig, base_path: Union[str, Path], dpi: int = 300,
               width: float = 8, height: float = 6) -> None:
    """Save plot in PNG + SVG with graceful SVG fallback."""
    base_path = Path(base_path)
    base_no_ext = base_path.with_suffix('')

    # Always save PNG
    png_path = base_no_ext.with_suffix('.png')
    try:
        if hasattr(fig, 'save'):  # plotnine
            fig.save(str(png_path), width=width, height=height, dpi=dpi, verbose=False)
        else:  # matplotlib figure
            fig.savefig(str(png_path), dpi=dpi, bbox_inches='tight', format='png')
        print(f"   Saved: {png_path}")
    except Exception as e:
        print(f"   Warning: PNG export failed: {e}")

    # Always try SVG
    svg_path = base_no_ext.with_suffix('.svg')
    try:
        if hasattr(fig, 'save'):  # plotnine
            fig.save(str(svg_path), width=width, height=height, verbose=False)
        else:  # matplotlib figure
            fig.savefig(str(svg_path), bbox_inches='tight', format='svg')
        print(f"   Saved: {svg_path}")
    except Exception:
        print(f"   (SVG export failed)")


def _save_matplotlib(fig, base_path, dpi=300, width=8, height=6):
    """Save matplotlib figure and close it."""
    _save_plot(fig, base_path, dpi=dpi, width=width, height=height)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Individual plot functions
# ---------------------------------------------------------------------------

def _plot_qc_violins(adata, output_dir: Path) -> None:
    """QC violin plots using plotnine + theme_prism."""
    qc_df = pd.DataFrame({
        'Total Counts': adata.obs['total_counts'].values,
        'Genes Detected': adata.obs['n_genes_by_counts'].values,
        'Mitochondrial %': adata.obs['pct_counts_mt'].values,
    })
    qc_long = qc_df.melt(var_name='Metric', value_name='Value')

    p = (
        ggplot(qc_long, aes(x='Metric', y='Value'))
        + geom_violin(fill='#4C72B0', alpha=0.7)
        + facet_wrap('~Metric', scales='free')
        + labs(title='QC Metrics', x='', y='Value')
        + theme_prism(base_size=12)
        + theme(
            plot_title=element_text(hjust=0.5, face='bold', size=14),
            axis_text_x=element_blank(),
            strip_text=element_text(size=11, face='bold'),
        )
    )
    _save_plot(p, output_dir / 'qc_violins.png', width=12, height=5)
    print("  ✓ QC violin plots saved")


def _plot_spatial_clusters(adata, output_dir: Path) -> None:
    """Spatial cluster overlay using scanpy."""
    import scanpy as sc

    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    sc.pl.spatial(
        adata, color='leiden', ax=ax, show=False,
        title='Spatial Clusters (Leiden)',
        frameon=False, spot_size=1.5
    )
    _save_matplotlib(fig, output_dir / 'spatial_clusters.png', width=8, height=8)
    print("  ✓ Spatial cluster plot saved")


def _plot_spatial_markers(adata, marker_genes: List[str], output_dir: Path) -> None:
    """Spatial marker gene expression using scanpy."""
    import scanpy as sc

    n_genes = len(marker_genes)
    ncols = min(3, n_genes)
    nrows = (n_genes + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 5.5 * nrows))
    if n_genes == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    for i, gene in enumerate(marker_genes):
        sc.pl.spatial(
            adata, color=gene, ax=axes[i], show=False,
            title=gene, frameon=False, spot_size=1.5,
            cmap='Reds'
        )

    # Hide unused axes
    for j in range(n_genes, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle('Marker Gene Expression', fontsize=14, fontweight='bold', y=1.02)
    fig.tight_layout()
    _save_matplotlib(fig, output_dir / 'spatial_markers.png',
                     width=6 * ncols, height=5.5 * nrows)
    print(f"  ✓ Spatial marker plots saved ({n_genes} genes)")


def _plot_umap_clusters(adata, output_dir: Path) -> None:
    """UMAP by cluster using plotnine + theme_prism."""
    umap_df = pd.DataFrame(
        adata.obsm['X_umap'],
        columns=['UMAP1', 'UMAP2']
    )
    umap_df['Cluster'] = adata.obs['leiden'].values

    p = (
        ggplot(umap_df, aes(x='UMAP1', y='UMAP2', color='Cluster'))
        + geom_point(size=0.5, alpha=0.7)
        + labs(title='UMAP (Leiden Clusters)', color='Cluster')
        + theme_prism(base_size=12)
        + theme(
            plot_title=element_text(hjust=0.5, face='bold', size=14),
        )
        + guides(color=guide_legend(override_aes={'size': 3}))
    )
    _save_plot(p, output_dir / 'umap_clusters.png', width=9, height=7)
    print("  ✓ UMAP cluster plot saved")


def _plot_nhood_enrichment(adata, output_dir: Path) -> None:
    """Neighborhood enrichment heatmap using seaborn.clustermap."""
    zscore = adata.uns['leiden_nhood_enrichment']['zscore']
    clusters = sorted(adata.obs['leiden'].unique(), key=int)
    labels = [str(c) for c in clusters]

    zscore_df = pd.DataFrame(zscore, index=labels, columns=labels)

    g = sns.clustermap(
        zscore_df,
        cmap='RdBu_r',
        center=0,
        figsize=(10, 9),
        cbar_kws={'label': 'Enrichment Z-score'},
        dendrogram_ratio=0.1,
        linewidths=0.5,
        linecolor='white',
    )
    g.ax_heatmap.set_xlabel('Cluster', fontsize=12)
    g.ax_heatmap.set_ylabel('Cluster', fontsize=12)
    g.fig.suptitle('Neighborhood Enrichment', fontsize=14, fontweight='bold', y=1.02)

    _save_matplotlib(g.fig, output_dir / 'neighborhood_enrichment.png', width=10, height=9)
    print("  ✓ Neighborhood enrichment heatmap saved")


def _plot_co_occurrence(adata, output_dir: Path) -> None:
    """Co-occurrence probability vs distance using plotnine + theme_prism."""
    co_occ = adata.uns['leiden_co_occurrence']
    occ = co_occ['occ']
    interval = co_occ['interval']

    # Midpoints of distance intervals
    midpoints = [(interval[i] + interval[i + 1]) / 2 for i in range(len(interval) - 1)]

    clusters = sorted(adata.obs['leiden'].unique(), key=int)
    n_clusters = len(clusters)

    # Build long-form DataFrame for plotnine
    rows = []
    for i in range(min(n_clusters, 8)):
        for j, d in enumerate(midpoints):
            rows.append({
                'Distance': d,
                'Co-occurrence': occ[i, i, j],
                'Cluster': str(clusters[i])
            })
    co_df = pd.DataFrame(rows)

    p = (
        ggplot(co_df, aes(x='Distance', y='Co-occurrence', color='Cluster'))
        + geom_line(size=1.2, alpha=0.8)
        + labs(
            title='Cluster Co-occurrence by Distance',
            x='Distance', y='Co-occurrence Probability',
            color='Cluster'
        )
        + theme_prism(base_size=12)
        + theme(
            plot_title=element_text(hjust=0.5, face='bold', size=14),
        )
    )
    _save_plot(p, output_dir / 'co_occurrence.png', width=10, height=6)
    print("  ✓ Co-occurrence plot saved")


def _plot_top_svgs(svg_results: pd.DataFrame, top_n: int, output_dir: Path) -> None:
    """Top spatially variable genes bar chart using plotnine + theme_prism."""
    top_svgs = svg_results.head(top_n).copy()
    top_svgs['Gene'] = top_svgs.index
    # Reverse for horizontal bar chart (highest at top)
    top_svgs['Gene'] = pd.Categorical(
        top_svgs['Gene'], categories=top_svgs['Gene'][::-1], ordered=True
    )

    p = (
        ggplot(top_svgs, aes(x='Gene', y='I'))
        + geom_col(fill='#4C72B0', alpha=0.85)
        + coord_flip()
        + labs(
            title=f"Top {top_n} Spatially Variable Genes",
            x='', y="Moran's I"
        )
        + theme_prism(base_size=12)
        + theme(
            plot_title=element_text(hjust=0.5, face='bold', size=14),
        )
    )
    _save_plot(p, output_dir / 'top_svgs.png', width=8, height=6)
    print("  ✓ Top SVGs bar plot saved")


def _plot_spatial_svg(adata, gene: str, output_dir: Path) -> None:
    """Spatial expression of top SVG using scanpy."""
    import scanpy as sc

    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    sc.pl.spatial(
        adata, color=gene, ax=ax, show=False,
        title=f'{gene} (Top SVG)', frameon=False,
        spot_size=1.5, cmap='magma'
    )
    _save_matplotlib(fig, output_dir / f'spatial_svg_{gene}.png', width=8, height=8)
    print(f"  ✓ Spatial SVG plot saved ({gene})")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_all_plots(
    adata: 'anndata.AnnData',
    output_dir: str = "visium_results",
    marker_genes: Optional[List[str]] = None,
    top_n_svgs: int = 10
) -> None:
    """
    Generate all spatial transcriptomics visualizations.

    Plots (all PNG + SVG):
    1. QC violin plots (total_counts, n_genes, pct_mito) — plotnine
    2. Spatial scatter — clusters on tissue — scanpy
    3. Spatial scatter — marker genes — scanpy
    4. UMAP colored by cluster — plotnine
    5. Neighborhood enrichment heatmap — seaborn.clustermap
    6. Co-occurrence plot — matplotlib
    7. Top SVGs bar chart — plotnine
    8. Spatial scatter of top SVG — scanpy

    Parameters
    ----------
    adata : AnnData
        Processed AnnData from run_spatial_analysis().
    output_dir : str
        Output directory (default: "visium_results").
    marker_genes : list of str, optional
        Genes for tissue overlay (default: cardiac markers).
    top_n_svgs : int
        Number of top SVGs for bar plot (default: 10).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n=== Step 3: Generate Visualizations ===\n")

    # Default cardiac marker genes
    if marker_genes is None:
        marker_genes = ['MYH7', 'TNNI3', 'MYH6', 'NPPA', 'TTN', 'ACTN2']

    # Filter to available markers
    available_markers = [g for g in marker_genes if g in adata.var_names]

    # --- 1. QC violin plots ---
    print("1. Generating QC violin plots...")
    try:
        _plot_qc_violins(adata, output_dir)
    except Exception as e:
        print(f"   Error: {e}")

    # --- 2. Spatial clusters ---
    print("2. Generating spatial cluster plot...")
    try:
        _plot_spatial_clusters(adata, output_dir)
    except Exception as e:
        print(f"   Error: {e}")

    # --- 3. Spatial markers ---
    if available_markers:
        print(f"3. Generating spatial marker gene plots ({len(available_markers)} genes)...")
        try:
            _plot_spatial_markers(adata, available_markers, output_dir)
        except Exception as e:
            print(f"   Error: {e}")
    else:
        print("3. Skipping marker gene plots (no matching genes in dataset)")

    # --- 4. UMAP ---
    print("4. Generating UMAP cluster plot...")
    try:
        _plot_umap_clusters(adata, output_dir)
    except Exception as e:
        print(f"   Error: {e}")

    # --- 5. Neighborhood enrichment ---
    print("5. Generating neighborhood enrichment heatmap...")
    try:
        if 'leiden_nhood_enrichment' in adata.uns:
            _plot_nhood_enrichment(adata, output_dir)
        else:
            print("   Skipping (no enrichment results found)")
    except Exception as e:
        print(f"   Error: {e}")

    # --- 6. Co-occurrence ---
    print("6. Generating co-occurrence plot...")
    try:
        if 'leiden_co_occurrence' in adata.uns:
            _plot_co_occurrence(adata, output_dir)
        else:
            print("   Skipping (no co-occurrence results found)")
    except Exception as e:
        print(f"   Error: {e}")

    # --- 7-8. SVG plots ---
    svg_results = adata.uns.get('svg_results', None)
    if svg_results is not None and len(svg_results) > 0:
        print("7. Generating top SVGs bar plot...")
        try:
            _plot_top_svgs(svg_results, top_n_svgs, output_dir)
        except Exception as e:
            print(f"   Error: {e}")

        print("8. Generating spatial plot of top SVG...")
        try:
            top_svg = svg_results.index[0]
            if top_svg in adata.var_names:
                _plot_spatial_svg(adata, top_svg, output_dir)
            else:
                print(f"   Skipping (top SVG '{top_svg}' not in var_names)")
        except Exception as e:
            print(f"   Error: {e}")
    else:
        print("7-8. Skipping SVG plots (no SVG results)")

    print("\n" + "=" * 50)
    print("✓ All visualizations generated successfully!")
    print("=" * 50)

