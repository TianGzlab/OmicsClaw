"""
Export all trajectory inference results to standard formats.

Saves analysis objects (h5ad, pickle) for downstream skills and exports
results to CSV/markdown/PDF formats for human analysis.

Usage:
  from scripts.export_results import export_all
  export_all(adata, results, output_dir="trajectory_results")
"""

import json
import os
import pickle
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


def export_all(adata, results, output_dir="trajectory_results"):
    """
    Export all trajectory results to h5ad, pickle, CSV, and report formats.

    Parameters
    ----------
    adata : AnnData
        AnnData with trajectory analysis results embedded.
    results : dict
        Output from run_trajectory().
    output_dir : str
        Directory to save outputs.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\nExporting trajectory results...")

    # 1. Save AnnData with trajectory annotations
    print("  Saving AnnData object...")
    h5ad_path = output_dir / "adata_trajectory.h5ad"
    _save_h5ad(adata, h5ad_path)
    print(f"   Saved: {h5ad_path}")
    print(f"   (Load with: adata = sc.read_h5ad('{h5ad_path}'))")

    # 2. Save trajectory results as pickle (for downstream skills)
    print("  Saving trajectory results object...")
    pkl_path = output_dir / "trajectory_results.pkl"
    # Strip non-serializable items
    pkl_results = _make_serializable(results)
    with open(pkl_path, "wb") as f:
        pickle.dump(pkl_results, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"   Saved: {pkl_path}")
    print(f"   (Load with: results = pickle.loads(Path('{pkl_path}').read_bytes()))")

    # 3. Export pseudotime assignments
    print("  Exporting pseudotime assignments...")
    pseudotime = results.get("pseudotime")
    if pseudotime is not None:
        pt_df = pd.DataFrame({
            "cell_id": pseudotime.index,
            "pseudotime": pseudotime.values,
        })
        # Add cluster info if available
        params = results.get("parameters", {})
        cluster_key = params.get("cluster_key", "clusters")
        if cluster_key in adata.obs.columns:
            pt_df["cell_type"] = adata.obs[cluster_key].values
        pt_path = output_dir / "pseudotime_assignments.csv"
        pt_df.to_csv(pt_path, index=False)
        print(f"   Saved: {pt_path} ({len(pt_df)} cells)")

    # 4. Export trajectory genes
    print("  Exporting trajectory genes...")
    traj_genes = results.get("trajectory_genes")
    if traj_genes is not None and len(traj_genes) > 0:
        genes_path = output_dir / "trajectory_genes.csv"
        traj_genes.to_csv(genes_path, index=False)
        print(f"   Saved: {genes_path} ({len(traj_genes)} genes)")

    # 5. Export velocity genes (if available)
    vel_results = results.get("velocity_results")
    if vel_results and "velocity_genes" in vel_results:
        vel_genes = vel_results["velocity_genes"]
        if len(vel_genes) > 0:
            vel_path = output_dir / "velocity_genes.csv"
            vel_genes.to_csv(vel_path, index=False)
            print(f"   Saved: {vel_path} ({len(vel_genes)} genes)")

    # 6. Export fate probabilities (if CellRank ran)
    cr_results = results.get("cellrank_results")
    if cr_results and "fate_probabilities" in cr_results:
        fate_df = cr_results["fate_probabilities"]
        fate_path = output_dir / "fate_probabilities.csv"
        fate_df.to_csv(fate_path)
        print(f"   Saved: {fate_path} ({len(fate_df)} cells, "
              f"{fate_df.shape[1]} fates)")

        # Driver genes per fate
        driver_genes = cr_results.get("driver_genes", {})
        for state, df in driver_genes.items():
            if len(df) > 0:
                driver_path = output_dir / f"driver_genes_{state}.csv"
                df.to_csv(driver_path, index=False)
                print(f"   Saved: {driver_path}")

    # 7. Export analysis metadata
    print("  Exporting analysis metadata...")
    metadata = _build_metadata(adata, results)
    meta_path = output_dir / "analysis_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"   Saved: {meta_path}")

    # 8. Generate markdown report
    print("  Generating markdown report...")
    md_path = output_dir / "trajectory_analysis_report.md"
    _write_markdown_report(adata, results, md_path)
    print(f"   Saved: {md_path}")

    # 9. Generate PDF report (optional, with fallback)
    # Use importlib to load from same directory — works regardless of cwd
    print("  Generating PDF report...")
    try:
        import importlib.util
        _report_path = os.path.join(os.path.dirname(__file__), "generate_report.py")
        _spec = importlib.util.spec_from_file_location("generate_report", _report_path)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _mod.generate_report(
            adata=adata,
            results=results,
            output_dir=str(output_dir),
        )
    except Exception as e:
        print(f"   PDF generation skipped: {e}")
        print("   (Markdown report still available)")

    # Summary
    print("\n" + "=" * 50)
    print("=== Export Complete ===")
    print("=" * 50)
    print(f"\nAll results saved to: {output_dir}")
    print("\nKey files:")
    print(f"  - adata_trajectory.h5ad (processed AnnData)")
    print(f"  - trajectory_results.pkl (full results for downstream)")
    print(f"  - pseudotime_assignments.csv (cell pseudotime values)")
    print(f"  - trajectory_genes.csv (pseudotime-correlated genes)")
    print(f"  - trajectory_analysis_report.pdf (publication-quality report)")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _save_h5ad(adata, path):
    """Save AnnData with cleanup for serialization issues.

    Removes problematic keys in-place and restores them after writing
    to avoid a full adata.copy() which doubles memory usage.
    """
    # Track removed items so we can restore them
    removed_uns = {}
    removed_obsp = {}

    try:
        # Remove problematic keys that can't be serialized
        problematic_keys = ["rank_genes_groups_filtered", "velocity_graph", "velocity_graph_neg"]
        for key in problematic_keys:
            if key in adata.uns:
                removed_uns[key] = adata.uns.pop(key)

        # Clean obsp entries that may have incompatible formats
        for key in list(adata.obsp.keys()):
            try:
                _ = adata.obsp[key]
            except Exception:
                removed_obsp[key] = adata.obsp.pop(key)

        adata.write_h5ad(path, compression="gzip")

    finally:
        # Restore removed keys
        for key, val in removed_uns.items():
            adata.uns[key] = val
        for key, val in removed_obsp.items():
            adata.obsp[key] = val


def _make_serializable(results):
    """Create a pickle-safe copy of results dict."""
    safe = {}
    for k, v in results.items():
        if isinstance(v, (pd.DataFrame, pd.Series)):
            safe[k] = v.copy()
        elif isinstance(v, np.ndarray):
            safe[k] = v.copy()
        elif isinstance(v, dict):
            safe[k] = _make_serializable(v)
        elif isinstance(v, (str, int, float, bool, list, type(None))):
            safe[k] = v
        else:
            # Skip non-serializable objects (e.g., CellRank estimators)
            try:
                pickle.dumps(v)
                safe[k] = v
            except Exception:
                safe[k] = str(v)
    return safe


def _pseudotime_range(pseudotime):
    """Compute finite pseudotime range (excludes inf values for valid JSON)."""
    if pseudotime is None:
        return [None, None]
    valid_pt = pseudotime[~np.isinf(pseudotime)]
    if len(valid_pt) == 0:
        return [None, None]
    return [float(valid_pt.min()), float(valid_pt.max())]


def _build_metadata(adata, results):
    """Build analysis metadata JSON."""
    params = results.get("parameters", {})
    pseudotime = results.get("pseudotime")
    traj_genes = results.get("trajectory_genes")

    metadata = {
        "analysis_date": datetime.now().isoformat(),
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "parameters": {k: v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
                       for k, v in params.items()},
        "pseudotime": {
            "range": _pseudotime_range(pseudotime),
            "root_cell": results.get("root_cell", "unknown"),
        },
        "trajectory_genes": {
            "n_significant": int(len(traj_genes)) if traj_genes is not None else 0,
            "fdr_threshold": 0.05,
        },
        "rna_velocity": {
            "computed": results.get("velocity_results") is not None,
            "model": (results["velocity_results"]["model"]
                      if results.get("velocity_results") else None),
        },
        "cellrank": {
            "computed": results.get("cellrank_results") is not None,
            "terminal_states": (results["cellrank_results"]["terminal_states"]
                                if results.get("cellrank_results") else []),
        },
        "outputs": {
            "adata": "adata_trajectory.h5ad",
            "results_pickle": "trajectory_results.pkl",
            "pseudotime": "pseudotime_assignments.csv",
            "trajectory_genes": "trajectory_genes.csv",
            "report_pdf": "trajectory_analysis_report.pdf",
            "report_md": "trajectory_analysis_report.md",
        },
    }
    return metadata


def _write_markdown_report(adata, results, output_path):
    """Write a markdown analysis report."""
    params = results.get("parameters", {})
    pseudotime = results.get("pseudotime")
    traj_genes = results.get("trajectory_genes")
    vel_results = results.get("velocity_results")
    cr_results = results.get("cellrank_results")

    with open(output_path, "w") as f:
        f.write("# Single-Cell Trajectory Analysis Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Summary
        f.write("## Summary Statistics\n\n")
        f.write(f"- **Cells analyzed:** {adata.n_obs:,}\n")
        f.write(f"- **Genes:** {adata.n_vars:,}\n")
        f.write(f"- **Root cell type:** {params.get('root_cell_type', 'N/A')}\n")
        if pseudotime is not None:
            valid_pt = pseudotime[~np.isinf(pseudotime)]
            f.write(f"- **Pseudotime range:** [{valid_pt.min():.3f}, {valid_pt.max():.3f}]\n")
        f.write(f"- **Trajectory genes (FDR < 0.05):** {len(traj_genes) if traj_genes is not None else 0}\n")
        f.write(f"- **RNA velocity:** {'Yes (' + vel_results['model'] + ')' if vel_results else 'No'}\n")
        f.write(f"- **CellRank fates:** {', '.join(cr_results['terminal_states']) if cr_results else 'N/A'}\n\n")

        # Methods
        f.write("## Methods\n\n")
        f.write("| Parameter | Value |\n")
        f.write("|-----------|-------|\n")
        for k, v in params.items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n")

        # Top genes
        if traj_genes is not None and len(traj_genes) > 0:
            f.write("## Top 20 Trajectory Genes\n\n")
            f.write("| Rank | Gene | Correlation | FDR | Direction |\n")
            f.write("|------|------|-------------|-----|----------|\n")
            for i, (_, row) in enumerate(traj_genes.head(20).iterrows(), 1):
                f.write(f"| {i} | {row['gene']} | {row['correlation']:.3f} | "
                        f"{row['fdr']:.2e} | {row['direction']} |\n")
            f.write("\n")

        # CellRank terminal states
        if cr_results:
            f.write("## Terminal States (CellRank)\n\n")
            f.write(f"Terminal states identified: **{', '.join(cr_results['terminal_states'])}**\n\n")

        # Files
        f.write("## Files Generated\n\n")
        f.write("**Analysis objects:**\n")
        f.write("- `adata_trajectory.h5ad` — AnnData with trajectory annotations\n")
        f.write("- `trajectory_results.pkl` — Full results for downstream analysis\n\n")
        f.write("**Results (CSV):**\n")
        f.write("- `pseudotime_assignments.csv` — Cell pseudotime values\n")
        f.write("- `trajectory_genes.csv` — Pseudotime-correlated genes\n")
        if vel_results:
            f.write("- `velocity_genes.csv` — Top RNA velocity genes\n")
        if cr_results:
            f.write("- `fate_probabilities.csv` — Cell fate probabilities\n")
            f.write("- `driver_genes_*.csv` — Driver genes per terminal fate\n")
        f.write("\n**Reports:**\n")
        f.write("- `trajectory_analysis_report.pdf` — Publication-quality PDF\n")
        f.write("- `trajectory_analysis_report.md` — This markdown report\n")

