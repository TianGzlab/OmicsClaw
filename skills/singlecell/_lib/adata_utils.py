"""AnnData utilities for single-cell analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

import scanpy as sc

if TYPE_CHECKING:
    from anndata import AnnData

from .exceptions import PreprocessingRequiredError

logger = logging.getLogger(__name__)
INPUT_CONTRACT_KEY = "omicsclaw_input_contract"
INPUT_CONTRACT_VERSION = "1.0"

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


def ensure_input_contract(
    adata: AnnData,
    *,
    source_path: str | None = None,
    standardized: bool | None = None,
) -> dict[str, Any]:
    """Ensure ``adata.uns`` contains a basic single-cell input contract block."""
    contract = get_input_contract(adata).copy()
    contract.setdefault("version", INPUT_CONTRACT_VERSION)
    contract.setdefault("domain", "singlecell")
    contract.setdefault("standardized", False)
    contract.setdefault("counts_layer", "counts" if "counts" in adata.layers else None)
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
    """Persist the canonical OmicsClaw single-cell input contract."""
    contract = ensure_input_contract(adata, standardized=True)
    contract.update(
        {
            "standardized": True,
            "standardized_by": standardizer_skill,
            "standardized_at": datetime.now(timezone.utc).isoformat(),
            "expression_source": expression_source,
            "gene_name_source": gene_name_source,
            "counts_layer": "counts" if "counts" in adata.layers else contract.get("counts_layer"),
            "x_count_like": matrix_looks_count_like(adata.X),
            "obs_names_unique": bool(adata.obs_names.is_unique),
            "var_names_unique": bool(adata.var_names.is_unique),
            "warnings": list(warnings or []),
        }
    )
    adata.uns[INPUT_CONTRACT_KEY] = contract
    return contract


def build_standardization_recommendation(
    *,
    source_path: str | None = None,
    skill_name: str | None = None,
) -> str:
    """Build a user-facing recommendation to run the standardization skill first."""
    prefix = f"`{skill_name}` detected" if skill_name else "This single-cell workflow detected"
    input_arg = str(source_path) if source_path else "<input.h5ad>"
    return (
        f"{prefix} input that has not been standardized by `sc-standardize-input`; "
        f"for more stable cross-skill behavior, run `oc run sc-standardize-input --input {input_arg} --output <dir>` first."
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
