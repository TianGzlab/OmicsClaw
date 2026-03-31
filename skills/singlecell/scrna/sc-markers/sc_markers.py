#!/usr/bin/env python3
"""Single-Cell Markers - Find marker genes for cell clusters.

Usage:
    python sc_markers.py --input <data.h5ad> --output <dir> --groupby leiden
    python sc_markers.py --demo --output <dir>
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
import seaborn as sns

# Fix for anndata >= 0.11 with StringArray
try:
    import anndata
    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    load_result_json,
    write_output_readme,
    write_result_json,
)
from omicsclaw.common.checksums import sha256_file
from skills.singlecell._lib.method_config import (
    MethodConfig,
    validate_method_choice,
)
from skills.singlecell._lib.viz_utils import save_figure
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib import markers as sc_markers_utils

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-markers"
SKILL_VERSION = "0.3.0"


def _write_repro_requirements(repro_dir: Path, packages: list[str]) -> None:
    try:
        from importlib.metadata import PackageNotFoundError, version as get_version
    except ImportError:  # pragma: no cover
        PackageNotFoundError = Exception
        from importlib_metadata import version as get_version  # type: ignore

    lines: list[str] = []
    for pkg in packages:
        try:
            lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            continue
        except Exception:
            continue
    (repro_dir / "requirements.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_standard_run_artifacts(output_dir: Path, result_payload: dict, summary: dict) -> None:
    notebook_path = None
    try:
        from omicsclaw.common.notebook_export import write_analysis_notebook

        notebook_path = write_analysis_notebook(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Marker gene discovery for clustered single-cell RNA-seq data.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "wilcoxon"),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Marker gene discovery for clustered single-cell RNA-seq data.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "wilcoxon"),
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md: %s", exc)

# ---------------------------------------------------------------------------
# Method registry
# ---------------------------------------------------------------------------

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "wilcoxon": MethodConfig(
        name="wilcoxon",
        description="Wilcoxon rank-sum test (scanpy built-in)",
        dependencies=("scanpy",),
    ),
    "t-test": MethodConfig(
        name="t-test",
        description="Welch's t-test (scanpy built-in)",
        dependencies=("scanpy",),
    ),
    "logreg": MethodConfig(
        name="logreg",
        description="Logistic regression (scanpy built-in)",
        dependencies=("scanpy",),
    ),
}

SUPPORTED_METHODS = tuple(METHOD_REGISTRY.keys())

# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------

# All methods are dispatched via sc_markers_utils.find_all_cluster_markers;
# _METHOD_DISPATCH kept for structural consistency.
_METHOD_DISPATCH = {
    "wilcoxon": "wilcoxon",
    "t-test": "t-test",
    "logreg": "logreg",
}


def generate_marker_figures(adata, markers, output_dir: Path, n_top: int = 10) -> list[str]:
    """Generate marker gene visualization figures."""
    figures = []
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Top markers heatmap
    try:
        logger.info("Generating marker heatmap...")
        sc_markers_utils.plot_top_markers_heatmap(
            adata, markers, n_top=n_top, output_dir=figures_dir
        )
        fig_path = figures_dir / "markers_heatmap.png"
        if fig_path.exists():
            figures.append(str(fig_path))
            logger.info(f"  Saved: markers_heatmap.png")
    except Exception as e:
        logger.warning(f"Marker heatmap failed: {e}")

    # Top markers dotplot
    try:
        logger.info("Generating marker dotplot...")
        sc_markers_utils.plot_markers_dotplot(
            adata, markers, n_top=5, output_dir=figures_dir
        )
        fig_path = figures_dir / "markers_dotplot.png"
        if fig_path.exists():
            figures.append(str(fig_path))
            logger.info(f"  Saved: markers_dotplot.png")
    except Exception as e:
        logger.warning(f"Marker dotplot failed: {e}")

    # Volcano plots for top clusters
    try:
        top_clusters = markers['group'].value_counts().head(4).index.tolist()
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        axes = axes.flatten()

        for i, cluster in enumerate(top_clusters):
            cluster_markers = markers[markers['group'] == cluster].head(50)
            if len(cluster_markers) == 0:
                continue

            ax = axes[i]
            x = cluster_markers['logfoldchanges'].values
            y = -np.log10(cluster_markers['pvals_adj'].values + 1e-300)

            # Color by significance
            colors = ['red' if (lf > 1 and pv < 0.05) else 'gray'
                      for lf, pv in zip(cluster_markers['logfoldchanges'], cluster_markers['pvals_adj'])]

            ax.scatter(x, y, c=colors, alpha=0.6, s=20)
            ax.set_xlabel('Log Fold Change')
            ax.set_ylabel('-Log10(Adj P-value)')
            ax.set_title(f'Cluster {cluster}')
            ax.axhline(-np.log10(0.05), color='blue', linestyle='--', alpha=0.5)
            ax.axvline(1, color='blue', linestyle='--', alpha=0.5)

        fig.suptitle('Top Marker Genes by Cluster', fontweight='bold')
        fig.tight_layout()
        fig_path = figures_dir / "volcano_plots.png"
        fig.savefig(fig_path, dpi=300, bbox_inches='tight')
        figures.append(str(fig_path))
        plt.close()
        logger.info(f"  Saved: volcano_plots.png")
    except Exception as e:
        logger.warning(f"Volcano plots failed: {e}")

    return figures


def write_marker_report(output_dir: Path, summary: dict, params: dict, input_file: str | None, top_markers: dict) -> None:
    """Write marker gene identification report."""
    header = generate_report_header(
        title="Single-Cell Marker Genes Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Clusters": str(summary["n_clusters"]),
            "Total Markers": str(summary["n_markers"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Clusters analyzed**: {summary['n_clusters']}",
        f"- **Total markers found**: {summary['n_markers']}",
        f"- **Method**: {params['method']}",
        f"- **Grouping**: {params['groupby']}",
        "",
        "## Top Markers by Cluster\n",
    ]

    for cluster, markers in top_markers.items():
        body_lines.append(f"### Cluster {cluster}\n")
        body_lines.append("| Gene | LogFC | P-adj |")
        body_lines.append("|------|-------|-------|")
        for _, row in markers.head(5).iterrows():
            gene = row.get('names', 'N/A')
            lfc = row.get('logfoldchanges', 0)
            padj = row.get('pvals_adj', 1)
            body_lines.append(f"| {gene} | {lfc:.2f} | {padj:.2e} |")
        body_lines.append("")

    body_lines.extend([
        "## Parameters\n",
        f"- `--groupby`: {params['groupby']}",
        f"- `--method`: {params['method']}",
        f"- `--n-genes`: {params.get('n_genes', 'all')}",
        "",
        "## Output Files\n",
        "- `tables/cluster_markers_all.csv` — All markers for all clusters",
        "- `tables/cluster_markers_top10.csv` — Top 10 markers per cluster",
        "- `figures/markers_heatmap.png` — Heatmap of top markers",
        "- `figures/markers_dotplot.png` — Dot plot of marker expression",
        "- `figures/volcano_plots.png` — Volcano plots per cluster",
        "",
        "## Interpretation\n",
        "- **Log fold change > 1**: Gene is upregulated in this cluster",
        "- **Adjusted p-value < 0.05**: Statistically significant",
        "- Use these markers to annotate cell types",
        "",
    ])

    footer = generate_report_footer()
    report = header + "\n" + "\n".join(body_lines) + "\n" + footer

    (output_dir / "report.md").write_text(report)


def generate_demo_data():
    """Generate demo data with clusters."""
    import scanpy as sc

    logger.info("Generating demo data with clusters...")

    try:
        adata, demo_path = sc_io.load_repo_demo_data("pbmc3k_raw")
        logger.info("Loaded demo dataset: %s", demo_path or "scanpy-pbmc3k")
        # Quick preprocessing
        sc.pp.filter_cells(adata, min_genes=200)
        sc.pp.filter_genes(adata, min_cells=3)
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        sc.pp.highly_variable_genes(adata, n_top_genes=2000)
        sc.pp.pca(adata)
        sc.pp.neighbors(adata)

        # Try leiden clustering, fallback to kmeans if not available
        try:
            sc.tl.leiden(adata, resolution=0.8)
            cluster_key = 'leiden'
        except ImportError:
            logger.warning("leidenalg not installed, using kmeans clustering")
            from sklearn.cluster import KMeans
            kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
            adata.obs['leiden'] = pd.Categorical(kmeans.fit_predict(adata.obsm['X_pca'][:, :30]).astype(str))
            cluster_key = 'leiden'

        logger.info(f"Generated: {adata.n_obs} cells x {adata.n_vars} genes, {adata.obs['leiden'].nunique()} clusters")
    except Exception as e:
        # Synthetic fallback
        logger.warning(f"Failed to load local/scanpy pbmc3k: {e}. Generating synthetic data.")
        np.random.seed(42)
        n_cells, n_genes = 500, 1000
        counts = np.random.negative_binomial(2, 0.02, size=(n_cells, n_genes))
        adata = sc.AnnData(
            X=counts.astype(np.float32),
            obs=pd.DataFrame(index=[f"cell_{i}" for i in range(n_cells)]),
            var=pd.DataFrame(index=[f"gene_{i}" for i in range(n_genes)]),
        )
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        sc.pp.pca(adata)
        sc.pp.neighbors(adata)

        # Use kmeans for clustering
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
        adata.obs['leiden'] = pd.Categorical(kmeans.fit_predict(adata.obsm['X_pca'][:, :30]).astype(str))

    return adata


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Marker Gene Identification")
    parser.add_argument("--input", dest="input_path", help="Input AnnData file (.h5ad)")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with demo data")
    parser.add_argument("--groupby", default="leiden", help="Grouping column (default: leiden)")
    parser.add_argument("--method", default="wilcoxon", choices=list(METHOD_REGISTRY.keys()),
                        help="Statistical test method")
    parser.add_argument("--n-genes", type=int, default=None, help="Number of genes per cluster")
    parser.add_argument("--n-top", type=int, default=10, help="Top N markers per cluster for visualization")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    if args.demo:
        adata = generate_demo_data()
        input_file = None
    else:
        if not args.input_path:
            parser.error("--input required when not using --demo")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        logger.info(f"Loading: {input_path}")
        adata = sc_io.smart_load(input_path)
        input_file = str(input_path)

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    # Check grouping exists
    if args.groupby not in adata.obs.columns:
        logger.error(f"Grouping column '{args.groupby}' not found in adata.obs")
        logger.info(f"Available columns: {list(adata.obs.columns)}")
        raise ValueError(f"Column '{args.groupby}' not found")

    # Validate method & check dependencies
    method = validate_method_choice(args.method, METHOD_REGISTRY)

    # Parameters
    params = {
        "groupby": args.groupby,
        "method": method,
        "n_genes": args.n_genes,
        "n_top": args.n_top,
    }

    # Find markers
    logger.info(f"Finding marker genes using {method}...")
    markers = sc_markers_utils.find_all_cluster_markers(
        adata,
        cluster_key=args.groupby,
        method=method,
        n_genes=args.n_genes,
    )

    n_clusters = markers['group'].nunique()
    n_total_markers = len(markers)

    logger.info(f"Found {n_total_markers} markers for {n_clusters} clusters")

    # Organize top markers per cluster
    top_markers = {}
    for cluster in markers['group'].unique():
        cluster_markers = markers[markers['group'] == cluster]
        sort_col = 'pvals_adj' if 'pvals_adj' in cluster_markers.columns else 'scores'
        top_markers[str(cluster)] = cluster_markers.sort_values(sort_col)

    # Generate figures
    logger.info("Generating figures...")
    figures = generate_marker_figures(adata, markers, output_dir, n_top=args.n_top)

    # Export tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    # All markers
    markers.to_csv(tables_dir / "cluster_markers_all.csv", index=False)
    logger.info(f"  Saved: tables/cluster_markers_all.csv")

    # Top N per cluster
    top_n_markers = markers.groupby('group').head(args.n_top)
    top_n_markers.to_csv(tables_dir / f"cluster_markers_top{args.n_top}.csv", index=False)
    logger.info(f"  Saved: tables/cluster_markers_top{args.n_top}.csv")

    # Summary
    summary = {
        "n_clusters": int(n_clusters),
        "n_markers": int(n_total_markers),
        "clusters": {str(k): len(v) for k, v in top_markers.items()},
    }

    # Write report
    logger.info("Writing report...")
    write_marker_report(output_dir, summary, params, input_file, top_markers)

    # Save data with markers
    # Note: Remove rank_genes_groups results to avoid h5py serialization issues
    if 'rank_genes_groups' in adata.uns:
        del adata.uns['rank_genes_groups']
    if 'rank_genes_groups_filtered' in adata.uns:
        del adata.uns['rank_genes_groups_filtered']

    output_h5ad = output_dir / "adata_with_markers.h5ad"
    from skills.singlecell._lib.adata_utils import store_analysis_metadata
    store_analysis_metadata(adata, SKILL_NAME, args.method, params)
    adata.write_h5ad(output_h5ad)
    logger.info(f"Saved: {output_h5ad}")

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    cmd = f"python sc_markers.py --output {output_dir} --groupby {args.groupby} --method {args.method}"
    if input_file:
        cmd += f" --input {input_file}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    _write_repro_requirements(
        repro_dir,
        ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "seaborn"],
    )

    # Result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {"params": params}
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }
    write_standard_run_artifacts(output_dir, result_payload, summary)

    # Summary
    print(f"\n{'='*60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'='*60}")
    print(f"  Clusters: {n_clusters}")
    print(f"  Total markers: {n_total_markers}")
    print(f"  Method: {args.method}")
    print(f"  Output: {output_dir}")


if __name__ == "__main__":
    main()
