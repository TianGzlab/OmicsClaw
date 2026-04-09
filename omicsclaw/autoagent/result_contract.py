"""Normalize skill result payloads to the autoagent contract."""

from __future__ import annotations

from typing import Any, Callable


def normalize_result_payload(
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a normalized copy of a result payload when possible."""
    if not isinstance(payload, dict):
        return payload

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return payload

    skill_name = str(payload.get("skill", "")).strip()
    normalizer = _SUMMARY_NORMALIZERS.get(skill_name)
    if normalizer is None:
        return payload

    normalized = dict(payload)
    normalized_summary = dict(summary)
    data = payload.get("data", {})
    normalized["summary"] = normalizer(
        normalized_summary,
        data if isinstance(data, dict) else {},
    )
    return normalized


def _normalize_sc_preprocessing_summary(
    summary: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, Any]:
    """Normalize ``sc-preprocessing`` summary field names."""
    del data  # Reserved for future contract upgrades.

    n_cells_after = _first_int(summary, "n_cells", "n_cells_after", "n_obs")
    n_genes_after = _first_int(summary, "n_genes", "n_genes_after", "n_vars")
    n_cells_before = _first_int(
        summary,
        "n_cells_before",
        "n_cells_before_filter",
        "initial_cells",
    )
    n_genes_before = _first_int(
        summary,
        "n_genes_before",
        "n_genes_before_filter",
        "initial_genes",
    )
    n_hvgs = _first_int(summary, "n_hvgs", "n_hvg")

    _set_default(summary, "n_cells", n_cells_after)
    _set_default(summary, "n_cells_after", n_cells_after)
    _set_default(summary, "n_genes", n_genes_after)
    _set_default(summary, "n_genes_after", n_genes_after)
    _set_default(summary, "n_cells_before", n_cells_before)
    _set_default(summary, "n_cells_before_filter", n_cells_before)
    _set_default(summary, "n_genes_before", n_genes_before)
    _set_default(summary, "n_genes_before_filter", n_genes_before)
    _set_default(summary, "n_hvgs", n_hvgs)
    _set_default(summary, "n_hvg", n_hvgs)

    cell_retention_rate = _first_rate(
        summary,
        rate_keys=("cell_retention_rate",),
        percent_keys=("cells_retained_pct",),
        numerator=n_cells_after,
        denominator=n_cells_before,
    )
    gene_retention_rate = _first_rate(
        summary,
        rate_keys=("gene_retention_rate",),
        percent_keys=("genes_retained_pct",),
        numerator=n_genes_after,
        denominator=n_genes_before,
    )

    _set_default(summary, "cell_retention_rate", cell_retention_rate)
    _set_default(summary, "gene_retention_rate", gene_retention_rate)
    if cell_retention_rate is not None:
        _set_default(summary, "cells_retained_pct", round(cell_retention_rate * 100, 2))
    if gene_retention_rate is not None:
        _set_default(summary, "genes_retained_pct", round(gene_retention_rate * 100, 2))

    return summary


def _first_int(summary: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = summary.get(key)
        if value is None or value == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _first_float(summary: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = summary.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _first_rate(
    summary: dict[str, Any],
    *,
    rate_keys: tuple[str, ...],
    percent_keys: tuple[str, ...],
    numerator: int | None,
    denominator: int | None,
) -> float | None:
    rate = _first_float(summary, *rate_keys)
    if rate is not None:
        return rate

    percent = _first_float(summary, *percent_keys)
    if percent is not None:
        return percent / 100.0

    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _set_default(summary: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    existing = summary.get(key)
    if key not in summary or existing is None or existing == "":
        summary[key] = value


_SUMMARY_NORMALIZERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "sc-preprocessing": _normalize_sc_preprocessing_summary,
}
