#!/usr/bin/env python3
"""Single-cell drug response prediction (CaDRReS, simple_correlation)."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scanpy as sc
import seaborn as sns

try:
    import anndata
    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_output_readme,
    write_result_json,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    get_matrix_contract,
    infer_x_matrix_kind,
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-drug-response"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-drug-response/sc_drug_response.py"

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "omicsclaw" / "drug_response"
DEFAULT_N_DRUGS = 10

# Known drug target gene sets (simplified correlation approach)
# Each drug maps to a set of target / sensitivity-associated genes.
_BUILTIN_DRUG_TARGETS: dict[str, list[str]] = {
    "Cisplatin": ["ERCC1", "XPA", "BRCA1", "MLH1", "MSH2"],
    "Paclitaxel": ["TUBB", "TUBB3", "MAP4", "STMN1", "BCL2"],
    "Doxorubicin": ["TOP2A", "TOP2B", "ABCB1", "TP53", "BCL2"],
    "5-Fluorouracil": ["TYMS", "DPYD", "UMPS", "TK1", "RRM1"],
    "Gemcitabine": ["RRM1", "RRM2", "DCK", "CDA", "SLC29A1"],
    "Sorafenib": ["RAF1", "BRAF", "VEGFA", "KDR", "FLT4"],
    "Erlotinib": ["EGFR", "ERBB2", "ERBB3", "AKT1", "KRAS"],
    "Imatinib": ["ABL1", "BCR", "KIT", "PDGFRA", "PDGFRB"],
    "Temozolomide": ["MGMT", "MLH1", "MSH2", "MSH6", "ALKBH2"],
    "Olaparib": ["BRCA1", "BRCA2", "PARP1", "RAD51", "ATM"],
    "Vemurafenib": ["BRAF", "CRAF", "MAP2K1", "MAP2K2", "MAPK1"],
    "Lapatinib": ["EGFR", "ERBB2", "AKT1", "PIK3CA", "PTEN"],
    "Methotrexate": ["DHFR", "FPGS", "GGH", "SLC19A1", "TYMS"],
    "Venetoclax": ["BCL2", "BCL2L1", "MCL1", "BAX", "BAK1"],
    "Trametinib": ["MAP2K1", "MAP2K2", "MAPK1", "MAPK3", "BRAF"],
}

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "cadrres": MethodConfig(
        name="cadrres",
        description="CaDRReS-Sc pharmacogenomic model (requires pretrained model files)",
        dependencies=("scanpy", "numpy", "pandas"),
    ),
    "simple_correlation": MethodConfig(
        name="simple_correlation",
        description="Gene expression correlation with known drug target genes (no external model needed)",
        dependencies=("scanpy", "numpy", "pandas"),
    ),
}

# ── Preflight ──────────────────────────────────────────────────────────────

CADRRES_MODEL_FILES = {
    "gdsc": [
        "cadrres-wo-sample-bias_param_dict_all_genes.pickle",
        "masked_drugs.csv",
    ],
    "prism": [
        "cadrres-wo-sample-bias_param_dict_prism.pickle",
        "masked_drugs.csv",
    ],
}

CADRRES_DOWNLOAD_INSTRUCTIONS = """\
  CaDRReS-Sc model files are required for the 'cadrres' method.

  How to obtain them:
    1. Clone the CaDRReS-Sc repository:
       git clone https://github.com/CSB5/CaDRReS-Sc.git

    2. Download the pre-trained models:
       wget https://github.com/CSB5/CaDRReS-Sc/releases/download/v1.0/CaDRReS-Sc-model.tar.gz
       tar -xzf CaDRReS-Sc-model.tar.gz -C ~/.cache/omicsclaw/drug_response/

    3. Download GDSC bulk expression data:
       wget https://github.com/CSB5/CaDRReS-Sc/releases/download/v1.0/GDSC_exp.tsv.gz
       mv GDSC_exp.tsv.gz ~/.cache/omicsclaw/drug_response/

  Expected directory layout:
    ~/.cache/omicsclaw/drug_response/
      cadrres-wo-sample-bias_param_dict_all_genes.pickle  (GDSC)
      cadrres-wo-sample-bias_param_dict_prism.pickle      (PRISM)
      masked_drugs.csv
      GDSC_exp.tsv.gz

  Then run:
    python omicsclaw.py run sc-drug-response \\
      --input <preprocessed.h5ad> --output <dir> \\
      --method cadrres --model-dir ~/.cache/omicsclaw/drug_response/ \\
      --drug-db gdsc

  Alternative (no model needed):
    python omicsclaw.py run sc-drug-response \\
      --input <preprocessed.h5ad> --output <dir> \\
      --method simple_correlation
"""


def preflight_cadrres(model_dir: Path, drug_db: str) -> None:
    """Check that CaDRReS model files exist. Raises FileNotFoundError if missing."""
    required_files = CADRRES_MODEL_FILES.get(drug_db, CADRRES_MODEL_FILES["gdsc"])
    missing = [f for f in required_files if not (model_dir / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing CaDRReS model files in {model_dir}:\n"
            + "\n".join(f"  - {f}" for f in missing)
            + "\n\n"
            + CADRRES_DOWNLOAD_INSTRUCTIONS
        )


def preflight_data(adata: anndata.AnnData, cluster_key: str) -> None:
    """Validate input data has required metadata and gene nomenclature."""
    if cluster_key not in adata.obs.columns:
        candidates = [c for c in adata.obs.columns if adata.obs[c].dtype.name == "category" or adata.obs[c].nunique() < 50]
        raise ValueError(
            f"Cluster key '{cluster_key}' not found in adata.obs.\n"
            f"Available categorical columns: {candidates[:10]}\n"
            f"Use --cluster-key <column> to specify."
        )
    n_groups = adata.obs[cluster_key].nunique()
    if n_groups < 2:
        logger.warning(
            "Only %d group found in '%s'. Drug response comparison across clusters "
            "will be less informative.", n_groups, cluster_key
        )

    # Gene nomenclature check: drug targets use HGNC symbols
    all_targets = sorted({g for genes in _BUILTIN_DRUG_TARGETS.values() for g in genes})
    var_set = set(adata.var_names.astype(str))
    overlap = [g for g in all_targets if g in var_set]
    pct = len(overlap) / len(all_targets) * 100 if all_targets else 0
    if pct == 0:
        sample_genes = list(adata.var_names[:5])
        looks_ensembl = any(str(g).startswith("ENSG") or str(g).startswith("ENSMUSG") for g in sample_genes)
        msg = (
            f"0% overlap between drug target genes and your gene names.\n"
            f"  Drug targets expect HGNC symbols (e.g., BRCA1, EGFR, TP53).\n"
            f"  Your gene names look like: {sample_genes}\n"
        )
        if looks_ensembl:
            msg += (
                "  Your data uses Ensembl IDs. Convert first:\n"
                "    python omicsclaw.py run bulkrna-geneid-mapping --input data.h5ad --output mapped/ --from ensembl --to symbol\n"
            )
        else:
            msg += (
                "  Check whether your gene names are symbols, Ensembl IDs, or another format.\n"
                "  Use sc-standardize-input to canonicalize gene names.\n"
            )
        raise ValueError(msg)
    elif pct < 20:
        logger.warning(
            "Low overlap (%.0f%%) between drug target genes and your data (%d/%d). "
            "Results may be unreliable. Check gene nomenclature.",
            pct, len(overlap), len(all_targets),
        )


# ── Demo data ──────────────────────────────────────────────────────────────

def _generate_demo_data() -> anndata.AnnData:
    """Generate synthetic scRNA-seq data with cluster structure for demo."""
    np.random.seed(42)
    n_cells = 500
    n_genes = 200
    n_clusters = 4

    # Generate cluster assignments
    cluster_labels = np.random.choice([f"Cluster_{i}" for i in range(n_clusters)], size=n_cells)

    # Gene names: mix of real drug-target genes and random genes
    target_genes = sorted({g for genes in _BUILTIN_DRUG_TARGETS.values() for g in genes})
    n_target = min(len(target_genes), 60)
    selected_targets = target_genes[:n_target]
    filler_genes = [f"Gene_{i}" for i in range(n_genes - n_target)]
    gene_names = selected_targets + filler_genes

    # Generate count-like expression matrix with cluster structure
    counts = np.random.negative_binomial(n=2, p=0.3, size=(n_cells, len(gene_names))).astype(np.float32)

    # Add cluster-specific expression patterns for drug target genes
    for i, cluster in enumerate(sorted(set(cluster_labels))):
        mask = cluster_labels == cluster
        # Each cluster has elevated expression in different drug target sets
        drug_idx = i % len(list(_BUILTIN_DRUG_TARGETS.keys()))
        drug_name = list(_BUILTIN_DRUG_TARGETS.keys())[drug_idx]
        for gene in _BUILTIN_DRUG_TARGETS[drug_name]:
            if gene in gene_names:
                gene_idx = gene_names.index(gene)
                counts[mask, gene_idx] += np.random.poisson(8, size=mask.sum())

    adata = anndata.AnnData(
        X=counts,
        obs=pd.DataFrame({"cluster": pd.Categorical(cluster_labels)}, index=[f"Cell_{i}" for i in range(n_cells)]),
        var=pd.DataFrame(index=gene_names),
    )

    # Standard preprocessing
    adata.layers["counts"] = adata.X.copy()
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, n_top_genes=min(150, len(gene_names)), flavor="seurat_v3", layer="counts")
    sc.pp.pca(adata, n_comps=min(30, len(gene_names) - 1))
    sc.pp.neighbors(adata)
    sc.tl.umap(adata)

    adata.uns["omicsclaw_input_contract"] = {
        "producer_skill": "demo",
        "x_kind": "normalized_expression",
    }
    adata.uns["omicsclaw_matrix_contract"] = {
        "x_kind": "normalized_expression",
        "raw": "counts_in_layer",
        "producer_skill": "demo",
    }

    return adata


# ── simple_correlation method ─────────────────────────────────────────────

def _detect_species_hint(var_names) -> str:
    """Detect human vs mouse from gene naming convention."""
    sample = list(var_names[:500])
    if not sample:
        return "unknown"
    upper_ratio = sum(1 for g in sample if g == g.upper()) / len(sample)
    if upper_ratio > 0.7:
        return "human"
    title_ratio = sum(1 for g in sample if g != g.upper() and g[0].isupper()) / len(sample)
    if title_ratio > 0.5:
        return "mouse"
    return "unknown"


def _adapt_gene_case(gene_list: list[str], species: str) -> list[str]:
    """Adapt gene names to species convention."""
    if species == "mouse":
        return [g.capitalize() for g in gene_list]
    return gene_list  # human / unknown: keep UPPER


def run_simple_correlation(
    adata: anndata.AnnData,
    cluster_key: str,
    n_drugs: int,
    drug_targets: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    """Score drug sensitivity per cluster using target gene expression correlation.

    Returns a DataFrame with columns: Drug, Cluster, Score, Rank.
    """
    if drug_targets is None:
        drug_targets = dict(_BUILTIN_DRUG_TARGETS)

    species = _detect_species_hint(adata.var_names)
    logger.info("Detected species hint: %s", species)

    clusters = sorted(adata.obs[cluster_key].unique())
    records: list[dict[str, Any]] = []

    for drug_name, targets in drug_targets.items():
        adapted = _adapt_gene_case(targets, species)
        available = [g for g in adapted if g in adata.var_names]
        if not available:
            # Try case-insensitive rescue
            lower_map = {v.lower(): v for v in adata.var_names}
            available = [lower_map[g.lower()] for g in targets if g.lower() in lower_map]
        overlap_pct = len(available) / len(targets) * 100 if targets else 0
        if not available:
            logger.debug("Drug %s: 0/%d target genes found, skipping", drug_name, len(targets))
            continue
        if overlap_pct < 40:
            logger.warning(
                "Drug %s: only %.0f%% target genes found (%d/%d). Score may be unreliable.",
                drug_name, overlap_pct, len(available), len(targets),
            )

        for cluster in clusters:
            mask = adata.obs[cluster_key] == cluster
            if mask.sum() == 0:
                continue
            # Mean expression of target genes in this cluster
            expr = adata[mask, available].X
            if hasattr(expr, "toarray"):
                expr = expr.toarray()
            mean_expr = float(np.mean(expr))
            records.append({
                "Drug": drug_name,
                "Cluster": str(cluster),
                "Score": round(mean_expr, 4),
                "TargetGenes": len(available),
                "TotalTargets": len(targets),
                "OverlapPct": round(overlap_pct, 1),
            })

    if not records:
        return pd.DataFrame(columns=["Drug", "Cluster", "Score", "Rank", "TargetGenes", "TotalTargets", "OverlapPct"])

    df = pd.DataFrame(records)
    # Rank drugs within each cluster (higher score = higher sensitivity)
    df["Rank"] = df.groupby("Cluster")["Score"].rank(ascending=False, method="min").astype(int)
    df = df.sort_values(["Cluster", "Rank"])

    return df


def run_cadrres(
    adata: anndata.AnnData,
    cluster_key: str,
    model_dir: Path,
    drug_db: str,
    n_drugs: int,
) -> pd.DataFrame:
    """Run CaDRReS-Sc drug response prediction.

    Requires pretrained model files in model_dir.
    """
    # This is the real-mode path. We defer to omicverse's Drug_Response class
    # or the CaDRReS-Sc library directly.
    try:
        from omicverse.single._scdrug import Drug_Response
    except ImportError:
        raise ImportError(
            "CaDRReS method requires omicverse with CaDRReS-Sc support.\n"
            "Install: pip install omicverse\n"
            "And clone: git clone https://github.com/CSB5/CaDRReS-Sc.git\n\n"
            "Alternative (no external model needed):\n"
            "  --method simple_correlation"
        )

    # Prepare adata with louvain labels expected by Drug_Response
    adata_copy = adata.copy()
    if "louvain" not in adata_copy.obs.columns:
        adata_copy.obs["louvain"] = adata_copy.obs[cluster_key].astype(str)

    # Find CaDRReS-Sc script path
    cadrres_script = model_dir.parent / "CaDRReS-Sc"
    if not cadrres_script.exists():
        cadrres_script = Path.home() / "CaDRReS-Sc"
    if not cadrres_script.exists():
        raise FileNotFoundError(
            f"CaDRReS-Sc script directory not found.\n"
            f"Searched: {model_dir.parent / 'CaDRReS-Sc'}, {Path.home() / 'CaDRReS-Sc'}\n\n"
            + CADRRES_DOWNLOAD_INSTRUCTIONS
        )

    dr = Drug_Response(
        adata=adata_copy,
        scriptpath=str(cadrres_script),
        modelpath=str(model_dir) + "/",
        output=str(model_dir / "_tmp_output"),
        model=drug_db.upper(),
        clusters="All",
        n_drugs=n_drugs,
    )

    # Convert CaDRReS output to standard DataFrame format
    if drug_db.lower() == "gdsc":
        pred_file = model_dir / "_tmp_output" / "IC50_prediction.csv"
    else:
        pred_file = model_dir / "_tmp_output" / "PRISM_prediction.csv"

    if pred_file.exists():
        pred_df = pd.read_csv(pred_file, header=[0, 1], index_col=0)
        records = []
        for cluster in pred_df.index:
            for col in pred_df.columns:
                drug_name = col[1] if isinstance(col, tuple) else col
                records.append({
                    "Drug": str(drug_name),
                    "Cluster": str(cluster),
                    "Score": round(float(pred_df.loc[cluster, col]), 4),
                })
        df = pd.DataFrame(records)
        df["Rank"] = df.groupby("Cluster")["Score"].rank(ascending=False, method="min").astype(int)
        return df.sort_values(["Cluster", "Rank"])

    return pd.DataFrame(columns=["Drug", "Cluster", "Score", "Rank"])


# ── Visualization ─────────────────────────────────────────────────────────

def _save_fig(fig: plt.Figure, output_dir: Path, name: str, dpi: int = 200) -> Path:
    """Save figure to output_dir/figures/ and close it."""
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    path = fig_dir / name
    fig.savefig(path, bbox_inches="tight", dpi=dpi)
    plt.close(fig)
    logger.info("Saved figure: %s", path)
    return path


def plot_drug_sensitivity_umap(
    adata: anndata.AnnData,
    drug_scores: pd.DataFrame,
    cluster_key: str,
    output_dir: Path,
    top_n: int = 4,
) -> list[Path]:
    """Overlay top drug sensitivity scores on UMAP."""
    paths: list[Path] = []
    if "X_umap" not in adata.obsm:
        logger.warning("No UMAP embedding found, skipping UMAP overlay plots.")
        return paths

    # Get top drugs by mean score across clusters
    top_drugs = (
        drug_scores.groupby("Drug")["Score"]
        .mean()
        .sort_values(ascending=False)
        .head(top_n)
        .index.tolist()
    )

    for drug in top_drugs:
        drug_data = drug_scores[drug_scores["Drug"] == drug].set_index("Cluster")["Score"]
        adata.obs[f"drug_{drug}"] = adata.obs[cluster_key].astype(str).map(drug_data).fillna(0).astype(float)

    n_plots = len(top_drugs)
    if n_plots == 0:
        return paths

    fig, axes = plt.subplots(1, n_plots, figsize=(5 * n_plots, 4.5))
    if n_plots == 1:
        axes = [axes]

    for ax, drug in zip(axes, top_drugs):
        col = f"drug_{drug}"
        sc_vals = adata.obs[col].values
        umap = adata.obsm["X_umap"]
        scatter = ax.scatter(
            umap[:, 0], umap[:, 1],
            c=sc_vals, cmap="YlOrRd", s=3, alpha=0.8,
            vmin=np.percentile(sc_vals, 5),
            vmax=np.percentile(sc_vals, 95),
        )
        ax.set_title(drug, fontsize=12, fontweight="bold")
        ax.set_xlabel("UMAP1")
        ax.set_ylabel("UMAP2")
        ax.set_xticks([])
        ax.set_yticks([])
        plt.colorbar(scatter, ax=ax, shrink=0.6, label="Sensitivity Score")

    fig.suptitle("Drug Sensitivity on UMAP", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    paths.append(_save_fig(fig, output_dir, "drug_sensitivity_umap.png"))

    # Clean up temp obs columns
    for drug in top_drugs:
        col = f"drug_{drug}"
        if col in adata.obs.columns:
            del adata.obs[col]

    return paths


def plot_top_drugs_bar(
    drug_scores: pd.DataFrame,
    output_dir: Path,
    n_drugs: int = 10,
) -> Path | None:
    """Bar chart of top N drugs by mean sensitivity score."""
    if drug_scores.empty:
        return None

    top = (
        drug_scores.groupby("Drug")["Score"]
        .mean()
        .sort_values(ascending=False)
        .head(n_drugs)
    )

    fig, ax = plt.subplots(figsize=(8, max(4, n_drugs * 0.4)))
    colors = plt.cm.RdYlBu_r(np.linspace(0.2, 0.8, len(top)))
    bars = ax.barh(range(len(top)), top.values, color=colors, edgecolor="white", linewidth=0.5)
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(top.index, fontsize=10)
    ax.set_xlabel("Mean Sensitivity Score", fontsize=12)
    ax.set_title(f"Top {len(top)} Predicted Drug Responses", fontsize=13, fontweight="bold")
    ax.invert_yaxis()

    # Add value labels
    for bar, val in zip(bars, top.values):
        ax.text(bar.get_width() + 0.01 * top.max(), bar.get_y() + bar.get_height() / 2,
                f"{val:.3f}", va="center", fontsize=9)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _save_fig(fig, output_dir, "top_drugs_bar.png")


def plot_drug_cluster_heatmap(
    drug_scores: pd.DataFrame,
    output_dir: Path,
    n_drugs: int = 15,
) -> Path | None:
    """Heatmap of drug sensitivity scores across clusters."""
    if drug_scores.empty:
        return None

    # Select top drugs by variance across clusters
    pivot = drug_scores.pivot_table(index="Drug", columns="Cluster", values="Score", aggfunc="mean")
    if pivot.shape[0] > n_drugs:
        var_rank = pivot.var(axis=1).sort_values(ascending=False)
        pivot = pivot.loc[var_rank.head(n_drugs).index]

    fig, ax = plt.subplots(figsize=(max(6, pivot.shape[1] * 1.2), max(5, pivot.shape[0] * 0.45)))
    sns.heatmap(
        pivot,
        cmap="YlOrRd",
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"shrink": 0.6, "label": "Sensitivity Score"},
        ax=ax,
        annot=True,
        fmt=".2f",
        annot_kws={"fontsize": 8},
    )
    ax.set_title("Drug Sensitivity Across Clusters", fontsize=13, fontweight="bold")
    ax.set_xlabel("Cluster", fontsize=11)
    ax.set_ylabel("Drug", fontsize=11)
    ax.tick_params(axis="both", labelsize=9)
    fig.tight_layout()
    return _save_fig(fig, output_dir, "drug_cluster_heatmap.png")


# ── Report ─────────────────────────────────────────────────────────────────

def write_report(
    output_dir: Path,
    summary: dict,
    drug_scores: pd.DataFrame,
    method: str,
    params: dict,
    *,
    degenerate: bool = False,
) -> None:
    """Write analysis report in Markdown."""
    header = generate_report_header(
        title="Single-Cell Drug Response Prediction",
        skill_name=SKILL_NAME,
    )

    lines: list[str] = []
    lines.append(f"## Method: {method}\n")
    lines.append(f"- Cells analyzed: {summary.get('n_cells', 'N/A')}")
    lines.append(f"- Clusters: {summary.get('n_clusters', 'N/A')}")
    lines.append(f"- Drugs scored: {summary.get('n_drugs_scored', 0)}")
    lines.append(f"- Drug database: {params.get('drug_db', 'builtin')}")
    lines.append("")

    if not drug_scores.empty:
        lines.append("## Top Drugs (by mean score across clusters)\n")
        top = (
            drug_scores.groupby("Drug")["Score"]
            .mean()
            .sort_values(ascending=False)
            .head(10)
        )
        lines.append("| Rank | Drug | Mean Score |")
        lines.append("|------|------|-----------|")
        for rank, (drug, score) in enumerate(top.items(), 1):
            lines.append(f"| {rank} | {drug} | {score:.4f} |")
        lines.append("")

    lines.append("## Output Files\n")
    lines.append("- `processed.h5ad` — AnnData with drug sensitivity scores in `.obs`")
    lines.append("- `tables/drug_rankings.csv` — Full drug ranking table")
    lines.append("- `figures/top_drugs_bar.png` — Top drug bar chart")
    lines.append("- `figures/drug_cluster_heatmap.png` — Drug-cluster heatmap")
    lines.append("- `figures/drug_sensitivity_umap.png` — UMAP overlay")
    lines.append("")

    if degenerate:
        lines.extend([
            "",
            "## Troubleshooting: No Drugs Scored\n",
            "### Cause 1: No target genes found in expression data",
            "The built-in drug target genes may not match your gene names.",
            "  - Check if genes are Ensembl IDs instead of symbols",
            "  - For mouse data, gene names should be Title-case (e.g., Brca1)",
            "",
            "### Cause 2: Gene filtering removed target genes",
            "If aggressive HVG filtering was applied, target genes may have been excluded.",
            "  - Re-run preprocessing with more genes: `--n-top-genes 3000`",
            "",
            "### Alternative: Use CaDRReS for model-based prediction",
            "  ```bash",
            "  python omicsclaw.py run sc-drug-response \\",
            "    --input data.h5ad --output results/ \\",
            "    --method cadrres --model-dir ~/.cache/omicsclaw/drug_response/",
            "  ```",
        ])

    lines.append("")
    lines.append("## Disclaimer\n")
    lines.append(
        "*SpatialClaw is a research and educational tool for spatial transcriptomics analysis. "
        "It is not a medical device and does not provide clinical diagnoses. "
        "Consult a domain expert before making decisions based on these results.*"
    )

    report = header + "\n".join(lines) + "\n" + generate_report_footer()
    (output_dir / "report.md").write_text(report, encoding="utf-8")


def write_reproducibility(output_dir: Path, params: dict, input_file: str | None, *, demo_mode: bool = False) -> None:
    """Write reproducibility artifacts."""
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    elif input_file:
        command_parts.extend(["--input", input_file])
    else:
        command_parts.extend(["--input", "<input.h5ad>"])
    command_parts.extend(["--output", str(output_dir)])
    for key in ("method", "drug_db", "n_drugs", "cluster_key"):
        if key in params:
            flag = f"--{key.replace('_', '-')}"
            command_parts.extend([flag, str(params[key])])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")

    # Write requirements
    try:
        from importlib.metadata import PackageNotFoundError, version as get_version
    except ImportError:
        PackageNotFoundError = Exception
        from importlib_metadata import version as get_version

    lines: list[str] = []
    for pkg in ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "seaborn"]:
        try:
            lines.append(f"{pkg}=={get_version(pkg)}")
        except Exception:
            continue
    (repro_dir / "requirements.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_standard_run_artifacts(output_dir: Path, result_payload: dict, summary: dict) -> None:
    """Write notebook and README."""
    notebook_path = None
    try:
        from omicsclaw.common.notebook_export import write_analysis_notebook

        notebook_path = write_analysis_notebook(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Single-cell drug response prediction.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "simple_correlation"),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Single-cell drug response prediction.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "simple_correlation"),
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md: %s", exc)


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Single-Cell Drug Response Prediction")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true", help="Run with synthetic demo data")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default="simple_correlation")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_CACHE_DIR, help="Directory with CaDRReS model files")
    parser.add_argument("--drug-db", choices=["gdsc", "prism"], default="gdsc", help="Drug database (GDSC or PRISM)")
    parser.add_argument("--n-drugs", type=int, default=DEFAULT_N_DRUGS, help="Number of top drugs to report")
    parser.add_argument("--cluster-key", default=None, help="obs column for cluster labels")
    parser.add_argument("--r-enhanced", action="store_true",
        help="(Accepted for CLI consistency; no R Enhanced plots available for this skill.)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "figures").mkdir(exist_ok=True)
    (output_dir / "tables").mkdir(exist_ok=True)

    method = validate_method_choice(args.method, METHOD_REGISTRY)
    demo_mode = args.demo

    # ── Load data ──
    if demo_mode:
        logger.info("Running in DEMO mode with synthetic data.")
        adata = _generate_demo_data()
        input_file = None
        cluster_key = "cluster"
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc_io.smart_load(args.input_path, skill_name=SKILL_NAME)
        input_file = str(Path(args.input_path))

        # Resolve cluster key
        cluster_key = args.cluster_key
        if cluster_key is None:
            for candidate in ("leiden", "louvain", "cluster", "cell_type", "celltype"):
                if candidate in adata.obs.columns:
                    cluster_key = candidate
                    break
            if cluster_key is None:
                cat_cols = [c for c in adata.obs.columns if adata.obs[c].dtype.name == "category"]
                if cat_cols:
                    cluster_key = cat_cols[0]
                    logger.warning("No standard cluster key found, using '%s'. Override with --cluster-key.", cluster_key)
                else:
                    raise ValueError(
                        "No cluster labels found in adata.obs. "
                        "Run sc-preprocessing first, or specify --cluster-key."
                    )

    logger.info("Using cluster key: %s", cluster_key)
    preflight_data(adata, cluster_key)

    params = {
        "method": method,
        "drug_db": args.drug_db,
        "n_drugs": args.n_drugs,
        "cluster_key": cluster_key,
        "model_dir": str(args.model_dir),
    }

    # ── Run method ──
    if method == "cadrres":
        if not demo_mode:
            preflight_cadrres(args.model_dir, args.drug_db)
            drug_scores = run_cadrres(adata, cluster_key, args.model_dir, args.drug_db, args.n_drugs)
        else:
            # Demo mode for CaDRReS: generate synthetic scores
            logger.info("CaDRReS demo mode: generating synthetic drug sensitivity scores.")
            drug_scores = _generate_demo_cadrres_scores(adata, cluster_key, args.drug_db, args.n_drugs)
    elif method == "simple_correlation":
        drug_scores = run_simple_correlation(adata, cluster_key, args.n_drugs)
    else:
        raise ValueError(f"Unknown method: {method}")

    # ── Degenerate output detection ──
    degenerate = drug_scores.empty or drug_scores["Score"].isna().all()
    if degenerate:
        print()
        print("  *** NO DRUGS WERE SCORED — drug response prediction did not produce results. ***")
        print("  This usually means none of the drug target genes were found in your expression data.")
        print()
        print("  How to fix:")
        print("    Option 1 — Check gene names (Ensembl vs symbols):")
        print("      python omicsclaw.py run bulkrna-geneid-mapping --input data.h5ad --output mapped/")
        print("    Option 2 — Use CaDRReS model-based prediction:")
        print(f"      python omicsclaw.py run sc-drug-response --input <data.h5ad> --output <dir> \\")
        print(f"        --method cadrres --model-dir ~/.cache/omicsclaw/drug_response/")
        print("    Option 3 — Provide custom drug-target gene mapping (future feature)")
        print()

    # ── Store drug scores in adata.obs ──
    if not drug_scores.empty:
        # Add top drug scores per cell (mapped from cluster)
        top_drugs_list = (
            drug_scores.groupby("Drug")["Score"]
            .mean()
            .sort_values(ascending=False)
            .head(args.n_drugs)
            .index.tolist()
        )
        for drug in top_drugs_list:
            drug_data = drug_scores[drug_scores["Drug"] == drug].set_index("Cluster")["Score"]
            col_name = f"drug_score_{drug.replace(' ', '_').replace('-', '_')}"
            adata.obs[col_name] = (
                adata.obs[cluster_key].astype(str).map(drug_data).fillna(0).astype(float)
            )

    # ── Save table ──
    drug_scores.to_csv(output_dir / "tables" / "drug_rankings.csv", index=False)
    logger.info("Saved drug rankings: %s", output_dir / "tables" / "drug_rankings.csv")

    # ── Visualizations ──
    figure_paths: list[Path] = []
    try:
        umap_paths = plot_drug_sensitivity_umap(adata, drug_scores, cluster_key, output_dir, top_n=min(4, args.n_drugs))
        figure_paths.extend(umap_paths)
    except Exception as exc:
        logger.warning("Failed to create UMAP overlay: %s", exc)

    try:
        bar_path = plot_top_drugs_bar(drug_scores, output_dir, n_drugs=args.n_drugs)
        if bar_path:
            figure_paths.append(bar_path)
    except Exception as exc:
        logger.warning("Failed to create bar chart: %s", exc)

    try:
        heatmap_path = plot_drug_cluster_heatmap(drug_scores, output_dir, n_drugs=min(15, args.n_drugs))
        if heatmap_path:
            figure_paths.append(heatmap_path)
    except Exception as exc:
        logger.warning("Failed to create heatmap: %s", exc)

    # ── Persist results ──
    input_contract, matrix_contract = propagate_singlecell_contracts(
        adata, adata,
        producer_skill=SKILL_NAME,
        x_kind=infer_x_matrix_kind(adata),
        raw_kind=get_matrix_contract(adata).get("raw"),
        primary_cluster_key=cluster_key,
    )
    store_analysis_metadata(adata, SKILL_NAME, method, params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)

    # ── Summary ──
    n_drugs_scored = drug_scores["Drug"].nunique() if not drug_scores.empty else 0
    summary = {
        "method": method,
        "n_cells": adata.n_obs,
        "n_clusters": adata.obs[cluster_key].nunique(),
        "n_drugs_scored": n_drugs_scored,
        "n_drugs_reported": min(args.n_drugs, n_drugs_scored),
        "drug_db": args.drug_db,
        "degenerate": degenerate,
    }

    # ── Write report ──
    write_report(output_dir, summary, drug_scores, method, params, degenerate=degenerate)

    # ── Write result.json ──
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data: dict[str, Any] = {
        "params": params,
        "input_contract": input_contract,
        "matrix_contract": matrix_contract,
        "visualization": {
            "available_figures": [str(p.name) for p in figure_paths],
        },
    }
    if degenerate:
        result_data["drug_response_diagnostics"] = {
            "degenerate": True,
            "n_drugs_scored": 0,
            "suggested_actions": [
                "Check gene naming convention (Ensembl vs symbol)",
                "Try --method cadrres with pretrained model",
                "Re-run preprocessing with more genes (--n-top-genes 3000)",
            ],
        }
    result_data["next_steps"] = []
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {"skill": SKILL_NAME, "summary": summary, "data": result_data}
    write_standard_run_artifacts(output_dir, result_payload, summary)
    write_reproducibility(output_dir, params, input_file, demo_mode=demo_mode)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"  Method: {method}")
    print(f"  Drugs scored: {n_drugs_scored}")
    if not drug_scores.empty:
        top_drug = drug_scores.groupby("Drug")["Score"].mean().idxmax()
        print(f"  Top predicted drug: {top_drug}")

    # --- Next-step guidance ---
    print()
    print(">> Analysis complete.")


def _generate_demo_cadrres_scores(
    adata: anndata.AnnData,
    cluster_key: str,
    drug_db: str,
    n_drugs: int,
) -> pd.DataFrame:
    """Generate synthetic CaDRReS-style drug scores for demo mode."""
    np.random.seed(123)
    clusters = sorted(adata.obs[cluster_key].unique().astype(str))

    # Fake drug names from GDSC/PRISM
    if drug_db == "gdsc":
        drug_names = [
            "Cisplatin", "Paclitaxel", "Doxorubicin", "5-FU", "Gemcitabine",
            "Sorafenib", "Erlotinib", "Imatinib", "Temozolomide", "Olaparib",
            "Vemurafenib", "Lapatinib", "Methotrexate", "Venetoclax", "Trametinib",
        ]
    else:
        drug_names = [
            "BRD-K12345", "BRD-K23456", "BRD-K34567", "BRD-K45678", "BRD-K56789",
            "BRD-K67890", "BRD-K78901", "BRD-K89012", "BRD-K90123", "BRD-K01234",
            "BRD-K11111", "BRD-K22222", "BRD-K33333", "BRD-K44444", "BRD-K55555",
        ]

    records = []
    for drug in drug_names[:max(n_drugs, 10)]:
        for cluster in clusters:
            score = np.random.beta(2, 5)  # Skewed toward lower sensitivity
            records.append({
                "Drug": drug,
                "Cluster": cluster,
                "Score": round(score, 4),
            })
    df = pd.DataFrame(records)
    df["Rank"] = df.groupby("Cluster")["Score"].rank(ascending=False, method="min").astype(int)
    return df.sort_values(["Cluster", "Rank"])


if __name__ == "__main__":
    main()
