"""Call a pilot skill's function library on the demo input its CLI case uses, and save what it returns.

Run as ``python -m tests.parity.api_runs <skill> <case> <folder>``; the parity
test runs it in a subprocess so the library runs with the same environment as
the recorded CLI (``tests/conftest.py`` turns numba's JIT off in the test
process). The folder gets ``tables/<name>.csv`` for each table the library
returns, and ``obs_labels/`` plus ``obs_numeric.csv`` for the AnnData, laid
out like a snapshot.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tests.parity import snapshot


def _load(name: str):
    from skills._sdk.notebook import load_skill

    return load_skill(name)


def _demo(name: str):
    from skills.singlecell._lib.io import load_repo_demo_data

    return load_repo_demo_data(name)[0]


def api_sc_qc(case: str) -> dict:
    qc = _load("sc-qc")
    adata = qc.calculate_qc(_demo("pbmc3k_raw"), species="mouse" if case == "mouse" else "human")
    metrics = [c for c in qc.qc_metrics_table(adata).columns if c != "cell_id"]
    return {
        "adata": adata,
        "tables": {
            "qc_metrics_summary.csv": qc.qc_summary(adata),
            "qc_metrics_per_cell.csv": qc.qc_metrics_table(adata),
            "highest_expr_genes.csv": qc.highest_expressed_genes(adata, n_top=20),
            "barcode_rank_curve.csv": qc.barcode_rank_table(adata),
            "qc_metric_correlations.csv": qc.qc_correlation_table(adata, metrics=metrics),
        },
    }


def api_sc_preprocessing(case: str) -> dict:
    from skills.singlecell._lib.adata_utils import canonicalize_singlecell_adata, infer_qc_species

    pre = _load("sc-preprocessing")
    adata = _demo("pbmc3k_raw")
    adata, _, _ = canonicalize_singlecell_adata(
        adata, species=infer_qc_species(adata), preferred_layer="counts", standardizer_skill="sc-preprocessing"
    )
    adata = pre.preprocess(adata, method="pearson_residuals" if case == "pearson" else "scanpy")
    return {
        "adata": adata,
        "tables": {
            "hvg_summary.csv": pre.hvg_table(adata, n_top=50),
            "pca_variance_ratio.csv": pre.pca_variance_table(adata),
            "pca_embedding.csv": pre.pca_embedding_table(adata, n_components=5),
            "qc_metrics_per_cell.csv": pre.qc_metrics_table(adata),
        },
    }


def api_sc_clustering(case: str) -> dict:
    clustering = _load("sc-clustering")
    method = "louvain" if case == "louvain" else "leiden"
    adata = clustering.cluster(_demo("pbmc3k_processed"), method=method, resolution=1.0)
    return {"adata": adata, "tables": {"cluster_summary.csv": clustering.cluster_summary(adata, key=method)}}


def _annotation_demo():
    """The PBMC3k object the annotation CLI builds in --demo mode."""
    import scanpy as sc

    adata = _demo("pbmc3k_raw")
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.filter_genes(adata, min_cells=3)
    adata.layers["counts"] = adata.X.copy()
    adata.raw = adata.copy()
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.pca(adata)
    sc.pp.neighbors(adata)
    sc.tl.umap(adata)
    sc.tl.louvain(adata, resolution=0.8, key_added="louvain")
    return adata


def api_sc_cell_annotation(case: str) -> dict:
    import tempfile

    annotation = _load("sc-cell-annotation")
    adata = _annotation_demo()
    if case == "knnpredict":
        names = ["CD4+ T", "CD14+ Mono", "B cell", "CD8+ T", "NK", "FCGR3A+ Mono", "DC", "Platelet"]
        reference = adata.copy()
        label_map = {str(i): name for i, name in enumerate(names)}
        reference.obs["cell_type"] = reference.obs["louvain"].astype(str).map(lambda x: label_map.get(x, f"Unknown_{x}"))
        path = Path(tempfile.mkdtemp()) / "demo_ref.h5ad"
        reference.write_h5ad(path)
        adata = annotation.annotate(adata, method="knnpredict", reference=str(path))
    else:
        adata = annotation.annotate(adata, method="markers")
    key = annotation.run_info(adata)["cluster_key"]
    return {
        "adata": adata,
        "tables": {
            "cell_type_counts.csv": annotation.annotation_table(adata, key="cell_type"),
            "cluster_annotation_matrix.csv": annotation.cluster_annotation_matrix(adata, cluster_key=key),
        },
    }


def api_sc_de(case: str) -> dict:
    de = _load("sc-de")
    adata = _demo("pbmc3k_processed")
    table = de.rank_genes(adata, groupby="leiden", method="t-test" if case == "ttest" else "wilcoxon")
    return {"tables": {"de_full.csv": table, "markers_top.csv": de.top_genes(table, n_top=10)}}


API_RUNNERS = {
    "sc-qc": api_sc_qc,
    "sc-preprocessing": api_sc_preprocessing,
    "sc-clustering": api_sc_clustering,
    "sc-cell-annotation": api_sc_cell_annotation,
    "sc-de": api_sc_de,
}


def save(produced: dict, folder: Path) -> None:
    """Write what a runner returned in the snapshot layout."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, frame in produced.get("tables", {}).items():
        path = folder / "tables" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
    adata = produced.get("adata")
    if adata is not None:
        labels, numeric = snapshot.obs_frames(adata)
        for column, series in labels.items():
            path = folder / "obs_labels" / f"{column}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            series.rename("label").rename_axis("obs_name").to_csv(path)
        numeric.to_csv(folder / "obs_numeric.csv")


def main(argv: list[str] | None = None) -> int:
    skill, case, folder = (argv if argv is not None else sys.argv[1:])
    save(API_RUNNERS[skill](case), Path(folder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
