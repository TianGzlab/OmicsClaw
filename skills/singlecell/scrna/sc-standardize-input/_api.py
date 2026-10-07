"""Canonical count matrices and single-cell input contracts."""

from __future__ import annotations

import json

from skills.singlecell._lib.adata_utils import canonicalize_singlecell_adata, infer_qc_species

__all__ = ["standardize", "infer_species", "run_info"]
_RUN_KEY = "omicsclaw_sc_standardize_run"


def infer_species(adata) -> str:
    """Infer human or mouse from feature names, defaulting to human.

    :param adata: AnnData whose feature names or gene-symbol metadata are examined.
    :returns: The species hint used by standardize(species="auto").
    """
    return infer_qc_species(adata, default="human")


def standardize(adata, *, species: str = "auto"):
    """Return a canonical copy with count-like X, layers['counts'] and raw.

    Select counts from layers['counts'], aligned raw or X, in that order;
    harmonize feature names and record the matrix and input contracts.

    :param adata: AnnData with at least one count-like expression matrix.
    :param species: 'auto' uses infer_species; 'human' or 'mouse' overrides it.
    :returns: A new AnnData. run_info reports the selected matrix and warnings.
    :raises ValueError: The species is invalid or no count-like matrix is present.
    """
    if species not in {"auto", "human", "mouse"}:
        raise ValueError("species must be auto, human or mouse")
    detected = infer_species(adata)
    species = detected if species == "auto" else species
    result, prepared, contract = canonicalize_singlecell_adata(
        adata, species=species, standardizer_skill="sc-standardize-input",
    )
    result.uns["omicsclaw_matrix_contract"] = {
        "X": "raw_counts", "raw": "raw_counts_snapshot", "layers": {"counts": "raw_counts"},
        "producer_skill": "sc-standardize-input",
    }
    result.uns[_RUN_KEY] = json.dumps({
        "method": "canonical_ann_data", "n_cells": int(result.n_obs), "n_genes": int(result.n_vars),
        "species": species, "species_auto_detected": detected,
        "expression_source": prepared.expression_source, "gene_name_source": prepared.gene_name_source,
        "warnings": prepared.warnings, "counts_layer_present": "counts" in result.layers,
        "input_contract_version": contract.get("version", ""),
    })
    return result


def run_info(adata, *, keep: bool = True) -> dict:
    """Read standardization diagnostics stored as JSON in adata.uns.

    :param adata: The AnnData returned by standardize.
    :param keep: False removes these diagnostics after reading; default True.
    :returns: A dictionary, or an empty dictionary before standardize runs.
    """
    value = adata.uns.get(_RUN_KEY, "{}") if keep else adata.uns.pop(_RUN_KEY, "{}")
    return json.loads(value)
