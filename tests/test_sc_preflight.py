from __future__ import annotations

import anndata as ad
import numpy as np
import pandas as pd

from skills.singlecell._lib.preflight import (
    preflight_sc_ambient_removal,
    preflight_sc_batch_integration,
    preflight_sc_cell_annotation,
    preflight_sc_cell_communication,
    preflight_sc_de,
    preflight_sc_doublet_detection,
    preflight_sc_enrichment,
    preflight_sc_filter,
    preflight_sc_grn,
    preflight_sc_markers,
    preflight_sc_pseudotime,
    preflight_sc_preprocessing,
    preflight_sc_qc,
    preflight_sc_velocity,
)
from skills.singlecell._lib.adata_utils import record_matrix_contract


def _adata(
    *,
    x: np.ndarray | None = None,
    obs: dict[str, list[str]] | None = None,
    var_names: list[str] | None = None,
) -> ad.AnnData:
    matrix = x if x is not None else np.array([[1, 0], [0, 1]], dtype=float)
    obs_df = pd.DataFrame(obs or {}, index=[f"cell{i}" for i in range(matrix.shape[0])])
    var_df = pd.DataFrame(index=var_names or [f"gene{i}" for i in range(matrix.shape[1])])
    return ad.AnnData(X=matrix, obs=obs_df, var=var_df)


def test_preflight_sc_de_deseq2_requires_explicit_design_inputs():
    adata = _adata(
        x=np.array([[10, 1], [8, 2], [5, 0]], dtype=float),
        obs={"condition": ["A", "A", "B"], "sample_id": ["s1", "s1", "s2"], "cell_type": ["T", "T", "T"]},
    )
    adata.layers["counts"] = adata.X.copy()

    decision = preflight_sc_de(
        adata,
        method="deseq2_r",
        groupby="leiden",
        group1=None,
        group2=None,
        sample_key=None,
        celltype_key="cell_type",
    )

    assert decision.status == "needs_user_input"
    assert any("--groupby" in line for line in decision.confirmations)
    assert any("--sample-key" in line for line in decision.confirmations)


def test_preflight_sc_de_deseq2_blocks_without_count_like_source():
    adata = _adata(
        x=np.array([[1.2, 0.5], [0.7, 0.3]], dtype=float),
        obs={"condition": ["A", "B"], "sample_id": ["s1", "s2"], "cell_type": ["T", "T"]},
    )

    decision = preflight_sc_de(
        adata,
        method="deseq2_r",
        groupby="condition",
        group1="A",
        group2="B",
        sample_key="sample_id",
        celltype_key="cell_type",
    )

    assert decision.status == "blocked"
    assert any("raw count-like expression" in line for line in decision.missing_requirements)


def test_preflight_sc_cell_annotation_celltypist_needs_confirmation_on_count_like_input():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))

    decision = preflight_sc_cell_annotation(
        adata,
        method="celltypist",
        model="Immune_All_Low",
        reference="HPCA",
        cluster_key="leiden",
    )

    assert decision.status == "needs_user_input"
    assert any("CellTypist model" in line or "`celltypist`" in line for line in decision.confirmations)


def test_preflight_sc_cell_annotation_blocks_qc_style_count_contract_for_scmap():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))
    adata.layers["counts"] = adata.X.copy()
    adata.raw = adata.copy()
    record_matrix_contract(
        adata,
        x_kind="raw_counts",
        raw_kind="raw_counts_snapshot",
        layers={"counts": "raw_counts"},
        producer_skill="sc-qc",
    )

    decision = preflight_sc_cell_annotation(
        adata,
        method="scmap",
        model="Immune_All_Low",
        reference="custom_ref",
        cluster_key="leiden",
    )

    assert decision.status == "blocked"
    assert any("expects log-normalized expression" in line for line in decision.missing_requirements)


def test_preflight_sc_cell_annotation_markers_now_requires_existing_cluster_key():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))

    decision = preflight_sc_cell_annotation(
        adata,
        method="markers",
        model="Immune_All_Low",
        reference="HPCA",
        cluster_key="leiden",
    )

    assert decision.status == "blocked"
    assert any("Run `sc-clustering` first" in line or "existing cluster/label column" in line for line in decision.missing_requirements)
    assert any("auto-cluster" in line for line in decision.guidance)


def test_preflight_sc_cell_annotation_manual_requires_mapping():
    adata = _adata(x=np.array([[0.1, 0.2], [0.4, 0.5]], dtype=float), obs={"louvain": ["0", "1"]})

    decision = preflight_sc_cell_annotation(
        adata,
        method="manual",
        model="Immune_All_Low",
        reference="HPCA",
        cluster_key="louvain",
        manual_map=None,
        manual_map_file=None,
    )

    assert decision.status == "needs_user_input"
    assert any("--manual-map" in line or "Manual annotation needs either" in line for line in decision.confirmations)


def test_preflight_sc_cell_communication_needs_label_confirmation():
    adata = _adata(
        x=np.array([[1, 0], [0, 1]], dtype=float),
        obs={"leiden": ["0", "1"]},
    )

    decision = preflight_sc_cell_communication(
        adata,
        method="builtin",
        cell_type_key="cell_type",
        species="human",
    )

    assert decision.status == "needs_user_input"
    assert any("--cell-type-key" in line for line in decision.confirmations)


def test_preflight_sc_cell_communication_blocks_mouse_cellphonedb():
    adata = _adata(
        x=np.array([[1, 0], [0, 1]], dtype=float),
        obs={"cell_type": ["T", "B"]},
    )

    decision = preflight_sc_cell_communication(
        adata,
        method="cellphonedb",
        cell_type_key="cell_type",
        species="mouse",
        counts_data="hgnc_symbol",
    )

    assert decision.status == "blocked"
    assert any("only supports `--species human`" in line for line in decision.missing_requirements)


def test_preflight_sc_batch_integration_requires_batch_confirmation():
    adata = _adata(
        x=np.array([[10, 1], [8, 2]], dtype=float),
        obs={"sample_id": ["s1", "s2"]},
    )
    adata.layers["counts"] = adata.X.copy()

    decision = preflight_sc_batch_integration(
        adata,
        method="harmony",
        batch_key="batch",
    )

    assert decision.status == "needs_user_input"
    assert any("--batch-key" in line for line in decision.confirmations)


def test_preflight_sc_batch_integration_scanvi_needs_labels():
    adata = _adata(
        x=np.array([[10, 1], [8, 2], [5, 0], [9, 1], [7, 2], [6, 1]], dtype=float),
        obs={"batch": ["b1", "b1", "b1", "b2", "b2", "b2"]},
    )
    adata.layers["counts"] = adata.X.copy()

    decision = preflight_sc_batch_integration(
        adata,
        method="scanvi",
        batch_key="batch",
    )

    assert decision.status == "needs_user_input"
    assert any("scanvi" in line for line in decision.confirmations)


def test_preflight_sc_doublet_detection_blocks_non_count_like_input():
    adata = _adata(x=np.array([[1.2, 0.5], [0.7, 0.3]], dtype=float))

    decision = preflight_sc_doublet_detection(
        adata,
        method="scrublet",
        expected_doublet_rate=0.06,
    )

    assert decision.status == "blocked"
    assert any("raw count-like input" in line for line in decision.missing_requirements)


def test_preflight_sc_doublet_detection_requires_confirmation_for_threshold_on_r_method():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))
    adata.layers["counts"] = adata.X.copy()

    decision = preflight_sc_doublet_detection(
        adata,
        method="doubletfinder",
        expected_doublet_rate=0.06,
        threshold=0.2,
    )

    assert decision.status == "needs_user_input"
    assert any("`--threshold` only affects the Scrublet path" in line for line in decision.confirmations)


def test_preflight_sc_ambient_removal_requires_confirmation_for_soupx_fallback():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))
    adata.layers["counts"] = adata.X.copy()

    decision = preflight_sc_ambient_removal(
        adata,
        method="soupx",
        raw_h5=None,
        raw_matrix_dir=None,
        filtered_matrix_dir=None,
        contamination=0.05,
    )

    assert decision.status == "needs_user_input"
    assert any("fall back to `simple`" in line or "fall back to `simple`" in line.replace("fallback", "fall back") for line in decision.confirmations)


def test_preflight_sc_ambient_removal_blocks_cellbender_without_raw_h5():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))
    adata.layers["counts"] = adata.X.copy()

    decision = preflight_sc_ambient_removal(
        adata,
        method="cellbender",
        raw_h5=None,
        raw_matrix_dir=None,
        filtered_matrix_dir=None,
        contamination=0.05,
    )

    assert decision.status == "blocked"
    assert any("`cellbender` requires `--raw-h5`" in line for line in decision.missing_requirements)


def test_preflight_sc_velocity_blocks_missing_splicing_layers():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))

    decision = preflight_sc_velocity(
        adata,
        method="scvelo_stochastic",
    )

    assert decision.status == "blocked"
    assert any("`spliced` and `unspliced`" in line for line in decision.missing_requirements)


def test_preflight_sc_velocity_dynamical_adds_guidance_without_umap():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))
    adata.layers["spliced"] = adata.X.copy()
    adata.layers["unspliced"] = adata.X.copy()

    decision = preflight_sc_velocity(
        adata,
        method="scvelo_dynamical",
    )

    assert decision.status == "proceed_with_guidance"
    assert any("preprocessed with PCA/UMAP" in line for line in decision.guidance)


def test_preflight_sc_preprocessing_blocks_non_count_like_input():
    adata = _adata(x=np.array([[1.2, 0.5], [0.7, 0.3]], dtype=float))

    decision = preflight_sc_preprocessing(
        adata,
        method="scanpy",
    )

    assert decision.status == "blocked"
    assert any("raw count-like input" in line for line in decision.missing_requirements)


def test_preflight_sc_qc_blocks_non_count_like_input():
    adata = _adata(x=np.array([[1.2, 0.5], [0.7, 0.3]], dtype=float))

    decision = preflight_sc_qc(
        adata,
        species="human",
    )

    assert decision.status == "blocked"
    assert any("expects a raw count-like matrix" in line for line in decision.missing_requirements)


def test_preflight_sc_filter_guides_when_qc_metrics_missing():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))

    decision = preflight_sc_filter(
        adata,
        tissue=None,
    )

    assert decision.status == "proceed_with_guidance"
    assert any("will compute QC metrics automatically" in line for line in decision.guidance)


def test_preflight_sc_filter_blocks_count_threshold_without_total_counts():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))
    adata.obs["n_genes_by_counts"] = [2, 2]

    decision = preflight_sc_filter(
        adata,
        tissue=None,
        min_counts=100,
    )

    assert decision.status == "blocked"
    assert any("`total_counts` is missing" in line for line in decision.missing_requirements)


def test_preflight_sc_markers_requires_groupby_confirmation():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float), obs={"cell_type": ["T", "B"]})

    decision = preflight_sc_markers(
        adata,
        groupby="leiden",
        method="wilcoxon",
        n_genes=None,
        n_top=10,
        min_in_group_fraction=0.25,
        min_fold_change=0.25,
        max_out_group_fraction=0.5,
    )

    assert decision.status == "needs_user_input"
    assert any("--groupby" in line for line in decision.confirmations)


def test_preflight_sc_markers_requires_confirmation_on_qc_style_count_contract():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float), obs={"leiden": ["0", "1"]})
    adata.layers["counts"] = adata.X.copy()
    adata.raw = adata.copy()
    record_matrix_contract(
        adata,
        x_kind="raw_counts",
        raw_kind="raw_counts_snapshot",
        layers={"counts": "raw_counts"},
        producer_skill="sc-qc",
    )

    decision = preflight_sc_markers(
        adata,
        groupby="leiden",
        method="wilcoxon",
        n_genes=None,
        n_top=10,
        min_in_group_fraction=0.25,
        min_fold_change=0.25,
        max_out_group_fraction=0.5,
    )

    assert decision.status == "needs_user_input"
    assert any("expects normalized expression" in line for line in decision.confirmations)


def test_preflight_sc_markers_can_auto_use_single_primary_cluster_key():
    adata = _adata(
        x=np.array([[0.1, 0.2], [0.4, 0.5]], dtype=float),
        obs={"louvain": ["0", "1"]},
    )
    record_matrix_contract(
        adata,
        x_kind="normalized_expression",
        raw_kind="raw_counts_snapshot",
        layers={"counts": "raw_counts"},
        producer_skill="sc-clustering",
        primary_cluster_key="louvain",
    )

    decision = preflight_sc_markers(
        adata,
        groupby=None,
        method="wilcoxon",
        n_genes=None,
        n_top=10,
        min_in_group_fraction=0.25,
        min_fold_change=0.25,
        max_out_group_fraction=0.5,
    )

    assert decision.status == "proceed_with_guidance"
    assert any("will use `louvain`" in line for line in decision.guidance)


def test_preflight_sc_grn_requires_full_db_bundle_confirmation():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))

    decision = preflight_sc_grn(
        adata,
        tf_list="tf.txt",
        database_glob=None,
        motif_annotations=None,
    )

    assert decision.status == "needs_user_input"
    assert any("`--tf-list`, `--db`, and `--motif` together" in line for line in decision.confirmations)


def test_preflight_sc_grn_requires_confirmation_for_simplified_mode_without_databases():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))

    decision = preflight_sc_grn(
        adata,
        tf_list=None,
        database_glob=None,
        motif_annotations=None,
        demo_mode=False,
    )

    assert decision.status == "needs_user_input"
    assert any("simplified GRNBoost2-style fallback" in line for line in decision.confirmations)


def test_preflight_sc_pseudotime_requires_root_confirmation():
    adata = _adata(
        x=np.array([[10, 1], [8, 2], [5, 0]], dtype=float),
        obs={"leiden": ["0", "0", "1"]},
    )

    decision = preflight_sc_pseudotime(
        adata,
        method="dpt",
        cluster_key="leiden",
        root_cluster=None,
        root_cell=None,
    )

    assert decision.status == "needs_user_input"
    assert any("starting state" in line for line in decision.confirmations)


def test_preflight_sc_pseudotime_requires_cluster_key_confirmation():
    adata = _adata(
        x=np.array([[10, 1], [8, 2], [5, 0]], dtype=float),
        obs={"cell_type": ["A", "A", "B"]},
    )

    decision = preflight_sc_pseudotime(
        adata,
        method="dpt",
        cluster_key="leiden",
        root_cluster="A",
        root_cell=None,
    )

    assert decision.status == "needs_user_input"
    assert any("--cluster-key" in line for line in decision.confirmations)


def test_preflight_sc_enrichment_blocks_without_gene_sets():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float))

    decision = preflight_sc_enrichment(
        adata,
        gene_sets_path=None,
        groupby="leiden",
    )

    assert decision.status == "blocked"
    assert any("requires `--gene-sets`" in line for line in decision.missing_requirements)


def test_preflight_sc_enrichment_guides_when_groupby_missing():
    adata = _adata(x=np.array([[10, 1], [8, 2]], dtype=float), obs={"cell_type": ["T", "B"]})

    decision = preflight_sc_enrichment(
        adata,
        gene_sets_path="sets.gmt",
        groupby="leiden",
    )

    assert decision.status == "needs_user_input"
    assert any("grouped AUCell summaries would be skipped" in line for line in decision.confirmations)
