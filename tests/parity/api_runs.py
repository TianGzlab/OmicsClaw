"""Call a registered skill library on its CLI case's input and save the returned objects.

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


def api_sc_filter(case: str) -> dict:
    library = _load("sc-filter")
    adata = library.filter_cells(_demo("pbmc3k_raw"), tissue="pbmc" if case == "pbmc" else None)
    return {"adata": adata, "tables": {
        "filter_stats.csv": library.filter_stats_table(adata),
        "filter_summary.csv": library.filter_summary(adata),
        "retention_summary.csv": library.retention_table(adata),
    }}


def api_sc_markers(case: str) -> dict:
    library = _load("sc-markers")
    adata = _demo("pbmc3k_processed")
    table = library.find_markers(adata, groupby="louvain", method="t-test" if case == "ttest" else "wilcoxon")
    return {"adata": adata, "tables": {
        "markers_all.csv": table, "markers_top.csv": library.top_markers(table),
        "cluster_summary.csv": library.cluster_summary(table),
    }}


def api_sc_batch_integration(case: str, *, input_path: Path) -> dict:
    import anndata as ad

    library = _load("sc-batch-integration")
    adata = library.integrate(ad.read_h5ad(input_path), method=case)
    summary = library.run_info(adata)["summary"]
    return {"adata": adata, "tables": {
        "batch_sizes.csv": library.batch_sizes_table(adata),
        "batch_mixing_matrix.csv": library.batch_mixing_table(adata, label_key="louvain"),
        "integration_metrics.csv": library.integration_metrics(adata, label_key="louvain", embedding_key=summary["embedding_key"]),
    }}


def api_sc_enrichment(case: str) -> dict:
    library = _load("sc-enrichment")
    adata = _demo("pbmc3k_processed")
    ranking = library.rank_groups(adata, groupby="louvain")
    sets = library.demo_gene_sets()
    kwargs = dict(source="omicsclaw_demo", library_mode="builtin_demo")
    if case == "gsea":
        result = library.gsea(ranking, sets, **kwargs)
    else:
        result = library.ora(ranking, sets, background=adata.var_names, **kwargs)
    result.attrs.clear()
    return {"adata": adata, "tables": {
        "enrichment_results.csv": result,
        "group_summary.csv": library.group_summary(result),
        "ranking_input.csv": ranking,
        "top_terms.csv": library.top_terms(result),
    }}


def api_sc_standardize_input(case: str) -> dict:
    library = _load("sc-standardize-input")
    return {"adata": library.standardize(_demo("pbmc3k_raw"), species="human" if case == "human" else "auto")}


def api_sc_doublet_detection(case: str) -> dict:
    library = _load("sc-doublet-detection")
    adata = library.detect_doublets(_demo("pbmc3k_raw"),
                                   method="doubletdetection" if case == "doubletdetection" else "scrublet")
    return {"adata": adata, "tables": {"doublet_calls.csv": library.doublet_calls_table(adata),
                                       "summary.csv": library.doublet_summary(adata)}}


def api_sc_ambient_removal(case: str) -> dict:
    library = _load("sc-ambient-removal")
    return {"adata": library.remove_ambient(_demo("pbmc3k_raw"), contamination=0.1 if case == "tenth" else 0.05)}


def api_sc_pathway_scoring(case: str) -> dict:
    library = _load('sc-pathway-scoring')
    adata = _demo('pbmc3k_processed')
    genes = list(adata.var_names[:60])
    sets = {f'Demo_Set_{label}': genes[i * 15:(i + 1) * 15] for i, label in enumerate('ABCD')}
    scores = library.score_gene_sets(adata, sets, method=case, random_state=0 if case == 'score_genes_py' else 42)
    groups = library.score_summary(adata, scores, groupby='louvain', top_pathways=20)
    return {'adata': library.attach_scores(adata, scores), 'tables': {
        'enrichment_scores.csv': scores.rename_axis('Cell').reset_index(),
        'gene_set_overlap.csv': library.gene_set_overlap(adata, sets),
        'top_pathways.csv': groups['top_pathways_df'],
        'group_mean_scores.csv': groups['group_means_df'].reset_index(),
        'group_high_fraction.csv': groups['group_high_fraction_df'].reset_index(),
    }}


def api_sc_gene_programs(case: str) -> dict:
    import pandas as pd
    from skills.singlecell._lib.gene_programs import make_demo_gene_program_adata
    library = _load('sc-gene-programs')
    adata = library.find_programs(make_demo_gene_program_adata(), method='nmf', n_programs=4 if case == 'four' else 6)
    usage = pd.DataFrame(adata.obsm['X_gene_programs'], index=adata.obs_names,
                         columns=adata.uns['gene_programs']['program_names'])
    return {'adata': adata, 'tables': {
        'program_usage.csv': usage.reset_index().rename(columns={'index': 'Unnamed: 0'}),
        'program_weights.csv': library.program_weights(adata).reset_index().rename(columns={'index': 'Unnamed: 0'}),
        'top_program_genes.csv': library.top_program_genes(adata),
    }}


def api_sc_differential_abundance(case: str) -> dict:
    from skills.singlecell._lib.differential_abundance import make_demo_da_adata
    library = _load('sc-differential-abundance')
    adata = make_demo_da_adata()
    counts, props = library.composition(adata, sample_key='sample', condition_key='condition', celltype_key='cell_type')
    means = library.condition_proportions(adata, sample_key='sample', condition_key='condition', celltype_key='cell_type')
    table = library.test_abundance(adata, method=case)
    return {'adata': adata, 'tables': {
        'sample_by_celltype_counts.csv': counts.reset_index(),
        'sample_by_celltype_proportions.csv': props.reset_index(),
        'condition_mean_proportions.csv': means.reset_index(),
        ('simple_da_results.csv' if case == 'simple' else 'milo_nhood_results.csv'): table,
    }}


def api_sc_cell_communication(case: str) -> dict:
    import numpy as np
    import scipy.sparse as sp
    library = _load('sc-cell-communication')
    raw, processed = _demo('pbmc3k_raw'), _demo('pbmc3k_processed')
    labels = processed.obs.reindex(raw.obs_names)['louvain']
    adata = raw[labels.notna()].copy()
    adata.obs['cell_type'] = labels[labels.notna()].astype(str).values
    matrix = adata.X.tocsr(copy=True).astype(np.float64)
    counts = np.asarray(matrix.sum(axis=1)).reshape(-1)
    counts[counts == 0] = 1.0
    matrix = sp.diags(1e4 / counts) @ matrix
    matrix.data = np.log1p(matrix.data)
    adata.X = matrix
    table = library.communicate(adata, method=case)
    return {'adata': adata, 'tables': {
        'lr_interactions.csv': table, 'top_interactions.csv': library.top_interactions(table),
        'sender_receiver_summary.csv': library.sender_receiver_summary(table),
        'group_role_summary.csv': library.group_role_summary(table),
        'pathway_summary.csv': library.pathway_summary(table),
    }}


def api_sc_multi_count(case: str) -> dict:
    library = _load("sc-multi-count")
    adata = _demo("pbmc3k_raw")
    middle = adata.n_obs // 2
    parts = [adata[:middle].copy(), adata[middle:].copy()]
    for part, label, prefix in zip(parts, ("sample_A", "sample_B"), ("sampleA", "sampleB")):
        part.obs["sample_id"] = label
        part.obs_names = [f"{prefix}_{name}" for name in part.obs_names]
    merged = library.merge_samples(parts)
    return {"adata": merged, "tables": {"barcode_metrics.csv": library.barcode_metrics(merged),
                                           "per_sample_summary.csv": library.per_sample_summary(merged)}}


def api_scatac_preprocessing(case: str) -> dict:
    from skills._sdk.notebook._demos import atac_synthetic

    library = _load("scatac-preprocessing")
    adata = library.preprocess(atac_synthetic(), n_lsi=20 if case == "lsi20" else 30)
    return {"adata": adata, "tables": {"qc_metrics_per_cell.csv": library.qc_metrics_table(adata),
                                       "peak_summary.csv": library.peak_summary(adata),
                                       "lsi_variance_ratio.csv": library.lsi_variance_table(adata),
                                       "cluster_summary.csv": library.cluster_summary(adata)}}


def _legacy_demo(skill: str, function: str):
    """Read an unchanged CLI demo constructor without invoking its main function."""
    import importlib.util
    path = snapshot.REPO / snapshot.REGISTRY[skill].script
    spec = importlib.util.spec_from_file_location("parity_demo_" + skill.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, function)()


def api_sc_cytotrace(case: str) -> dict:
    library = _load("sc-cytotrace")
    adata = library.cytotrace(_demo("pbmc3k_processed"), n_neighbors=15 if case == "neighbors15" else 30)
    return {"adata": adata, "tables": {"cytotrace_scores.csv": library.potency_table(adata).reset_index()}}


def api_sc_metacell(case: str) -> dict:
    from skills.singlecell._lib.metacell import make_demo_metacell_adata
    library = _load("sc-metacell")
    adata = make_demo_metacell_adata(seed=0)
    result = library.metacells(adata, method="kmeans", n_metacells=20 if case == "twenty" else 30)
    return {"adata": adata, "tables": {"metacell_summary.csv": library.metacell_summary(result).reset_index(),
                                       "cell_to_metacell.csv": library.cell_to_metacell(adata)}}


def api_sc_pseudotime(case: str) -> dict:
    import numpy as np
    import pandas as pd
    from skills.singlecell._lib.adata_utils import record_matrix_contract
    library = _load("sc-pseudotime")
    adata = _demo("pbmc3k_processed")
    adata.obs["leiden"] = adata.obs["louvain"].astype(str)
    record_matrix_contract(adata, x_kind="normalized_expression", producer_skill="parity")
    root = str(adata.obs["leiden"].value_counts().idxmax())
    result = library.pseudotime(adata, method="palantir" if case == "palantir" else "dpt",
                                use_rep="X_pca", root_cluster=root)
    info = library.run_info(result)
    genes = library.trajectory_genes(result)
    summary = {"method": info["method"], "backend": info["backend"], "cluster_key": "leiden",
               "use_rep": "X_pca", "display_embedding": info["display_embedding"],
               "root_cluster": root, "root_cell": info["root_cell"], "root_cell_name": info["root_cell_name"],
               "n_cells": result.n_obs, "n_clusters": result.obs["leiden"].nunique(),
               "n_trajectory_genes": len(genes), "pseudotime_min": float(np.nanmin(result.obs["pseudotime"])),
               "pseudotime_max": float(np.nanmax(result.obs["pseudotime"]))}
    summary.update({key: value for key, value in info.items() if key not in summary
                    and key not in {"pseudotime_key", "fate_obsm_key"}})
    tables = {"pseudotime_cells.csv": library.pseudotime_table(result), "trajectory_genes.csv": genes,
              "trajectory_summary.csv": pd.DataFrame([{"metric": key, "value": value} for key, value in summary.items()])}
    fate = library.fate_probability_table(result)
    if not fate.empty:
        tables["fate_probabilities.csv"] = fate
    return {"adata": result, "tables": tables}


def api_sc_velocity(case: str) -> dict:
    library = _load("sc-velocity")
    adata = _legacy_demo("sc-velocity", "generate_demo_data")
    library.velocity(adata, mode="steady_state" if case == "steady_state" else "stochastic")
    return {"adata": adata, "tables": {"velocity_summary.csv": library.velocity_summary(adata),
                                       "velocity_cells.csv": library.velocity_cells_table(adata),
                                       "top_velocity_genes.csv": library.top_velocity_genes(adata)}}


def api_sc_grn(case: str) -> dict:
    import pandas as pd
    library = _load("sc-grn")
    adata = _legacy_demo("sc-grn", "generate_demo_data")
    tfs = ["TP53", "MYC", "STAT1", "NFkB1", "SP1", "E2F1", "GATA1", "FOXA1", "CEBPB", "IRF1"]
    adjacency = library.infer_adjacencies(adata, tfs=tfs, method="correlation")
    regulons = library.regulons_from_adjacencies(adjacency)
    scores = library.score_regulons(adata, regulons, method="mean")
    for column in scores:
        adata.obs[f"regulon_{column}"] = scores[column].to_numpy()
    return {"adata": adata, "tables": {"grn_adjacencies.csv": adjacency, "grn_regulons.csv": pd.DataFrame(regulons),
               "grn_regulon_targets.csv": pd.DataFrame([{"tf": r["tf"], "target": target} for r in regulons for target in r["targets"]]),
               "grn_auc_matrix.csv": scores.reset_index().rename(columns={"index": "Unnamed: 0"})}}


def api_sc_perturb_prep(case: str) -> dict:
    import pandas as pd
    from skills.singlecell._lib.perturbation import make_demo_perturb_adata, make_demo_perturb_mapping

    library = _load('sc-perturb-prep')
    adata = make_demo_perturb_adata(seed=0)
    mapping = library.standardize_mapping(make_demo_perturb_mapping(adata))
    assigned, dropped = library.collapse_assignments(mapping, drop_multi_guide=case != 'keep_multi')
    result = library.attach_assignments(adata, assigned)
    assignments = result.obs[['perturbation', 'sgRNA', 'target_gene', 'assignment_status', 'n_sgrnas']]
    tables = {
        'perturbation_assignments.csv': assignments.rename_axis('Unnamed: 0').reset_index(),
        'assignment_status_counts.csv': library.assignment_summary(result),
        'perturbation_counts.csv': library.perturbation_counts(result),
        'feature_type_summary.csv': pd.DataFrame({'feature_type': ['Gene Expression'], 'n_features': [adata.n_vars]}),
    }
    if not dropped.empty:
        tables['dropped_multi_guide_cells.csv'] = dropped
    return {'adata': result, 'tables': tables}


def api_sc_perturb(case: str) -> dict:
    from skills.singlecell._lib.perturbation import make_demo_perturb_adata

    library = _load('sc-perturb')
    result = library.mixscape(make_demo_perturb_adata(seed=0),
                              logfc_threshold=2. if case == 'high_threshold' else .25, random_state=0)
    cells = result.obs[['perturbation', 'mixscape_class_p_ko', 'mixscape_class', 'mixscape_class_global']]
    return {'adata': result, 'tables': {
        'mixscape_class_counts.csv': library.class_counts(result),
        'mixscape_global_class_counts.csv': library.global_class_counts(result),
        'mixscape_cell_classes.csv': cells.rename_axis('Unnamed: 0').reset_index(),
    }}


def api_sc_in_silico_perturbation(case: str) -> dict:
    library = _load('sc-in-silico-perturbation')
    adata = _legacy_demo('sc-in-silico-perturbation', '_make_demo_adata')
    result = library.knockout_correlation(adata, ko_gene='G10', n_top_genes=500 if case == 'top500' else 2000)
    return {'adata': adata, 'tables': {'diff_regulation.csv': result}}


def api_sc_drug_response(case: str, *, input_path=None) -> dict:
    from skills.singlecell._lib import io as sc_io

    library = _load('sc-drug-response')
    if input_path is None:
        adata = _legacy_demo('sc-drug-response', '_generate_demo_data')
        cluster_key = 'cluster'
    else:
        adata = sc_io.smart_load(input_path, skill_name='sc-drug-response')
        cluster_key = 'comparison_group'
    scores = library.score_drug_targets(adata, cluster_key=cluster_key)
    for drug in library.top_drugs(scores)['Drug']:
        values = scores[scores['Drug'] == drug].set_index('Cluster')['mean_target_expression']
        key = 'drug_score_' + drug.replace(' ', '_').replace('-', '_')
        adata.obs[key] = adata.obs[cluster_key].astype(str).map(values).fillna(0).astype(float)
    return {'adata': adata, 'tables': {'drug_rankings.csv': scores}}


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
    name = snapshot.REGISTRY[skill].api_runner
    if name is None:
        raise ValueError(f"{skill} has no registered API runner")
    runner = globals()[name]
    source = snapshot.case_input(skill, case, Path(folder).parent / "input")
    produced = runner(case, input_path=source) if source is not None else runner(case)
    save(produced, Path(folder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
