"""Shared user-facing preflight validation for scRNA skills."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING

from omicsclaw.common.user_guidance import emit_user_guidance, emit_user_guidance_payload

from .adata_utils import (
    build_standardization_recommendation,
    get_input_contract,
    matrix_kind_is_count_like,
    matrix_kind_is_normalized,
    matrix_looks_count_like,
    raw_matrix_kind,
    x_matrix_kind,
)
from . import annotation as sc_annotation_utils

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
    return _declared_x_is_normalized(adata) or _declared_raw_is_normalized(adata)


def _aligned_raw_is_count_like(adata: AnnData) -> bool:
    if adata.raw is None or adata.raw.shape != adata.shape:
        return False
    kind = raw_matrix_kind(adata)
    if kind:
        return matrix_kind_is_count_like(kind)
    return matrix_looks_count_like(adata.raw.X)


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
) -> PreflightDecision:
    decision = PreflightDecision("sc-de")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    if bool(group1) ^ bool(group2):
        decision.require_confirmation("Provide both `--group1` and `--group2`, or omit both for a full ranking run.")

    if method == "deseq2_r":
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
    else:
        if groupby not in adata.obs.columns and not (groupby == "leiden" and "louvain" in adata.obs.columns):
            candidates = _obs_candidates(adata, "cluster") + _obs_candidates(adata, "condition")
            hint = f" Candidate grouping columns: {_format_candidates(candidates)}." if candidates else ""
            decision.require_confirmation(f"`--groupby {groupby}` was not found in `adata.obs`." + hint)

        if method == "mast" and not _normalized_expression_available(adata):
            decision.block(
                "`mast` expects log-normalized expression. Run `sc-preprocessing` first or provide a processed h5ad with normalized expression."
            )

    return decision


def preflight_sc_cell_annotation(
    adata: AnnData,
    *,
    method: str,
    model: str,
    reference: str,
    cluster_key: str,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-cell-annotation")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    if method == "markers":
        if cluster_key not in adata.obs.columns:
            candidates = _obs_candidates(adata, "cluster")
            if candidates:
                decision.add_guidance(
                    f"`--cluster-key {cluster_key}` was not found. Marker mode will auto-cluster unless you prefer an existing column such as {_format_candidates(candidates)}."
                )
            else:
                decision.add_guidance(
                    "Marker mode will auto-cluster because no existing cluster column was found. If you already have trusted labels, pass them via `--cluster-key` instead."
                )
        return decision

    use_raw = _declared_raw_is_normalized(adata)
    if not use_raw and not _declared_x_is_normalized(adata):
        if method == "celltypist":
            decision.require_confirmation(
                "`celltypist` currently sees count-like expression and would likely fall back to marker annotation. Run `sc-preprocessing` first or confirm that fallback is acceptable."
            )
        elif method == "popv":
            decision.add_guidance(
                "`popv` works best on log-normalized query expression aligned to a labeled reference. If matrix scale is uncertain, run `sc-preprocessing` first."
            )
        else:
            decision.block(
                f"`{method}` expects log-normalized expression. Run `sc-preprocessing` first or provide a processed h5ad with normalized expression."
            )

    if method == "celltypist":
        if model == "Immune_All_Low":
            decision.require_field(
                "model",
                "Confirm the CellTypist model via `--model`; the current default `Immune_All_Low` is not appropriate for every tissue.",
                aliases=["model", "celltypist_model"],
            )
        else:
            valid_input, reason = sc_annotation_utils.validate_celltypist_input_matrix(
                sc_annotation_utils.build_celltypist_input_adata(adata)[0]
            )
            if not valid_input:
                decision.block(reason)
        return decision

    if method == "popv":
        ref_path = Path(reference)
        if reference == "HPCA":
            decision.require_field(
                "reference",
                "`popv` expects `--reference` to be a labeled H5AD path; the default `HPCA` atlas keyword is not valid for this wrapper path.",
                aliases=["reference", "ref"],
            )
        elif not ref_path.exists():
            decision.block(
                f"`popv` reference file was not found at {reference}. Provide a labeled H5AD reference via `--reference`."
            )
        return decision

    if method in {"singler", "scmap"} and reference == "HPCA":
        decision.require_field(
            "reference",
            f"Confirm the reference atlas via `--reference`; the current default `HPCA` should not be used blindly for `{method}`.",
            aliases=["reference", "ref"],
        )
    return decision


def preflight_sc_cell_communication(
    adata: AnnData,
    *,
    method: str,
    cell_type_key: str,
    species: str,
    counts_data: str | None = None,
    condition_key: str | None = None,
    condition_oi: str | None = None,
    condition_ref: str | None = None,
    receiver: str | None = None,
    senders: list[str] | None = None,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-cell-communication")
    _add_standardization_guidance(decision, adata, source_path=source_path)

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

    if method == "cellphonedb" and species != "human":
        decision.block("The current CellPhoneDB wrapper only supports `--species human`.")

    if method == "cellphonedb" and (counts_data or "hgnc_symbol") == "hgnc_symbol":
        decision.require_field(
            "cellphonedb_counts_data",
            "Confirm that your gene identifiers are HGNC symbols before using the default `--cellphonedb-counts-data hgnc_symbol`.",
            choices=["hgnc_symbol", "ensembl", "gene_name"],
            aliases=["cellphonedb_counts_data", "counts_data"],
        )

    if method == "cellchat_r" and not _normalized_expression_available(adata):
        decision.require_confirmation(
            "`cellchat_r` expects log-normalized expression; the current `adata.X` still looks count-like. Run `sc-preprocessing` first or confirm the matrix state."
        )

    if method == "nichenet_r":
        if species != "human":
            decision.block("The current NicheNet wrapper only supports `--species human`.")
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

    return decision


def preflight_sc_batch_integration(
    adata: AnnData,
    *,
    method: str,
    batch_key: str,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-batch-integration")
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
        if not labels:
            decision.require_field(
                "method",
                "`scanvi` needs existing labels such as `cell_type`, `leiden`, or `louvain`; otherwise choose `scvi` instead.",
                choices=["scanvi", "scvi"],
                aliases=["method"],
            )
        elif len(labels) > 1:
            decision.add_guidance(
                f"`scanvi` will prefer `{labels[0]}` as labels because the wrapper does not currently expose a `labels_key` parameter."
            )

    return decision


def preflight_sc_doublet_detection(
    adata: AnnData,
    *,
    method: str,
    expected_doublet_rate: float,
    threshold: float | None = None,
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

    if "counts" not in adata.layers:
        if _declared_x_is_count_like(adata):
            decision.add_guidance(
                "No explicit `layers['counts']` was found; doublet detection will use count-like `adata.X`."
            )
        else:
            decision.block(
                "Doublet detection requires raw count-like input in `layers['counts']` or count-like `adata.X`."
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
    root_cluster: str | None,
    root_cell: int | None,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-pseudotime")
    _add_standardization_guidance(decision, adata, source_path=source_path)

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

    if method == "palantir":
        decision.add_guidance(
            "`palantir` is available here, but it is heavier than DPT and should be chosen deliberately when users want waypoint-based pseudotime."
        )
        if find_spec("palantir") is None:
            decision.block("`palantir` was requested but the Python package `palantir` is not installed in the current environment.")
    if method == "via":
        decision.add_guidance(
            "`via` is intended for graph-based trajectory inference with automatic terminal-state discovery; keep the root choice explicit and do not present it as a generic replacement for every pseudotime workflow."
        )
        if find_spec("pyVIA") is None:
            decision.block("`via` was requested but the Python package `pyVIA` is not installed in the current environment.")
    if method == "cellrank":
        decision.add_guidance(
            "`cellrank` is intended for macrostate and fate-probability inference on top of a transition kernel; use it when users explicitly want terminal states or lineage probabilities."
        )
        if find_spec("cellrank") is None:
            decision.block("`cellrank` was requested but the Python package `cellrank` is not installed in the current environment.")

    if "neighbors" not in adata.uns:
        decision.add_guidance(
            "Neighbor graph is missing; `sc-pseudotime` will compute it automatically, but results are more stable after `sc-preprocessing`."
        )

    return decision


def preflight_sc_preprocessing(
    adata: AnnData,
    *,
    method: str,
    min_genes: int | None = None,
    max_mt_pct: float | None = None,
    min_cells: int | None = None,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-preprocessing")

    has_qc_metrics = {"n_genes_by_counts", "total_counts", "pct_counts_mt"}.issubset(set(adata.obs.columns))
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

    if "predicted_doublet" not in adata.obs.columns and "doublet_score" not in adata.obs.columns:
        decision.add_guidance(
            "`sc-preprocessing` does not remove doublets automatically. If doublets are a concern, consider `sc-doublet-detection` before downstream interpretation."
        )

    batch_candidates = _obs_candidates(adata, "batch")
    if batch_candidates:
        decision.add_guidance(
            f"Potential batch/sample columns were detected: {_format_candidates(batch_candidates)}. If batch effects are expected, plan `sc-batch-integration` after preprocessing."
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

    return decision


def preflight_sc_markers(
    adata: AnnData,
    *,
    groupby: str,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-markers")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    if groupby not in adata.obs.columns:
        candidates = _obs_candidates(adata, "cluster") + _obs_candidates(adata, "cell_type")
        if candidates:
            decision.require_field(
                "groupby",
                f"`--groupby {groupby}` was not found. Confirm which grouping column to use: {_format_candidates(candidates)}.",
                aliases=["groupby", "cluster_key"],
            )
        else:
            decision.block(
                "Marker detection requires an existing grouping column in `adata.obs` such as `leiden` or `cell_type`."
            )

    if _declared_raw_is_normalized(adata):
        decision.add_guidance(
            "`sc-markers` will prefer `adata.raw` over `adata.X` when available. Make sure that is the expression state you want for marker ranking."
        )
    elif not _declared_x_is_normalized(adata):
        decision.require_confirmation(
            "Marker detection expects normalized expression, but this object currently looks count-like. Run `sc-preprocessing` first or confirm that you want to continue anyway."
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


def preflight_sc_enrichment(
    adata: AnnData,
    *,
    gene_sets_path: str | None,
    groupby: str | None,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision("sc-enrichment")
    _add_standardization_guidance(decision, adata, source_path=source_path)

    if not gene_sets_path:
        decision.block("`sc-enrichment` requires `--gene-sets` unless `--demo` is used.")

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

    return decision


def apply_preflight(decision: PreflightDecision, logger) -> None:
    """Emit user-facing guidance and raise on blocking conditions."""
    decision.emit(logger)
    decision.raise_if_blocking()
