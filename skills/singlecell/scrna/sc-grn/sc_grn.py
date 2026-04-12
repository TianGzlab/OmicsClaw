#!/usr/bin/env python3
"""Single-Cell Gene Regulatory Network Analysis - pySCENIC workflow.

Usage:
    python sc_grn.py --input <data.h5ad> --output <dir> --tf-list <tf.txt> --db <db_glob> --motif <motif.tbl>
    python sc_grn.py --demo --output <dir>

This skill performs GRN inference using pySCENIC:
1. GRNBoost2 for co-expression network inference
2. cisTarget for motif enrichment and pruning
3. AUCell for regulon activity scoring

Requirements:
    - arboreto (GRNBoost2)
    - pyscenic
    - External databases: TF list, cisTarget DBs, motif annotations
"""
from __future__ import annotations

import argparse
import json
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
    write_replot_hint,
)
from omicsclaw.common.checksums import sha256_file
from skills.singlecell._lib.viz_utils import save_figure
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib import grn as sc_grn_utils
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_grn
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    get_matrix_contract,
    infer_x_matrix_kind,
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-grn"
SKILL_VERSION = "0.2.0"

# R Enhanced plotting configuration
R_ENHANCED_PLOTS = {
    # sc-grn exports AUC scores as gene_expression.csv (regulons as features).
    # No UMAP/embedding CSV — embedding renderers not appropriate here.
    "plot_feature_violin": "r_regulon_violin.png",
    "plot_feature_cor": "r_regulon_cor.png",
}


def _render_r_enhanced(output_dir: Path, figure_data_dir: Path, r_enhanced: bool) -> list[str]:
    """Render R Enhanced plots if requested. Returns list of generated paths."""
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths: list[str] = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths


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
            description="Gene regulatory network inference with pySCENIC-style workflow.",
            result_payload=result_payload,
            preferred_method="pyscenic",
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Gene regulatory network inference with pySCENIC-style workflow.",
            result_payload=result_payload,
            preferred_method="pyscenic",
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md: %s", exc)

# Database download instructions
DB_DOWNLOAD_INSTRUCTIONS = """
================================================================================
pySCENIC Database Files Required for Full GRN Analysis
================================================================================

For full pySCENIC analysis with motif enrichment, download the following files:

1. TF List (transcription factor gene symbols):
   wget https://raw.githubusercontent.com/aertslab/pySCENIC/master/resources/hs_hgnc_tfs.txt

2. cisTarget Database (motif-to-gene mappings):
   wget https://resources.aertslab.org/cistarget/databases/homo_sapiens/hg38/refseq_r80/mc9nr/gene_based/hg38__refseq_r80__mc9nr_gg6_500bp_upstream.feather

3. Motif Annotations (TF-to-motif mappings):
   wget https://resources.aertslab.org/cistarget/motif2tf/motifs-v9-nr.hgnc-m0.001-o0.0.tbl

Alternatively, store databases in: examples/databases/motifs/ (or a custom path)

For more databases, visit:
- TF list: https://github.com/aertslab/pySCENIC/tree/master/resources
- cisTarget DBs: https://resources.aertslab.org/cistarget/
================================================================================
"""


def print_db_instructions():
    """Print instructions for downloading pySCENIC databases."""
    print(DB_DOWNLOAD_INSTRUCTIONS)


# ---------------------------------------------------------------------------
# Figure manifest helpers
# ---------------------------------------------------------------------------

def _write_figure_manifest(output_dir: Path, figure_paths: list[str]) -> None:
    """Write figures/manifest.json cataloguing all generated figures."""
    manifest = {
        "skill": SKILL_NAME,
        "recipe_id": "standard-sc-grn-gallery",
        "figures": [{"filename": Path(path).name, "path": str(path)} for path in figure_paths],
    }
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    (figures_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _write_figure_data(
    output_dir: Path,
    *,
    adjacencies: pd.DataFrame,
    regulons: list[dict],
    auc_matrix: pd.DataFrame,
    cluster_labels: pd.Series | None = None,
) -> dict[str, str]:
    """Write figure_data/ with plot-ready CSVs and a manifest."""
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}

    # Top adjacencies (plot-ready subset)
    top_adj = adjacencies.nlargest(500, "importance") if len(adjacencies) > 500 else adjacencies
    files["top_adjacencies"] = "top_adjacencies.csv"
    top_adj.to_csv(figure_data_dir / files["top_adjacencies"], index=False)

    # Regulon summary
    reg_df = pd.DataFrame([
        {"tf": r["tf"], "n_targets": r["n_targets"], "motif_nes": r.get("motif_nes")}
        for r in regulons
    ])
    files["regulon_summary"] = "regulon_summary.csv"
    reg_df.to_csv(figure_data_dir / files["regulon_summary"], index=False)

    # AUC matrix (if manageable size)
    if auc_matrix.shape[1] > 0:
        files["auc_matrix"] = "auc_matrix.csv"
        auc_matrix.to_csv(figure_data_dir / files["auc_matrix"])

        # Write gene_expression.csv in long format for plot_feature_violin/plot_feature_cor.
        # Pivots AUC matrix wide -> long, treating each regulon/TF as a "gene" feature.
        # Includes cluster/cell-type column so the violin plot groups by cluster, not "All".
        try:
            sample_n = min(len(auc_matrix), 1000)
            sampled = auc_matrix.sample(n=sample_n, random_state=42) if len(auc_matrix) > sample_n else auc_matrix
            # Build cluster lookup for sampled cells
            cluster_lookup: dict[str, str] = {}
            if cluster_labels is not None:
                for cell_id in sampled.index:
                    if cell_id in cluster_labels.index:
                        cluster_lookup[str(cell_id)] = str(cluster_labels[cell_id])
            long_rows = []
            for tf in sampled.columns:
                for cell_id, val in sampled[tf].items():
                    row = {"cell_id": str(cell_id), "gene": tf, "expression": float(val)}
                    if cluster_lookup:
                        row["cluster"] = cluster_lookup.get(str(cell_id), "Unknown")
                    long_rows.append(row)
            pd.DataFrame(long_rows).to_csv(figure_data_dir / "gene_expression.csv", index=False)
            files["gene_expression"] = "gene_expression.csv"
        except Exception:
            pass

    manifest = {"skill": SKILL_NAME, "available_files": files}
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return files


# ---------------------------------------------------------------------------
# Degenerate output detection  (UX three-layer guidance)
# ---------------------------------------------------------------------------

def _check_degenerate_output(
    regulons: list[dict],
    adjacencies: pd.DataFrame,
    auc_matrix: pd.DataFrame,
    params: dict,
) -> dict | None:
    """Return a diagnostics dict if output is degenerate, else None."""
    n_regulons = len(regulons)
    n_adj = len(adjacencies) if adjacencies is not None else 0

    if n_regulons == 0 and n_adj == 0:
        return {
            "degenerate": True,
            "reason": "no_regulons_no_adjacencies",
            "n_regulons": 0,
            "n_adjacencies": 0,
            "suggested_actions": [
                "Provide a TF list that matches your gene names: --tf-list <file>",
                "Ensure the input data is preprocessed with sc-preprocessing first",
                "Check species: human genes are UPPER-CASE (TP53), mouse are Title-case (Tp53)",
            ],
        }
    if n_regulons == 0 and n_adj > 0:
        return {
            "degenerate": True,
            "reason": "adjacencies_but_no_regulons",
            "n_regulons": 0,
            "n_adjacencies": n_adj,
            "suggested_actions": [
                "The TF list may not overlap with genes in the data. Check gene naming convention.",
                "Try providing a broader TF list: --tf-list <file>",
            ],
        }
    # Check if AUC matrix is all zeros / NaN
    if auc_matrix is not None and auc_matrix.shape[1] > 0:
        non_zero_ratio = (auc_matrix.abs().sum().sum()) / max(auc_matrix.size, 1)
        if non_zero_ratio < 1e-10:
            return {
                "degenerate": True,
                "reason": "all_zero_auc",
                "n_regulons": n_regulons,
                "n_adjacencies": n_adj,
                "suggested_actions": [
                    "Regulon target genes may not be expressed in the data.",
                    "Check that input data is normalized (not raw counts in X).",
                ],
            }
    return None


def _print_degenerate_guidance(diag: dict) -> None:
    """Print actionable guidance to stdout (layer 1 of three-layer rule)."""
    reason = diag.get("reason", "unknown")
    print()
    print("  *** GRN analysis produced degenerate output ***")
    if reason == "no_regulons_no_adjacencies":
        print("  No TF-target adjacencies or regulons were identified.")
        print()
        print("  How to fix:")
        print("    Option 1 -- Provide a TF list matching your gene names:")
        print("      python omicsclaw.py run sc-grn --input data.h5ad --tf-list hs_hgnc_tfs.txt --output dir")
        print("    Option 2 -- Ensure preprocessing is done first:")
        print("      python omicsclaw.py run sc-preprocessing --input raw.h5ad --output dir")
        print("    Option 3 -- Check species naming (human=UPPER, mouse=Title):")
        print("      head -5 your_tf_list.txt")
    elif reason == "adjacencies_but_no_regulons":
        print(f"  Found {diag['n_adjacencies']} adjacencies but 0 regulons.")
        print("  This means TFs in your list did not match genes in the data well enough.")
        print()
        print("  How to fix:")
        print("    Option 1 -- Provide a TF list that matches your data species/gene names")
        print("    Option 2 -- Lower --n-top-targets to be less restrictive")
    elif reason == "all_zero_auc":
        print("  All regulon activity scores are zero -- targets may not be expressed.")
        print()
        print("  How to fix:")
        print("    Option 1 -- Verify input is normalized expression (not raw counts)")
        print("    Option 2 -- Run sc-preprocessing first")
    print()


# ---------------------------------------------------------------------------
# Figure generation
# ---------------------------------------------------------------------------

def generate_grn_figures(
    adata,
    regulons: list[dict],
    auc_matrix: pd.DataFrame,
    output_dir: Path,
    cluster_key: str = "leiden",
) -> list[str]:
    """Generate GRN visualization figures."""
    figures = []
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Regulon activity UMAP
    try:
        logger.info("Generating regulon activity UMAP...")
        fig_paths = sc_grn_utils.plot_regulon_activity_umap(
            adata,
            auc_matrix,
            output_dir=figures_dir,
            n_top=9,
        )
        figures.extend(fig_paths)
    except Exception as e:
        logger.warning(f"Regulon activity UMAP failed: {e}")

    # Regulon heatmap
    try:
        logger.info("Generating regulon heatmap...")
        cluster_labels = adata.obs[cluster_key] if cluster_key in adata.obs.columns else None
        fig_path = sc_grn_utils.plot_regulon_heatmap(
            auc_matrix,
            output_dir=figures_dir,
            cluster_labels=cluster_labels,
            n_top=20,
            title="Regulon Activity by Cluster",
        )
        if fig_path:
            figures.append(fig_path)
    except Exception as e:
        logger.warning(f"Regulon heatmap failed: {e}")

    # Regulon network
    try:
        logger.info("Generating regulon network diagram...")
        fig_path = sc_grn_utils.plot_regulon_network(
            regulons,
            output_dir=figures_dir,
            n_top=20,
            min_targets=5,
            title="Gene Regulatory Network",
        )
        if fig_path:
            figures.append(fig_path)
    except Exception as e:
        logger.warning(f"Regulon network plot failed: {e}")

    return figures


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_grn_report(
    output_dir: Path,
    summary: dict,
    params: dict,
    input_file: str | None,
    top_regulons: list[dict],
    degenerate_diag: dict | None = None,
    used_fallback: bool = False,
    fallback_reason: str | None = None,
) -> None:
    """Write GRN analysis report."""
    header = generate_report_header(
        title="Single-Cell Gene Regulatory Network Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Regulons": str(summary.get("n_regulons", 0)),
            "TFs": str(summary.get("n_tfs", 0)),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Transcription factors**: {summary.get('n_tfs', 'N/A')}",
        f"- **Regulons identified**: {summary.get('n_regulons', 0)}",
        f"- **Total adjacencies**: {summary.get('n_adjacencies', 0)}",
        f"- **Cells analyzed**: {summary.get('n_cells', 'N/A')}",
    ]

    if used_fallback:
        body_lines.extend([
            "",
            f"> **Note**: Fell back to correlation-based GRN inference. Reason: {fallback_reason or 'GRNBoost2 unavailable or failed.'}",
            "> Correlation-based results are approximate. For full analysis, provide --tf-list, --db, and --motif.",
        ])

    body_lines.extend([
        "",
        "## Methods\n",
        "### GRNBoost2",
        "GRNBoost2 is a gradient boosting-based method for inferring co-expression",
        "networks between TFs and target genes.\n",
        "### cisTarget",
        "cisTarget performs motif enrichment analysis to identify direct TF targets",
        "by matching regulatory sequences to known TF binding motifs.\n",
        "### AUCell",
        "AUCell calculates the activity of each regulon in each cell by computing",
        "the area under the recovery curve of gene expression rankings.\n",
        "",
        "## Top Regulons\n",
    ])

    # Add top regulons table
    body_lines.append("| TF | Targets | Motif NES |")
    body_lines.append("|----|---------|-----------|")
    for r in top_regulons[:15]:
        nes = f"{r.get('motif_nes', 0):.2f}" if r.get('motif_nes') else "N/A"
        body_lines.append(f"| {r['tf']} | {r['n_targets']} | {nes} |")
    body_lines.append("")

    body_lines.extend([
        "## Parameters\n",
        f"- `--tf-list`: {params.get('tf_list', 'N/A')}",
        f"- `--n-top-targets`: {params.get('n_top_targets', 50)}",
        f"- `--n-jobs`: {params.get('n_jobs', 4)}",
        "",
        "## Output Files\n",
        "- `processed.h5ad` -- AnnData with regulon activity scores and contracts",
        "- `tables/grn_adjacencies.csv` -- All TF-target adjacencies",
        "- `tables/grn_regulons.csv` -- Regulon summary",
        "- `tables/grn_regulon_targets.csv` -- TF-target pairs",
        "- `tables/grn_auc_matrix.csv` -- AUCell activity scores",
        "- `figures/regulon_activity_umap.png` -- Regulon activity on UMAP",
        "- `figures/regulon_heatmap.png` -- Regulon activity heatmap",
        "- `figures/regulon_network.png` -- Network diagram",
        "- `figure_data/` -- Plot-ready CSV data for downstream customization",
    ])

    # Troubleshooting section when degenerate
    if degenerate_diag is not None:
        reason = degenerate_diag.get("reason", "unknown")
        body_lines.extend([
            "",
            "## Troubleshooting: Degenerate GRN Output\n",
        ])
        if reason == "no_regulons_no_adjacencies":
            body_lines.extend([
                "### Cause 1: TF list does not match gene names in the data",
                "Check whether gene naming matches your species (human=UPPER, mouse=Title-case).",
                "```bash",
                "python omicsclaw.py run sc-grn --input data.h5ad --tf-list hs_hgnc_tfs.txt --output dir",
                "```\n",
                "### Cause 2: Input data not preprocessed",
                "GRN inference requires normalized, log-transformed expression.",
                "```bash",
                "python omicsclaw.py run sc-preprocessing --input raw.h5ad --output dir",
                "```\n",
            ])
        elif reason == "adjacencies_but_no_regulons":
            body_lines.extend([
                "### Cause: TF names do not overlap with data gene names",
                "Provide a TF list that uses the same gene naming convention as your data.\n",
            ])
        elif reason == "all_zero_auc":
            body_lines.extend([
                "### Cause: Target genes not expressed",
                "Ensure input is normalized expression, not raw counts.\n",
            ])

    body_lines.extend([
        "",
        "## Requirements\n",
        "This skill requires:",
        "- **pySCENIC** and **arboreto** packages (optional for correlation fallback)",
        "- **TF list file**: One TF symbol per line",
        "- **cisTarget databases**: .feather or .db files",
        "- **Motif annotations**: .tbl or .csv file",
        "",
        "### Database Sources\n",
        "- TF list: [pySCENIC resources](https://github.com/aertslab/pySCENIC/tree/master/resources)",
        "- cisTarget DBs: [cisTarget DBs](https://resources.aertslab.org/cistarget/)",
        "- Motif annotations: [motif2TF](https://resources.aertslab.org/cistarget/motif2tf/)",
        "",
    ])

    footer = generate_report_footer()
    report = header + "\n" + "\n".join(body_lines) + "\n" + footer

    (output_dir / "report.md").write_text(report)


# ---------------------------------------------------------------------------
# Demo data generation
# ---------------------------------------------------------------------------

def generate_demo_data():
    """Generate demo data for GRN analysis."""
    import scanpy as sc

    logger.info("Generating synthetic demo data...")

    np.random.seed(42)
    n_cells = 300
    n_genes = 1000

    # Generate synthetic counts
    counts = np.random.negative_binomial(5, 0.1, size=(n_cells, n_genes)).astype(np.float32)

    adata = sc.AnnData(
        X=counts,
        obs=pd.DataFrame(index=[f"cell_{i}" for i in range(n_cells)]),
        var=pd.DataFrame(index=[f"gene_{i}" for i in range(n_genes)]),
    )

    # Add some TF-like gene names
    tf_names = ["TP53", "MYC", "STAT1", "NFkB1", "SP1", "E2F1", "GATA1", "FOXA1", "CEBPB", "IRF1"]
    for i, tf in enumerate(tf_names):
        if i < len(adata.var_names):
            adata.var_names.values[i] = tf

    # Store raw counts in layers before normalization
    adata.layers["counts"] = adata.X.copy()

    # Preprocessing
    sc.pp.filter_genes(adata, min_cells=10)
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)

    # Snapshot raw counts after filtering
    adata.raw = adata.copy()

    sc.pp.highly_variable_genes(adata, n_top_genes=500)
    sc.pp.pca(adata)
    sc.pp.neighbors(adata)

    # Clustering
    try:
        sc.tl.leiden(adata, resolution=0.8)
    except ImportError:
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
        adata.obs['leiden'] = pd.Categorical(
            kmeans.fit_predict(adata.obsm['X_pca'][:, :30]).astype(str)
        )

    # UMAP
    sc.tl.umap(adata)

    # Set up contracts for demo data
    ensure_input_contract(adata, standardized=True)
    from skills.singlecell._lib.adata_utils import record_matrix_contract
    record_matrix_contract(
        adata,
        x_kind="normalized_expression",
        raw_kind="raw_counts_snapshot",
        layers={"counts": "raw_counts"},
        producer_skill="sc-grn-demo",
    )

    logger.info(f"Generated: {adata.n_obs} cells x {adata.n_vars} genes")

    return adata


def create_demo_tf_list(output_dir: Path) -> Path:
    """Create demo TF list file."""
    tf_file = output_dir / "demo_tf_list.txt"
    tf_list = ["TP53", "MYC", "STAT1", "NFkB1", "SP1", "E2F1", "GATA1", "FOXA1", "CEBPB", "IRF1",
               "JUN", "FOS", "ATF3", "CREB1", "ELK1", "SRF", "YY1", "CTCF", "MAX", "MXD1"]

    with open(tf_file, "w") as f:
        f.write("\n".join(tf_list))

    return tf_file


# ---------------------------------------------------------------------------
# Demo / fallback mode
# ---------------------------------------------------------------------------

def run_demo_mode(adata, output_dir: Path, params: dict) -> dict | None:
    """Run GRN analysis in demo mode (GRNBoost2 or correlation fallback)."""
    logger.warning("=" * 60)
    logger.warning("Demo mode: Running GRN inference")
    logger.warning("For full analysis, provide database files:")
    logger.warning("  --tf-list <file> --db <glob> --motif <file>")
    logger.warning("=" * 60)

    adjacencies = None
    regulons = []
    auc_matrix = pd.DataFrame(index=adata.obs_names)
    used_fallback = False
    fallback_reason = None

    # Prepare expression matrix
    ex_matrix = sc_grn_utils.prepare_expression_matrix(adata)

    # Create demo TF list
    tf_file = create_demo_tf_list(output_dir)
    tf_list = sc_grn_utils.load_tf_list(tf_file)

    # Filter TFs to those in data
    tf_list = [tf for tf in tf_list if tf in adata.var_names]
    logger.info(f"Using {len(tf_list)} TFs from demo list")

    if len(tf_list) == 0:
        logger.warning("No TFs from the demo list found in data gene names.")
        logger.warning("Gene name sample: %s", list(adata.var_names[:10]))
        return None

    # Try GRNBoost2 first, then fallback to correlation
    try:
        adjacencies = sc_grn_utils.run_grnboost2(
            ex_matrix,
            tf_list,
            seed=42,
            n_jobs=params.get("n_jobs", 4),
        )
    except ImportError:
        logger.warning("arboreto not installed, using correlation-based GRN")
        used_fallback = True
        fallback_reason = "arboreto package not installed"
        adjacencies = None
    except Exception as e:
        logger.warning(f"GRNBoost2 failed: {e}")
        logger.info("Falling back to correlation-based GRN inference...")
        used_fallback = True
        fallback_reason = f"GRNBoost2 error: {e}"
        adjacencies = None

    # Fallback to correlation-based GRN if GRNBoost2 failed
    if adjacencies is None or len(adjacencies) == 0:
        used_fallback = True
        if fallback_reason is None:
            fallback_reason = "GRNBoost2 returned empty results"
        try:
            adjacencies = sc_grn_utils.run_correlation_grn(
                ex_matrix,
                tf_list,
                method="spearman",
                n_top=params.get("n_top_targets", 50),
            )
            logger.info("Using correlation-based GRN results")
        except Exception as e:
            logger.error(f"Correlation-based GRN also failed: {e}")
            return None

    if used_fallback:
        logger.warning("FALLBACK: Used correlation-based GRN instead of GRNBoost2. Reason: %s", fallback_reason)
        print(f"\n  Note: Fell back to correlation-based GRN. Reason: {fallback_reason}")
        print("  For better results, install arboreto: pip install arboreto")

    # Create simple regulons from adjacencies
    for tf in tf_list:
        tf_adj = adjacencies[adjacencies["TF"] == tf].nlargest(params.get("n_top_targets", 50), "importance")
        if len(tf_adj) > 0:
            regulons.append({
                "tf": tf,
                "targets": tf_adj["target"].tolist(),
                "n_targets": len(tf_adj),
                "motif_nes": None,
            })

    # Compute pseudo-AUC scores (using top targets)
    logger.info("Computing pseudo-activity scores...")
    for r in regulons:
        target_mask = adata.var_names.isin(r["targets"])
        if target_mask.sum() > 0:
            if hasattr(adata.X, "toarray"):
                expr = adata.X[:, target_mask].toarray()
            else:
                expr = adata.X[:, target_mask]
            # Mean expression of targets
            auc_matrix[r["tf"]] = expr.mean(axis=1)

    if len(regulons) == 0:
        logger.error("No regulons identified")
        return None

    return {
        "adjacencies": adjacencies,
        "regulons": regulons,
        "auc_matrix": auc_matrix,
        "used_fallback": used_fallback,
        "fallback_reason": fallback_reason,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Single-Cell Gene Regulatory Network Analysis")
    parser.add_argument("--input", dest="input_path", help="Input AnnData file (.h5ad)")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with demo data (GRNBoost2 only)")
    parser.add_argument("--tf-list", dest="tf_list", help="TF list file (one TF per line)")
    parser.add_argument("--db", dest="database_glob", help="cisTarget database glob pattern")
    parser.add_argument("--motif", dest="motif_annotations", help="Motif annotations file")
    parser.add_argument("--n-top-targets", type=int, default=50, help="Max targets per regulon")
    parser.add_argument("--n-jobs", type=int, default=4, help="Number of parallel jobs")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--cluster-key", dest="cluster_key", default="leiden", help="Cluster key for grouping (default: leiden)")
    parser.add_argument("--r-enhanced", action="store_true", help="Generate R Enhanced plots (requires R + ggplot2)")
    parser.add_argument(
        "--allow-simplified-grn",
        dest="allow_simplified_grn",
        action="store_true",
        help="Accept correlation-based GRN fallback when no TF/database/motif files are provided",
    )
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
            raise FileNotFoundError(
                f"Input file not found: {input_path}\n"
                "Provide a valid preprocessed .h5ad file, or use --demo for a quick test."
            )
        logger.info(f"Loading: {input_path}")
        adata = sc_io.smart_load(input_path, skill_name=SKILL_NAME)
        input_file = str(input_path)
        ensure_input_contract(adata, source_path=input_file)

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")
    apply_preflight(
        preflight_sc_grn(
            adata,
            tf_list=args.tf_list,
            database_glob=args.database_glob,
            motif_annotations=args.motif_annotations,
            demo_mode=args.demo or args.allow_simplified_grn,
            source_path=input_file,
        ),
        logger,
        demo_mode=args.demo or args.allow_simplified_grn,
    )

    # Parameters
    params = {
        "tf_list": args.tf_list,
        "database_glob": args.database_glob,
        "motif_annotations": args.motif_annotations,
        "n_top_targets": args.n_top_targets,
        "n_jobs": args.n_jobs,
        "seed": args.seed,
        "cluster_key": args.cluster_key,
    }

    # Check for full analysis requirements
    has_full_dbs = all([args.tf_list, args.database_glob, args.motif_annotations])
    used_fallback = False
    fallback_reason = None

    if has_full_dbs and not args.demo:
        # Full pySCENIC workflow
        logger.info("Running full pySCENIC workflow...")
        try:
            result = sc_grn_utils.run_complete_grn_workflow(
                adata,
                tf_list_file=args.tf_list,
                database_glob=args.database_glob,
                motif_annotations_file=args.motif_annotations,
                n_top_targets=args.n_top_targets,
                n_jobs=args.n_jobs,
                seed=args.seed,
            )
        except Exception as e:
            logger.error(f"Full workflow failed: {e}")
            logger.info("Falling back to GRNBoost2 only...")
            used_fallback = True
            fallback_reason = f"Full pySCENIC workflow failed: {e}"
            result = run_demo_mode(adata, output_dir, params)
    else:
        # Demo mode (GRNBoost2 only)
        result = run_demo_mode(adata, output_dir, params)

    if result is None:
        # Total failure -- three-layer guidance
        diag = {
            "degenerate": True,
            "reason": "total_failure",
            "n_regulons": 0,
            "n_adjacencies": 0,
            "suggested_actions": [
                "Check that input data is preprocessed (sc-preprocessing)",
                "Provide a TF list matching your gene names: --tf-list <file>",
                "Try demo mode first: python omicsclaw.py run sc-grn --demo --output /tmp/grn_demo",
            ],
        }

        # Layer 1: stdout
        print()
        print("  *** GRN analysis failed completely ***")
        print("  Demo mode uses correlation-based GRN inference (no external databases needed).")
        print()
        print("  How to fix:")
        print("    Option 1 -- Run with demo to verify the tool works:")
        print("      python omicsclaw.py run sc-grn --demo --output /tmp/grn_demo")
        print("    Option 2 -- Provide proper TF list and databases:")
        print_db_instructions()

        # Layer 2: report.md
        write_grn_report(output_dir, {"n_regulons": 0, "n_tfs": 0, "n_adjacencies": 0, "n_cells": adata.n_obs, "n_genes": adata.n_vars}, params, input_file, [], degenerate_diag=diag)

        # Layer 3: result.json
        checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
        result_data = {"params": params, "grn_diagnostics": diag}
        write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, {"n_regulons": 0, "status": "failed"}, result_data, checksum)

        sys.exit(1)

    # Extract result
    adjacencies = result["adjacencies"]
    regulons = result["regulons"]
    auc_matrix = result["auc_matrix"]
    if "used_fallback" in result:
        used_fallback = result["used_fallback"]
        fallback_reason = result.get("fallback_reason")

    # Degenerate output check
    degenerate_diag = _check_degenerate_output(regulons, adjacencies, auc_matrix, params)
    if degenerate_diag is not None:
        _print_degenerate_guidance(degenerate_diag)

    # Add AUC scores to adata
    for col in auc_matrix.columns:
        adata.obs[f"regulon_{col}"] = auc_matrix[col].values

    # Summary
    summary = {
        "n_cells": adata.n_obs,
        "n_genes": adata.n_vars,
        "n_tfs": len(set(adjacencies["TF"].unique())),
        "n_regulons": len(regulons),
        "n_adjacencies": len(adjacencies),
        "used_fallback": used_fallback,
    }
    if used_fallback:
        summary["fallback_reason"] = fallback_reason

    logger.info(f"Identified {len(regulons)} regulons")

    # Ensure UMAP is computed
    import scanpy as sc
    if "X_umap" not in adata.obsm:
        sc.tl.umap(adata)

    # Generate figures
    logger.info("Generating figures...")
    figures = generate_grn_figures(adata, regulons, auc_matrix, output_dir, cluster_key=args.cluster_key)

    # Write figure manifest
    _write_figure_manifest(output_dir, figures)

    # Export tables
    logger.info("Exporting results...")
    table_files = sc_grn_utils.export_grn_results(
        output_dir / "tables",
        adjacencies,
        regulons,
        auc_matrix,
        prefix="grn",
    )

    # Write figure_data
    cluster_labels_series = adata.obs[args.cluster_key] if args.cluster_key in adata.obs.columns else None
    figure_data_files = _write_figure_data(
        output_dir,
        adjacencies=adjacencies,
        regulons=regulons,
        auc_matrix=auc_matrix,
        cluster_labels=cluster_labels_series,
    )

    # Sort regulons by target count
    regulons_sorted = sorted(regulons, key=lambda x: x["n_targets"], reverse=True)

    # Write report
    logger.info("Writing report...")
    write_grn_report(
        output_dir, summary, params, input_file, regulons_sorted,
        degenerate_diag=degenerate_diag,
        used_fallback=used_fallback,
        fallback_reason=fallback_reason,
    )

    # Propagate contracts and save processed.h5ad
    propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind=infer_x_matrix_kind(adata),
        primary_cluster_key=args.cluster_key,
    )
    store_analysis_metadata(adata, SKILL_NAME, "pyscenic", params)

    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)
    logger.info(f"Saved: {output_h5ad}")

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    cmd = f"python sc_grn.py --output {output_dir} --n-top-targets {args.n_top_targets} --n-jobs {args.n_jobs}"
    if input_file:
        cmd += f" --input {input_file}"
    if args.tf_list:
        cmd += f" --tf-list {args.tf_list}"
    if args.database_glob:
        cmd += f" --db '{args.database_glob}'"
    if args.motif_annotations:
        cmd += f" --motif {args.motif_annotations}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    _write_repro_requirements(
        repro_dir,
        ["anndata", "numpy", "pandas", "matplotlib", "arboreto", "pyscenic"],
    )

    # Result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "params": params,
        "output_files": {
            "processed_h5ad": "processed.h5ad",
            "report": "report.md",
            "tables": table_files,
            "figure_data": figure_data_files,
            "figures": [Path(path).name for path in figures],
        },
    }
    if degenerate_diag is not None:
        result_data["grn_diagnostics"] = degenerate_diag
    if used_fallback:
        result_data["used_fallback"] = True
        result_data["fallback_reason"] = fallback_reason

    result_data["next_steps"] = []
    result_data["r_enhanced_figures"] = []
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }
    write_standard_run_artifacts(output_dir, result_payload, summary)

    # R Enhanced plots
    r_enhanced_figures = _render_r_enhanced(
        output_dir, output_dir / "figure_data", args.r_enhanced
    )
    if r_enhanced_figures:
        result_data["r_enhanced_figures"] = r_enhanced_figures
        write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    write_replot_hint(output_dir, SKILL_NAME, R_ENHANCED_PLOTS)

    # Summary
    print(f"\n{'='*60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'='*60}")
    print(f"  Regulons: {len(regulons)}")
    print(f"  TFs: {summary['n_tfs']}")
    if used_fallback:
        print(f"  Note: Used correlation fallback ({fallback_reason})")
    if degenerate_diag is not None:
        print(f"  WARNING: Output may be degenerate -- see report.md Troubleshooting section")
    print(f"  Output: {output_dir}")

    # --- Next-step guidance ---
    print()
    print("▶ Analysis complete.")


if __name__ == "__main__":
    main()
