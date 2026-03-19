#!/usr/bin/env python3
"""bulkrna-trajblend — Bulk→single-cell trajectory interpolation.

Bridges bulk RNA-seq with scRNA-seq reference to estimate cell fractions,
generate synthetic single-cell profiles, and map bulk onto developmental
trajectories. Pure-Python/NumPy fallback when PyTorch is unavailable.

Usage:
    python bulkrna_trajblend.py --demo --output results/
    python bulkrna_trajblend.py --input bulk.csv --reference ref.h5ad --output results/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import nnls
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    write_result_json,
)

logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-trajblend"
SKILL_VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Demo Data
# ---------------------------------------------------------------------------

def _generate_demo_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, np.ndarray]:
    """Generate demo bulk + scRNA-seq reference with trajectory.

    Returns: (bulk_counts, ref_counts, ref_celltypes, ref_pseudotime)
    """
    np.random.seed(42)
    n_genes = 500
    n_bulk = 10
    n_cells = 800
    genes = [f"Gene_{i}" for i in range(n_genes)]
    cell_types = ["Progenitor", "Intermediate", "Mature_A", "Mature_B"]

    # Reference scRNA-seq: 4 cell types along a trajectory
    ref_data = np.zeros((n_cells, n_genes))
    ref_labels = []
    ref_pt = np.zeros(n_cells)

    cells_per_type = n_cells // len(cell_types)
    for ti, ct in enumerate(cell_types):
        idx = slice(ti * cells_per_type, (ti + 1) * cells_per_type)
        # Each cell type has different expression profiles
        base = np.random.exponential(5, n_genes)
        # Cell-type specific marker genes (50 per type)
        markers = np.arange(ti * 50, (ti + 1) * 50) % n_genes
        base[markers] *= np.random.uniform(5, 15)
        for j in range(cells_per_type):
            noise = np.random.exponential(1, n_genes)
            ref_data[ti * cells_per_type + j] = base + noise
        ref_labels.extend([ct] * cells_per_type)
        # Pseudotime increases with cell type progression
        ref_pt[idx] = np.linspace(ti * 0.25, (ti + 1) * 0.25, cells_per_type) + \
                      np.random.normal(0, 0.02, cells_per_type)

    ref_pt = np.clip(ref_pt, 0, 1)

    # Bulk data: mixtures of cell types
    bulk_data = np.zeros((n_bulk, n_genes))
    true_fractions = np.random.dirichlet([2, 3, 4, 1], n_bulk)
    for i in range(n_bulk):
        for ti, ct in enumerate(cell_types):
            ct_mean = ref_data[ti * cells_per_type:(ti + 1) * cells_per_type].mean(axis=0)
            bulk_data[i] += true_fractions[i, ti] * ct_mean * np.random.uniform(80, 120)
    bulk_data = np.round(bulk_data).astype(int)

    bulk_df = pd.DataFrame(bulk_data, columns=genes,
                           index=[f"BulkSample_{i}" for i in range(n_bulk)])
    ref_df = pd.DataFrame(ref_data, columns=genes,
                          index=[f"Cell_{i}" for i in range(n_cells)])

    return bulk_df, ref_df, pd.Series(ref_labels, index=ref_df.index), ref_pt


# ---------------------------------------------------------------------------
# Core Analysis
# ---------------------------------------------------------------------------

def estimate_fractions(bulk: pd.DataFrame, ref: pd.DataFrame,
                       ref_labels: pd.Series) -> pd.DataFrame:
    """Estimate cell type fractions via NNLS deconvolution."""
    cell_types = sorted(ref_labels.unique())

    # Build signature matrix: mean expression per cell type
    sig = pd.DataFrame(index=ref.columns)
    for ct in cell_types:
        ct_cells = ref_labels[ref_labels == ct].index
        sig[ct] = ref.loc[ct_cells].mean(axis=0)

    # Common genes
    common = bulk.columns.intersection(sig.index)
    if len(common) < 50:
        raise ValueError(f"Only {len(common)} common genes — need >= 50")

    S = sig.loc[common].values  # genes x cell_types
    fractions = {}
    for sample in bulk.index:
        b = bulk.loc[sample, common].values.astype(float)
        x, _ = nnls(S, b)
        x_norm = x / x.sum() if x.sum() > 0 else x
        fractions[sample] = dict(zip(cell_types, x_norm))

    return pd.DataFrame(fractions).T


def generate_synthetic_cells(ref: pd.DataFrame, ref_labels: pd.Series,
                             fractions: pd.DataFrame,
                             n_synthetic_per_sample: int = 100) -> pd.DataFrame:
    """Generate synthetic cells weighted by estimated fractions."""
    np.random.seed(42)
    cell_types = sorted(ref_labels.unique())
    ct_indices = {ct: ref_labels[ref_labels == ct].index.tolist()
                  for ct in cell_types}

    synth_rows = []
    synth_labels = []
    for sample in fractions.index:
        for ct in cell_types:
            n = max(1, int(fractions.loc[sample, ct] * n_synthetic_per_sample))
            source_cells = ct_indices[ct]
            chosen = np.random.choice(source_cells, min(n, len(source_cells)), replace=True)
            for cell_id in chosen:
                noise = np.random.normal(1.0, 0.05, ref.shape[1]).clip(0.5, 1.5)
                synth_rows.append(ref.loc[cell_id].values * noise)
                synth_labels.append(f"{sample}_{ct}")

    synth_df = pd.DataFrame(synth_rows, columns=ref.columns,
                            index=[f"Synth_{i}" for i in range(len(synth_rows))])
    return synth_df


def map_bulk_to_trajectory(bulk: pd.DataFrame, ref: pd.DataFrame,
                           ref_pseudotime: np.ndarray,
                           k: int = 15) -> pd.DataFrame:
    """Map bulk samples onto reference trajectory via PCA + KNN."""
    common = bulk.columns.intersection(ref.columns)

    combined = pd.concat([ref[common], bulk[common]], axis=0)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(np.log1p(combined.values))

    pca = PCA(n_components=min(20, scaled.shape[1], scaled.shape[0]))
    pcs = pca.fit_transform(scaled)

    n_ref = ref.shape[0]
    ref_pcs = pcs[:n_ref]
    bulk_pcs = pcs[n_ref:]

    # KNN mapping
    nn = NearestNeighbors(n_neighbors=k, metric="euclidean")
    nn.fit(ref_pcs)
    dists, indices = nn.kneighbors(bulk_pcs)

    results = []
    for i, sample in enumerate(bulk.index):
        neighbor_pts = ref_pseudotime[indices[i]]
        mean_pt = float(np.mean(neighbor_pts))
        std_pt = float(np.std(neighbor_pts))
        results.append({
            "sample": sample,
            "pseudotime": round(mean_pt, 4),
            "pseudotime_std": round(std_pt, 4),
            "mean_neighbor_dist": round(float(np.mean(dists[i])), 4),
            "pc1": float(bulk_pcs[i, 0]),
            "pc2": float(bulk_pcs[i, 1]),
        })

    return pd.DataFrame(results).set_index("sample"), ref_pcs, bulk_pcs, pca


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def generate_figures(output_dir: Path, fractions: pd.DataFrame,
                     pt_results: pd.DataFrame,
                     ref_pcs: np.ndarray, bulk_pcs: np.ndarray,
                     ref_pt: np.ndarray, ref_labels: pd.Series) -> list[str]:
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    # 1. Fraction heatmap
    fig, ax = plt.subplots(figsize=(8, max(4, fractions.shape[0] * 0.4)))
    im = ax.imshow(fractions.values, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(fractions.shape[1]))
    ax.set_xticklabels(fractions.columns, rotation=45, ha="right", fontsize=9)
    ax.set_yticks(range(fractions.shape[0]))
    ax.set_yticklabels(fractions.index, fontsize=9)
    plt.colorbar(im, ax=ax, label="Fraction")
    ax.set_title("Estimated Cell Type Fractions")
    fig.tight_layout()
    p = fig_dir / "fraction_heatmap.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 2. Trajectory embedding (reference + bulk overlay)
    fig, ax = plt.subplots(figsize=(9, 7))
    sc = ax.scatter(ref_pcs[:, 0], ref_pcs[:, 1], c=ref_pt,
                    cmap="viridis", s=8, alpha=0.4, label="Reference cells")
    ax.scatter(bulk_pcs[:, 0], bulk_pcs[:, 1], c="red", s=80,
               marker="*", edgecolor="black", linewidth=0.5,
               label="Bulk samples", zorder=5)
    for i, sample in enumerate(pt_results.index):
        ax.annotate(sample, (bulk_pcs[i, 0], bulk_pcs[i, 1]),
                    fontsize=6, alpha=0.7, xytext=(5, 5),
                    textcoords="offset points")
    plt.colorbar(sc, ax=ax, label="Pseudotime")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_title("Bulk Samples on Reference Trajectory")
    ax.legend(fontsize=9)
    fig.tight_layout()
    p = fig_dir / "bulk_on_trajectory.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 3. Pseudotime distribution
    fig, ax = plt.subplots(figsize=(7, 5))
    pts = pt_results["pseudotime"].values
    stds = pt_results["pseudotime_std"].values
    y = range(len(pts))
    ax.barh(y, pts, xerr=stds, color="#4878CF", alpha=0.7,
            edgecolor="white", capsize=3)
    ax.set_yticks(y)
    ax.set_yticklabels(pt_results.index, fontsize=9)
    ax.set_xlabel("Estimated Pseudotime")
    ax.set_title("Bulk Sample Pseudotime Estimates")
    ax.invert_yaxis()
    fig.tight_layout()
    p = fig_dir / "pseudotime_distribution.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 4. Trajectory embedding colored by cell type
    fig, ax = plt.subplots(figsize=(9, 7))
    cts = sorted(ref_labels.unique())
    colors = plt.cm.tab10(np.linspace(0, 1, len(cts)))
    for ci, ct in enumerate(cts):
        mask = ref_labels.values == ct
        ax.scatter(ref_pcs[mask, 0], ref_pcs[mask, 1], c=[colors[ci]],
                   s=8, alpha=0.5, label=ct)
    ax.scatter(bulk_pcs[:, 0], bulk_pcs[:, 1], c="red", s=80,
               marker="*", edgecolor="black", linewidth=0.5,
               label="Bulk", zorder=5)
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_title("Cell Type Composition in Trajectory Space")
    ax.legend(fontsize=8, markerscale=2)
    fig.tight_layout()
    p = fig_dir / "trajectory_embedding.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    return paths


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, fractions: pd.DataFrame,
                 pt_results: pd.DataFrame, params: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    header = generate_report_header(
        title="Bulk→Single-Cell Trajectory Interpolation Report",
        skill_name=SKILL_NAME,
    )

    body_lines = [
        "## Summary\n",
        f"- **Bulk samples**: {fractions.shape[0]}",
        f"- **Cell types**: {fractions.shape[1]} ({', '.join(fractions.columns)})",
        f"- **Pseudotime range**: [{pt_results['pseudotime'].min():.3f}, "
        f"{pt_results['pseudotime'].max():.3f}]",
        "",
        "## Cell Type Fractions\n",
        fractions.round(4).to_csv(sep="\t"),
        "",
        "## Pseudotime Estimates\n",
        pt_results[["pseudotime", "pseudotime_std", "mean_neighbor_dist"]].round(4).to_csv(sep="\t"),
    ]

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(
        "\n".join([header, "\n".join(body_lines), footer]), encoding="utf-8")

    fractions.to_csv(tables_dir / "cell_fractions.csv")
    pt_results.to_csv(tables_dir / "pseudotime_estimates.csv")

    metrics = {
        "n_samples": fractions.shape[0],
        "n_cell_types": fractions.shape[1],
        "cell_types": list(fractions.columns),
        "pseudotime_summary": {
            "min": float(pt_results["pseudotime"].min()),
            "max": float(pt_results["pseudotime"].max()),
            "mean": float(pt_results["pseudotime"].mean()),
        },
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, metrics, params)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    (repro_dir / "commands.sh").write_text(
        f"#!/usr/bin/env bash\npython bulkrna_trajblend.py "
        f"--input {params.get('input', '<BULK_COUNTS>')} "
        f"--reference {params.get('reference', '<REF_H5AD>')} "
        f"--output {params.get('output', '<OUTPUT>')}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=f"{SKILL_NAME} v{SKILL_VERSION}")
    ap.add_argument("--input", type=str, help="Bulk count matrix (CSV/TSV)")
    ap.add_argument("--reference", type=str, help="scRNA-seq reference (h5ad or CSV)")
    ap.add_argument("--output", type=str, required=True)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--n-epochs", type=int, default=50, help="VAE epochs (unused in fallback)")
    args = ap.parse_args()

    output_dir = Path(args.output)
    params = {"output": str(output_dir)}

    if args.demo:
        logger.info("Generating demo data...")
        bulk, ref, ref_labels, ref_pt = _generate_demo_data()
        params["input"] = "demo"
        params["reference"] = "demo"
    else:
        if not args.input or not args.reference:
            ap.error("--input and --reference required (or use --demo)")
        bulk = pd.read_csv(args.input, index_col=0)
        params["input"] = args.input
        params["reference"] = args.reference

        # Try loading reference
        ref_path = Path(args.reference)
        if ref_path.suffix == ".h5ad":
            try:
                import anndata as ad
                adata = ad.read_h5ad(ref_path)
                ref = pd.DataFrame(adata.X.toarray() if hasattr(adata.X, "toarray") else adata.X,
                                   index=adata.obs_names, columns=adata.var_names)
                ref_labels = adata.obs.get("cell_type", adata.obs.iloc[:, 0])
                ref_pt = adata.obs.get("pseudotime",
                                       pd.Series(np.zeros(adata.n_obs), index=adata.obs_names)).values
            except ImportError:
                ap.error("anndata required for .h5ad reference files")
        else:
            ref = pd.read_csv(ref_path, index_col=0)
            ref_labels = pd.Series(["Unknown"] * ref.shape[0], index=ref.index)
            ref_pt = np.zeros(ref.shape[0])

    # 1. Estimate cell type fractions
    logger.info("Step 1: Estimating cell type fractions...")
    fractions = estimate_fractions(bulk, ref, ref_labels)

    # 2. Map to trajectory
    logger.info("Step 2: Mapping bulk to trajectory...")
    pt_results, ref_pcs, bulk_pcs, pca = map_bulk_to_trajectory(
        bulk, ref, ref_pt, k=15)

    # 3. Generate figures
    logger.info("Step 3: Generating visualizations...")
    generate_figures(output_dir, fractions, pt_results,
                     ref_pcs, bulk_pcs, ref_pt, ref_labels)

    # 4. Write report
    logger.info("Step 4: Writing report...")
    write_report(output_dir, fractions, pt_results, params)

    logger.info("✓ TrajBlend complete → %s", output_dir)


if __name__ == "__main__":
    main()
