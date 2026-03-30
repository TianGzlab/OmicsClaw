"""
Generate all trajectory visualizations.

Produces 12-15 publication-quality plots across three analysis levels:
  Core: PAGA graph, pseudotime UMAP, violin, diffusion components, gene heatmap, gene trends
  Velocity: stream UMAP, confidence, latent time, top velocity genes
  CellRank: fate probabilities UMAP, fate heatmap, driver genes

All custom plots use seaborn with sns.set_style("ticks") + Helvetica.
scanpy/scVelo native plots (sc.pl.*, scv.pl.*) use their own rendering.
Heatmaps use seaborn.clustermap() per project standard.
All saved as PNG (300 DPI) + SVG with graceful fallback.

Usage:
  from scripts.generate_all_plots import generate_all_plots
  generate_all_plots(adata, results, output_dir="trajectory_results")
"""

import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

# Project plotting standard
sns.set_style("ticks")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Helvetica"]
plt.rcParams["figure.dpi"] = 300


def generate_all_plots(adata, results, output_dir="trajectory_results", cluster_key="clusters"):
    """
    Generate all trajectory visualizations.

    Parameters
    ----------
    adata : AnnData
        AnnData with trajectory results computed.
    results : dict
        Output from run_trajectory().
    output_dir : str
        Directory to save plots.
    cluster_key : str
        Column in adata.obs with cluster labels.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("GENERATING TRAJECTORY VISUALIZATIONS")
    print("=" * 60)

    n_plots = 0

    # =====================================================================
    # Core trajectory plots (always generated)
    # =====================================================================
    print("\n--- Core Trajectory Plots ---")

    # 1. PAGA graph
    try:
        _plot_paga(adata, cluster_key, output_dir)
        n_plots += 1
    except Exception as e:
        print(f"  Warning: PAGA plot failed: {e}")

    # 2. Pseudotime UMAP
    try:
        _plot_pseudotime_umap(adata, cluster_key, output_dir)
        n_plots += 1
    except Exception as e:
        print(f"  Warning: Pseudotime UMAP failed: {e}")

    # 3. Pseudotime violin
    try:
        _plot_pseudotime_violin(adata, results, cluster_key, output_dir)
        n_plots += 1
    except Exception as e:
        print(f"  Warning: Pseudotime violin failed: {e}")

    # 4. Diffusion components
    try:
        _plot_diffusion_components(adata, cluster_key, output_dir)
        n_plots += 1
    except Exception as e:
        print(f"  Warning: Diffusion components plot failed: {e}")

    # 5. Gene expression heatmap along pseudotime
    try:
        _plot_gene_heatmap(adata, results, output_dir)
        n_plots += 1
    except Exception as e:
        print(f"  Warning: Gene heatmap failed: {e}")

    # 6. Gene expression trends along pseudotime
    try:
        _plot_gene_trends(adata, results, output_dir)
        n_plots += 1
    except Exception as e:
        print(f"  Warning: Gene trends plot failed: {e}")

    # 7. PAGA-based cell type connectivity
    try:
        _plot_paga_connectivity(adata, results, cluster_key, output_dir)
        n_plots += 1
    except Exception as e:
        print(f"  Warning: PAGA connectivity plot failed: {e}")

    # =====================================================================
    # RNA velocity plots (if available)
    # =====================================================================
    if results.get("velocity_results"):
        print("\n--- RNA Velocity Plots ---")

        # 8. Velocity stream UMAP
        try:
            _plot_velocity_stream(adata, cluster_key, output_dir)
            n_plots += 1
        except Exception as e:
            print(f"  Warning: Velocity stream plot failed: {e}")

        # 9. Velocity confidence
        try:
            _plot_velocity_confidence(adata, output_dir)
            n_plots += 1
        except Exception as e:
            print(f"  Warning: Velocity confidence plot failed: {e}")

        # 10. Latent time
        if results["velocity_results"].get("has_latent_time"):
            try:
                _plot_latent_time(adata, cluster_key, output_dir)
                n_plots += 1
            except Exception as e:
                print(f"  Warning: Latent time plot failed: {e}")

        # 11. Top velocity genes
        try:
            _plot_top_velocity_genes(adata, results, output_dir)
            n_plots += 1
        except Exception as e:
            print(f"  Warning: Velocity genes plot failed: {e}")

    # =====================================================================
    # CellRank plots (if available)
    # =====================================================================
    if results.get("cellrank_results"):
        print("\n--- CellRank Fate Mapping Plots ---")

        # 12. Fate probabilities UMAP
        try:
            _plot_fate_probabilities(adata, results, cluster_key, output_dir)
            n_plots += 1
        except Exception as e:
            print(f"  Warning: Fate probabilities plot failed: {e}")

        # 13. Fate probability heatmap
        try:
            _plot_fate_heatmap(adata, results, cluster_key, output_dir)
            n_plots += 1
        except Exception as e:
            print(f"  Warning: Fate heatmap failed: {e}")

        # 14. Driver genes
        try:
            _plot_driver_genes(adata, results, output_dir)
            n_plots += 1
        except Exception as e:
            print(f"  Warning: Driver genes plot failed: {e}")

    print(f"\n✓ All plots generated successfully! ({n_plots} plots)")


# ---------------------------------------------------------------------------
# Save helper
# ---------------------------------------------------------------------------


def _save_plot(fig, base_path, dpi=300):
    """Save figure as PNG + SVG with graceful SVG fallback."""
    base_path = Path(base_path)
    base_path.parent.mkdir(parents=True, exist_ok=True)

    # Always save PNG
    png_path = base_path.with_suffix(".png")
    fig.savefig(png_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    print(f"   Saved: {png_path}")

    # Always try SVG
    svg_path = base_path.with_suffix(".svg")
    try:
        fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
        print(f"   Saved: {svg_path}")
    except Exception:
        print(f"   (SVG export failed, PNG available)")

    plt.close(fig)


# ---------------------------------------------------------------------------
# Core trajectory plots
# ---------------------------------------------------------------------------


def _plot_paga(adata, cluster_key, output_dir):
    """Plot PAGA graph with cluster connectivity."""
    import scanpy as sc

    print("  Plotting PAGA graph...")
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Left: PAGA graph
    sc.pl.paga(
        adata,
        color=cluster_key,
        ax=axes[0],
        show=False,
        frameon=False,
        fontsize=10,
        node_size_scale=1.5,
    )
    axes[0].set_title("PAGA Cluster Connectivity", fontsize=14, fontweight="bold")

    # Right: UMAP with clusters
    sc.pl.umap(
        adata,
        color=cluster_key,
        ax=axes[1],
        show=False,
        frameon=False,
        legend_loc="on data",
        legend_fontsize=8,
    )
    axes[1].set_title("UMAP (PAGA-initialized)", fontsize=14, fontweight="bold")

    fig.tight_layout()
    _save_plot(fig, output_dir / "paga_graph")


def _plot_pseudotime_umap(adata, cluster_key, output_dir):
    """Plot UMAP colored by diffusion pseudotime."""
    import scanpy as sc

    print("  Plotting pseudotime UMAP...")
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Left: colored by pseudotime
    sc.pl.umap(
        adata,
        color="dpt_pseudotime",
        ax=axes[0],
        show=False,
        frameon=False,
        color_map="viridis",
    )
    axes[0].set_title("Diffusion Pseudotime", fontsize=14, fontweight="bold")

    # Right: colored by cell type for reference
    sc.pl.umap(
        adata,
        color=cluster_key,
        ax=axes[1],
        show=False,
        frameon=False,
        legend_loc="on data",
        legend_fontsize=8,
    )
    axes[1].set_title("Cell Types", fontsize=14, fontweight="bold")

    fig.tight_layout()
    _save_plot(fig, output_dir / "pseudotime_umap")


def _plot_pseudotime_violin(adata, results, cluster_key, output_dir):
    """Violin plot of pseudotime distribution per cell type."""
    print("  Plotting pseudotime violin...")

    pt = adata.obs["dpt_pseudotime"].copy()
    valid = ~np.isinf(pt)
    df = pd.DataFrame({
        "Pseudotime": pt[valid],
        "Cell Type": adata.obs[cluster_key][valid],
    })

    # Order cell types by median pseudotime
    order = df.groupby("Cell Type")["Pseudotime"].median().sort_values().index.tolist()

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.violinplot(
        data=df,
        x="Cell Type",
        y="Pseudotime",
        order=order,
        ax=ax,
        inner="box",
        palette="viridis",
        cut=0,
    )
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right", fontsize=9)
    ax.set_title("Pseudotime Distribution by Cell Type", fontsize=14, fontweight="bold")
    ax.set_ylabel("Diffusion Pseudotime", fontsize=11)
    ax.set_xlabel("", fontsize=11)
    sns.despine()
    fig.tight_layout()
    _save_plot(fig, output_dir / "pseudotime_violin")


def _plot_diffusion_components(adata, cluster_key, output_dir):
    """Plot first 3 diffusion map components."""
    print("  Plotting diffusion components...")

    if "X_diffmap" not in adata.obsm:
        print("    No diffusion map computed — skipping")
        return

    diffmap = adata.obsm["X_diffmap"]
    clusters = adata.obs[cluster_key]
    categories = (clusters.cat.categories.tolist()
                  if hasattr(clusters, "cat") else sorted(clusters.unique().tolist()))
    palette = sns.color_palette("tab20", len(categories))
    color_map = {cat: palette[i] for i, cat in enumerate(categories)}
    colors = [color_map[c] for c in clusters]

    fig, axes = plt.subplots(1, 3, figsize=(20, 6))
    pairs = [(0, 1), (0, 2), (1, 2)]
    for ax, (i, j) in zip(axes, pairs):
        ax.scatter(diffmap[:, i], diffmap[:, j], c=colors, s=5, alpha=0.6)
        ax.set_xlabel(f"DC{i+1}", fontsize=10)
        ax.set_ylabel(f"DC{j+1}", fontsize=10)
        ax.set_title(f"DC{i+1} vs DC{j+1}", fontsize=12, fontweight="bold")
        sns.despine(ax=ax)

    # Add legend to last panel
    from matplotlib.lines import Line2D
    handles = [Line2D([0], [0], marker='o', color='w', markerfacecolor=color_map[c],
                       markersize=6, label=c) for c in categories]
    axes[2].legend(handles=handles, bbox_to_anchor=(1.05, 1), loc="upper left",
                   fontsize=8, frameon=False)

    fig.suptitle("Diffusion Map Components", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    _save_plot(fig, output_dir / "diffusion_components")


def _plot_gene_heatmap(adata, results, output_dir, n_genes=50):
    """
    Heatmap of top trajectory genes ordered by pseudotime.
    Uses seaborn.clustermap() per project standard.
    """
    print("  Plotting gene expression heatmap...")

    traj_genes = results.get("trajectory_genes")
    if traj_genes is None or len(traj_genes) == 0:
        print("    No trajectory genes to plot — skipping heatmap")
        return

    genes = traj_genes["gene"].head(n_genes).tolist()
    genes_in_data = [g for g in genes if g in adata.var_names]
    if len(genes_in_data) < 5:
        print("    Too few trajectory genes found in data — skipping heatmap")
        return

    # Get pseudotime and sort cells
    pt = adata.obs["dpt_pseudotime"].copy()
    valid = ~np.isinf(pt) & ~np.isnan(pt)
    cell_order = pt[valid].sort_values().index

    # Get expression matrix for selected genes
    X = adata[cell_order, genes_in_data].X
    if hasattr(X, "toarray"):
        X = X.toarray()

    # Z-score normalize per gene
    from scipy import stats
    X_z = stats.zscore(X, axis=0)
    X_z = np.nan_to_num(X_z, nan=0.0)

    # Subsample cells for readability (max 500)
    if X_z.shape[0] > 500:
        idx = np.linspace(0, X_z.shape[0] - 1, 500, dtype=int)
        X_z = X_z[idx, :]

    df = pd.DataFrame(X_z, columns=genes_in_data)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = sns.clustermap(
            df.T,
            cmap="RdBu_r",
            center=0,
            figsize=(14, max(8, len(genes_in_data) * 0.2)),
            col_cluster=False,  # Don't reorder cells — keep pseudotime order
            row_cluster=True,
            cbar_kws={"label": "Z-score"},
            dendrogram_ratio=(0.1, 0.02),
            xticklabels=False,
            yticklabels=True if len(genes_in_data) <= 50 else False,
        )
        g.ax_heatmap.set_xlabel("Cells (ordered by pseudotime)", fontsize=10)
        g.ax_heatmap.set_ylabel("Genes", fontsize=10)
        g.fig.suptitle(
            f"Top {len(genes_in_data)} Trajectory Genes",
            fontsize=14, fontweight="bold", y=1.01,
        )

    base_path = output_dir / "gene_heatmap"
    _save_plot(g.fig, base_path)


def _plot_gene_trends(adata, results, output_dir, n_genes=8):
    """Smoothed gene expression trends along pseudotime."""
    print("  Plotting gene expression trends...")

    traj_genes = results.get("trajectory_genes")
    if traj_genes is None or len(traj_genes) == 0:
        print("    No trajectory genes — skipping trends")
        return

    genes = traj_genes["gene"].head(n_genes).tolist()
    genes_in_data = [g for g in genes if g in adata.var_names]
    if len(genes_in_data) < 2:
        print("    Too few genes — skipping trends")
        return

    pt = adata.obs["dpt_pseudotime"].values
    valid = ~np.isinf(pt) & ~np.isnan(pt)

    ncols = min(4, len(genes_in_data))
    nrows = int(np.ceil(len(genes_in_data) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3.5 * nrows))
    if nrows == 1 and ncols == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    for i, gene in enumerate(genes_in_data):
        ax = axes[i]
        expr = adata[valid, gene].X
        if hasattr(expr, "toarray"):
            expr = expr.toarray()
        expr = expr.flatten()

        df_g = pd.DataFrame({"pseudotime": pt[valid], "expression": expr})
        sns.scatterplot(
            data=df_g, x="pseudotime", y="expression",
            ax=ax, s=3, alpha=0.3, color="gray", linewidth=0,
        )
        # Smoothed trend
        try:
            from scipy.ndimage import uniform_filter1d
            sort_idx = np.argsort(df_g["pseudotime"].values)
            x_sorted = df_g["pseudotime"].values[sort_idx]
            y_sorted = df_g["expression"].values[sort_idx]
            window = max(len(x_sorted) // 50, 10)
            y_smooth = uniform_filter1d(y_sorted.astype(float), size=window)
            ax.plot(x_sorted, y_smooth, color="red", linewidth=2)
        except Exception:
            pass

        corr = traj_genes[traj_genes["gene"] == gene]["correlation"].values
        corr_str = f" (r={corr[0]:.2f})" if len(corr) > 0 else ""
        ax.set_title(f"{gene}{corr_str}", fontsize=10, fontweight="bold")
        ax.set_xlabel("Pseudotime", fontsize=9)
        ax.set_ylabel("Expression", fontsize=9)
        sns.despine(ax=ax)

    # Hide unused axes
    for j in range(len(genes_in_data), len(axes)):
        axes[j].set_visible(False)

    fig.suptitle("Gene Expression Along Pseudotime", fontsize=14, fontweight="bold")
    fig.tight_layout()
    _save_plot(fig, output_dir / "gene_trends")


def _plot_paga_connectivity(adata, results, cluster_key, output_dir):
    """PAGA connectivity heatmap between clusters. Uses seaborn.clustermap() per project standard."""
    print("  Plotting PAGA connectivity heatmap...")

    conn = results.get("paga_connectivities")
    if conn is None:
        return

    col = adata.obs[cluster_key]
    labels = (col.cat.categories.tolist()
              if hasattr(col, "cat") else sorted(col.unique().tolist()))
    conn_df = pd.DataFrame(conn, index=labels, columns=labels)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = sns.clustermap(
            conn_df,
            cmap="YlOrRd",
            figsize=(max(8, len(labels) * 0.8), max(7, len(labels) * 0.7)),
            linewidths=0.5,
            cbar_kws={"label": "PAGA connectivity"},
            annot=True,
            fmt=".2f",
            annot_kws={"fontsize": 8},
            dendrogram_ratio=0.1,
        )
        g.fig.suptitle(
            "PAGA Cluster Connectivity",
            fontsize=14, fontweight="bold", y=1.02,
        )
        plt.setp(g.ax_heatmap.get_xticklabels(), rotation=45, ha="right", fontsize=9)
        plt.setp(g.ax_heatmap.get_yticklabels(), rotation=0, fontsize=9)

    _save_plot(g.fig, output_dir / "paga_connectivity")


# ---------------------------------------------------------------------------
# RNA velocity plots (scVelo)
# ---------------------------------------------------------------------------


def _plot_velocity_stream(adata, cluster_key, output_dir):
    """RNA velocity stream plot on UMAP."""
    import scvelo as scv

    print("  Plotting velocity stream...")
    fig, ax = plt.subplots(figsize=(10, 8))
    scv.pl.velocity_embedding_stream(
        adata,
        basis="umap",
        color=cluster_key,
        ax=ax,
        show=False,
        legend_loc="right margin",
        frameon=False,
    )
    ax.set_title("RNA Velocity Stream", fontsize=14, fontweight="bold")
    _save_plot(fig, output_dir / "velocity_stream")


def _plot_velocity_confidence(adata, output_dir):
    """Velocity confidence on UMAP."""
    import scanpy as sc

    if "velocity_confidence" not in adata.obs.columns:
        return

    print("  Plotting velocity confidence...")
    fig, ax = plt.subplots(figsize=(10, 8))
    sc.pl.umap(
        adata,
        color="velocity_confidence",
        ax=ax,
        show=False,
        frameon=False,
        color_map="magma",
    )
    ax.set_title("Velocity Confidence", fontsize=14, fontweight="bold")
    _save_plot(fig, output_dir / "velocity_confidence")


def _plot_latent_time(adata, cluster_key, output_dir):
    """scVelo latent time on UMAP."""
    import scanpy as sc

    if "latent_time" not in adata.obs.columns:
        return

    print("  Plotting latent time...")
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    sc.pl.umap(
        adata,
        color="latent_time",
        ax=axes[0],
        show=False,
        frameon=False,
        color_map="viridis",
    )
    axes[0].set_title("scVelo Latent Time", fontsize=14, fontweight="bold")

    sc.pl.umap(
        adata,
        color=cluster_key,
        ax=axes[1],
        show=False,
        frameon=False,
        legend_loc="on data",
        legend_fontsize=8,
    )
    axes[1].set_title("Cell Types (reference)", fontsize=14, fontweight="bold")

    fig.tight_layout()
    _save_plot(fig, output_dir / "latent_time")


def _plot_top_velocity_genes(adata, results, output_dir):
    """Phase portraits for top velocity genes."""
    import scvelo as scv

    vel_results = results.get("velocity_results", {})
    vel_genes = vel_results.get("velocity_genes")
    if vel_genes is None or len(vel_genes) == 0:
        return

    top_genes = vel_genes["gene"].head(4).tolist()
    top_genes = [g for g in top_genes if g in adata.var_names]
    if len(top_genes) == 0:
        return

    print("  Plotting top velocity genes...")
    fig, axes = plt.subplots(1, len(top_genes), figsize=(5 * len(top_genes), 4))
    if len(top_genes) == 1:
        axes = [axes]

    for ax, gene in zip(axes, top_genes):
        try:
            scv.pl.velocity(adata, var_names=[gene], ax=ax, show=False, frameon=False)
        except Exception:
            ax.text(0.5, 0.5, f"{gene}\n(plot failed)", ha="center", va="center",
                    transform=ax.transAxes)
        ax.set_title(gene, fontsize=11, fontweight="bold")

    fig.suptitle("Top Velocity Genes (Phase Portraits)", fontsize=14, fontweight="bold")
    fig.tight_layout()
    _save_plot(fig, output_dir / "velocity_top_genes")


# ---------------------------------------------------------------------------
# CellRank plots
# ---------------------------------------------------------------------------


def _plot_fate_probabilities(adata, results, cluster_key, output_dir):
    """UMAP colored by fate probability for each terminal state."""
    import scanpy as sc

    cr_results = results["cellrank_results"]
    fate_df = cr_results["fate_probabilities"]
    terminal_states = cr_results["terminal_states"]

    n_states = len(terminal_states)
    if n_states == 0:
        return

    print("  Plotting fate probabilities...")
    ncols = min(3, n_states)
    nrows = int(np.ceil(n_states / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 5 * nrows))
    if n_states == 1:
        axes = np.array([axes])
    axes = np.array(axes).flatten()

    # Add temporary columns and ensure cleanup even on failure
    temp_cols = []
    try:
        for i, state in enumerate(terminal_states):
            ax = axes[i]
            col = f"fate_{state}"
            adata.obs[col] = fate_df[state].values
            temp_cols.append(col)
            sc.pl.umap(
                adata,
                color=col,
                ax=ax,
                show=False,
                frameon=False,
                color_map="RdYlBu_r",
                vmin=0,
                vmax=1,
            )
            ax.set_title(f"P(fate -> {state})", fontsize=12, fontweight="bold")

        for j in range(n_states, len(axes)):
            axes[j].set_visible(False)

        fig.suptitle("Cell Fate Probabilities", fontsize=14, fontweight="bold")
        fig.tight_layout()
        _save_plot(fig, output_dir / "fate_probabilities")
    finally:
        # Always clean up temporary columns and close figure on error
        for col in temp_cols:
            if col in adata.obs.columns:
                del adata.obs[col]
        if not plt.fignum_exists(fig.number):
            return  # _save_plot already closed it
        plt.close(fig)


def _plot_fate_heatmap(adata, results, cluster_key, output_dir):
    """Heatmap of mean fate probability per cluster. Uses seaborn.clustermap()."""
    cr_results = results["cellrank_results"]
    fate_df = cr_results["fate_probabilities"]
    terminal_states = cr_results["terminal_states"]

    if len(terminal_states) < 2:
        return

    print("  Plotting fate probability heatmap...")

    # Compute mean fate probability per cell type (use copy to avoid mutating original)
    fate_with_ct = fate_df.copy()
    fate_with_ct["cell_type"] = adata.obs[cluster_key].values
    mean_fates = fate_with_ct.groupby("cell_type")[terminal_states].mean()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = sns.clustermap(
            mean_fates,
            cmap="RdYlBu_r",
            figsize=(max(6, len(terminal_states) * 1.5), max(6, len(mean_fates) * 0.6)),
            cbar_kws={"label": "Fate Probability"},
            annot=True,
            fmt=".2f",
            annot_kws={"fontsize": 9},
            linewidths=0.5,
        )
        g.fig.suptitle(
            "Mean Fate Probability per Cell Type",
            fontsize=14, fontweight="bold", y=1.02,
        )

    _save_plot(g.fig, output_dir / "fate_heatmap")


def _plot_driver_genes(adata, results, output_dir, n_genes=10):
    """Top driver genes per terminal fate."""
    cr_results = results["cellrank_results"]
    driver_genes = cr_results.get("driver_genes", {})

    non_empty = {k: v for k, v in driver_genes.items() if len(v) > 0}
    if not non_empty:
        return

    print("  Plotting driver genes...")
    n_states = len(non_empty)
    fig, axes = plt.subplots(1, n_states, figsize=(5 * n_states, 6))
    if n_states == 1:
        axes = [axes]

    for ax, (state, df) in zip(axes, non_empty.items()):
        top = df.head(n_genes)
        if "index" in top.columns:
            gene_col = "index"
        else:
            gene_col = top.columns[0]

        score_col = [c for c in top.columns if c != gene_col]
        if score_col:
            y_vals = top[score_col[0]].values
            y_label = score_col[0]
        else:
            y_vals = range(len(top))
            y_label = "rank"

        ax.barh(range(len(top)), y_vals, color=sns.color_palette("viridis", len(top)))
        ax.set_yticks(range(len(top)))
        ax.set_yticklabels(top[gene_col].values, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel(y_label, fontsize=10)
        ax.set_title(f"Drivers -> {state}", fontsize=12, fontweight="bold")
        sns.despine(ax=ax)

    fig.suptitle("Top Driver Genes per Cell Fate", fontsize=14, fontweight="bold")
    fig.tight_layout()
    _save_plot(fig, output_dir / "driver_genes")

