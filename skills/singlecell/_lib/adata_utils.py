"""AnnData utilities for single-cell analysis."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

import scanpy as sc

if TYPE_CHECKING:
    from anndata import AnnData

from .exceptions import PreprocessingRequiredError

logger = logging.getLogger(__name__)
INPUT_CONTRACT_KEY = "omicsclaw_input_contract"
INPUT_CONTRACT_VERSION = "1.0"
MATRIX_CONTRACT_KEY = "omicsclaw_matrix_contract"

GENE_SYMBOL_CANDIDATE_COLUMNS = (
    "gene_symbols",
    "gene_symbol",
    "symbol",
    "gene_name",
    "feature_name",
    "feature_names",
    "genes",
    "gene",
)


@dataclass
class CountLikePreparationResult:
    """Prepared count-like AnnData plus diagnostics about how it was built."""

    adata: AnnData
    expression_source: str
    gene_name_source: str
    warnings: list[str]


def select_count_like_expression_source(
    adata: AnnData,
    *,
    preferred_layer: str = "counts",
) -> tuple[Any, str, list[str]]:
    """Select the best available raw-count-like matrix source.

    Preference order:
    1. ``adata.layers[preferred_layer]`` when present and count-like
    2. ``adata.raw`` when aligned to ``adata.shape`` and count-like
    3. ``adata.X`` when count-like
    """
    warnings: list[str] = []

    if preferred_layer in adata.layers and matrix_looks_count_like(adata.layers[preferred_layer]):
        expression_source = f"layers.{preferred_layer}"
        if not matrix_looks_count_like(adata.X):
            warnings.append(
                f"`adata.X` does not look count-like; falling back to `{expression_source}`."
            )
        return adata.layers[preferred_layer], expression_source, warnings

    if adata.raw is not None and adata.raw.shape == adata.shape and matrix_looks_count_like(adata.raw.X):
        warnings.append(
            "`adata.X` does not look count-like or no counts layer was available; falling back to `adata.raw`."
        )
        return adata.raw.X, "adata.raw", warnings

    if matrix_looks_count_like(adata.X):
        return adata.X, "adata.X", warnings

    raise ValueError(
        "This workflow requires a raw count-like matrix. Provide `adata.layers['counts']`, aligned `adata.raw`, or count-like `adata.X`."
    )


def get_input_contract(adata: AnnData) -> dict[str, Any]:
    """Return the standardized input-contract block from ``adata.uns`` if present."""
    contract = adata.uns.get(INPUT_CONTRACT_KEY, {})
    return contract if isinstance(contract, dict) else {}


def get_matrix_contract(adata: AnnData) -> dict[str, Any]:
    """Return the matrix-semantics contract from ``adata.uns`` when present."""
    contract = adata.uns.get(MATRIX_CONTRACT_KEY, {})
    return contract if isinstance(contract, dict) else {}


def record_matrix_contract(
    adata: AnnData,
    *,
    x_kind: str,
    raw_kind: str | None = None,
    layers: dict[str, str | None] | None = None,
    producer_skill: str | None = None,
    preprocess_method: str | None = None,
    primary_cluster_key: str | None = None,
) -> dict[str, Any]:
    """Persist explicit matrix semantics for downstream skill routing."""
    contract = {
        "X": x_kind,
        "raw": raw_kind,
        "layers": dict(layers or {}),
    }
    if producer_skill:
        contract["producer_skill"] = str(producer_skill)
    if preprocess_method:
        contract["preprocess_method"] = str(preprocess_method)
    if primary_cluster_key:
        contract["primary_cluster_key"] = str(primary_cluster_key)
    adata.uns[MATRIX_CONTRACT_KEY] = contract
    return contract


def matrix_kind_is_count_like(kind: str | None) -> bool:
    """Return True when a contract label represents raw/count-like expression."""
    return str(kind or "").lower() in {"raw_counts", "count_like", "count_like_expression", "raw_counts_snapshot"}


def matrix_kind_is_normalized(kind: str | None) -> bool:
    """Return True when a contract label represents normalized/transformed expression."""
    return str(kind or "").lower() in {
        "normalized_expression",
        "log1p_normalized_expression",
        "scaled_expression",
    }


def x_matrix_kind(adata: AnnData) -> str | None:
    """Return the declared semantic role of ``adata.X`` when available."""
    return get_matrix_contract(adata).get("X")


def raw_matrix_kind(adata: AnnData) -> str | None:
    """Return the declared semantic role of ``adata.raw`` when available."""
    return get_matrix_contract(adata).get("raw")


def infer_x_matrix_kind(adata: AnnData, *, fallback: str = "normalized_expression") -> str:
    """Infer the semantic role of ``adata.X`` when no explicit contract exists."""
    declared = x_matrix_kind(adata)
    if declared in {"raw_counts", "normalized_expression"}:
        return declared
    return "raw_counts" if matrix_looks_count_like(adata.X) else fallback


def ensure_input_contract(
    adata: AnnData,
    *,
    source_path: str | None = None,
    standardized: bool | None = None,
) -> dict[str, Any]:
    """Ensure ``adata.uns`` contains a minimal single-cell input contract block."""
    contract = get_input_contract(adata).copy()
    contract.setdefault("version", INPUT_CONTRACT_VERSION)
    contract.setdefault("domain", "singlecell")
    contract.setdefault("standardized", False)
    if source_path:
        contract.setdefault("source_path", str(source_path))
    if standardized is not None:
        contract["standardized"] = bool(standardized)
    adata.uns[INPUT_CONTRACT_KEY] = contract
    return contract


def record_standardized_input_contract(
    adata: AnnData,
    *,
    expression_source: str,
    gene_name_source: str,
    warnings: list[str] | None = None,
    standardizer_skill: str = "sc-standardize-input",
) -> dict[str, Any]:
    """Persist a minimal canonical OmicsClaw single-cell input contract."""
    contract = ensure_input_contract(adata, standardized=True)
    contract.update(
        {
            "standardized": True,
            "standardized_by": standardizer_skill,
            "standardized_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    adata.uns[INPUT_CONTRACT_KEY] = contract
    return contract


def propagate_singlecell_contracts(
    source: AnnData,
    target: AnnData,
    *,
    producer_skill: str,
    x_kind: str | None = None,
    raw_kind: str | None = None,
    preprocess_method: str | None = None,
    primary_cluster_key: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Copy minimal single-cell contracts onto a downstream output object."""
    source_input = get_input_contract(source)
    ensure_input_contract(
        target,
        source_path=source_input.get("source_path"),
        standardized=bool(source_input.get("standardized", False)),
    )

    source_matrix = get_matrix_contract(source)
    layers = dict(source_matrix.get("layers") or {})
    if "counts" in target.layers:
        layers["counts"] = "raw_counts"

    resolved_x_kind = x_kind or source_matrix.get("X") or infer_x_matrix_kind(target)
    resolved_raw_kind = raw_kind
    if resolved_raw_kind is None and target.raw is not None:
        resolved_raw_kind = source_matrix.get("raw") or "raw_counts_snapshot"

    matrix_contract = record_matrix_contract(
        target,
        x_kind=resolved_x_kind,
        raw_kind=resolved_raw_kind,
        layers=layers,
        producer_skill=producer_skill,
        preprocess_method=preprocess_method,
        primary_cluster_key=primary_cluster_key,
    )
    return get_input_contract(target), matrix_contract


def build_standardization_recommendation(
    *,
    source_path: str | None = None,
    skill_name: str | None = None,
) -> str:
    """Build a user-facing note about auto-canonicalization and the optional wrapper skill."""
    prefix = f"`{skill_name}` detected" if skill_name else "This single-cell workflow detected"
    input_arg = str(source_path) if source_path else "<input.h5ad>"
    return (
        f"{prefix} input that has not yet been canonicalized under the OmicsClaw scRNA contract. "
        f"Compatible workflows will auto-prepare it when possible; run `oc run sc-standardize-input --input {input_arg} --output <dir>` only if you want to inspect or export the canonical object explicitly."
    )


def _matrix_preview(matrix: Any, *, max_obs: int = 200, max_vars: int = 200) -> np.ndarray:
    """Return a small dense preview for heuristic validation."""
    preview = matrix[: min(max_obs, matrix.shape[0]), : min(max_vars, matrix.shape[1])]
    if hasattr(preview, "toarray"):
        preview = preview.toarray()
    return np.asarray(preview)


def matrix_looks_count_like(matrix: Any) -> bool:
    """Heuristically detect whether a matrix still looks like raw counts."""
    sample = _matrix_preview(matrix)
    if sample.size == 0:
        return True
    if not np.all(np.isfinite(sample)):
        return False
    if np.nanmin(sample) < 0:
        return False

    frac_integer = float(np.mean(np.isclose(sample, np.round(sample), atol=1e-6)))
    return frac_integer > 0.98


def _species_prefix_match_counts(names: pd.Index, species: str) -> dict[str, int]:
    """Count mitochondrial / ribosomal prefix matches for a gene-name index."""
    normalized = pd.Index([str(value) for value in names], dtype="object")
    species = str(species).lower()
    if species == "human":
        mt_count = int(normalized.str.startswith("MT-").sum())
        ribo_count = int(normalized.str.match(r"^RP[SL]").sum())
    elif species == "mouse":
        mt_count = int(normalized.str.startswith("mt-").sum())
        ribo_count = int(normalized.str.match(r"^Rp[sl]").sum())
    else:
        mt_count = 0
        ribo_count = 0
    return {"mt": mt_count, "ribo": ribo_count}


def infer_qc_species(adata: AnnData, *, default: str = "human") -> str:
    """Infer whether QC prefix matching is more consistent with human or mouse."""
    names = pd.Index([str(value) for value in adata.var_names], dtype="object")
    human_score = _species_prefix_match_counts(names, "human")
    mouse_score = _species_prefix_match_counts(names, "mouse")
    human_total = human_score["mt"] + human_score["ribo"]
    mouse_total = mouse_score["mt"] + mouse_score["ribo"]
    if mouse_total > human_total:
        return "mouse"
    if human_total > 0:
        return "human"
    return default


def _best_qc_gene_name_index(adata: AnnData, *, species: str) -> tuple[pd.Index, str, list[str]]:
    """Choose the most informative gene identifiers for QC prefix matching."""
    warnings: list[str] = []
    current = pd.Index([str(value) for value in adata.var_names], dtype="object")
    best_names = current
    best_source = "var_names"
    best_score = _species_prefix_match_counts(current, species)

    for column in GENE_SYMBOL_CANDIDATE_COLUMNS:
        if column not in adata.var.columns:
            continue
        values = adata.var[column]
        if values.isna().all():
            continue
        normalized = pd.Index(values.fillna("").astype(str), dtype="object")
        score = _species_prefix_match_counts(normalized, species)
        if (score["mt"] + score["ribo"]) > (best_score["mt"] + best_score["ribo"]):
            best_names = normalized
            best_source = f"var.{column}"
            best_score = score

    if best_source != "var_names":
        warnings.append(
            f"Detected better QC gene identifiers in `{best_source}`; using them instead of `var_names` for MT/ribosomal tagging."
        )

    if best_score["mt"] == 0:
        warnings.append(
            "No mitochondrial genes matched the selected species prefix convention; `pct_counts_mt` may be unavailable or underestimated."
        )
    if best_score["ribo"] == 0:
        warnings.append(
            "No ribosomal genes matched the selected species prefix convention; `pct_counts_ribo` may be unavailable or underestimated."
        )

    return best_names, best_source, warnings


def prepare_count_like_adata(
    adata: AnnData,
    *,
    species: str,
    preferred_layer: str = "counts",
) -> CountLikePreparationResult:
    """Build a QC-ready AnnData from the best available count-like source.

    Preference order:
    1. ``adata.layers[preferred_layer]`` when present and count-like
    2. ``adata.raw`` when aligned to ``adata.shape`` and count-like
    3. ``adata.X`` when count-like

    Raises
    ------
    ValueError
        If no count-like matrix can be found.
    """
    matrix, expression_source, source_warnings = select_count_like_expression_source(
        adata,
        preferred_layer=preferred_layer,
    )
    prepared = adata.copy()
    prepared.X = matrix.copy()
    source_warnings = [
        f"{warning.rstrip('.')} for QC metric calculation."
        for warning in source_warnings
    ]

    prepared.var_names = pd.Index([str(value) for value in prepared.var_names], dtype="object")
    best_names, gene_name_source, gene_warnings = _best_qc_gene_name_index(prepared, species=species)
    prepared.var["_omicsclaw_qc_gene_name"] = best_names.astype(str)
    if gene_name_source != "var_names":
        prepared.var["_omicsclaw_original_var_names"] = prepared.var_names.astype(str)
        prepared.var_names = pd.Index(best_names.astype(str), dtype="object")

    if not prepared.var_names.is_unique:
        prepared.var_names_make_unique()
        source_warnings.append(
            "Gene identifiers used for QC were not unique; unique suffixes were added temporarily for stable processing."
        )

    return CountLikePreparationResult(
        adata=prepared,
        expression_source=expression_source,
        gene_name_source=gene_name_source,
        warnings=source_warnings + gene_warnings,
    )




def canonicalize_singlecell_adata(
    adata: AnnData,
    *,
    species: str,
    preferred_layer: str = "counts",
    standardizer_skill: str = "sc-standardize-input",
) -> tuple[AnnData, CountLikePreparationResult, dict[str, Any]]:
    """Return a canonical count-like AnnData plus preparation diagnostics.

    The returned object is safe for downstream OmicsClaw scRNA skills: ``X`` is
    count-like, ``layers['counts']`` is populated, gene identifiers are made
    stable, and the input contract records how the canonical object was built.
    """
    prepared = prepare_count_like_adata(
        adata,
        species=species,
        preferred_layer=preferred_layer,
    )
    standardized = prepared.adata

    standardized.obs_names = standardized.obs_names.astype(str)
    standardized.var_names = standardized.var_names.astype(str)
    standardized.obs_names_make_unique()
    standardized.var_names_make_unique()

    if (
        "gene_symbols" not in standardized.var.columns
        or standardized.var["gene_symbols"].astype(str).eq("").all()
    ):
        standardized.var["gene_symbols"] = standardized.var_names.astype(str)

    if "_omicsclaw_original_var_names" in standardized.var.columns and "feature_id" not in standardized.var.columns:
        standardized.var["feature_id"] = standardized.var["_omicsclaw_original_var_names"].astype(str)

    standardized.layers[preferred_layer] = standardized.X.copy()
    standardized.raw = standardized.copy()
    record_matrix_contract(
        standardized,
        x_kind="raw_counts",
        raw_kind="raw_counts_snapshot",
        layers={preferred_layer: "raw_counts"},
        producer_skill=standardizer_skill,
    )
    contract = record_standardized_input_contract(
        standardized,
        expression_source=prepared.expression_source,
        gene_name_source=prepared.gene_name_source,
        warnings=prepared.warnings,
        standardizer_skill=standardizer_skill,
    )
    return standardized, prepared, contract

def require_preprocessed(adata: AnnData) -> None:
    """Require PCA to be computed."""
    if "X_pca" not in adata.obsm:
        raise PreprocessingRequiredError(
            "PCA not found. Run sc-preprocess first:\n"
            "  python omicsclaw.py run sc-preprocess --input data.h5ad --output results/"
        )


def ensure_pca(adata: AnnData, n_comps: int = 50) -> None:
    """Compute PCA if missing."""
    if "X_pca" not in adata.obsm:
        logger.info("Computing PCA (%d components)", n_comps)
        sc.tl.pca(adata, n_comps=min(n_comps, adata.n_vars - 1))


def ensure_neighbors(adata: AnnData, n_neighbors: int = 15, n_pcs: int = 50) -> None:
    """Compute neighbors if missing."""
    if "neighbors" not in adata.uns:
        ensure_pca(adata, n_comps=n_pcs)
        logger.info("Computing neighbors (n=%d, pcs=%d)", n_neighbors, n_pcs)
        sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=min(n_pcs, adata.obsm["X_pca"].shape[1]))


def store_analysis_metadata(adata: AnnData, skill_name: str, method: str, params: dict) -> None:
    """Store analysis metadata in adata.uns."""
    record = {
        "method": str(method),
        "params": params or {},
    }

    analyses = adata.uns.get("omicsclaw_analyses")
    if not isinstance(analyses, dict):
        analyses = {}
        adata.uns["omicsclaw_analyses"] = analyses

    analyses[str(skill_name)] = record
    adata.uns[f"omicsclaw_{skill_name}"] = record
