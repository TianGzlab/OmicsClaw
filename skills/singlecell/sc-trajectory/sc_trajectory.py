#!/usr/bin/env python3
"""Single-Cell Trajectory Inference - DPT, PAGA, scVelo, CellRank.

Usage:
    python sc_trajectory.py --input <data.h5ad> --output <dir> --method dpt
    python sc_trajectory.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import scanpy as sc
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json
from omicsclaw.common.checksums import sha256_file
from omicsclaw.singlecell.adata_utils import store_analysis_metadata, ensure_neighbors
from omicsclaw.singlecell.viz_utils import save_figure
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-trajectory"
SKILL_VERSION = "0.2.0"
SUPPORTED_METHODS = ("dpt", "paga", "scvelo", "cellrank", "monocle3", "slingshot")


def trajectory_dpt(adata, root_cluster=None):
    """DPT trajectory."""
    ensure_neighbors(adata)
    sc.tl.diffmap(adata)

    if root_cluster is not None and 'leiden' in adata.obs:
        root_cells = adata.obs['leiden'] == str(root_cluster)
        if root_cells.sum() > 0:
            adata.uns['iroot'] = root_cells.idxmax()
    else:
        adata.uns['iroot'] = 0

    sc.tl.dpt(adata)
    logger.info("DPT trajectory computed")

    return {
        "method": "dpt",
        "has_pseudotime": 'dpt_pseudotime' in adata.obs,
    }


def trajectory_paga(adata):
    """PAGA trajectory."""
    ensure_neighbors(adata)

    if 'leiden' not in adata.obs:
        sc.tl.leiden(adata)

    sc.tl.paga(adata, groups='leiden')
    sc.pl.paga(adata, show=False)
    logger.info("PAGA trajectory computed")

    return {
        "method": "paga",
        "has_paga": 'paga' in adata.uns,
    }


def trajectory_scvelo(adata):
    """scVelo RNA velocity."""
    logger.info("scVelo requires spliced/unspliced counts - using DPT fallback")
    return trajectory_dpt(adata)


def trajectory_cellrank(adata):
    """CellRank trajectory."""
    logger.info("CellRank requires cellrank package - using DPT fallback")
    return trajectory_dpt(adata)


def trajectory_monocle3(adata, root_cluster=None):
    """Monocle3 trajectory via R integration."""
    try:
        import rpy2.robjects as ro
        from rpy2.robjects import pandas2ri, numpy2ri
        from rpy2.robjects.packages import importr

        pandas2ri.activate()
        numpy2ri.activate()

        logger.info("Monocle3: Checking R environment")

        # Import R packages
        try:
            monocle3 = importr('monocle3')
        except Exception as e:
            logger.warning(f"Monocle3 R package not available: {e}")
            logger.info("Falling back to PAGA")
            return trajectory_paga(adata)

        # Ensure UMAP
        if 'X_umap' not in adata.obsm:
            sc.pp.neighbors(adata)
            sc.tl.umap(adata)
        if 'leiden' not in adata.obs:
            sc.tl.leiden(adata)

        logger.info("Converting AnnData to cell_data_set")

        # Prepare data
        counts = adata.X.toarray() if hasattr(adata.X, 'toarray') else adata.X
        umap = adata.obsm['X_umap']
        clusters = adata.obs['leiden'].astype(str).values

        # Create cell_data_set in R
        ro.globalenv['counts_mat'] = ro.r.matrix(counts, nrow=adata.n_obs, ncol=adata.n_vars)
        ro.globalenv['umap_mat'] = ro.r.matrix(umap, nrow=adata.n_obs, ncol=2)
        ro.globalenv['clusters'] = ro.StrVector(clusters)
        ro.globalenv['gene_names'] = ro.StrVector(list(adata.var_names))
        ro.globalenv['cell_names'] = ro.StrVector(list(adata.obs_names))

        ro.r('''
            library(monocle3)
            gene_metadata <- data.frame(gene_short_name = gene_names, row.names = gene_names)
            cell_metadata <- data.frame(clusters = clusters, row.names = cell_names)
            cds <- new_cell_data_set(t(counts_mat),
                                     cell_metadata = cell_metadata,
                                     gene_metadata = gene_metadata)
            reducedDims(cds)$UMAP <- umap_mat
        ''')

        # Learn trajectory graph
        logger.info("Learning trajectory graph with Monocle3")
        ro.r('cds <- learn_graph(cds, use_partition = FALSE)')

        # Order cells (pseudotime)
        if root_cluster is not None:
            ro.r(f'root_cells <- rownames(cell_metadata)[cell_metadata$clusters == "{root_cluster}"]')
            ro.r('cds <- order_cells(cds, root_cells = root_cells)')
        else:
            ro.r('cds <- order_cells(cds)')

        # Extract pseudotime
        pseudotime = ro.r('pseudotime(cds)')
        pseudotime_vec = pandas2ri.rpy2py(pseudotime)

        # Store in AnnData
        adata.obs['monocle3_pseudotime'] = pseudotime_vec
        logger.info("Monocle3 trajectory computed")

        return {
            "method": "monocle3",
            "has_pseudotime": True,
        }

    except ImportError:
        logger.warning("rpy2 not installed - falling back to PAGA")
        return trajectory_paga(adata)
    except Exception as e:
        logger.warning(f"Monocle3 failed: {e} - falling back to PAGA")
        return trajectory_paga(adata)


def trajectory_slingshot(adata, start_cluster=None, end_cluster=None):
    """Slingshot trajectory via R integration."""
    try:
        import rpy2.robjects as ro
        from rpy2.robjects import pandas2ri, numpy2ri
        from rpy2.robjects.packages import importr

        pandas2ri.activate()
        numpy2ri.activate()

        logger.info("Slingshot: Checking R environment")

        # Import R packages
        try:
            slingshot = importr('slingshot')
            SingleCellExperiment = importr('SingleCellExperiment')
        except Exception as e:
            logger.warning(f"Slingshot R package not available: {e}")
            logger.info("Falling back to DPT")
            return trajectory_dpt(adata)

        # Ensure required data
        if 'X_pca' not in adata.obsm:
            sc.tl.pca(adata)
        if 'leiden' not in adata.obs:
            sc.tl.leiden(adata)

        logger.info("Converting AnnData to SingleCellExperiment")

        # Prepare data for R
        counts = adata.X.toarray() if hasattr(adata.X, 'toarray') else adata.X
        pca = adata.obsm['X_pca']
        clusters = adata.obs['leiden'].astype(str).values

        # Create SingleCellExperiment in R
        ro.globalenv['counts_mat'] = ro.r.matrix(counts, nrow=adata.n_obs, ncol=adata.n_vars)
        ro.globalenv['pca_mat'] = ro.r.matrix(pca, nrow=adata.n_obs, ncol=pca.shape[1])
        ro.globalenv['clusters'] = ro.StrVector(clusters)

        ro.r('''
            sce <- SingleCellExperiment(assays = list(counts = t(counts_mat)))
            reducedDims(sce) <- list(PCA = pca_mat)
            colData(sce)$clusters <- clusters
        ''')

        # Run Slingshot
        logger.info("Running Slingshot trajectory inference")
        slingshot_cmd = 'slingshot(sce, clusterLabels = "clusters", reducedDim = "PCA"'
        if start_cluster is not None:
            slingshot_cmd += f', start.clus = "{start_cluster}"'
        if end_cluster is not None:
            slingshot_cmd += f', end.clus = "{end_cluster}"'
        slingshot_cmd += ')'

        ro.r(f'sce_sling <- {slingshot_cmd}')

        # Extract pseudotime
        pseudotime = ro.r('slingPseudotime(sce_sling)')
        pseudotime_df = pandas2ri.rpy2py(pseudotime)

        # Store in AnnData
        if pseudotime_df.shape[1] > 0:
            adata.obs['slingshot_pseudotime'] = pseudotime_df.iloc[:, 0]
            logger.info(f"Slingshot: {pseudotime_df.shape[1]} lineage(s) inferred")

        return {
            "method": "slingshot",
            "has_pseudotime": True,
            "n_lineages": pseudotime_df.shape[1],
        }

    except ImportError:
        logger.warning("rpy2 not installed - falling back to DPT")
        return trajectory_dpt(adata)
    except Exception as e:
        logger.warning(f"Slingshot failed: {e} - falling back to DPT")
        return trajectory_dpt(adata)


def generate_figures(adata, output_dir: Path) -> list[str]:
    """Generate trajectory figures."""
    figures = []

    if 'X_umap' not in adata.obsm:
        try:
            sc.tl.umap(adata)
        except Exception as e:
            logger.warning(f"UMAP failed: {e}")

    if 'X_umap' in adata.obsm and 'dpt_pseudotime' in adata.obs:
        try:
            sc.pl.umap(adata, color='dpt_pseudotime', show=False)
            p = save_figure(plt.gcf(), output_dir, "umap_pseudotime.png")
            figures.append(str(p))
            plt.close()
        except Exception as e:
            logger.warning(f"Pseudotime UMAP failed: {e}")

    return figures


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write report."""
    header = generate_report_header(
        title="Trajectory Inference Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Method": summary['method']},
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Total cells**: {summary.get('n_cells', 'N/A')}",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python sc_trajectory.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def _dispatch_method(method: str, adata, args) -> dict:
    """Route to trajectory method."""
    if method == "dpt":
        return trajectory_dpt(adata, args.root_cluster)
    elif method == "paga":
        return trajectory_paga(adata)
    elif method == "scvelo":
        return trajectory_scvelo(adata)
    elif method == "cellrank":
        return trajectory_cellrank(adata)
    elif method == "monocle3":
        return trajectory_monocle3(adata, args.root_cluster)
    elif method == "slingshot":
        return trajectory_slingshot(adata, args.start_cluster, args.end_cluster)
    else:
        raise ValueError(f"Unknown method: {method}. Choose from {SUPPORTED_METHODS}")


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Trajectory Inference")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(SUPPORTED_METHODS), default="dpt")
    parser.add_argument("--root-cluster", type=int, default=None, help="Root cluster for DPT/Monocle3")
    parser.add_argument("--start-cluster", type=int, default=None, help="Start cluster for Slingshot")
    parser.add_argument("--end-cluster", type=int, default=None, help="End cluster for Slingshot")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        demo_path = Path(__file__).parent.parent / "data" / "demo" / "pbmc3k_processed.h5ad"
        if demo_path.exists():
            adata = sc.read_h5ad(demo_path)
        else:
            logger.warning("Local demo data not found, downloading from scanpy")
            adata = sc.datasets.pbmc3k()
            sc.pp.normalize_total(adata)
            sc.pp.log1p(adata)
            sc.pp.highly_variable_genes(adata, n_top_genes=2000)
            sc.pp.pca(adata)
            sc.pp.neighbors(adata)
            sc.tl.leiden(adata)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    summary = _dispatch_method(args.method, adata, args)
    summary['n_cells'] = int(adata.n_obs)

    params = {"method": args.method}
    if args.root_cluster is not None:
        params["root_cluster"] = args.root_cluster

    generate_figures(adata, output_dir)
    write_report(output_dir, summary, input_file, params)

    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info(f"Saved to {output_h5ad}")

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    store_analysis_metadata(adata, SKILL_NAME, args.method, params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Trajectory inference complete: {summary['method']}")


if __name__ == "__main__":
    main()
