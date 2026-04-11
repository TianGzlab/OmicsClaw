#!/usr/bin/env python3
"""Gene Regulatory Network inference utilities using pySCENIC.

Provides GRN inference workflow:
1. GRNBoost2 for co-expression network inference
2. cisTarget for motif enrichment and pruning
3. AUCell for regulon activity scoring

Based on validated reference scripts from biomni_scripts/grn-pyscenic-scripts/

Requirements:
    - arboreto (GRNBoost2)
    - pyscenic
    - External databases: TF list, cisTarget DBs, motif annotations
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def check_pyscenic_available() -> bool:
    """Check if pySCENIC and dependencies are available."""
    try:
        import pyscenic
        import arboreto
        return True
    except ImportError:
        logger.warning("pySCENIC or arboreto not installed")
        return False


def check_database_files(
    tf_list_file: str | Path,
    database_glob: str,
    motif_annotations_file: str | Path,
) -> dict[str, bool]:
    """Check if required database files exist.

    Parameters
    ----------
    tf_list_file : str or Path
        Path to TF list file (one TF name per line)
    database_glob : str
        Glob pattern for cisTarget database files (.feather or .db)
    motif_annotations_file : str or Path
        Path to motif annotations file (.tbl or .csv)

    Returns
    -------
    dict with file existence status
    """
    import glob

    status = {
        "tf_list": Path(tf_list_file).exists(),
        "databases": len(glob.glob(database_glob)) > 0,
        "motif_annotations": Path(motif_annotations_file).exists(),
    }

    missing = [k for k, v in status.items() if not v]
    if missing:
        logger.warning(f"Missing database files: {missing}")

    return status


def load_tf_list(tf_list_file: str | Path) -> list[str]:
    """Load list of transcription factors from file.

    Parameters
    ----------
    tf_list_file : str or Path
        Path to TF list file (one TF name per line)

    Returns
    -------
    List of TF gene symbols
    """
    tf_list_file = Path(tf_list_file)

    if not tf_list_file.exists():
        raise FileNotFoundError(f"TF list file not found: {tf_list_file}")

    with open(tf_list_file, "r") as f:
        tfs = [line.strip() for line in f if line.strip()]

    logger.info(f"Loaded {len(tfs)} transcription factors from {tf_list_file}")
    return tfs


def prepare_expression_matrix(adata, layer: str | None = None) -> pd.DataFrame:
    """Prepare expression matrix for GRN inference.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    layer : str, optional
        Layer to use (default: adata.X)

    Returns
    -------
    DataFrame with genes as columns and cells as rows
    """
    if layer is not None:
        X = adata.layers[layer]
        var_names = adata.var_names
    elif "counts" in adata.layers:
        X = adata.layers["counts"]
        var_names = adata.var_names
    elif adata.raw is not None and adata.raw.shape == adata.shape:
        X = adata.raw.X
        var_names = adata.raw.var_names
    else:
        X = adata.X
        var_names = adata.var_names

    if hasattr(X, "toarray"):
        X = X.toarray()

    df = pd.DataFrame(
        X,
        index=adata.obs_names,
        columns=var_names,
    )

    return df


def run_correlation_grn(
    ex_matrix: pd.DataFrame,
    tf_list: list[str],
    method: str = "spearman",
    n_top: int = 50,
) -> pd.DataFrame:
    """Run simple correlation-based GRN inference as fallback.

    This is a simpler alternative to GRNBoost2 that doesn't require dask.
    It computes correlation between TFs and all genes, then returns top correlations.

    Parameters
    ----------
    ex_matrix : DataFrame
        Expression matrix (cells x genes)
    tf_list : list of str
        List of transcription factors
    method : str
        Correlation method: 'spearman' or 'pearson'
    n_top : int
        Number of top targets per TF to return

    Returns
    -------
    DataFrame with columns: TF, target, importance
    """
    import numpy as np
    from scipy import stats

    logger.info(f"Running correlation-based GRN inference ({method})...")
    logger.info(f"Expression matrix: {ex_matrix.shape[0]} cells x {ex_matrix.shape[1]} genes")

    # Filter TFs to those in the expression matrix
    available_tfs = [tf for tf in tf_list if tf in ex_matrix.columns]
    if not available_tfs:
        raise ValueError("None of the provided TFs are in the expression matrix")

    logger.info(f"Using {len(available_tfs)} TFs from the list")

    # Get TF expression
    tf_expr = ex_matrix[available_tfs]

    # Get target genes (all genes except TFs)
    target_genes = [g for g in ex_matrix.columns if g not in available_tfs]

    results = []

    # Compute correlations for each TF
    for tf in available_tfs:
        tf_values = tf_expr[tf].values

        # Compute correlation with all targets
        correlations = []
        for target in target_genes:
            target_values = ex_matrix[target].values

            if method == "spearman":
                corr, _ = stats.spearmanr(tf_values, target_values)
            else:  # pearson
                corr, _ = stats.pearsonr(tf_values, target_values)

            if not np.isnan(corr):
                correlations.append((target, abs(corr)))

        # Sort by absolute correlation and take top n
        correlations.sort(key=lambda x: x[1], reverse=True)
        for target, importance in correlations[:n_top]:
            results.append({
                "TF": tf,
                "target": target,
                "importance": importance,
            })

    adjacencies = pd.DataFrame(results)
    logger.info(f"Generated {len(adjacencies)} TF-target adjacencies")
    return adjacencies


def run_grnboost2(
    ex_matrix: pd.DataFrame,
    tf_list: list[str],
    seed: int = 42,
    n_jobs: int = 4,
    verbose: bool = True,
) -> pd.DataFrame:
    """Run GRNBoost2 co-expression network inference.

    Parameters
    ----------
    ex_matrix : DataFrame
        Expression matrix (cells x genes)
    tf_list : list of str
        List of transcription factors
    seed : int
        Random seed for reproducibility
    n_jobs : int
        Number of parallel jobs (not used, arboreto uses dask)
    verbose : bool
        Print progress information

    Returns
    -------
    DataFrame with columns: TF, target, importance
    """
    try:
        from arboreto.algo import grnboost2
    except ImportError:
        raise ImportError(
            "arboreto package required for GRNBoost2. "
            "Install with: pip install arboreto"
        )

    logger.info(f"Running GRNBoost2 with {len(tf_list)} TFs...")
    logger.info(f"Expression matrix: {ex_matrix.shape[0]} cells x {ex_matrix.shape[1]} genes")

    # Suppress dask distributed logging noise
    import logging as py_logging
    dask_logger = py_logging.getLogger("distributed")
    old_level = dask_logger.level
    dask_logger.setLevel(py_logging.WARNING)

    try:
        # Run GRNBoost2 with local dask cluster (default behavior)
        adjacencies = grnboost2(
            expression_data=ex_matrix,
            tf_names=tf_list,
            seed=seed,
            verbose=verbose,
            client_or_address="local",
        )
        logger.info(f"Generated {len(adjacencies)} TF-target adjacencies")
        return adjacencies
    finally:
        # Restore logging level
        dask_logger.setLevel(old_level)
        # Clean up any lingering dask client
        try:
            from dask.distributed import get_client
            client = get_client()
            client.close()
        except ValueError:
            pass  # No active client


def run_cistarget_pruning(
    adjacencies: pd.DataFrame,
    database_glob: str,
    motif_annotations_file: str | Path,
    rank_threshold: int = 5000,
    auc_threshold: float = 0.05,
    nes_threshold: float = 3.0,
    n_jobs: int = 4,
) -> tuple[pd.DataFrame, list]:
    """Run cisTarget motif enrichment and network pruning.

    Parameters
    ----------
    adjacencies : DataFrame
        TF-target adjacencies from GRNBoost2
    database_glob : str
        Glob pattern for cisTarget database files
    motif_annotations_file : str or Path
        Path to motif annotations file
    rank_threshold : int
        Maximum rank threshold for motif enrichment
    auc_threshold : float
        AUC threshold for motif enrichment
    nes_threshold : float
        NES threshold for significant motifs
    n_jobs : int
        Number of parallel jobs

    Returns
    -------
    Tuple of (motif_enrichment_df, modules_list)
    """
    try:
        from pyscenic.prune import prune2df
        from pyscenic.utils import modules_from_adjacencies
    except ImportError:
        raise ImportError(
            "pyscenic package required for cisTarget pruning. "
            "Install with: pip install pyscenic"
        )

    import glob
    db_fnames = glob.glob(database_glob)

    if not db_fnames:
        raise FileNotFoundError(f"No database files found: {database_glob}")

    logger.info(f"Running cisTarget pruning with {len(db_fnames)} databases...")

    # Create modules from adjacencies
    modules = list(modules_from_adjacencies(adjacencies, ex_matrix=None))

    logger.info(f"Created {len(modules)} modules from adjacencies")

    # Run pruning
    df_motifs = prune2df(
        modules,
        db_fnames,
        motif_annotations_file,
        rank_threshold=rank_threshold,
        auc_threshold=auc_threshold,
        nes_threshold=nes_threshold,
        num_workers=n_jobs,
    )

    logger.info(f"Pruned to {len(df_motifs)} significant motif enrichments")

    return df_motifs, modules


def derive_regulons(
    motif_enrichment: pd.DataFrame,
    adjacencies: pd.DataFrame,
    n_top_targets: int = 50,
) -> list[dict]:
    """Derive regulons from motif enrichment results.

    Parameters
    ----------
    motif_enrichment : DataFrame
        Motif enrichment results from cisTarget
    adjacencies : DataFrame
        Original TF-target adjacencies
    n_top_targets : int
        Maximum targets per regulon

    Returns
    -------
    List of regulon dictionaries with keys: tf, targets, score
    """
    regulons = []

    # Group by TF
    tf_motifs = motif_enrichment.groupby("TF")

    for tf, group in tf_motifs:
        # Get top enriched motifs for this TF
        top_motif = group.nlargest(1, "NES")

        # Get targets for this TF from adjacencies
        tf_targets = adjacencies[adjacencies["TF"] == tf].nlargest(n_top_targets, "importance")
        targets = tf_targets["target"].tolist()

        if len(targets) > 0:
            regulons.append({
                "tf": tf,
                "targets": targets,
                "n_targets": len(targets),
                "motif_nes": top_motif["NES"].values[0] if len(top_motif) > 0 else None,
            })

    logger.info(f"Derived {len(regulons)} regulons")
    return regulons


def run_aucell_scoring(
    ex_matrix: pd.DataFrame,
    regulons: list[dict],
    seed: int = 42,
    n_jobs: int = 4,
) -> pd.DataFrame:
    """Run AUCell regulon activity scoring.

    Parameters
    ----------
    ex_matrix : DataFrame
        Expression matrix (cells x genes)
    regulons : list of dict
        List of regulons with 'tf' and 'targets' keys
    seed : int
        Random seed
    n_jobs : int
        Number of parallel jobs

    Returns
    -------
    DataFrame with AUC scores (cells x regulons)
    """
    try:
        from pyscenic.aucell import aucell
    except ImportError:
        raise ImportError(
            "pyscenic package required for AUCell. "
            "Install with: pip install pyscenic"
        )

    logger.info(f"Running AUCell scoring for {len(regulons)} regulons...")

    # Convert regulons to required format
    from pyscenic.genesig import GeneSignature

    signatures = [
        GeneSignature(
            name=f"{r['tf']}(+)",
            gene2weight={g: 1.0 for g in r["targets"]},
        )
        for r in regulons
    ]

    # Run AUCell
    auc_mtx = aucell(
        ex_matrix,
        signatures,
        seed=seed,
        num_workers=n_jobs,
    )

    logger.info(f"AUCell matrix: {auc_mtx.shape[0]} cells x {auc_mtx.shape[1]} regulons")

    return auc_mtx


def run_complete_grn_workflow(
    adata,
    tf_list_file: str | Path,
    database_glob: str,
    motif_annotations_file: str | Path,
    layer: str | None = None,
    n_top_targets: int = 50,
    n_jobs: int = 4,
    seed: int = 42,
) -> dict[str, Any]:
    """Run complete GRN inference workflow.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    tf_list_file : str or Path
        Path to TF list file
    database_glob : str
        Glob pattern for cisTarget database files
    motif_annotations_file : str or Path
        Path to motif annotations file
    layer : str, optional
        Layer to use for expression
    n_top_targets : int
        Maximum targets per regulon
    n_jobs : int
        Number of parallel jobs
    seed : int
        Random seed

    Returns
    -------
    dict with keys:
        - 'adjacencies': TF-target adjacencies DataFrame
        - 'motif_enrichment': Motif enrichment DataFrame
        - 'regulons': List of regulon dictionaries
        - 'auc_matrix': AUCell activity scores DataFrame
    """
    # Check databases
    db_status = check_database_files(tf_list_file, database_glob, motif_annotations_file)
    if not all(db_status.values()):
        raise FileNotFoundError(f"Missing database files: {db_status}")

    # Load TF list
    tf_list = load_tf_list(tf_list_file)

    # Prepare expression matrix
    logger.info("Preparing expression matrix...")
    ex_matrix = prepare_expression_matrix(adata, layer=layer)

    # Step 1: GRNBoost2
    logger.info("Step 1/3: Running GRNBoost2...")
    adjacencies = run_grnboost2(ex_matrix, tf_list, seed=seed, n_jobs=n_jobs)

    # Step 2: cisTarget pruning
    logger.info("Step 2/3: Running cisTarget pruning...")
    motif_enrichment, modules = run_cistarget_pruning(
        adjacencies,
        database_glob,
        motif_annotations_file,
        n_jobs=n_jobs,
    )

    # Derive regulons
    logger.info("Deriving regulons...")
    regulons = derive_regulons(motif_enrichment, adjacencies, n_top_targets=n_top_targets)

    # Step 3: AUCell scoring
    logger.info("Step 3/3: Running AUCell scoring...")
    auc_matrix = run_aucell_scoring(ex_matrix, regulons, seed=seed, n_jobs=n_jobs)

    logger.info("GRN workflow complete!")

    return {
        "adjacencies": adjacencies,
        "motif_enrichment": motif_enrichment,
        "regulons": regulons,
        "auc_matrix": auc_matrix,
    }


def export_grn_results(
    output_dir: str | Path,
    adjacencies: pd.DataFrame,
    regulons: list[dict],
    auc_matrix: pd.DataFrame,
    prefix: str = "grn",
) -> dict[str, str]:
    """Export GRN results to files.

    Parameters
    ----------
    output_dir : str or Path
        Output directory
    adjacencies : DataFrame
        TF-target adjacencies
    regulons : list of dict
        Regulon list
    auc_matrix : DataFrame
        AUCell scores
    prefix : str
        File prefix

    Returns
    -------
    dict mapping file type to file path
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = {}

    # Export adjacencies
    adj_file = output_dir / f"{prefix}_adjacencies.csv"
    adjacencies.to_csv(adj_file, index=False)
    files["adjacencies"] = str(adj_file)
    logger.info(f"Saved: {adj_file}")

    # Export regulons
    regulon_df = pd.DataFrame(regulons)
    regulon_file = output_dir / f"{prefix}_regulons.csv"
    regulon_df.to_csv(regulon_file, index=False)
    files["regulons"] = str(regulon_file)
    logger.info(f"Saved: {regulon_file}")

    # Export regulon targets (long format)
    targets_records = []
    for r in regulons:
        for t in r["targets"]:
            targets_records.append({
                "tf": r["tf"],
                "target": t,
            })
    targets_df = pd.DataFrame(targets_records)
    targets_file = output_dir / f"{prefix}_regulon_targets.csv"
    targets_df.to_csv(targets_file, index=False)
    files["regulon_targets"] = str(targets_file)
    logger.info(f"Saved: {targets_file}")

    # Export AUC matrix
    auc_file = output_dir / f"{prefix}_auc_matrix.csv"
    auc_matrix.to_csv(auc_file)
    files["auc_matrix"] = str(auc_file)
    logger.info(f"Saved: {auc_file}")

    return files


def plot_regulon_activity_umap(
    adata,
    auc_matrix: pd.DataFrame,
    output_dir: str | Path,
    n_top: int = 9,
) -> list[str]:
    """Plot regulon activity on UMAP.

    Parameters
    ----------
    adata : AnnData
        AnnData object with UMAP coordinates
    auc_matrix : DataFrame
        AUCell scores
    output_dir : str or Path
        Output directory
    n_top : int
        Number of top regulons to plot

    Returns
    -------
    List of paths to saved figures
    """
    import matplotlib.pyplot as plt
    import scanpy as sc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    figures = []

    # Get top regulons by variance
    top_regulons = auc_matrix.var().nlargest(n_top).index.tolist()

    # Add AUC scores to adata with a prefix to avoid name collisions
    # with var_names (e.g. TF "NFkB1" may also be a gene name).
    obs_keys: list[str] = []
    for regulon in top_regulons:
        key = f"_auc_{regulon}"
        adata.obs[key] = auc_matrix.loc[adata.obs_names, regulon].values
        obs_keys.append(key)

    try:
        # Plot
        n_cols = 3
        n_rows = (n_top + n_cols - 1) // n_cols
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(5 * n_cols, 4 * n_rows))
        axes = axes.flatten() if n_top > 1 else [axes]

        for i, (regulon, key) in enumerate(zip(top_regulons, obs_keys)):
            if i >= len(axes):
                break
            sc.pl.umap(
                adata,
                color=key,
                ax=axes[i],
                show=False,
                cmap="viridis",
            )
            axes[i].set_title(regulon)

        # Hide empty axes
        for i in range(len(top_regulons), len(axes)):
            axes[i].set_visible(False)

        fig.tight_layout()
        fig_path = output_dir / "regulon_activity_umap.png"
        fig.savefig(fig_path, dpi=300, bbox_inches="tight")
        figures.append(str(fig_path))
        plt.close()

        logger.info(f"Saved: {fig_path}")

    except Exception as e:
        logger.warning(f"Regulon activity UMAP plot failed: {e}")

    finally:
        # Clean up adata.obs
        for key in obs_keys:
            if key in adata.obs.columns:
                del adata.obs[key]

    return figures


def plot_regulon_heatmap(
    auc_matrix: pd.DataFrame,
    output_dir: str | Path,
    cluster_key: str | None = None,
    cluster_labels: pd.Series | None = None,
    n_top: int = 20,
    title: str = "Regulon Activity Heatmap",
) -> str | None:
    """Plot heatmap of regulon activity.

    Parameters
    ----------
    auc_matrix : DataFrame
        AUCell scores
    output_dir : str or Path
        Output directory
    cluster_key : str, optional
        Key to group cells by (if auc_matrix index matches cluster labels)
    cluster_labels : Series, optional
        Cluster labels (alternative to cluster_key)
    n_top : int
        Number of top regulons to show
    title : str
        Plot title

    Returns
    -------
    Path to saved figure or None if failed
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Get top regulons by variance
        top_regulons = auc_matrix.var().nlargest(n_top).index.tolist()
        auc_subset = auc_matrix[top_regulons]

        # Group by cluster if provided
        if cluster_labels is not None:
            mean_auc = auc_subset.groupby(cluster_labels).mean()
        else:
            mean_auc = auc_subset.T

        # Plot
        fig, ax = plt.subplots(figsize=(12, max(8, n_top * 0.4)))

        sns.heatmap(
            mean_auc,
            cmap="RdBu_r",
            center=0.5,
            ax=ax,
            xticklabels=True,
            yticklabels=True,
        )
        ax.set_title(title, fontsize=14, fontweight="bold")

        fig.tight_layout()
        fig_path = output_dir / "regulon_heatmap.png"
        fig.savefig(fig_path, dpi=300, bbox_inches="tight")
        plt.close()

        logger.info(f"Saved: {fig_path}")
        return str(fig_path)

    except Exception as e:
        logger.warning(f"Regulon heatmap plot failed: {e}")
        return None


def plot_regulon_network(
    regulons: list[dict],
    output_dir: str | Path,
    n_top: int = 20,
    min_targets: int = 5,
    title: str = "Gene Regulatory Network",
) -> str | None:
    """Plot network diagram of TF-target relationships.

    Parameters
    ----------
    regulons : list of dict
        List of regulons
    output_dir : str or Path
        Output directory
    n_top : int
        Number of top regulons to plot
    min_targets : int
        Minimum targets for TF to be included
    title : str
        Plot title

    Returns
    -------
    Path to saved figure or None if failed
    """
    import matplotlib.pyplot as plt
    import networkx as nx

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Filter regulons
        filtered = [r for r in regulons if r["n_targets"] >= min_targets]
        filtered = sorted(filtered, key=lambda x: x["n_targets"], reverse=True)[:n_top]

        if not filtered:
            logger.warning("No regulons meet criteria for network plot")
            return None

        # Build network
        G = nx.DiGraph()

        for r in filtered:
            tf = r["tf"]
            G.add_node(tf, node_type="tf")
            for target in r["targets"][:10]:  # Limit targets per TF
                G.add_node(target, node_type="target")
                G.add_edge(tf, target)

        # Plot
        fig, ax = plt.subplots(figsize=(14, 14))

        pos = nx.spring_layout(G, k=1, iterations=50, seed=42)

        # Draw TFs
        tf_nodes = [n for n, d in G.nodes(data=True) if d.get("node_type") == "tf"]
        nx.draw_networkx_nodes(
            G, pos,
            nodelist=tf_nodes,
            node_color="red",
            node_size=500,
            alpha=0.8,
            ax=ax,
        )

        # Draw targets
        target_nodes = [n for n, d in G.nodes(data=True) if d.get("node_type") == "target"]
        nx.draw_networkx_nodes(
            G, pos,
            nodelist=target_nodes,
            node_color="lightblue",
            node_size=200,
            alpha=0.6,
            ax=ax,
        )

        # Draw edges
        nx.draw_networkx_edges(
            G, pos,
            edge_color="gray",
            alpha=0.3,
            arrows=True,
            arrowsize=10,
            ax=ax,
        )

        # Labels for TFs only
        labels = {n: n for n in tf_nodes}
        nx.draw_networkx_labels(G, pos, labels, font_size=10, ax=ax)

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.axis("off")

        fig.tight_layout()
        fig_path = output_dir / "regulon_network.png"
        fig.savefig(fig_path, dpi=300, bbox_inches="tight")
        plt.close()

        logger.info(f"Saved: {fig_path}")
        return str(fig_path)

    except Exception as e:
        logger.warning(f"Regulon network plot failed: {e}")
        return None
