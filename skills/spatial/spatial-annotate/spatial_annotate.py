#!/usr/bin/env python3
"""Spatial Annotate — cell type annotation for spatial transcriptomics.

Supported methods:
  - marker_based: Marker gene scoring (no reference needed, fast, default)
  - tangram:      Deep learning mapping from scRNA-seq reference (tangram-sc)
  - scanvi:       Semi-supervised VAE transfer learning (scvi-tools)
  - cellassign:   Probabilistic marker-based assignment (scvi-tools)

Usage:
    python spatial_annotate.py --input <preprocessed.h5ad> --output <dir>
    python spatial_annotate.py --demo --output <dir>
    python spatial_annotate.py --input <file> --method tangram --reference <sc_ref.h5ad> --output <dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from omicsclaw.spatial.adata_utils import (
    get_spatial_key,
    require_preprocessed,
    store_analysis_metadata,
)
from omicsclaw.spatial.dependency_manager import require
from omicsclaw.spatial.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-annotate"
SKILL_VERSION = "0.1.0"

SUPPORTED_METHODS = ("marker_based", "tangram", "scanvi", "cellassign")


# ---------------------------------------------------------------------------
# Marker-based annotation (no reference required)
# ---------------------------------------------------------------------------


def annotate_marker_based(
    adata,
    *,
    cluster_key: str = "leiden",
    species: str = "human",
    n_top_markers: int = 5,
) -> dict:
    """Score-based cell type annotation using cluster marker genes.

    Runs DE to find cluster markers, then scores them against known
    cell type signatures. Works without external reference data.
    """
    if cluster_key not in adata.obs.columns:
        raise ValueError(f"Cluster key '{cluster_key}' not in adata.obs")

    adata.obs[cluster_key] = adata.obs[cluster_key].astype("category")

    logger.info("Finding marker genes per cluster (%s) ...", cluster_key)
    sc.tl.rank_genes_groups(adata, cluster_key, method="wilcoxon", n_genes=50)

    marker_signatures = _get_default_signatures(species)

    cluster_annotations = {}
    cluster_scores = {}
    clusters = sorted(adata.obs[cluster_key].cat.categories, key=str)

    for cluster in clusters:
        markers_df = sc.get.rank_genes_groups_df(adata, group=str(cluster))
        top_markers = markers_df.head(50)["names"].tolist()

        best_type = "Unknown"
        best_score = 0.0

        for cell_type, sig_genes in marker_signatures.items():
            overlap = set(top_markers[:30]) & set(sig_genes)
            score = len(overlap) / max(len(sig_genes), 1)
            if score > best_score:
                best_score = score
                best_type = cell_type

        if best_score < 0.05:
            best_type = "Unknown"

        cluster_annotations[str(cluster)] = best_type
        cluster_scores[str(cluster)] = round(best_score, 3)

    adata.obs["cell_type"] = (
        adata.obs[cluster_key].astype(str).map(cluster_annotations)
    )
    adata.obs["cell_type"] = pd.Categorical(adata.obs["cell_type"])

    counts = adata.obs["cell_type"].value_counts().to_dict()
    n_types = adata.obs["cell_type"].nunique()

    logger.info("Annotated %d clusters -> %d cell types", len(clusters), n_types)

    return {
        "method": "marker_based",
        "n_clusters": len(clusters),
        "n_cell_types": n_types,
        "cluster_annotations": cluster_annotations,
        "cluster_scores": cluster_scores,
        "cell_type_counts": counts,
        "species": species,
    }


def _get_default_signatures(species: str) -> dict[str, list[str]]:
    """Return basic cell type marker signatures."""
    if species == "mouse":
        return {
            "T cells": ["Cd3d", "Cd3e", "Cd4", "Cd8a", "Trac"],
            "B cells": ["Cd79a", "Cd79b", "Ms4a1", "Cd19", "Pax5"],
            "Macrophages": ["Cd68", "Csf1r", "Adgre1", "Lyz2", "C1qa"],
            "NK cells": ["Nkg7", "Klrb1c", "Gzma", "Ncr1", "Prf1"],
            "Fibroblasts": ["Col1a1", "Col1a2", "Dcn", "Fn1", "Vim"],
            "Epithelial": ["Epcam", "Krt8", "Krt18", "Krt19", "Cdh1"],
            "Endothelial": ["Pecam1", "Cdh5", "Vwf", "Kdr", "Flt1"],
            "Smooth muscle": ["Acta2", "Myh11", "Tagln", "Des", "Cnn1"],
            "Neurons": ["Snap25", "Syt1", "Rbfox3", "Map2", "Tubb3"],
            "Astrocytes": ["Gfap", "Aqp4", "S100b", "Aldh1l1", "Slc1a3"],
            "Oligodendrocytes": ["Mbp", "Plp1", "Mog", "Mag", "Cnp"],
        }
    return {
        "T cells": ["CD3D", "CD3E", "CD4", "CD8A", "TRAC"],
        "B cells": ["CD79A", "CD79B", "MS4A1", "CD19", "PAX5"],
        "Macrophages": ["CD68", "CSF1R", "CD163", "LYZ", "C1QA"],
        "NK cells": ["NKG7", "KLRB1", "GZMA", "GNLY", "PRF1"],
        "Fibroblasts": ["COL1A1", "COL1A2", "DCN", "FN1", "VIM"],
        "Epithelial": ["EPCAM", "KRT8", "KRT18", "KRT19", "CDH1"],
        "Endothelial": ["PECAM1", "CDH5", "VWF", "KDR", "FLT1"],
        "Smooth muscle": ["ACTA2", "MYH11", "TAGLN", "DES", "CNN1"],
        "Neurons": ["SNAP25", "SYT1", "RBFOX3", "MAP2", "TUBB3"],
        "Astrocytes": ["GFAP", "AQP4", "S100B", "ALDH1L1", "SLC1A3"],
        "Oligodendrocytes": ["MBP", "PLP1", "MOG", "MAG", "CNP"],
    }


# ---------------------------------------------------------------------------
# Tangram — deep learning mapping from reference
# ---------------------------------------------------------------------------


def annotate_tangram(
    adata,
    *,
    reference_path: str,
    cell_type_key: str = "cell_type",
    n_epochs: int = 500,
) -> dict:
    """Transfer cell type labels from scRNA-seq reference using Tangram."""
    require("tangram", feature="Tangram cell type annotation")
    import tangram as tg

    logger.info("Loading reference data: %s", reference_path)
    adata_ref = sc.read_h5ad(reference_path)

    if cell_type_key not in adata_ref.obs.columns:
        raise ValueError(
            f"Cell type key '{cell_type_key}' not in reference. "
            f"Available: {list(adata_ref.obs.columns)}"
        )

    if "highly_variable" in adata_ref.var.columns:
        training_genes = list(adata_ref.var_names[adata_ref.var["highly_variable"]])
    else:
        sc.pp.highly_variable_genes(adata_ref, n_top_genes=2000)
        training_genes = list(adata_ref.var_names[adata_ref.var["highly_variable"]])

    adata_sp = adata.raw.to_adata() if adata.raw is not None else adata.copy()
    spatial_key = get_spatial_key(adata)
    if spatial_key and spatial_key not in adata_sp.obsm:
        adata_sp.obsm[spatial_key] = adata.obsm[spatial_key].copy()

    tg.pp_adatas(adata_ref, adata_sp, genes=training_genes)

    logger.info("Running Tangram mapping (%d epochs) ...", n_epochs)
    ad_map = tg.map_cells_to_space(
        adata_ref, adata_sp, mode="cells", num_epochs=n_epochs, device="cpu",
    )

    tg.project_cell_annotations(ad_map, adata_sp, annotation=cell_type_key)

    if "tangram_ct_pred" in adata_sp.obsm:
        ct_pred = adata_sp.obsm["tangram_ct_pred"]
        ct_prob = ct_pred.div(ct_pred.sum(axis=1), axis=0)
        adata.obs["cell_type"] = pd.Categorical(ct_prob.idxmax(axis=1))
        adata.obsm["tangram_ct_pred"] = ct_pred
    else:
        raise RuntimeError("Tangram did not produce cell type predictions")

    counts = adata.obs["cell_type"].value_counts().to_dict()

    return {
        "method": "tangram",
        "n_cell_types": adata.obs["cell_type"].nunique(),
        "cell_type_counts": counts,
        "n_training_genes": len(training_genes),
        "n_epochs": n_epochs,
    }


# ---------------------------------------------------------------------------
# scANVI — semi-supervised transfer
# ---------------------------------------------------------------------------


def annotate_scanvi(
    adata,
    *,
    reference_path: str,
    cell_type_key: str = "cell_type",
    n_latent: int = 10,
    n_epochs: int = 100,
) -> dict:
    """Transfer cell type labels using scANVI semi-supervised VAE."""
    require("scvi", feature="scANVI cell type annotation")
    import scvi

    logger.info("Loading reference: %s", reference_path)
    adata_ref = sc.read_h5ad(reference_path)

    if cell_type_key not in adata_ref.obs.columns:
        raise ValueError(f"'{cell_type_key}' not found in reference adata.obs")

    common_genes = list(set(adata_ref.var_names) & set(adata.var_names))
    if len(common_genes) < 100:
        raise ValueError(
            f"Insufficient gene overlap: {len(common_genes)} common genes"
        )

    logger.info("Gene overlap: %d common genes", len(common_genes))
    adata_ref_sub = adata_ref[:, common_genes].copy()
    adata_sub = adata[:, common_genes].copy()

    if "counts" not in adata_ref_sub.layers:
        adata_ref_sub.layers["counts"] = adata_ref_sub.X.copy()
    if "counts" not in adata_sub.layers:
        adata_sub.layers["counts"] = adata_sub.X.copy()

    scvi.model.SCVI.setup_anndata(
        adata_ref_sub, labels_key=cell_type_key, layer="counts",
    )
    scvi_model = scvi.model.SCVI(adata_ref_sub, n_latent=n_latent)
    scvi_model.train(max_epochs=200, early_stopping=True)

    scanvi_model = scvi.model.SCANVI.from_scvi_model(scvi_model, "Unknown")
    scanvi_model.train(max_epochs=n_epochs, early_stopping=True)

    adata_sub.obs[cell_type_key] = "Unknown"
    scvi.model.SCANVI.setup_anndata(
        adata_sub, labels_key=cell_type_key, unlabeled_category="Unknown",
        layer="counts",
    )
    query_model = scvi.model.SCANVI.load_query_data(adata_sub, scanvi_model)
    query_model.train(max_epochs=100, early_stopping=True)

    predictions = query_model.predict()
    adata.obs["cell_type"] = pd.Categorical(predictions)

    counts = adata.obs["cell_type"].value_counts().to_dict()
    logger.info("scANVI: %d cell types predicted", len(counts))

    return {
        "method": "scanvi",
        "n_cell_types": len(counts),
        "cell_type_counts": counts,
        "n_common_genes": len(common_genes),
        "n_latent": n_latent,
    }


# ---------------------------------------------------------------------------
# CellAssign — probabilistic marker-based
# ---------------------------------------------------------------------------


def annotate_cellassign(
    adata,
    *,
    marker_genes: dict[str, list[str]],
    max_epochs: int = 400,
) -> dict:
    """Assign cell types using CellAssign probabilistic model."""
    require("scvi", feature="CellAssign cell type annotation")
    from scvi.external import CellAssign

    valid_markers = {}
    all_genes = set(adata.var_names)
    for ct, genes in marker_genes.items():
        found = [g for g in genes if g in all_genes]
        if found:
            valid_markers[ct] = found

    if not valid_markers:
        raise ValueError("No marker genes found in the dataset")

    cell_types = list(valid_markers.keys())
    marker_gene_list = list({g for genes in valid_markers.values() for g in genes})

    marker_matrix = pd.DataFrame(
        np.zeros((len(marker_gene_list), len(cell_types))),
        index=marker_gene_list,
        columns=cell_types,
    )
    for ct, genes in valid_markers.items():
        for g in genes:
            marker_matrix.loc[g, ct] = 1

    adata_sub = adata[:, marker_gene_list].copy()

    lib_size = np.asarray(adata_sub.X.sum(axis=1)).flatten()
    adata_sub.obs["size_factors"] = np.maximum(lib_size, 1e-6) / np.mean(np.maximum(lib_size, 1e-6))

    CellAssign.setup_anndata(adata_sub, size_factor_key="size_factors")
    model = CellAssign(adata_sub, marker_matrix)
    model.train(max_epochs=max_epochs)

    predictions = model.predict()
    if isinstance(predictions, pd.DataFrame):
        labels = [cell_types[i] for i in predictions.values.argmax(axis=1)]
    else:
        labels = [cell_types[i] for i in predictions]

    adata.obs["cell_type"] = pd.Categorical(labels)
    counts = adata.obs["cell_type"].value_counts().to_dict()

    return {
        "method": "cellassign",
        "n_cell_types": len(counts),
        "cell_type_counts": counts,
        "n_marker_genes": len(marker_gene_list),
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Generate cell type annotation visualizations."""
    import matplotlib.pyplot as plt

    figures = []
    spatial_key = get_spatial_key(adata)

    if "cell_type" not in adata.obs.columns:
        return figures

    # 1. Spatial cell type plot
    try:
        if spatial_key:
            if "spatial" in adata.uns and len(adata.uns["spatial"]) > 0:
                sc.pl.spatial(adata, color="cell_type", show=False)
            else:
                if "X_spatial" not in adata.obsm and spatial_key == "spatial":
                    adata.obsm["X_spatial"] = adata.obsm["spatial"]
                sc.pl.embedding(adata, basis="spatial", color="cell_type", show=False)
            fig = plt.gcf()
            p = save_figure(fig, output_dir, "cell_type_spatial.png")
            figures.append(str(p))
    except Exception as e:
        logger.warning("Could not generate spatial annotation plot: %s", e)

    # 2. UMAP cell type plot
    try:
        if "X_umap" not in adata.obsm:
            sc.tl.umap(adata)
        if "X_umap" in adata.obsm:
            sc.pl.umap(adata, color="cell_type", show=False)
            fig = plt.gcf()
            p = save_figure(fig, output_dir, "cell_type_umap.png")
            figures.append(str(p))
    except Exception as e:
        logger.warning("Could not generate UMAP annotation plot: %s", e)

    # 3. Barplot
    try:
        counts = adata.obs["cell_type"].value_counts()
        fig, ax = plt.subplots(figsize=(8, max(4, len(counts) * 0.35)))
        counts.plot.barh(ax=ax, color="steelblue")
        ax.set_xlabel("Number of cells")
        ax.set_title("Cell Type Distribution")
        fig.tight_layout()
        p = save_figure(fig, output_dir, "cell_type_barplot.png")
        figures.append(str(p))
    except Exception as e:
        logger.warning("Could not generate barplot: %s", e)

    return figures


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write report.md, result.json, tables, reproducibility."""
    header = generate_report_header(
        title="Cell Type Annotation Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Method": summary["method"]},
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Cell types identified**: {summary['n_cell_types']}",
    ]

    body_lines.extend(["", "### Cell type distribution\n"])
    body_lines.append("| Cell Type | Cells | Proportion |")
    body_lines.append("|-----------|-------|------------|")

    total = sum(summary["cell_type_counts"].values())
    for ct, count in sorted(summary["cell_type_counts"].items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total else 0
        body_lines.append(f"| {ct} | {count} | {pct:.1f}% |")

    if "cluster_annotations" in summary:
        body_lines.extend(["", "### Cluster to cell type mapping\n"])
        body_lines.append("| Cluster | Cell Type | Score |")
        body_lines.append("|---------|-----------|-------|")
        for cl, ct in summary["cluster_annotations"].items():
            score = summary.get("cluster_scores", {}).get(cl, "")
            body_lines.append(f"| {cl} | {ct} | {score} |")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    summary_json = {k: v for k, v in summary.items() if k != "cluster_annotations"}
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
                      summary=summary_json, data={"params": params, **summary_json},
                      input_checksum=checksum)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    pd.DataFrame([
        {"cell_type": ct, "n_cells": n, "proportion": round(n / total * 100, 2)}
        for ct, n in summary["cell_type_counts"].items()
    ]).to_csv(tables_dir / "cell_type_counts.csv", index=False)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def get_demo_data():
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    with tempfile.TemporaryDirectory(prefix="annotate_demo_") as tmpdir:
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", tmpdir],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"spatial-preprocess --demo failed: {result.stderr}")
        adata = sc.read_h5ad(Path(tmpdir) / "processed.h5ad")
    return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Annotate — multi-method cell type annotation",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method", choices=list(SUPPORTED_METHODS), default="marker_based",
        help=f"Annotation method (default: marker_based). Options: {', '.join(SUPPORTED_METHODS)}",
    )
    parser.add_argument("--reference", default=None, help="Reference scRNA-seq h5ad (for tangram/scanvi)")
    parser.add_argument("--cell-type-key", default="cell_type", help="Cell type column in reference")
    parser.add_argument("--cluster-key", default="leiden", help="Cluster key for marker_based")
    parser.add_argument("--species", default="human", choices=["human", "mouse"])
    parser.add_argument("--model", default=None, help="Pre-trained model path (future)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    params = {"method": args.method, "species": args.species}

    if args.method == "marker_based":
        summary = annotate_marker_based(
            adata, cluster_key=args.cluster_key, species=args.species,
        )
    elif args.method == "tangram":
        if not args.reference:
            print("ERROR: --reference required for tangram", file=sys.stderr)
            sys.exit(1)
        summary = annotate_tangram(
            adata, reference_path=args.reference, cell_type_key=args.cell_type_key,
        )
        params["reference"] = args.reference
    elif args.method == "scanvi":
        if not args.reference:
            print("ERROR: --reference required for scanvi", file=sys.stderr)
            sys.exit(1)
        summary = annotate_scanvi(
            adata, reference_path=args.reference, cell_type_key=args.cell_type_key,
        )
        params["reference"] = args.reference
    elif args.method == "cellassign":
        marker_file = args.model
        if marker_file and Path(marker_file).exists():
            with open(marker_file) as f:
                marker_genes = json.load(f)
        else:
            marker_genes = _get_default_signatures(args.species)
        summary = annotate_cellassign(adata, marker_genes=marker_genes)
    else:
        print(f"ERROR: Unknown method {args.method}", file=sys.stderr)
        sys.exit(1)

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved: %s", h5ad_path)

    print(f"Annotation complete: {summary['n_cell_types']} cell types ({summary['method']})")


if __name__ == "__main__":
    main()
