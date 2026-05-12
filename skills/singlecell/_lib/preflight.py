"""Shared user-facing preflight validation for scRNA skills."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING

from omicsclaw.common.user_guidance import emit_user_guidance, emit_user_guidance_payload
from omicsclaw.core.r_dependency_manager import check_r_tier, suggest_r_install

from .adata_utils import (
    build_standardization_recommendation,
    get_matrix_contract,
    get_input_contract,
    infer_x_matrix_kind,
    matrix_kind_is_count_like,
    matrix_kind_is_normalized,
    matrix_looks_count_like,
    raw_matrix_kind,
    x_matrix_kind,
)
from . import annotation as sc_annotation_utils
from . import dependency_manager as sc_dep_manager

if TYPE_CHECKING:
    from anndata import AnnData


_STATUS_SEVERITY = {
    "proceed": 0,
    "proceed_with_guidance": 1,
    "needs_user_input": 2,
    "blocked": 3,
}

_OBS_FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "batch": ("batch", "sample", "sample_id", "donor", "patient", "replicate", "orig.ident", "library"),
    "condition": ("condition", "group", "treatment", "status", "disease", "diagnosis", "phenotype"),
    "cluster": ("leiden", "louvain", "cluster", "clusters", "seurat_clusters", "cell_type", "celltype", "annotation"),
    "cell_type": ("cell_type", "celltype", "annotation", "label", "labels", "predicted"),
}


@dataclass
class PreflightDecision:
    """Structured preflight outcome before starting a skill runtime."""

    skill_name: str
    status: str = "proceed"
    guidance: list[str] = field(default_factory=list)
    confirmations: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    pending_fields: list[dict[str, object]] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "preflight",
            "skill_name": self.skill_name,
            "status": self.status,
            "guidance": list(self.guidance),
            "confirmations": list(self.confirmations),
            "missing_requirements": list(self.missing_requirements),
            "pending_fields": [dict(item) for item in self.pending_fields],
        }

    def add_guidance(self, message: str) -> None:
        text = str(message).strip()
        if not text:
            return
        self.guidance.append(text)
        if _STATUS_SEVERITY[self.status] < _STATUS_SEVERITY["proceed_with_guidance"]:
            self.status = "proceed_with_guidance"

    def require_confirmation(self, message: str) -> None:
        text = str(message).strip()
        if not text:
            return
        self.confirmations.append(text)
        if _STATUS_SEVERITY[self.status] < _STATUS_SEVERITY["needs_user_input"]:
            self.status = "needs_user_input"

    def require_field(
        self,
        key: str,
        message: str,
        *,
        value_type: str = "string",
        choices: list[str] | None = None,
        aliases: list[str] | None = None,
        flag: str | None = None,
    ) -> None:
        self.require_confirmation(message)
        self.pending_fields.append(
            {
                "key": str(key),
                "flag": flag if flag is not None else f"--{str(key).replace('_', '-')}",
                "value_type": str(value_type),
                "choices": [str(item) for item in (choices or [])],
                "aliases": [str(item) for item in (aliases or [key])],
                "prompt": str(message),
            }
        )

    def block(self, message: str) -> None:
        text = str(message).strip()
        if not text:
            return
        self.missing_requirements.append(text)
        self.status = "blocked"

    def emit(self, logger) -> None:
        emit_user_guidance_payload(logger, self.to_payload())
        for line in self.guidance:
            emit_user_guidance(logger, line)
        for line in self.confirmations:
            emit_user_guidance(logger, f"User confirmation required: {line}")
        for line in self.missing_requirements:
            emit_user_guidance(logger, f"Cannot continue yet: {line}")

    def raise_if_blocking(self) -> None:
        if self.status == "proceed" or self.status == "proceed_with_guidance":
            return
        sections: list[str] = []
        if self.confirmations:
            sections.append("User confirmation required before running:")
            sections.extend(f"- {line}" for line in self.confirmations)
        if self.missing_requirements:
            sections.append("Missing data or metadata:")
            sections.extend(f"- {line}" for line in self.missing_requirements)
        if not sections:
            sections.append("Preflight validation did not pass.")
        raise ValueError("\n".join([f"{self.skill_name} preflight check failed:"] + sections))


def _obs_candidates(adata: AnnData, family: str) -> list[str]:
    keywords = _OBS_FAMILY_KEYWORDS.get(family, ())
    candidates: list[str] = []
    for column in adata.obs.columns.astype(str):
        lowered = column.lower()
        if any(keyword in lowered for keyword in keywords):
            candidates.append(column)
    return sorted(dict.fromkeys(candidates))


def _format_candidates(columns: list[str]) -> str:
    if not columns:
        return ""
    return ", ".join(f"`{column}`" for column in columns[:8])


def _looks_preprocessed_for_integration(adata: AnnData) -> bool:
    obsm_keys = {str(key).lower() for key in adata.obsm.keys()}
    obsp_keys = {str(key).lower() for key in adata.obsp.keys()}
    uns_keys = {str(key).lower() for key in adata.uns.keys()}
    obs_keys = {str(key).lower() for key in adata.obs.columns}
    return bool(
        {"x_pca", "x_umap"} & obsm_keys
        or {"neighbors", "pca"} & uns_keys
        or {"connectivities", "distances"} & obsp_keys
        or {"leiden", "louvain", "cluster", "clusters"} & obs_keys
    )


def _add_standardization_guidance(
    decision: PreflightDecision,
    adata: AnnData,
    *,
    source_path: str | None = None,
) -> None:
    contract = get_input_contract(adata)
    if get_matrix_contract(adata):
        return
    if not contract.get("standardized"):
        decision.add_guidance(
            build_standardization_recommendation(source_path=source_path, skill_name=decision.skill_name)
        )


def _declared_x_is_count_like(adata: AnnData) -> bool:
    kind = x_matrix_kind(adata)
    if kind:
        return matrix_kind_is_count_like(kind)
    return matrix_looks_count_like(adata.X)


def _declared_x_is_normalized(adata: AnnData) -> bool:
    kind = x_matrix_kind(adata)
    if kind:
        return matrix_kind_is_normalized(kind)
    return False


def _declared_raw_is_normalized(adata: AnnData) -> bool:
    if adata.raw is None or adata.raw.shape != adata.shape:
        return False
    kind = raw_matrix_kind(adata)
    if kind:
        return matrix_kind_is_normalized(kind)
    return False


def _normalized_expression_available(adata: AnnData) -> bool:
    if _declared_x_is_normalized(adata) or _declared_raw_is_normalized(adata):
        return True
    if not x_matrix_kind(adata) and not matrix_looks_count_like(adata.X):
        return True
    if adata.raw is not None and adata.raw.shape == adata.shape and not raw_matrix_kind(adata):
        return not matrix_looks_count_like(adata.raw.X)
    return False


def _aligned_raw_is_count_like(adata: AnnData) -> bool:
    if adata.raw is None or adata.raw.shape != adata.shape:
        return False
    kind = raw_matrix_kind(adata)
    if kind:
        return matrix_kind_is_count_like(kind)
    return matrix_looks_count_like(adata.raw.X)


def _count_like_matrix_available(adata: AnnData) -> bool:
    if "counts" in getattr(adata, "layers", {}):
        layer_kind = get_matrix_contract(adata).get("layers", {}).get("counts")
        if layer_kind:
            return matrix_kind_is_count_like(layer_kind)
        return matrix_looks_count_like(adata.layers["counts"])
    if _aligned_raw_is_count_like(adata):
        return True
    if not x_matrix_kind(adata):
        return matrix_looks_count_like(adata.X)
    return matrix_kind_is_count_like(x_matrix_kind(adata))


def preflight_sc_de(
    adata: AnnData,
    *,
    method: str,
    groupby: str,
    group1: str | None,
    group2: str | None,
    sample_key: str | None,
    celltype_key: str | None,
    source_path: str | None = None,
    n_top_genes: int | None = None,
    logreg_solver: str | None = None,
    pseudobulk_min_cells: int | None = None,
    pseudobulk_min_counts: int | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-de")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    if bool(group1) ^ bool(group2):
        decision.require_confirmation("Provide both `--group1` and `--group2`, or omit both for a full ranking run.")

    if method == "deseq2_r":
        decision.add_guidance(
            "This path is for replicate-aware condition DE after you already know the comparison groups and have real biological replicates."
        )
        condition_candidates = _obs_candidates(adata, "condition")
        if not groupby or groupby == "leiden":
            hint = f" Candidate condition-like columns: {_format_candidates(condition_candidates)}." if condition_candidates else ""
            decision.require_field(
                "groupby",
                "`deseq2_r` is replicate-aware condition DE; set `--groupby` to the condition column instead of relying on the default `leiden`."
                + hint,
                aliases=["groupby", "condition", "condition_key"],
            )
        elif groupby not in adata.obs.columns:
            hint = f" Available condition-like columns: {_format_candidates(condition_candidates)}." if condition_candidates else ""
            decision.require_field(
                "groupby",
                f"`--groupby {groupby}` was not found in `adata.obs`." + hint,
                aliases=["groupby", "condition", "condition_key"],
            )

        if not group1 or not group2:
            if not group1:
                decision.require_field("group1", "`deseq2_r` requires `--group1` to define the contrast.", aliases=["group1"])
            if not group2:
                decision.require_field("group2", "`deseq2_r` requires `--group2` to define the contrast.", aliases=["group2"])

        replicate_candidates = _obs_candidates(adata, "batch")
        if not sample_key:
            hint = f" Candidate replicate/sample columns: {_format_candidates(replicate_candidates)}." if replicate_candidates else ""
            decision.require_field("sample_key", "Specify `--sample-key` explicitly for pseudobulk DE." + hint, aliases=["sample_key", "sample", "sample_id"], flag="--sample-key")
        elif sample_key not in adata.obs.columns:
            hint = f" Candidate replicate/sample columns: {_format_candidates(replicate_candidates)}." if replicate_candidates else ""
            decision.require_field("sample_key", f"`--sample-key {sample_key}` was not found in `adata.obs`." + hint, aliases=["sample_key", "sample", "sample_id"], flag="--sample-key")

        label_candidates = _obs_candidates(adata, "cell_type")
        if not celltype_key:
            hint = f" Candidate label columns: {_format_candidates(label_candidates)}." if label_candidates else ""
            decision.require_field("celltype_key", "Specify `--celltype-key` for pseudobulk aggregation." + hint, aliases=["celltype_key", "cell_type_key", "cell_type"], flag="--celltype-key")
        elif celltype_key not in adata.obs.columns:
            hint = f" Candidate label columns: {_format_candidates(label_candidates)}." if label_candidates else ""
            decision.require_field("celltype_key", f"`--celltype-key {celltype_key}` was not found in `adata.obs`." + hint, aliases=["celltype_key", "cell_type_key", "cell_type"], flag="--celltype-key")

        if "counts" not in adata.layers and not _aligned_raw_is_count_like(adata):
            if _declared_x_is_count_like(adata):
                decision.require_confirmation(
                    "No explicit raw-count layer was found; confirm that `adata.X` is still the unnormalized count matrix before running `deseq2_r`."
                )
            else:
                decision.block(
                    "`deseq2_r` needs raw count-like expression in `layers['counts']`, aligned `adata.raw`, or count-like `adata.X`."
                )
        decision.add_guidance(
            f"Current first-pass settings: `method=deseq2_r`, `groupby={groupby}`, `sample_key={sample_key or 'sample_id'}`, `celltype_key={celltype_key or 'cell_type'}`, `pseudobulk_min_cells={pseudobulk_min_cells}`, `pseudobulk_min_counts={pseudobulk_min_counts}`."
        )
    else:
        if not _normalized_expression_available(adata):
            decision.block(
                f"`{method}` expects log-normalized expression in `adata.X`. Run `sc-preprocessing` first or provide a processed h5ad with normalized expression."
            )
        if groupby not in adata.obs.columns and not (groupby == "leiden" and "louvain" in adata.obs.columns):
            candidates = _obs_candidates(adata, "cluster") + _obs_candidates(adata, "condition")
            hint = f" Candidate grouping columns: {_format_candidates(candidates)}." if candidates else ""
            decision.require_confirmation(
                f"`--groupby {groupby}` was not found in `adata.obs`."
                + hint
                + " If you want cluster markers, run `sc-clustering` first; if you want condition DE, point `--groupby` to the condition column."
            )
        decision.add_guidance(
            "Exploratory single-cell DE usually comes after clustering or annotation, and before pathway enrichment or condition-focused follow-up."
        )
        if method == "logreg":
            decision.add_guidance(
                f"Current first-pass settings: `method=logreg`, `groupby={groupby}`, `n_top_genes={n_top_genes}`, `logreg_solver={logreg_solver}`."
            )
        else:
            decision.add_guidance(
                f"Current first-pass settings: `method={method}`, `groupby={groupby}`, `group1={group1}`, `group2={group2}`, `n_top_genes={n_top_genes}`."
            )

    return decision


def preflight_sc_cell_annotation(
    adata: AnnData,
    *,
    method: str,
    model: str,
    reference: str,
    cluster_key: str | None,
    celltypist_majority_voting: bool = False,
    manual_map: str | None = None,
    manual_map_file: str | None = None,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-cell-annotation")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    matrix_contract = get_matrix_contract(adata)
    cluster_candidates: list[str] = []
    primary_cluster_key = matrix_contract.get("primary_cluster_key")
    if primary_cluster_key and primary_cluster_key in adata.obs.columns:
        cluster_candidates.append(str(primary_cluster_key))
    for key in _obs_candidates(adata, "cluster"):
        if key not in cluster_candidates:
            cluster_candidates.append(key)

    if method == "markers":
        if cluster_key:
            if cluster_key not in adata.obs.columns:
                if cluster_candidates:
                    decision.require_field(
                        "cluster_key",
                        f"`--cluster-key {cluster_key}` was not found. Confirm which existing cluster/label column should guide marker-based annotation: {_format_candidates(cluster_candidates)}.",
                        aliases=["cluster_key", "groupby"],
                        flag="--cluster-key",
                        choices=cluster_candidates,
                    )
                else:
                    decision.add_guidance(
                        "`markers` annotation will not auto-cluster implicitly; cluster assignments should come from `sc-clustering` or another explicit upstream step."
                    )
                    decision.block(
                        "Marker-based annotation requires an existing cluster/label column in `adata.obs`. Run `sc-clustering` first."
                    )
            else:
                decision.add_guidance(f"`markers` will use `cluster_key={cluster_key}`.")
        else:
            if len(cluster_candidates) > 1:
                decision.require_field(
                    "cluster_key",
                    f"`markers` annotation needs a cluster/label column. Multiple candidates are available: {_format_candidates(cluster_candidates)}. Confirm which one should drive marker scoring.",
                    aliases=["cluster_key", "groupby"],
                    flag="--cluster-key",
                    choices=cluster_candidates,
                )
            elif len(cluster_candidates) == 1:
                decision.add_guidance(
                    f"`markers` annotation will use `{cluster_candidates[0]}` as the cluster column."
                )
            else:
                decision.block(
                    "Marker-based annotation needs an existing cluster/label column in `adata.obs`; it will not auto-cluster anymore. Run `sc-clustering` first."
                )
                decision.add_guidance(
                    "`markers` annotation no longer auto-clusters implicitly; cluster assignments should come from `sc-clustering` or an equivalent upstream step."
                )
        if not _declared_x_is_normalized(adata) and matrix_looks_count_like(adata.X):
            decision.require_confirmation(
                "`markers` annotation expects normalized expression. Run `sc-preprocessing` first or confirm that the current matrix has already been transformed outside OmicsClaw."
            )
        decision.add_guidance(
            "Marker-based annotation is best used after `sc-markers` or when you already have trusted lineage markers for the clustered groups."
        )
        decision.add_guidance(
            f"Current first-pass settings: `method=markers`, `cluster_key={cluster_key or (cluster_candidates[0] if len(cluster_candidates) == 1 else 'confirm')}`."
        )
        decision.add_guidance(
            "After annotation, inspect the annotated embedding and label distribution; if labels are still ambiguous, revisit `sc-markers` or try a reference-based method."
        )
        return decision

    if method == "manual":
        if cluster_key:
            if cluster_key not in adata.obs.columns:
                if cluster_candidates:
                    decision.require_field(
                        "cluster_key",
                        f"`--cluster-key {cluster_key}` was not found. Confirm which existing cluster/label column should guide manual relabeling: {_format_candidates(cluster_candidates)}.",
                        aliases=["cluster_key", "groupby"],
                        flag="--cluster-key",
                        choices=cluster_candidates,
                    )
                else:
                    decision.block(
                        "Manual annotation requires an existing cluster/label column in `adata.obs`. Run `sc-clustering` first."
                    )
            else:
                decision.add_guidance(f"`manual` annotation will use `cluster_key={cluster_key}`.")
        else:
            if len(cluster_candidates) > 1:
                decision.require_field(
                    "cluster_key",
                    f"`manual` annotation needs a cluster/label column. Multiple candidates are available: {_format_candidates(cluster_candidates)}. Confirm which one should be relabeled.",
                    aliases=["cluster_key", "groupby"],
                    flag="--cluster-key",
                    choices=cluster_candidates,
                )
            elif len(cluster_candidates) == 1:
                decision.add_guidance(
                    f"`manual` annotation will use `{cluster_candidates[0]}` as the cluster column."
                )
            else:
                decision.block(
                    "Manual annotation requires an existing cluster/label column in `adata.obs`; it will not auto-cluster. Run `sc-clustering` first."
                )

        if manual_map and manual_map_file:
            decision.require_confirmation(
                "Both `--manual-map` and `--manual-map-file` were provided. Confirm which one should take precedence."
            )
        elif not manual_map and not manual_map_file:
            decision.require_field(
                "manual_map",
                "Manual annotation needs either `--manual-map '0=T cell;1,2=Myeloid'` or `--manual-map-file <csv/json/txt>`.",
                aliases=["manual_map", "manual_labels", "mapping"],
                flag="--manual-map",
            )
        elif manual_map_file and not Path(manual_map_file).exists():
            decision.block(f"`--manual-map-file {manual_map_file}` was not found.")

        decision.add_guidance(
            "Manual annotation is the explicit relabeling path: it keeps the original cluster column and writes your chosen labels into `cell_type`."
        )
        decision.add_guidance(
            "Current first-pass settings: `method=manual`. Mapping can be supplied inline with `--manual-map` or via `--manual-map-file`."
        )
        return decision

    x_normalized = _declared_x_is_normalized(adata)
    if not x_normalized:
        if not matrix_looks_count_like(adata.X):
            decision.add_guidance(
                "This object does not declare a matrix contract yet, but `adata.X` does not look raw count-like, so annotation will treat it as normalized expression."
            )
        elif method == "celltypist":
            decision.require_confirmation(
                "`celltypist` expects normalized expression in `adata.X`. The current matrix still looks count-like, so it would likely fall back or misbehave. Run `sc-preprocessing` first or confirm the matrix state."
            )
        else:
            decision.block(
                f"`{method}` expects log-normalized expression in `adata.X`. Run `sc-preprocessing` first or provide a processed h5ad with normalized expression."
            )

    if method == "celltypist":
        if cluster_key and cluster_key not in adata.obs.columns and cluster_candidates:
            decision.add_guidance(
                f"`--cluster-key {cluster_key}` was not found. Annotation can still run per cell, but downstream summaries are easier to interpret if you later reuse one of: {_format_candidates(cluster_candidates)}."
            )
        if model == "Immune_All_Low":
            decision.add_guidance(
                "Using the default CellTypist model `Immune_All_Low`. Pass `--model <name>` to override for non-immune tissues."
            )
        else:
            valid_input, reason = sc_annotation_utils.validate_celltypist_input_matrix(
                sc_annotation_utils.build_celltypist_input_adata(adata)[0]
            )
            if not valid_input:
                decision.block(reason)
        model_available, model_path = sc_annotation_utils.celltypist_model_available_locally(model)
        if not model_available:
            decision.require_field(
                "allow_online_model_fetch",
                f"`celltypist` model `{model}` is not present locally at `{model_path}`. Running this path would need to download the model through the CellTypist model hub. Confirm whether network fetch is acceptable, or provide a model already cached locally.",
                value_type="boolean",
                aliases=["allow_online_model_fetch", "allow_download", "download_model"],
            )
            decision.add_guidance(
                "CellTypist models are typically downloaded into `~/.celltypist/data/models/`. If you want to stay offline, pre-download the model there and rerun."
            )
        decision.add_guidance(
            f"Current first-pass settings: `method=celltypist`, `model={model}`, `celltypist_majority_voting={celltypist_majority_voting}`."
        )
        decision.add_guidance(
            "If CellTypist fails or the matrix still looks incompatible, the wrapper may fall back to `markers` and should report that honestly."
        )
        decision.add_guidance(
            "After CellTypist annotation, compare the labels against clusters or marker evidence before trusting rare cell states."
        )
        return decision

    if method in {"popv", "knnpredict"}:
        if cluster_key and cluster_key not in adata.obs.columns and cluster_candidates:
            decision.add_guidance(
                f"`--cluster-key {cluster_key}` was not found. `{method}` can still label cells, but cluster-level summaries are easier if you later confirm one of: {_format_candidates(cluster_candidates)}."
            )
        ref_path = Path(reference)
        if reference == "HPCA":
            decision.require_field(
                "reference",
                f"`{method}` expects `--reference` to be a labeled H5AD path; the default `HPCA` atlas keyword is not valid for this wrapper path.",
                aliases=["reference", "ref"],
            )
        elif not ref_path.exists():
            decision.block(
                f"`{method}` reference file was not found at {reference}. Provide a labeled H5AD reference via `--reference`."
            )
        decision.add_guidance(
            f"Current first-pass settings: `method={method}`, `reference={reference}`."
        )
        if method == "popv":
            decision.add_guidance(
                "After PopV-style mapping, inspect cluster-to-label agreement and gene-overlap notes before trusting the projected labels."
            )
        else:
            decision.add_guidance(
                "`knnpredict` is the lightweight AnnData-first reference mapping path inspired by SCOP KNNPredict. It is useful when you already have a labeled H5AD reference and want a simpler projection step."
            )
        return decision

    if method in {"singler", "scmap"} and reference == "HPCA":
        decision.require_field(
            "reference",
            f"Confirm the reference atlas via `--reference`; the current default `HPCA` should not be used blindly for `{method}`.",
            aliases=["reference", "ref"],
        )
    if method in {"singler", "scmap"}:
        if not Path(reference).exists():
            cache_dir = sc_annotation_utils.experimenthub_cache_dir()
            decision.require_field(
                "allow_online_reference_fetch",
                f"`{method}` with atlas selector `{reference}` may need to download reference data through celldex / ExperimentHub. The local cache is expected under `{cache_dir}`. Confirm whether online fetch is acceptable, or provide a local labeled H5AD via `--reference` instead.",
                value_type="boolean",
                aliases=["allow_online_reference_fetch", "allow_download", "download_reference"],
            )
        decision.add_guidance(
            f"Current first-pass settings: `method={method}`, `reference={reference}`."
        )
        if cluster_key and cluster_key not in adata.obs.columns and cluster_candidates:
            decision.add_guidance(
                f"`--cluster-key {cluster_key}` was not found. The reference-based annotation can still run per cell, but cluster-level summaries are easier if you later reuse one of: {_format_candidates(cluster_candidates)}."
            )
        decision.add_guidance(
            "After reference-based annotation, compare labels against clusters and known markers before moving to DE or communication analysis."
        )
        decision.add_guidance(
            f"`{method}` currently uses celldex / ExperimentHub atlases in R. Even when the R packages are installed, this path can still fail in restricted-network or empty-cache environments."
        )
    return decision


def preflight_sc_cell_communication(
    adata: AnnData,
    *,
    method: str,
    cell_type_key: str,
    species: str,
    counts_data: str | None = None,
    counts_data_explicit: bool = False,
    cellphonedb_iterations: int | None = None,
    cellphonedb_threshold: float | None = None,
    cellphonedb_threads: int | None = None,
    cellphonedb_pvalue: float | None = None,
    cellchat_prob_type: str | None = None,
    cellchat_min_cells: int | None = None,
    condition_key: str | None = None,
    condition_oi: str | None = None,
    condition_ref: str | None = None,
    receiver: str | None = None,
    senders: list[str] | None = None,
    nichenet_top_ligands: int | None = None,
    nichenet_expression_pct: float | None = None,
    nichenet_lfc_cutoff: float | None = None,
    source_path: str | None = None,
) -> PreflightDecision:
    from pathlib import Path

    from skills.singlecell._lib import dependency_manager as sc_dep_manager

    decision = PreflightDecision("sc-cell-communication")
    _add_standardization_guidance(decision, adata, source_path=source_path)
    decision.add_guidance(
        "`sc-cell-communication` usually comes after `sc-cell-annotation` or at least `sc-clustering`, because the grouping column defines the interacting cell groups."
    )

    if cell_type_key not in adata.obs.columns:
        candidates = _obs_candidates(adata, "cell_type") + _obs_candidates(adata, "cluster")
        if candidates:
            decision.require_field(
                "cell_type_key",
                f"`--cell-type-key {cell_type_key}` was not found. Confirm which label column to use: {_format_candidates(candidates)}.",
                aliases=["cell_type_key", "celltype_key", "groupby"],
                flag="--cell-type-key",
            )
        else:
            decision.block(
                "Cell-cell communication requires cell-type or cluster labels in `adata.obs`. Run annotation/clustering first or provide `--cell-type-key`."
            )
        return decision

    if method in {"builtin", "liana", "cellphonedb", "cellchat_r"} and not _normalized_expression_available(adata):
        decision.block(
            f"`{method}` expects normalized expression in `adata.X`. Run `sc-preprocessing` first, then reuse cluster/annotation labels for communication analysis."
        )

    if method == "liana" and not sc_dep_manager.is_available("liana"):
        decision.block(
            "`liana` is not installed. Install the communication stack with `pip install -e \".[singlecell-communication]\"`."
        )

    if method == "cellphonedb":
        if not sc_dep_manager.is_available("cellphonedb"):
            decision.block(
                "`cellphonedb` is not installed. Install the communication stack with `pip install -e \".[singlecell-communication]\"`."
            )
        db_path = Path.home() / ".cache" / "omicsclaw" / "cellphonedb" / "v4.1.0" / "cellphonedb.zip"
        if not db_path.exists():
            decision.require_field(
                "allow_online_db_fetch",
                f"`cellphonedb` needs to download the official database to `{db_path}` on first use. Confirm whether online fetch is acceptable, or place the zip there manually before rerunning.",
                value_type="boolean",
                aliases=["allow_online_db_fetch", "allow_download", "download_cellphonedb_db"],
            )
        decision.add_guidance(
            "Current first-pass CellPhoneDB settings: `cellphonedb_counts_data={}`, `cellphonedb_threshold={}`, `cellphonedb_iterations={}`, `cellphonedb_threads={}`, `cellphonedb_pvalue={}`.".format(
                counts_data or "hgnc_symbol",
                cellphonedb_threshold if cellphonedb_threshold is not None else 0.1,
                cellphonedb_iterations if cellphonedb_iterations is not None else 1000,
                cellphonedb_threads if cellphonedb_threads is not None else 4,
                cellphonedb_pvalue if cellphonedb_pvalue is not None else 0.05,
            )
        )
    if method == "cellphonedb" and species != "human":
        decision.block("The current CellPhoneDB wrapper only supports `--species human`.")

    if method == "cellphonedb" and (counts_data or "hgnc_symbol") == "hgnc_symbol" and not counts_data_explicit:
        decision.require_field(
            "cellphonedb_counts_data",
            "Confirm that your gene identifiers are HGNC symbols before using the default `--cellphonedb-counts-data hgnc_symbol`.",
            choices=["hgnc_symbol", "ensembl", "gene_name"],
            aliases=["cellphonedb_counts_data", "counts_data"],
        )

    if method == "cellchat_r":
        if cellchat_prob_type:
            decision.add_guidance(
                f"Current CellChat settings: `cellchat_prob_type={cellchat_prob_type}`, `cellchat_min_cells={cellchat_min_cells or 10}`."
            )

    if method == "nichenet_r":
        if species != "human":
            decision.block("The current NicheNet wrapper only supports `--species human`.")
        cache_dir = Path.home() / ".cache" / "omicsclaw" / "nichenet"
        required_files = [
            cache_dir / "lr_network_human_21122021.rds",
            cache_dir / "weighted_networks_nsga2r_final.rds",
        ]
        if any(not path.exists() for path in required_files):
            decision.require_field(
                "allow_online_reference_fetch",
                f"`nichenet_r` needs to download prior-model resources into `{cache_dir}` on first use. Confirm whether online fetch is acceptable, or pre-populate those files manually.",
                value_type="boolean",
                aliases=["allow_online_reference_fetch", "allow_download", "download_nichenet_resources"],
            )
        if condition_key not in adata.obs.columns:
            candidates = _obs_candidates(adata, "condition") + _obs_candidates(adata, "group")
            if candidates:
                decision.require_field(
                    "condition_key",
                    f"`--condition-key {condition_key}` was not found. Confirm the perturbation/condition column: {_format_candidates(candidates)}.",
                    aliases=["condition_key", "condition", "group_key"],
                    flag="--condition-key",
                )
            else:
                decision.block(
                    "NicheNet requires a condition column in `adata.obs` so the receiver cell type can be compared between two conditions."
                )
        if not receiver:
            decision.require_field(
                "receiver",
                "NicheNet requires one receiver cell type via `--receiver`.",
                aliases=["receiver", "receiver_celltype"],
                flag="--receiver",
            )
        elif cell_type_key in adata.obs.columns and receiver not in set(adata.obs[cell_type_key].astype(str)):
            decision.block(
                f"`--receiver {receiver}` was not found in `adata.obs['{cell_type_key}']`."
            )
        if not senders:
            decision.require_field(
                "senders",
                "NicheNet requires one or more sender cell types via `--senders sender1,sender2`.",
                aliases=["senders", "sender", "sender_celltypes"],
                flag="--senders",
            )
        elif cell_type_key in adata.obs.columns:
            known = set(adata.obs[cell_type_key].astype(str))
            missing = [sender for sender in senders if sender not in known]
            if missing:
                decision.block(
                    f"`--senders` contains labels not found in `adata.obs['{cell_type_key}']`: {', '.join(missing)}."
                )
        if condition_key and condition_key in adata.obs.columns:
            values = set(adata.obs[condition_key].astype(str))
            if condition_oi and condition_oi not in values:
                decision.block(f"`--condition-oi {condition_oi}` was not found in `adata.obs['{condition_key}']`.")
            if condition_ref and condition_ref not in values:
                decision.block(f"`--condition-ref {condition_ref}` was not found in `adata.obs['{condition_key}']`.")
        decision.add_guidance(
            "Current NicheNet settings: `receiver={}`, `senders={}`, `nichenet_top_ligands={}`, `nichenet_expression_pct={}`, `nichenet_lfc_cutoff={}`.".format(
                receiver or "<receiver>",
                ",".join(senders or []) or "<sender1,sender2>",
                nichenet_top_ligands or 20,
                nichenet_expression_pct if nichenet_expression_pct is not None else 0.1,
                nichenet_lfc_cutoff if nichenet_lfc_cutoff is not None else 0.25,
            )
        )

    if method in {"builtin", "liana", "cellphonedb", "cellchat_r"}:
        decision.add_guidance(
            "If your grouping column is still coarse clustering rather than final cell types, communication results are useful as a first pass but usually need marker/annotation validation."
        )
        decision.add_guidance(
            "After communication analysis, common follow-up steps are `sc-markers`, `sc-de`, or `sc-enrichment` to explain sender/receiver biology."
        )

    return decision


def preflight_sc_batch_integration(
    adata: AnnData,
    *,
    method: str,
    batch_key: str,
    labels_key: str | None = None,
    effective_params: dict[str, object] | None = None,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-batch-integration")
    params = effective_params or {}
    _add_standardization_guidance(decision, adata, source_path=source_path)

    if batch_key not in adata.obs.columns:
        candidates = _obs_candidates(adata, "batch")
        if candidates:
            decision.require_field(
                "batch_key",
                f"`--batch-key {batch_key}` was not found. Confirm which batch/sample column to use: {_format_candidates(candidates)}.",
                aliases=["batch_key", "batch", "sample_key"],
                flag="--batch-key",
            )
        else:
            decision.block(
                "Batch integration requires a real batch/sample column in `adata.obs`; none was found. Stay on the standard `sc-preprocessing -> sc-clustering` path instead."
            )
        return decision

    if int(adata.obs[batch_key].astype(str).nunique()) < 2:
        decision.block(
            f"`{batch_key}` has fewer than 2 unique batches, so integration is not meaningful. "
            "Use `sc-clustering` directly on the preprocessed object instead."
        )
        return decision

    batch_sizes = adata.obs[batch_key].astype(str).value_counts()
    n_batches = int(batch_sizes.shape[0])
    singleton_fraction = float((batch_sizes == 1).mean()) if n_batches else 0.0
    if n_batches >= max(50, int(adata.n_obs * 0.5)) or singleton_fraction >= 0.5:
        decision.block(
            f"`{batch_key}` looks too close to a per-cell identifier ({n_batches} unique values for {adata.n_obs} cells). "
            "Use a real batch/sample column such as sample, donor, patient, or library instead."
        )
        return decision
    if n_batches >= max(20, int(adata.n_obs * 0.2)) or (n_batches >= 5 and int(batch_sizes.min()) < 3):
        decision.require_confirmation(
            f"`{batch_key}` has many small groups (min batch size={int(batch_sizes.min())}, total batches={n_batches}). "
            "Confirm that this column truly represents technical/sample batches rather than per-cell labels."
        )

    if not _aligned_raw_is_count_like(adata) and "counts" not in adata.layers and not _declared_x_is_count_like(adata):
        decision.block(
            "Batch integration needs raw counts in `layers['counts']`, aligned `adata.raw`, or count-like `adata.X`."
        )
    elif not _aligned_raw_is_count_like(adata) and "counts" not in adata.layers and _declared_x_is_count_like(adata):
        decision.add_guidance(
            "No explicit raw-count layer was found; integration will use count-like `adata.X`. Standardizing first is safer for downstream reuse."
        )

    if not _looks_preprocessed_for_integration(adata):
        decision.add_guidance(
            "This object does not yet show the usual preprocessing markers (`X_pca`, neighbors, or cluster labels). "
            "The standard OmicsClaw path is canonicalize the input first, then `sc-preprocessing`, then `sc-batch-integration`."
        )

    if method == "scanvi":
        labels = [name for name in ("cell_type", "leiden", "louvain", "seurat_clusters") if name in adata.obs.columns]
        if labels_key:
            if labels_key not in adata.obs.columns:
                decision.require_field(
                    "labels_key",
                    f"`--labels-key {labels_key}` was not found. Available label columns include: {_format_candidates(labels)}.",
                    aliases=["labels_key", "label_key", "labels"],
                    flag="--labels-key",
                )
        elif not labels:
            decision.require_field(
                "method",
                "`scanvi` needs existing labels such as `cell_type`, `leiden`, or `louvain`; otherwise choose `scvi` instead.",
                choices=["scanvi", "scvi"],
                aliases=["method"],
            )
        elif len(labels) > 1:
            decision.require_field(
                "labels_key",
                f"`scanvi` needs a label column. Multiple candidates are available: {_format_candidates(labels)}. Confirm which one should guide scANVI.",
                aliases=["labels_key", "label_key", "labels"],
                flag="--labels-key",
                choices=labels,
            )

    if params:
        decision.add_guidance(
            f"Current first-pass settings: `method={method}`, `batch_key={batch_key}`."
        )
        if method == "harmony":
            decision.add_guidance(
                f"`harmony`-specific settings: `harmony_theta={params.get('harmony_theta')}`, `integration_pcs={params.get('integration_pcs')}`."
            )
        elif method in {"scvi", "scanvi"}:
            guidance = (
                f"`{method}`-specific settings: `n_epochs={params.get('n_epochs')}`, "
                f"`n_latent={params.get('n_latent')}`, `no_gpu={params.get('no_gpu')}`."
            )
            if method == "scanvi":
                guidance += f" `labels_key={params.get('labels_key')}`."
            decision.add_guidance(guidance)
        elif method == "bbknn":
            decision.add_guidance(
                f"`bbknn`-specific settings: `bbknn_neighbors_within_batch={params.get('bbknn_neighbors_within_batch')}`."
            )
        elif method == "scanorama":
            decision.add_guidance(
                f"`scanorama`-specific settings: `scanorama_knn={params.get('scanorama_knn')}`."
            )
        elif method in {"fastmnn", "seurat_cca", "seurat_rpca"}:
            decision.add_guidance(
                f"`{method}`-specific settings: `integration_features={params.get('integration_features')}`, `integration_pcs={params.get('integration_pcs')}`."
            )

    return decision


def preflight_sc_doublet_detection(
    adata: AnnData,
    *,
    method: str,
    expected_doublet_rate: float,
    threshold: float | None = None,
    batch_key: str | None = None,
    doubletdetection_n_iters: int | None = None,
    scds_mode: str | None = None,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-doublet-detection")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    if not 0 < float(expected_doublet_rate) < 1:
        decision.require_confirmation(
            f"`--expected-doublet-rate {expected_doublet_rate}` is outside the usual 0-1 fraction range; confirm the intended value."
        )

    if threshold is not None and method != "scrublet":
        decision.require_field(
            "method",
            "`--threshold` only affects the Scrublet path in the current wrapper. Confirm whether you want `scrublet` instead.",
            choices=["scrublet", method],
            aliases=["method"],
        )

    if batch_key and batch_key not in adata.obs.columns:
        batch_candidates = _obs_candidates(adata, "batch")
        decision.require_field(
            "batch_key",
            f"`--batch-key {batch_key}` was not found. Available batch/sample-style columns include: {_format_candidates(batch_candidates)}.",
            aliases=["batch_key", "batch", "sample_key"],
            flag="--batch-key",
            choices=batch_candidates,
        )

    if method == "doubletdetection":
        if find_spec("doubletdetection") is None:
            decision.block(
                "`doubletdetection` requires the optional Python package `doubletdetection`, which is not installed in the current environment."
            )
        if doubletdetection_n_iters is not None and int(doubletdetection_n_iters) < 2:
            decision.block("`--doubletdetection-n-iters` must be at least 2.")

    if "counts" not in adata.layers:
        if _aligned_raw_is_count_like(adata) or (raw_matrix_kind(adata) and matrix_kind_is_count_like(raw_matrix_kind(adata))):
            decision.add_guidance(
                "No explicit `layers['counts']` was found; doublet detection will use aligned `adata.raw` while preserving the current `adata.X` semantics."
            )
        elif _declared_x_is_count_like(adata):
            decision.add_guidance(
                "No explicit `layers['counts']` was found; doublet detection will use count-like `adata.X`."
            )
        else:
            decision.block(
                "Doublet detection requires raw count-like input in `layers['counts']`, aligned `adata.raw`, or count-like `adata.X`."
            )

    batch_candidates = _obs_candidates(adata, "batch")
    if method == "scrublet" and not batch_key and batch_candidates:
        decision.add_guidance(
            f"Potential capture/sample columns were detected: {_format_candidates(batch_candidates)}. For multi-capture droplet data, `scrublet` is often safer run per capture via `--batch-key`."
        )

    if any(col in adata.obs.columns for col in ("predicted_doublet", "doublet_score", "doublet_classification")):
        decision.add_guidance(
            "Existing doublet annotations were detected and will be overwritten by the selected method."
        )

    decision.add_guidance(
        "Doublet detection is usually most helpful after QC review and before final clustering, annotation, or DE interpretation."
    )

    if method == "scrublet":
        decision.add_guidance(
            f"Current first-pass settings: `method=scrublet`, `expected_doublet_rate={expected_doublet_rate}`, `threshold={threshold if threshold is not None else 'auto'}`."
        )
        if batch_key:
            decision.add_guidance(f"`scrublet` will run per batch using `batch_key={batch_key}`.")
    elif method == "doubletdetection":
        decision.add_guidance(
            f"Current first-pass settings: `method=doubletdetection`, `doubletdetection_n_iters={doubletdetection_n_iters}`, `expected_doublet_rate` is recorded for context but does not control this backend's native classifier."
        )
    elif method == "scds":
        decision.add_guidance(
            f"Current first-pass settings: `method=scds`, `expected_doublet_rate={expected_doublet_rate}`, `scds_mode={scds_mode}`."
        )
    else:
        decision.add_guidance(
            f"Current first-pass settings: `method={method}`, `expected_doublet_rate={expected_doublet_rate}`."
        )
        if batch_key:
            decision.add_guidance(
                f"`batch_key={batch_key}` was provided, but the current `{method}` wrapper does not use it directly."
            )

    decision.add_guidance(
        "This skill annotates doublets in `obs` but does not remove cells automatically. After review, keep singlets for downstream preprocessing/clustering if needed."
    )
    return decision


def preflight_sc_ambient_removal(
    adata: AnnData,
    *,
    method: str,
    raw_h5: str | None,
    raw_matrix_dir: str | None,
    filtered_matrix_dir: str | None,
    contamination: float,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-ambient-removal")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    if contamination <= 0 or contamination >= 1:
        decision.require_confirmation(
            f"`--contamination {contamination}` is outside the usual 0-1 fraction range; confirm the intended subtraction fraction."
        )

    if method == "cellbender":
        if not raw_h5:
            decision.block("`cellbender` requires `--raw-h5` pointing to the raw 10x `.h5` file.")
        elif not str(raw_h5).lower().endswith(".h5"):
            decision.block("`cellbender` only accepts raw 10x `.h5` input in the current wrapper.")
        return decision

    if method == "soupx":
        if not raw_matrix_dir or not filtered_matrix_dir:
            if not raw_matrix_dir:
                decision.require_field(
                    "raw_matrix_dir",
                    "`soupx` needs both `--raw-matrix-dir` and `--filtered-matrix-dir`. Provide `--raw-matrix-dir` or switch methods.",
                    aliases=["raw_matrix_dir", "raw_dir"],
                    flag="--raw-matrix-dir",
                )
            if not filtered_matrix_dir:
                decision.require_field(
                    "filtered_matrix_dir",
                    "Provide `--filtered-matrix-dir` for `soupx`, or switch methods.",
                    aliases=["filtered_matrix_dir", "filtered_dir"],
                    flag="--filtered-matrix-dir",
                )
            decision.require_field(
                "method",
                "`soupx` needs both `--raw-matrix-dir` and `--filtered-matrix-dir`. Without them, the runtime would fall back to `simple` if a count-like matrix is available. Confirm whether you want to provide these directories or switch methods.",
                choices=["soupx", "simple"],
                aliases=["method"],
            )
        return decision

    has_raw_like = "counts" in adata.layers or (
        adata.raw is not None and adata.raw.shape == adata.shape and matrix_looks_count_like(adata.raw.X)
    )

    if not has_raw_like:
        if matrix_looks_count_like(adata.X):
            decision.add_guidance(
                "No explicit `layers['counts']` was found; simple ambient subtraction will use count-like `adata.X`."
            )
        else:
            decision.block(
                "Ambient RNA removal requires raw count-like input in `layers['counts']`, aligned `adata.raw`, or count-like `adata.X`."
            )
    elif "counts" not in adata.layers and adata.raw is not None:
        decision.add_guidance(
            "No explicit `layers['counts']` was found; simple ambient subtraction will use aligned `adata.raw`."
        )

    return decision


def preflight_sc_velocity(
    adata: AnnData,
    *,
    method: str,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-velocity")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    missing_layers = [layer for layer in ("spliced", "unspliced") if layer not in adata.layers]
    if missing_layers:
        decision.block(
            "RNA velocity requires both `spliced` and `unspliced` layers. Generate them with velocyto / kb-python or use `--demo`."
        )

    if method == "scvelo_dynamical" and "X_umap" not in adata.obsm:
        decision.add_guidance(
            "`scvelo_dynamical` can compute downstream embeddings, but results are easier to interpret if the object has already been preprocessed with PCA/UMAP."
        )

    return decision


def preflight_sc_qc(
    adata: AnnData,
    *,
    species: str,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-qc")
    contract = get_input_contract(adata)
    _add_standardization_guidance(decision, adata, source_path=source_path)

    if "counts" not in adata.layers and not _aligned_raw_is_count_like(adata):
        if _declared_x_is_count_like(adata):
            if not contract.get("standardized"):
                decision.add_guidance(
                    "`sc-qc` will use count-like `adata.X` because no explicit `counts` layer or aligned `adata.raw` was found."
                )
        else:
            decision.block(
                "`sc-qc` expects a raw count-like matrix in `layers['counts']`, aligned `adata.raw`, or `adata.X`."
            )

    if species == "human":
        decision.add_guidance(
            "Human QC expects mitochondrial genes like `MT-...` and ribosomal genes like `RPS/RPL`. If your feature IDs are Ensembl-like, `%MT` and `%ribo` may be underestimated."
        )
    elif species == "mouse":
        decision.add_guidance(
            "Mouse QC expects mitochondrial genes like `mt-...` and ribosomal genes like `Rps/Rpl`. If your feature IDs are Ensembl-like, `%MT` and `%ribo` may be underestimated."
        )

    return decision


def preflight_sc_pseudotime(
    adata: AnnData,
    *,
    method: str,
    cluster_key: str,
    use_rep: str | None,
    root_cluster: str | None,
    root_cell: str | None,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-pseudotime")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    matrix_contract = get_matrix_contract(adata)
    x_kind = matrix_contract.get("X") or infer_x_matrix_kind(adata, fallback="raw_counts")
    if x_kind != "normalized_expression":
        decision.block(
            "`sc-pseudotime` expects normalized expression. Run `sc-preprocessing` first, and if you need integration-aware trajectories use the integrated representation from `sc-batch-integration`."
        )
        return decision

    if cluster_key not in adata.obs.columns:
        candidates = _obs_candidates(adata, "cluster")
        if candidates:
            decision.require_field(
                "cluster_key",
                f"`--cluster-key {cluster_key}` was not found. Confirm which cluster/label column to use: {_format_candidates(candidates)}.",
                aliases=["cluster_key", "groupby", "cluster"],
                flag="--cluster-key",
            )
        else:
            decision.block(
                "Pseudotime requires a cluster column in `adata.obs`. Run `sc-preprocessing` first or provide `--cluster-key`."
            )

    rep_candidates = [
        key
        for key in ("X_harmony", "X_scvi", "X_scanvi", "X_scanorama", "X_pca")
        if key in getattr(adata, "obsm", {})
    ]
    if use_rep:
        if use_rep not in getattr(adata, "obsm", {}):
            decision.require_field(
                "use_rep",
                f"`--use-rep {use_rep}` was not found. Available representations include: {_format_candidates(rep_candidates)}.",
                aliases=["use_rep", "embedding", "representation"],
                flag="--use-rep",
                choices=rep_candidates,
            )
    else:
        if not rep_candidates:
            decision.block(
                "`sc-pseudotime` needs a graph/trajectory representation such as `X_pca`, `X_harmony`, or `X_scvi`. Run `sc-preprocessing` or `sc-batch-integration` first."
            )
        elif len(rep_candidates) > 1:
            decision.require_field(
                "use_rep",
                f"Multiple trajectory representations are available: {_format_candidates(rep_candidates)}. Confirm which one should drive pseudotime.",
                aliases=["use_rep", "embedding", "representation"],
                flag="--use-rep",
                choices=rep_candidates,
            )
        else:
            decision.add_guidance(f"`sc-pseudotime` will use `{rep_candidates[0]}` for graph / trajectory inference.")

    if root_cluster is None and root_cell is None:
        decision.require_field(
            "root_cluster",
            "Pseudotime direction depends on the starting state. Confirm `--root-cluster` (or `--root-cell`) instead of relying on implicit root selection.",
            aliases=["root_cluster", "root"],
            flag="--root-cluster",
        )
    if root_cluster is not None and cluster_key in adata.obs.columns:
        cluster_values = set(adata.obs[cluster_key].astype(str).tolist())
        if str(root_cluster) not in cluster_values:
            decision.require_field(
                "root_cluster",
                f"`--root-cluster {root_cluster}` was not found in `{cluster_key}`. Available clusters include: {', '.join(sorted(cluster_values)[:8])}.",
                aliases=["root_cluster", "root"],
                flag="--root-cluster",
            )

    decision.add_guidance(
        "`sc-pseudotime` is usually the step after `sc-clustering`. Use it when you already have cluster labels and a biologically defensible start state."
    )
    decision.add_guidance(
        "Current first-pass settings: "
        f"`method={method}`, `cluster_key={cluster_key}`, `use_rep={use_rep or (rep_candidates[0] if len(rep_candidates) == 1 else 'needs confirmation')}`. "
        "This skill will not guess the biological start state for you."
    )

    if method == "palantir":
        decision.add_guidance(
            "`palantir` is available here, but it is heavier than DPT and should be chosen deliberately when users want waypoint-based pseudotime."
        )
        decision.add_guidance(
            "Method-specific defaults: `palantir_knn=30`, `palantir_n_components=10`, `palantir_num_waypoints=1200`, `palantir_max_iterations=25`."
        )
        if find_spec("palantir") is None:
            decision.block(
                "`palantir` was requested but the Python package `palantir` is not installed.\n"
                + sc_dep_manager.install_hint("palantir")
            )
    if method == "via":
        decision.add_guidance(
            "`via` is intended for graph-based trajectory inference with automatic terminal-state discovery; keep the root choice explicit and do not present it as a generic replacement for every pseudotime workflow."
        )
        decision.add_guidance("Method-specific defaults: `via_knn=30`, `via_seed=20`.")
        if find_spec("pyVIA") is None:
            decision.block(
                "`via` was requested but the Python package `pyVIA` is not installed.\n"
                + sc_dep_manager.install_hint("pyVIA")
            )
    if method == "cellrank":
        decision.add_guidance(
            "`cellrank` is intended for macrostate and fate-probability inference on top of a transition kernel; use it when users explicitly want terminal states or lineage probabilities."
        )
        decision.add_guidance(
            "Method-specific defaults: `cellrank_n_states=3`, `cellrank_schur_components=20`, `cellrank_frac_to_keep=0.3`. `cellrank_use_velocity` only helps when velocity layers exist."
        )
        if find_spec("cellrank") is None:
            decision.block(
                "`cellrank` was requested but the Python package `cellrank` is not installed.\n"
                + sc_dep_manager.install_hint("cellrank")
            )
    if method == "dpt":
        decision.add_guidance("Method-specific defaults: `n_neighbors=15`, `n_pcs=50`, `n_dcs=10`.")
    if method == "slingshot_r":
        decision.add_guidance(
            "`slingshot_r` is a branch-aware lineage method through the R bridge. Use it when users want explicit lineages rather than only a single scalar ordering."
        )
        decision.add_guidance(
            "Method-specific defaults: `end_clusters` optional; if omitted, Slingshot will infer terminal branches from the cluster graph."
        )
        _, missing = check_r_tier("singlecell-pseudotime")
        required = [pkg for pkg in ("slingshot", "SingleCellExperiment", "zellkonverter") if pkg in missing]
        if required:
            decision.block(
                "Slingshot R dependencies are missing: " + ", ".join(required) + "\n" + suggest_r_install(required)
            )

    if "neighbors" not in adata.uns:
        decision.add_guidance(
            "Neighbor graph is missing; `sc-pseudotime` will compute it automatically from the chosen representation."
        )

    decision.add_guidance(
        "After pseudotime, the usual next steps are trajectory gene interpretation, `sc-pathway-scoring` for lineage signatures, or `sc-enrichment` for statistical pathway interpretation."
    )

    return decision


def preflight_sc_preprocessing(
    adata: AnnData,
    *,
    method: str,
    min_genes: int | None = None,
    max_mt_pct: float | None = None,
    min_cells: int | None = None,
    n_top_hvg: int | None = None,
    n_pcs: int | None = None,
    effective_params: dict[str, object] | None = None,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-preprocessing")
    params = effective_params or {}

    has_qc_metrics = {"n_genes_by_counts", "total_counts"}.issubset(set(adata.obs.columns))
    if not has_qc_metrics and source_path and (
        min_genes in {None, 200}
        and max_mt_pct in {None, 20.0}
        and min_cells in {None, 3}
    ):
        decision.require_confirmation(
            "You asked for preprocessing before reviewing QC. Recommended path: run `sc-qc` first to inspect `n_genes`, `total_counts`, and `%MT`, then confirm the filtering thresholds. If you want to continue now, confirm that the default first-pass filtering thresholds are acceptable."
        )

    if method in {"seurat", "sctransform"} and adata.raw is not None:
        decision.add_guidance(
            f"`{method}` will rebuild preprocessing from count-like input; existing `adata.raw` does not make the object already preprocessing-ready."
        )
    if method in {"seurat", "sctransform"} and "counts" not in adata.layers and not _aligned_raw_is_count_like(adata) and _declared_x_is_count_like(adata):
        decision.require_confirmation(
            f"`{method}` will use count-like `adata.X` as raw input because no `layers['counts']` or aligned `adata.raw` was found. Confirm that `adata.X` is still the unnormalized count matrix."
        )

    if "counts" not in adata.layers:
        if _declared_x_is_count_like(adata):
            decision.add_guidance(
                "No explicit `layers['counts']` was found; preprocessing will treat count-like `adata.X` as the raw matrix."
            )
        else:
            decision.block(
                "Preprocessing expects raw count-like input. Provide an unnormalized count matrix or use the shared canonicalization path first."
            )

    remove_doublets = bool(params.get("remove_doublets", True))
    doublet_score_threshold = float(params.get("doublet_score_threshold", 0.25))
    has_predicted = "predicted_doublet" in adata.obs.columns
    has_score = "doublet_score" in adata.obs.columns
    if remove_doublets:
        if has_predicted:
            n_doublets = int(adata.obs["predicted_doublet"].astype(bool).sum())
            decision.add_guidance(
                f"`predicted_doublet` column detected ({n_doublets:,} doublets flagged by sc-doublet-detection). "
                "These will be automatically removed during the QC filtering step."
            )
        elif has_score:
            n_doublets = int((adata.obs["doublet_score"] >= doublet_score_threshold).sum())
            decision.require_confirmation(
                f"`doublet_score` column detected — {n_doublets:,} cells score >= {doublet_score_threshold} "
                f"and will be removed. The threshold is a judgment call: confirm {doublet_score_threshold} is acceptable, "
                "or rerun with `--doublet-score-threshold <value>` to adjust. "
                "(Pass `--no-remove-doublets` to skip doublet removal entirely.)"
            )
        else:
            decision.add_guidance(
                "No doublet columns found (`predicted_doublet` / `doublet_score`). "
                "Doublet removal will be skipped. "
                "Run `sc-doublet-detection` before `sc-preprocessing` to enable automatic doublet removal."
            )
    else:
        if has_predicted or has_score:
            decision.add_guidance(
                "Doublet removal is disabled (`--no-remove-doublets`). "
                "Doublet labels are present but will NOT be used to filter cells."
            )

    batch_candidates = _obs_candidates(adata, "batch")
    if batch_candidates:
        decision.add_guidance(
            f"Potential batch/sample columns were detected: {_format_candidates(batch_candidates)}. If batch effects are expected, plan `sc-batch-integration` after preprocessing."
        )

    if params:
        decision.add_guidance(
            f"Current first-pass settings: `method={method}`, `min_genes={params.get('min_genes')}`, `min_cells={params.get('min_cells')}`, `max_mt_pct={params.get('max_mt_pct')}`, `n_top_hvg={params.get('n_top_hvg')}`, `n_pcs={params.get('n_pcs')}`."
        )
        if method == "scanpy":
            decision.add_guidance(
                f"`scanpy`-specific settings: `normalization_target_sum={params.get('normalization_target_sum')}`, `scanpy_hvg_flavor={params.get('scanpy_hvg_flavor')}`."
            )
        elif method == "pearson_residuals":
            decision.add_guidance(
                f"`pearson_residuals`-specific settings: `pearson_hvg_flavor={params.get('pearson_hvg_flavor')}`, `pearson_theta={params.get('pearson_theta')}`."
            )
        elif method == "seurat":
            decision.add_guidance(
                f"`seurat`-specific settings: `seurat_normalize_method={params.get('seurat_normalize_method')}`, `seurat_scale_factor={params.get('seurat_scale_factor')}`, `seurat_hvg_method={params.get('seurat_hvg_method')}`."
            )
        elif method == "sctransform":
            decision.add_guidance(
                f"`sctransform`-specific settings: `sctransform_regress_mt={params.get('sctransform_regress_mt')}`."
            )

    return decision


def preflight_sc_filter(
    adata: AnnData,
    *,
    tissue: str | None,
    min_counts: int | None = None,
    max_counts: int | None = None,
    max_mt_percent: float | None = None,
    min_genes: int | None = None,
    max_genes: int | None = None,
    min_cells: int | None = None,
    remove_doublets: bool = True,
    doublet_score_threshold: float = 0.25,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-filter")

    if "n_genes_by_counts" not in adata.obs.columns:
        if _declared_x_is_count_like(adata) or "counts" in adata.layers or _aligned_raw_is_count_like(adata):
            decision.add_guidance(
                "QC metrics are missing; `sc-filter` will compute QC metrics automatically before filtering."
            )
        else:
            decision.block(
                "`sc-filter` needs either existing QC metrics in `adata.obs` or a raw count-like matrix to recompute them safely."
            )
        if source_path and all(value is None for value in (min_counts, max_counts, max_genes, tissue)) and (
            min_genes in {None, 200}
            and max_mt_percent in {None, 20.0}
            and min_cells in {None, 3}
        ):
            decision.require_confirmation(
                "You asked for filtering before reviewing QC distributions. Recommended path: run `sc-qc` first to inspect `n_genes`, `total_counts`, and `%MT`, then confirm the filtering thresholds. If you want to continue now, confirm that the default first-pass thresholds are acceptable."
            )

    if (min_counts is not None or max_counts is not None) and "total_counts" not in adata.obs.columns and "n_genes_by_counts" in adata.obs.columns:
        decision.block(
            "Count-based filtering was requested, but `total_counts` is missing and this wrapper will not recompute QC when `n_genes_by_counts` already exists. Run `sc-qc` first or provide a fully QC-annotated object."
        )

    if max_mt_percent is not None and "pct_counts_mt" not in adata.obs.columns and "n_genes_by_counts" in adata.obs.columns:
        decision.add_guidance(
            "Mitochondrial filtering was requested, but `pct_counts_mt` is missing. In the current wrapper this would silently skip MT filtering unless you recompute QC first."
        )

    if "outlier" in adata.obs.columns:
        decision.require_confirmation(
            "This object already has `obs['outlier']`; `sc-filter` will automatically drop those cells in addition to the explicit thresholds. Confirm that you want to keep using the existing outlier flag."
        )

    if tissue and tissue not in {"pbmc", "brain", "tumor", "kidney", "liver", "heart", "default"}:
        decision.require_confirmation(
            f"`--tissue {tissue}` is not one of the built-in presets. Confirm whether you want the default thresholds instead."
        )
    elif tissue:
        decision.add_guidance(
            f"`--tissue {tissue}` will override the wrapper defaults for `min_genes`, `max_genes`, and `max_mt_percent`."
        )

    # Doublet removal guidance
    has_predicted = "predicted_doublet" in adata.obs.columns
    has_score = "doublet_score" in adata.obs.columns
    if remove_doublets:
        if has_predicted:
            n_doublets = int(adata.obs["predicted_doublet"].astype(bool).sum())
            decision.add_guidance(
                f"`predicted_doublet` column detected ({n_doublets:,} doublets flagged by sc-doublet-detection). "
                "These will be automatically removed during filtering."
            )
        elif has_score:
            n_doublets = int((adata.obs["doublet_score"] >= doublet_score_threshold).sum())
            decision.require_confirmation(
                f"`doublet_score` column detected — {n_doublets:,} cells score >= {doublet_score_threshold} "
                f"and will be removed. The threshold is a judgment call: confirm {doublet_score_threshold} is acceptable, "
                "or rerun with `--doublet-score-threshold <value>` to adjust. "
                "(Pass `--no-remove-doublets` to skip doublet removal entirely.)"
            )
        else:
            decision.add_guidance(
                "No doublet columns found (`predicted_doublet` / `doublet_score`). "
                "Doublet removal will be skipped. "
                "Run `sc-doublet-detection` before `sc-filter` to enable automatic doublet removal."
            )
    else:
        if has_predicted or has_score:
            decision.add_guidance(
                "Doublet removal is disabled (`--no-remove-doublets`). "
                "Doublet labels are present but will NOT be used to filter cells."
            )

    return decision


def preflight_sc_markers(
    adata: AnnData,
    *,
    groupby: str | None,
    method: str,
    n_genes: int | None,
    n_top: int,
    min_in_group_fraction: float,
    min_fold_change: float,
    max_out_group_fraction: float,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-markers")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    matrix_contract = get_matrix_contract(adata)
    primary_cluster_key = matrix_contract.get("primary_cluster_key")
    candidates = []
    if primary_cluster_key and primary_cluster_key in adata.obs.columns:
        candidates.append(str(primary_cluster_key))
    for key in _obs_candidates(adata, "cluster") + _obs_candidates(adata, "cell_type"):
        if key not in candidates:
            candidates.append(key)

    if groupby:
        if groupby not in adata.obs.columns:
            decision.require_field(
                "groupby",
                f"`--groupby {groupby}` was not found. Confirm which grouping column to use: {_format_candidates(candidates)}.",
                aliases=["groupby", "cluster_key"],
            )
        elif adata.obs[groupby].astype(str).nunique(dropna=False) < 2:
            decision.block(
                f"`--groupby {groupby}` has fewer than two groups, so marker ranking would not be meaningful."
            )
    else:
        if len(candidates) > 1:
            decision.require_field(
                "groupby",
                f"`sc-markers` needs a grouping column. Multiple candidates are available: {_format_candidates(candidates)}. Confirm which one should drive marker ranking.",
                aliases=["groupby", "cluster_key"],
                choices=candidates,
            )
        elif len(candidates) == 1:
            if adata.obs[candidates[0]].astype(str).nunique(dropna=False) < 2:
                decision.block(
                    f"`{candidates[0]}` has fewer than two groups, so marker ranking would not be meaningful."
                )
            decision.add_guidance(
                f"`sc-markers` will use `{candidates[0]}` as the grouping column."
            )
        else:
            decision.block(
                "Marker detection requires an existing grouping column in `adata.obs` such as `leiden` or `cell_type`."
            )

    if _declared_x_is_normalized(adata):
        pass
    elif not matrix_looks_count_like(adata.X):
        decision.add_guidance(
            "This object does not declare a matrix contract yet, but `adata.X` does not look raw count-like, so marker ranking will treat it as normalized expression."
        )
    else:
        decision.require_confirmation(
            "Marker detection expects normalized expression, but this object currently looks count-like. Run `sc-preprocessing` first or confirm that you want to continue anyway."
        )

    if n_top <= 0:
        decision.block("`--n-top` must be greater than 0.")
    if n_genes is not None and n_genes <= 0:
        decision.block("`--n-genes` must be greater than 0 when provided.")
    if min_in_group_fraction < 0 or min_in_group_fraction > 1:
        decision.block("`--min-in-group-fraction` must be between 0 and 1.")
    if max_out_group_fraction < 0 or max_out_group_fraction > 1:
        decision.block("`--max-out-group-fraction` must be between 0 and 1.")

    decision.add_guidance(
        "`sc-markers` is usually the step after clustering and before final annotation. It ranks cluster-discriminative genes, not replicate-aware condition DE."
    )
    decision.add_guidance(
        f"Current first-pass settings: `method={method}`, `n_genes={n_genes if n_genes is not None else 'all'}`, `n_top={n_top}`, `min_in_group_fraction={min_in_group_fraction}`, `min_fold_change={min_fold_change}`, `max_out_group_fraction={max_out_group_fraction}`."
    )
    if method == "wilcoxon":
        decision.add_guidance("`wilcoxon` is the safest first-pass default for cluster marker ranking.")
    elif method == "t-test":
        decision.add_guidance("`t-test` is a more parametric alternative and is more sensitive to distributional assumptions.")
    elif method == "logreg":
        decision.add_guidance("`logreg` provides classification-style ranking and may emphasize discriminative genes rather than large fold changes.")
    decision.add_guidance(
        "After marker review, the usual next step is `sc-cell-annotation`; if the question is treated-vs-control rather than cluster identity, use `sc-de`."
    )

    return decision


def preflight_sc_grn(
    adata: AnnData,
    *,
    tf_list: str | None,
    database_glob: str | None,
    motif_annotations: str | None,
    demo_mode: bool = False,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-grn")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    provided = [bool(tf_list), bool(database_glob), bool(motif_annotations)]
    if not demo_mode and not any(provided):
        decision.require_field(
            "allow_simplified_grn",
            "No TF/database/motif files were provided, so `sc-grn` would run the simplified GRNBoost2-style fallback instead of full pySCENIC. Confirm that this fallback is acceptable.",
            value_type="boolean",
            aliases=["allow_simplified_grn", "simplified_grn", "fallback"],
        )
    elif any(provided) and not all(provided):
        if not tf_list:
            decision.require_field("tf_list", "Full pySCENIC mode needs `--tf-list`, `--db`, and `--motif` together. Provide `--tf-list` or intentionally accept the simplified fallback.", aliases=["tf_list", "tf"], flag="--tf-list")
        if not database_glob:
            decision.require_field("database_glob", "Provide `--db` for full pySCENIC mode, or intentionally accept the simplified fallback.", aliases=["database_glob", "db"], flag="--db")
        if not motif_annotations:
            decision.require_field("motif_annotations", "Provide `--motif` for full pySCENIC mode, or intentionally accept the simplified fallback.", aliases=["motif_annotations", "motif"], flag="--motif")
        decision.require_field(
            "allow_simplified_grn",
            "Full pySCENIC mode needs `--tf-list`, `--db`, and `--motif` together. Confirm whether you want to provide the missing database files or intentionally use the demo-style fallback.",
            value_type="boolean",
            aliases=["allow_simplified_grn", "simplified_grn", "fallback"],
        )

    if not _normalized_expression_available(adata):
        decision.require_confirmation(
            "GRN inference currently does not see a declared normalized expression source. Run `sc-preprocessing` first or confirm the matrix state before interpreting regulons."
        )

    return decision


def preflight_sc_pathway_scoring(
    adata: AnnData,
    *,
    method: str,
    gene_sets_path: str | None,
    gene_set_db: str | None = None,
    groupby: str | None,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-pathway-scoring")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    if not gene_sets_path and not gene_set_db:
        decision.block(
            "`sc-pathway-scoring` requires either `--gene-sets <local.gmt>` or `--gene-set-db <hallmark|kegg|go_bp|...>` unless `--demo` is used."
        )

    if gene_set_db and find_spec("gseapy") is None:
        decision.block(
            "`--gene-set-db` needs the optional Python package `gseapy`, which is not installed in the current environment. Install it before using built-in pathway libraries."
        )
    elif gene_set_db:
        decision.add_guidance(
            f"`--gene-set-db {gene_set_db}` will try to resolve a built-in gene-set library automatically. The first run may need network access to download or refresh the library cache."
        )

    if method == "score_genes_py":
        if not _normalized_expression_available(adata):
            decision.block(
                "`score_genes_py` requires normalized expression in `adata.X`. Run `sc-preprocessing` first."
            )
        else:
            decision.add_guidance(
                "`score_genes_py` is a lightweight module-scoring path for normalized expression and works best after `sc-preprocessing`."
            )
    else:
        if _normalized_expression_available(adata):
            decision.add_guidance(
                "`aucell_r` will score pathway activity from the normalized expression already present in `adata.X`."
            )
        elif _count_like_matrix_available(adata):
            decision.add_guidance(
                "`aucell_r` can still score pathway activity from a count-like matrix by ranking genes within each cell, but grouped summaries are usually most interpretable after preprocessing or clustering."
            )
        else:
            decision.block(
                "`aucell_r` needs either normalized expression in `adata.X` or a usable count-like source."
            )

    if groupby and groupby not in adata.obs.columns:
        candidates = _obs_candidates(adata, "cluster") + _obs_candidates(adata, "cell_type")
        if candidates:
            decision.require_field(
                "groupby",
                f"`--groupby {groupby}` was not found, so grouped AUCell summaries would be skipped. Candidate label columns: {_format_candidates(candidates)}.",
                aliases=["groupby", "cluster_key"],
                flag="--groupby",
            )
        else:
            decision.add_guidance(
                f"`--groupby {groupby}` was not found, so this run would score gene sets per cell without grouped summaries."
            )
    elif not groupby:
        candidates = []
        for family in ("cell_type", "cluster"):
            for column in _obs_candidates(adata, family):
                if column not in candidates:
                    candidates.append(column)
        if candidates:
            decision.add_guidance(
                f"No `--groupby` was provided. This run can still score each cell, and grouped summaries can use one of: {_format_candidates(candidates)}."
            )
        else:
            decision.add_guidance(
                "No label column was provided, so this run will focus on per-cell pathway scores rather than grouped summaries."
            )

    decision.add_guidance(
        "This skill usually comes after `sc-preprocessing`, and often after `sc-clustering` or `sc-cell-annotation` when you want pathway summaries by cluster or cell type."
    )

    return decision


def preflight_sc_enrichment(
    adata: AnnData,
    *,
    method: str,
    engine: str,
    groupby: str | None,
    gene_sets_path: str | None,
    gene_set_db: str | None = None,
    gene_set_from_markers: str | None = None,
    marker_group: str | None = None,
    marker_top_n: str | None = None,
    source_mode: str | None = None,
    source_path: str | None = None,
    ranking_method: str | None = None,
    demo: bool = False,
) -> PreflightDecision:
    decision = PreflightDecision("sc-enrichment")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    if not demo and not gene_sets_path and not gene_set_db and not gene_set_from_markers:
        decision.block(
            "`sc-enrichment` needs a gene-set source. Provide one of: `--gene-sets <local.gmt/json>`, `--gene-set-db <hallmark|kegg|go_bp|...>`, or `--gene-set-from-markers <sc-markers-output>` unless `--demo` is used."
        )

    if gene_set_db and find_spec("gseapy") is None:
        decision.block(
            "`--gene-set-db` needs the optional Python package `gseapy`, which is not installed in the current environment."
        )
    elif gene_set_db:
        decision.add_guidance(
            f"`--gene-set-db {gene_set_db}` will try to resolve a built-in gene-set library automatically. The first run may need network access to populate the local cache."
        )

    if gene_set_from_markers:
        decision.add_guidance(
            "`--gene-set-from-markers` will convert marker genes into one or more custom gene sets for enrichment."
        )
        if marker_group:
            decision.add_guidance(
                f"Only marker group(s) `{marker_group}` will be turned into gene sets."
            )
        else:
            decision.add_guidance(
                "No `--marker-group` was provided, so each marker group in the source table will become its own gene set."
            )
        if marker_top_n:
            decision.add_guidance(
                f"Marker-derived gene sets will keep `marker_top_n={marker_top_n}` per group."
            )

    decision.add_guidance(
        "`sc-enrichment` does statistical term enrichment on marker or DE rankings. If you want per-cell pathway activity scores instead, use `sc-pathway-scoring`."
    )

    r_missing: list[str] = []
    if engine in {"auto", "r"}:
        try:
            from omicsclaw.core.r_dependency_manager import check_r_tier

            _, r_missing = check_r_tier("singlecell-enrichment")
        except Exception:
            r_missing = ["clusterProfiler", "enrichplot"]

    if engine == "r":
        if r_missing:
            decision.block(
                "R enrichment engine needs the singlecell enrichment R stack. "
                f"Missing packages: {', '.join(r_missing)}."
            )
        decision.add_guidance(
            "`--engine r` will use the clusterProfiler / enrichplot stack and can emit richer statistical enrichment figures such as enrichmap and ridgeplot."
        )
    elif engine == "auto":
        if r_missing:
            decision.add_guidance(
                "The R clusterProfiler stack is not fully available, so `engine=auto` would fall back to the Python implementation. "
                f"Missing R packages: {', '.join(r_missing)}."
            )
        else:
            decision.add_guidance(
                "The R clusterProfiler stack is available, so `engine=auto` will prefer the richer clusterProfiler / enrichplot implementation."
            )
        decision.add_guidance(
            "`--engine auto` will prefer the R clusterProfiler path when its packages are installed, and otherwise fall back to the Python implementation."
        )
    else:
        decision.add_guidance(
            "`--engine python` keeps the run fully in Python and does not require the R clusterProfiler stack."
        )

    if source_mode in {"markers_table", "de_table"}:
        decision.add_guidance(
            f"This run will reuse an exported ranking table from `{source_mode}` instead of recomputing markers."
        )
    else:
        if not _normalized_expression_available(adata):
            decision.block(
                "`sc-enrichment` auto-ranking expects normalized expression in `adata.X`. Run `sc-preprocessing` first, or provide an output directory from `sc-markers` / `sc-de`."
            )

        cluster_candidates = []
        for family in ("cluster", "cell_type"):
            for column in _obs_candidates(adata, family):
                if column not in cluster_candidates:
                    cluster_candidates.append(column)

        if groupby:
            if groupby not in adata.obs.columns:
                if cluster_candidates:
                    decision.require_field(
                        "groupby",
                        f"`--groupby {groupby}` was not found. Confirm which cluster/label column should drive automatic ranking: {_format_candidates(cluster_candidates)}.",
                        aliases=["groupby", "cluster_key"],
                        flag="--groupby",
                        choices=cluster_candidates,
                    )
                else:
                    decision.block(
                        "Automatic enrichment from h5ad needs a cluster/cell-type column in `adata.obs`. Run `sc-clustering` first or provide an output directory from `sc-markers` / `sc-de`."
                    )
        elif cluster_candidates:
            decision.add_guidance(
                f"No `--groupby` was provided, so automatic ranking will use `{cluster_candidates[0]}`. Other plausible columns: {_format_candidates(cluster_candidates)}."
            )
        else:
            decision.block(
                "Automatic enrichment from h5ad needs a cluster/cell-type column in `adata.obs`. Run `sc-clustering` first or provide an output directory from `sc-markers` / `sc-de`."
            )

        if source_mode == "auto_cluster_ranking":
            decision.add_guidance(
                f"This run will first compute cluster-vs-rest rankings with `ranking_method={ranking_method or 'wilcoxon'}` and then run `{method}` on those rankings."
            )

    if method == "ora":
        decision.add_guidance(
            "ORA is the right first choice when you already have a thresholded marker or DEG list and want the most enriched terms quickly."
        )
    else:
        decision.add_guidance(
            "GSEA keeps the full ranked gene list, so it is better when subtle coordinated shifts matter more than hard DEG thresholds."
        )
        if source_mode == "markers_table":
            decision.add_guidance(
                "A plain marker table is usually thresholded, so this wrapper may rebuild a fuller ranking from `processed.h5ad` for GSEA."
            )

    decision.add_guidance(
        "Typical workflow: `sc-clustering` or `sc-de` -> `sc-enrichment` -> interpret terms; use `sc-pathway-scoring` only when you want per-cell signature activity."
    )

    return decision


def apply_preflight(
    decision: PreflightDecision,
    logger,
    *,
    demo_mode: bool = False,
    confirmed: bool = False,
) -> None:
    """Emit user-facing guidance and raise on blocking conditions.

    When *demo_mode* is ``True``, confirmation-level blocks (``needs_user_input``)
    are downgraded to guidance so that ``--demo`` runs proceed without interactive
    input.  Hard ``blocked`` status is **not** downgraded because it typically
    indicates genuinely missing data layers or packages.
    """
    if (demo_mode or confirmed) and decision.status == "needs_user_input":
        # Treat user-confirmation prompts as non-blocking guidance once accepted.
        prefix = "demo auto-accepted" if demo_mode else "user confirmed"
        for msg in decision.confirmations:
            decision.guidance.append(f"[{prefix}] {msg}")
        decision.confirmations.clear()
        decision.pending_fields.clear()
        decision.status = "proceed_with_guidance"
    decision.emit(logger)
    decision.raise_if_blocking()
