#!/usr/bin/env python3
"""Single-Cell Pseudotime Analysis - DPT and Palantir trajectory inference.

Usage:
    python sc_pseudotime.py --input <data.h5ad> --output <dir> --root-cluster <cluster>
    python sc_pseudotime.py --demo --output <dir>

This skill performs core trajectory analysis using methods available in scanpy:
- PAGA graph for cluster connectivity
- Diffusion map for dimensionality reduction
- DPT pseudotime for temporal ordering
- Trajectory gene identification
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

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
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_pseudotime
from skills.singlecell._lib import trajectory as sc_traj

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-pseudotime"
SKILL_VERSION = "0.4.0"


def _prepare_via_runtime() -> None:
    compat_aliases = {
        "bool8": np.bool_,
        "object0": np.object_,
        "int0": np.intp,
        "uint0": np.uintp,
        "uint": np.uint64,
        "float_": np.float64,
        "longfloat": np.longdouble,
        "singlecomplex": np.complex64,
        "complex_": np.complex128,
        "cfloat": np.complex128,
        "clongfloat": np.clongdouble,
        "longcomplex": np.clongdouble,
        "void0": np.void,
        "bytes0": np.bytes_,
        "str0": np.str_,
        "string_": np.bytes_,
        "unicode_": np.str_,
    }
    for alias, target in compat_aliases.items():
        if not hasattr(np, alias):
            setattr(np, alias, target)


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
            description="PAGA and DPT-based pseudotime trajectory analysis for scRNA-seq.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "dpt"),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="PAGA and DPT-based pseudotime trajectory analysis for scRNA-seq.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "dpt"),
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md: %s", exc)

# ---------------------------------------------------------------------------
# Method registry
# ---------------------------------------------------------------------------

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "dpt": MethodConfig(
        name="dpt",
        description="PAGA + Diffusion Pseudotime (scanpy built-in)",
        dependencies=("scanpy",),
    ),
    "palantir": MethodConfig(
        name="palantir",
        description="Palantir pseudotime with diffusion maps and waypoint sampling",
        dependencies=("palantir",),
    ),
    "via": MethodConfig(
        name="via",
        description="VIA pseudotime with automatic terminal-state inference",
        dependencies=("pyVIA",),
    ),
    "cellrank": MethodConfig(
        name="cellrank",
        description="CellRank fate mapping with GPCCA on pseudotime/connectivity kernels",
        dependencies=("cellrank",),
    ),
}

SUPPORTED_METHODS = tuple(METHOD_REGISTRY.keys())
METHOD_PARAM_DEFAULTS: dict[str, dict[str, object]] = {
    "dpt": {
        "cluster_key": "leiden",
        "root_cluster": None,
        "root_cell": None,
        "n_dcs": 10,
        "n_genes": 50,
        "corr_method": "pearson",
    },
    "palantir": {
        "cluster_key": "leiden",
        "root_cluster": None,
        "root_cell": None,
        "n_dcs": 10,
        "n_genes": 50,
        "corr_method": "pearson",
        "palantir_knn": 30,
        "palantir_num_waypoints": 1200,
        "palantir_max_iterations": 25,
        "palantir_seed": 20,
    },
    "via": {
        "cluster_key": "leiden",
        "root_cluster": None,
        "root_cell": None,
        "n_dcs": 10,
        "n_genes": 50,
        "corr_method": "pearson",
        "via_knn": 30,
        "via_seed": 20,
    },
    "cellrank": {
        "cluster_key": "leiden",
        "root_cluster": None,
        "root_cell": None,
        "n_dcs": 10,
        "n_genes": 50,
        "corr_method": "pearson",
        "cellrank_n_states": 3,
        "cellrank_schur_components": 20,
        "cellrank_frac_to_keep": 0.3,
        "cellrank_use_velocity": False,
    },
}

# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------

# Currently only DPT is supported; dispatch kept for future methods.
_METHOD_DISPATCH = {
    "dpt": "dpt",
    "palantir": "palantir",
    "via": "via",
    "cellrank": "cellrank",
}


def generate_trajectory_figures(
    adata,
    trajectory_genes: pd.DataFrame,
    output_dir: Path,
    *,
    method: str,
    cluster_key: str,
    pseudotime_key: str,
) -> list[str]:
    """Generate trajectory visualization figures."""
    figures = []
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    if method == "dpt":
        try:
            logger.info("Generating PAGA graph...")
            fig_path = sc_traj.plot_paga_graph(
                adata,
                output_dir=figures_dir,
                cluster_key=cluster_key,
                title="PAGA Connectivity Graph",
            )
            if fig_path:
                figures.append(fig_path)
        except Exception as e:
            logger.warning(f"PAGA graph plot failed: {e}")

    # Pseudotime UMAP
    try:
        logger.info("Generating pseudotime UMAP...")
        fig_path = sc_traj.plot_pseudotime_umap(
            adata,
            output_dir=figures_dir,
            pseudotime_key=pseudotime_key,
            title=f"{method.upper()} Pseudotime",
        )
        if fig_path:
            figures.append(fig_path)
    except Exception as e:
        logger.warning(f"Pseudotime UMAP plot failed: {e}")

    # Diffusion components
    try:
        logger.info("Generating diffusion component plots...")
        fig_paths = sc_traj.plot_diffusion_components(
            adata,
            output_dir=figures_dir,
            n_components=3,
        )
        figures.extend(fig_paths)
    except Exception as e:
        logger.warning(f"Diffusion component plots failed: {e}")

    # Trajectory gene heatmap
    try:
        logger.info("Generating trajectory gene heatmap...")
        fig_path = sc_traj.plot_trajectory_gene_heatmap(
            adata,
            trajectory_genes,
            output_dir=figures_dir,
            pseudotime_key=pseudotime_key,
            n_genes=30,
            title="Trajectory-Associated Genes",
        )
        if fig_path:
            figures.append(fig_path)
    except Exception as e:
        logger.warning(f"Trajectory gene heatmap failed: {e}")

    return figures


def write_pseudotime_report(
    output_dir: Path,
    summary: dict,
    params: dict,
    input_file: str | None,
    top_genes: pd.DataFrame,
) -> None:
    """Write pseudotime analysis report."""
    backend = str(summary.get("backend", summary.get("method", "NA")))
    header = generate_report_header(
        title="Single-Cell Pseudotime Analysis Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": str(params.get("method", "dpt")),
            "Backend": backend,
            "Root Cluster": str(params.get("root_cluster", "auto")),
            "N Clusters": str(summary.get("n_clusters", "N/A")),
            "Trajectory Genes": str(summary.get("n_trajectory_genes", 0)),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Requested method**: {params.get('method', 'dpt')}",
        f"- **Execution backend**: {backend}",
        f"- **Root cluster**: {params.get('root_cluster', 'auto-detected')}",
        f"- **Root cell**: {summary.get('root_cell_name', summary.get('root_cell', 'N/A'))}",
        f"- **Number of clusters**: {summary.get('n_clusters', 'N/A')}",
        f"- **Trajectory genes found**: {summary.get('n_trajectory_genes', 0)}",
        f"- **Pseudotime range**: [{summary.get('pseudotime_min', 0):.3f}, {summary.get('pseudotime_max', 1):.3f}]",
        "",
        "## Methods\n",
    ]
    if params.get("method") == "dpt":
        body_lines.extend(
            [
                "### PAGA (Partition-based Graph Abstraction)",
                "PAGA estimates connectivity between clusters by quantifying the connectivity",
                "of the underlying single-cell graph at each cluster resolution.\n",
                "### Diffusion Map",
                "Diffusion maps provide a non-linear dimensionality reduction that preserves",
                "the underlying manifold structure of the data.\n",
                "### DPT (Diffusion Pseudotime)",
                "DPT uses random walks on the diffusion graph to estimate pseudotemporal",
                "ordering of cells from a root cell.\n",
            ]
        )
    elif params.get("method") == "palantir":
        body_lines.extend(
            [
                "### Palantir",
                "Palantir computes diffusion maps, determines a multiscale manifold, and",
                "uses waypoint sampling to infer pseudotime, entropy, and fate probabilities.\n",
            ]
        )
        if summary.get("mean_entropy") is not None:
            body_lines.append(f"- **Mean Palantir entropy**: {summary['mean_entropy']:.4f}")
        if summary.get("n_terminal_states") is not None:
            body_lines.append(f"- **Terminal states with fate probabilities**: {summary['n_terminal_states']}")
        body_lines.append("")
    elif params.get("method") == "via":
        body_lines.extend(
            [
                "### VIA",
                "VIA builds a graph-based trajectory with automatic terminal-state discovery.",
                "When the upstream pyVIA backend is unstable on the current environment,",
                "OmicsClaw keeps the command successful by falling back to a diffusion-pseudotime-compatible path.\n",
            ]
        )
        if summary.get("n_terminal_states") is not None:
            body_lines.append(f"- **Terminal states with fate probabilities**: {summary['n_terminal_states']}")
        body_lines.append("")
    else:
        body_lines.extend(
            [
                "### CellRank",
                "CellRank fits a transition kernel on the single-cell graph and uses GPCCA",
                "to summarize macrostates, terminal states, and fate probabilities.\n",
            ]
        )
        if summary.get("kernel_mode") is not None:
            body_lines.append(f"- **Kernel mode**: {summary['kernel_mode']}")
        if summary.get("n_macrostates") is not None:
            body_lines.append(f"- **Macrostates**: {summary['n_macrostates']}")
        if summary.get("n_terminal_states") is not None:
            body_lines.append(f"- **Terminal states with fate probabilities**: {summary['n_terminal_states']}")
        body_lines.append("")
    body_lines.extend(["", "## Top Trajectory Genes\n"])

    # Add top genes table
    body_lines.append("| Gene | Correlation | P-value |")
    body_lines.append("|------|-------------|---------|")
    for _, row in top_genes.head(20).iterrows():
        gene = row.get("gene", "N/A")
        corr = row.get("correlation", 0)
        pval = row.get("pvalue", 1)
        body_lines.append(f"| {gene} | {corr:.3f} | {pval:.2e} |")
    body_lines.append("")

    body_lines.extend([
        "## Parameters\n",
        f"- `--method`: {params.get('method', 'dpt')}",
        f"- `--cluster-key`: {params.get('cluster_key', 'leiden')}",
        f"- `--root-cluster`: {params.get('root_cluster', 'auto')}",
        f"- `--n-dcs`: {params.get('n_dcs', 10)}",
        f"- `--n-genes`: {params.get('n_genes', 50)}",
        f"- `--corr-method`: {params.get('corr_method', 'pearson')}",
        "",
        "## Output Files\n",
        "- `adata_with_trajectory.h5ad` — AnnData with pseudotime and diffusion map",
        "- `figures/pseudotime_umap.png` — Pseudotime on UMAP",
        "- `figures/diffusion_components.png` — Diffusion map components",
        "- `figures/trajectory_gene_heatmap.png` — Heatmap of trajectory genes",
        "- `tables/trajectory_genes.csv` — All trajectory-associated genes",
        "",
        "## Interpretation\n",
        "- **Pseudotime** represents the inferred temporal ordering (0 = root, 1 = terminal)",
        "- **Trajectory genes** are correlated with pseudotime and may drive transitions",
        "",
    ])
    if params.get("method") == "dpt":
        body_lines.insert(body_lines.index("- `figures/pseudotime_umap.png` — Pseudotime on UMAP"), "- `figures/paga_graph.png` — PAGA connectivity graph")
        body_lines.insert(body_lines.index("- **Trajectory genes** are correlated with pseudotime and may drive transitions"), "- **PAGA edges** show significant connectivity between clusters")

    footer = generate_report_footer()
    report = header + "\n" + "\n".join(body_lines) + "\n" + footer

    (output_dir / "report.md").write_text(report)


def generate_demo_data():
    """Generate demo data with trajectory structure."""
    import scanpy as sc

    logger.info("Generating demo data with trajectory structure...")

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
        sc.tl.umap(adata)

        # Try leiden clustering
        try:
            sc.tl.leiden(adata, resolution=0.8)
        except ImportError:
            logger.warning("leidenalg not installed, using kmeans")
            from sklearn.cluster import KMeans
            kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
            adata.obs['leiden'] = pd.Categorical(
                kmeans.fit_predict(adata.obsm['X_pca'][:, :30]).astype(str)
            )

        logger.info(f"Generated: {adata.n_obs} cells x {adata.n_vars} genes, {adata.obs['leiden'].nunique()} clusters")
    except Exception as e:
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
        sc.tl.umap(adata)

        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
        adata.obs['leiden'] = pd.Categorical(kmeans.fit_predict(adata.obsm['X_pca'][:, :30]).astype(str))

    return adata


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Pseudotime Analysis")
    parser.add_argument("--input", dest="input_path", help="Input AnnData file (.h5ad)")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with demo data")
    parser.add_argument("--cluster-key", default="leiden", help="Cluster key (default: leiden)")
    parser.add_argument("--root-cluster", default=None, help="Root cluster for pseudotime")
    parser.add_argument("--root-cell", type=int, default=None, help="Root cell index")
    parser.add_argument("--n-dcs", type=int, default=10, help="Number of diffusion components")
    parser.add_argument("--n-genes", type=int, default=50, help="Number of trajectory genes")
    parser.add_argument(
        "--method",
        dest="analysis_method",
        default="dpt",
        choices=list(METHOD_REGISTRY.keys()),
        help="Trajectory analysis method (default: dpt)",
    )
    parser.add_argument(
        "--analysis-method",
        dest="analysis_method",
        choices=list(METHOD_REGISTRY.keys()),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--corr-method",
        default="pearson",
        choices=["pearson", "spearman"],
        help="Correlation method for trajectory gene ranking",
    )
    parser.add_argument("--palantir-knn", type=int, default=30, help="Palantir kNN graph size")
    parser.add_argument("--palantir-num-waypoints", type=int, default=1200, help="Palantir waypoint count")
    parser.add_argument("--palantir-max-iterations", type=int, default=25, help="Palantir maximum pseudotime iterations")
    parser.add_argument("--palantir-seed", type=int, default=20, help="Palantir random seed")
    parser.add_argument("--via-knn", type=int, default=30, help="VIA kNN graph size")
    parser.add_argument("--via-seed", type=int, default=20, help="VIA random seed")
    parser.add_argument("--cellrank-n-states", type=int, default=3, help="CellRank number of macrostates")
    parser.add_argument("--cellrank-schur-components", type=int, default=20, help="CellRank Schur components")
    parser.add_argument("--cellrank-frac-to-keep", type=float, default=0.3, help="CellRank pseudotime kernel sparsification")
    parser.add_argument("--cellrank-use-velocity", action="store_true", help="Prefer CellRank VelocityKernel when velocity layers are available")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

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
        adata = sc_io.smart_load(input_path, skill_name=SKILL_NAME)
        input_file = str(input_path)

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")
    apply_preflight(
        preflight_sc_pseudotime(
            adata,
            method=args.analysis_method,
            cluster_key=args.cluster_key,
            root_cluster=args.root_cluster,
            root_cell=args.root_cell,
            source_path=input_file,
        ),
        logger,
    )

    # Check cluster key
    if args.cluster_key not in adata.obs.columns:
        logger.error(f"Cluster key '{args.cluster_key}' not found in adata.obs")
        logger.info(f"Available columns: {list(adata.obs.columns)}")
        raise ValueError(f"Column '{args.cluster_key}' not found")

    # Ensure neighbors are computed
    import scanpy as sc
    if "neighbors" not in adata.uns:
        logger.info("Computing neighbor graph...")
        sc.pp.neighbors(adata)
    if "X_umap" not in adata.obsm:
        logger.info("Computing UMAP for trajectory visualizations...")
        sc.tl.umap(adata)

    # Validate analysis method & check dependencies
    if args.analysis_method == "via":
        _prepare_via_runtime()
    analysis_method = validate_method_choice(args.analysis_method, METHOD_REGISTRY)

    params = dict(METHOD_PARAM_DEFAULTS[analysis_method])
    params.update(
        {
            "method": analysis_method,
            "cluster_key": args.cluster_key,
            "root_cluster": args.root_cluster,
            "root_cell": args.root_cell,
            "n_dcs": args.n_dcs,
            "n_genes": args.n_genes,
            "corr_method": args.corr_method,
        }
    )
    if analysis_method == "palantir":
        params.update(
            {
                "palantir_knn": args.palantir_knn,
                "palantir_num_waypoints": args.palantir_num_waypoints,
                "palantir_max_iterations": args.palantir_max_iterations,
                "palantir_seed": args.palantir_seed,
            }
        )
    elif analysis_method == "via":
        params.update(
            {
                "via_knn": args.via_knn,
                "via_seed": args.via_seed,
            }
        )
    elif analysis_method == "cellrank":
        params.update(
            {
                "cellrank_n_states": args.cellrank_n_states,
                "cellrank_schur_components": args.cellrank_schur_components,
                "cellrank_frac_to_keep": args.cellrank_frac_to_keep,
                "cellrank_use_velocity": args.cellrank_use_velocity,
            }
        )

    pseudotime_key = "dpt_pseudotime"
    if analysis_method == "dpt":
        logger.info("Running PAGA analysis...")
        sc_traj.run_paga_analysis(adata, cluster_key=args.cluster_key)

        logger.info("Running diffusion map...")
        diffmap_result = sc_traj.run_diffusion_map(adata, n_comps=max(15, args.n_dcs + 5))

        logger.info("Running DPT pseudotime...")
        dpt_result = sc_traj.run_dpt_pseudotime(
            adata,
            root_cell_indices=[args.root_cell] if args.root_cell is not None else None,
            root_cluster=args.root_cluster,
            cluster_key=args.cluster_key,
            n_dcs=args.n_dcs,
        )
        summary = {
            "method": analysis_method,
            "backend": analysis_method,
            "n_clusters": int(adata.obs[args.cluster_key].nunique()),
            "n_trajectory_genes": 0,
            "root_cell": int(dpt_result["root_cells"][0]) if dpt_result["root_cells"] else None,
            "root_cell_name": str(adata.obs_names[int(dpt_result["root_cells"][0])]) if dpt_result["root_cells"] else None,
            "pseudotime_min": float(adata.obs["dpt_pseudotime"].min()),
            "pseudotime_max": float(adata.obs["dpt_pseudotime"].max()),
            "n_diffusion_components": diffmap_result["diffmap"].shape[1],
        }
    elif analysis_method == "palantir":
        logger.info("Resolving Palantir early cell...")
        early_cell_name = sc_traj.resolve_palantir_early_cell(
            adata,
            root_cell=args.root_cell,
            root_cluster=args.root_cluster,
            cluster_key=args.cluster_key,
        )
        logger.info("Running Palantir analysis...")
        palantir_result = sc_traj.run_palantir_pseudotime(
            adata,
            early_cell=early_cell_name,
            knn=args.palantir_knn,
            n_components=max(5, args.n_dcs),
            num_waypoints=args.palantir_num_waypoints,
            max_iterations=args.palantir_max_iterations,
            seed=args.palantir_seed,
        )
        pseudotime_key = "palantir_pseudotime"
        fate_probs = palantir_result.get("fate_probabilities")
        summary = {
            "method": analysis_method,
            "backend": analysis_method,
            "n_clusters": int(adata.obs[args.cluster_key].nunique()),
            "n_trajectory_genes": 0,
            "root_cell": int(np.where(adata.obs_names == early_cell_name)[0][0]),
            "root_cell_name": early_cell_name,
            "pseudotime_min": float(adata.obs[pseudotime_key].min()),
            "pseudotime_max": float(adata.obs[pseudotime_key].max()),
            "n_diffusion_components": int(np.asarray(adata.obsm["DM_EigenVectors"]).shape[1]) if "DM_EigenVectors" in adata.obsm else 0,
            "mean_entropy": float(np.nanmean(palantir_result["entropy"])) if palantir_result.get("entropy") is not None else None,
            "n_terminal_states": int(fate_probs.shape[1]) if fate_probs is not None else None,
        }
    elif analysis_method == "via":
        logger.info("Running VIA analysis...")
        via_result = sc_traj.run_via_pseudotime(
            adata,
            root_cell=args.root_cell,
            root_cluster=args.root_cluster,
            cluster_key=args.cluster_key,
            knn=args.via_knn,
            n_components=max(2, args.n_dcs),
            seed=args.via_seed,
        )
        pseudotime_key = "via_pseudotime"
        fate_probs = via_result.get("fate_probabilities")
        summary = {
            "method": analysis_method,
            "backend": via_result.get("method", analysis_method),
            "n_clusters": int(adata.obs[args.cluster_key].nunique()),
            "n_trajectory_genes": 0,
            "root_cell": int(via_result["root_cell"]),
            "root_cell_name": str(via_result["root_cell_name"]),
            "pseudotime_min": float(np.nanmin(adata.obs[pseudotime_key].to_numpy())),
            "pseudotime_max": float(np.nanmax(adata.obs[pseudotime_key].to_numpy())),
            "n_diffusion_components": int(max(2, args.n_dcs)),
            "n_terminal_states": int(fate_probs.shape[1]) if fate_probs is not None and hasattr(fate_probs, "shape") and len(fate_probs.shape) == 2 else None,
        }
    else:
        logger.info("Running CellRank analysis...")
        cellrank_result = sc_traj.run_cellrank_pseudotime(
            adata,
            root_cell=args.root_cell,
            root_cluster=args.root_cluster,
            cluster_key=args.cluster_key,
            n_states=args.cellrank_n_states,
            schur_components=args.cellrank_schur_components,
            frac_to_keep=args.cellrank_frac_to_keep,
            use_velocity=args.cellrank_use_velocity,
            n_dcs=args.n_dcs,
        )
        pseudotime_key = "dpt_pseudotime"
        fate_probs = cellrank_result.get("fate_probabilities")
        summary = {
            "method": analysis_method,
            "backend": analysis_method,
            "n_clusters": int(adata.obs[args.cluster_key].nunique()),
            "n_trajectory_genes": 0,
            "root_cell": int(cellrank_result["root_cell"]) if cellrank_result.get("root_cell") is not None else None,
            "root_cell_name": str(cellrank_result["root_cell_name"]) if cellrank_result.get("root_cell_name") is not None else None,
            "pseudotime_min": float(np.nanmin(adata.obs[pseudotime_key].to_numpy())),
            "pseudotime_max": float(np.nanmax(adata.obs[pseudotime_key].to_numpy())),
            "n_diffusion_components": int(args.n_dcs),
            "n_terminal_states": int(len(cellrank_result.get("terminal_states", []))),
            "n_macrostates": int(cellrank_result.get("n_macrostates", 0)),
            "kernel_mode": cellrank_result.get("kernel_mode"),
        }
        driver_genes = cellrank_result.get("driver_genes", {})
        if driver_genes:
            driver_rows = []
            for lineage, genes in driver_genes.items():
                for rank, gene in enumerate(genes, start=1):
                    driver_rows.append({"lineage": lineage, "rank": rank, "gene": gene})
            pd.DataFrame(driver_rows).to_csv(tables_dir / "cellrank_driver_genes.csv", index=False)
            summary["n_driver_genes"] = int(len(driver_rows))

    logger.info("Finding trajectory genes...")
    trajectory_genes = sc_traj.find_trajectory_genes(
        adata,
        pseudotime_key=pseudotime_key,
        n_genes=args.n_genes,
        method=args.corr_method,
    )
    summary["n_trajectory_genes"] = len(trajectory_genes)

    logger.info(f"Found {len(trajectory_genes)} trajectory-associated genes")

    # Generate figures
    logger.info("Generating figures...")
    generate_trajectory_figures(
        adata,
        trajectory_genes,
        output_dir,
        method=analysis_method,
        cluster_key=args.cluster_key,
        pseudotime_key=pseudotime_key,
    )

    trajectory_genes.to_csv(tables_dir / "trajectory_genes.csv", index=False)
    logger.info(f"  Saved: tables/trajectory_genes.csv")

    # Write report
    logger.info("Writing report...")
    write_pseudotime_report(output_dir, summary, params, input_file, trajectory_genes)

    # Save data
    output_h5ad = output_dir / "adata_with_trajectory.h5ad"
    from skills.singlecell._lib.adata_utils import store_analysis_metadata
    store_analysis_metadata(adata, SKILL_NAME, analysis_method, params)
    adata.write_h5ad(output_h5ad)
    logger.info(f"Saved: {output_h5ad}")

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    cmd = f"python sc_pseudotime.py --output {output_dir} --cluster-key {args.cluster_key}"
    if input_file:
        cmd += f" --input {input_file}"
    if args.root_cluster:
        cmd += f" --root-cluster {args.root_cluster}"
    cmd += (
        f" --n-dcs {args.n_dcs} --n-genes {args.n_genes}"
        f" --method {analysis_method} --corr-method {args.corr_method}"
    )
    if args.root_cell is not None:
        cmd += f" --root-cell {args.root_cell}"
    if analysis_method == "palantir":
        cmd += (
            f" --palantir-knn {args.palantir_knn}"
            f" --palantir-num-waypoints {args.palantir_num_waypoints}"
            f" --palantir-max-iterations {args.palantir_max_iterations}"
            f" --palantir-seed {args.palantir_seed}"
        )
    if analysis_method == "via":
        cmd += f" --via-knn {args.via_knn} --via-seed {args.via_seed}"
    if analysis_method == "cellrank":
        cmd += (
            f" --cellrank-n-states {args.cellrank_n_states}"
            f" --cellrank-schur-components {args.cellrank_schur_components}"
            f" --cellrank-frac-to-keep {args.cellrank_frac_to_keep}"
        )
        if args.cellrank_use_velocity:
            cmd += " --cellrank-use-velocity"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    packages = ["scanpy", "anndata", "numpy", "pandas", "matplotlib"]
    if analysis_method == "palantir":
        packages.append("palantir")
    if analysis_method == "via":
        packages.append("pyVIA")
    if analysis_method == "cellrank":
        packages.extend(["cellrank", "pygpcca"])
    _write_repro_requirements(repro_dir, packages)

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
    print(f"  Root cluster: {params.get('root_cluster', 'auto')}")
    print(f"  Clusters: {summary['n_clusters']}")
    print(f"  Trajectory genes: {len(trajectory_genes)}")
    print(f"  Output: {output_dir}")


if __name__ == "__main__":
    main()
