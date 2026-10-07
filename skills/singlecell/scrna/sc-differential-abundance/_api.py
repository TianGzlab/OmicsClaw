"""Sample composition and differential abundance without output directories."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import tempfile
import logging

import pandas as pd
import scanpy as sc
from anndata import AnnData

from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR
from skills.singlecell._lib.differential_abundance import (
    build_composition_summary, run_simple_da, _load_pertpy_milo_class,
    _run_internal_milo_like_da, _run_sccoda_da_direct, _resolve_condition_groups,
)

__all__ = ['composition', 'condition_proportions', 'test_abundance', 'proportion_figure', 'run_info']
R_SCRIPTS_DIR = _SDK_R_SCRIPTS_DIR
_RUN_KEY = 'omicsclaw_sc_differential_abundance_run'
logger = logging.getLogger(__name__)


def _validate_metadata(adata, sample_key, condition_key, celltype_key):
    for key in (sample_key, condition_key, celltype_key):
        if key not in adata.obs:
            raise ValueError(f'Missing obs column: {key}')
        if adata.obs[key].isna().any():
            raise ValueError(f'Missing values in obs column: {key}')
    if (adata.obs.groupby(sample_key, observed=True)[condition_key].nunique() != 1).any():
        raise ValueError('Each sample must belong to exactly one condition')


def composition(adata, *, sample_key: str, celltype_key: str, condition_key: str):
    """Return sample-by-cell-type counts and row-normalized proportions.

    Each sample must belong to one condition. No cells or counts are changed.
    """
    _validate_metadata(adata, sample_key, condition_key, celltype_key)
    counts, proportions, _ = build_composition_summary(adata, sample_key=sample_key,
        celltype_key=celltype_key, condition_key=condition_key)
    return counts, proportions


def condition_proportions(adata, *, sample_key: str, celltype_key: str, condition_key: str) -> pd.DataFrame:
    """Return condition means of per-sample proportions, weighting samples equally."""
    _validate_metadata(adata, sample_key, condition_key, celltype_key)
    return build_composition_summary(adata, sample_key=sample_key,
        celltype_key=celltype_key, condition_key=condition_key)[2]


def _proportion_test(adata, condition_key, celltype_key, contrast, n_permutations):
    from skills._sdk.r_script_runner import RScriptRunner
    with tempfile.TemporaryDirectory(prefix='omicsclaw_proportion_') as folder:
        folder = Path(folder)
        meta = adata.obs[[celltype_key, condition_key]].copy().reset_index()
        meta.columns = ['cell_id', celltype_key, condition_key]
        path = folder / 'cell_meta.csv'
        meta.to_csv(path, index=False)
        RScriptRunner(timeout=300).run_script(R_SCRIPTS_DIR / 'sc_proportion_test_r.R',
            args=[str(path), str(folder), celltype_key, condition_key,
                  contrast or 'auto', str(n_permutations)],
            expected_outputs=['proportion_test_results.csv'], output_dir=folder)
        return pd.read_csv(folder / 'proportion_test_results.csv')


def test_abundance(adata, *, method: str = 'milo', sample_key: str = 'sample',
                   condition_key: str = 'condition', celltype_key: str = 'cell_type',
                   contrast: str | None = None, reference_cell_type: str = 'automatic',
                   fdr: float = 0.05, prop: float = 0.1, n_neighbors: int = 30,
                   n_permutations: int = 1000, random_state: int = 0) -> pd.DataFrame:
    """Return differential-abundance results without changing adata.

    simple tests sample proportions with two-sided Mann-Whitney and BH.
    milo uses pertpy, or the existing milo_like neighborhood screen when its
    import fails; run_info names the executed backend and reason. scCODA uses
    pertpy or the installed standalone sccoda backend. random_state controls
    pertpy and newly computed neighbors; standalone sccoda retains its sampler
    defaults. proportion_test_r uses the existing fixed R seed 42 and permutes
    cells, ignoring sample identity; its failures propagate instead of returning
    an empty success result. This function does not apply a minimum-count filter.
    """
    if method not in ('simple', 'milo', 'sccoda', 'proportion_test_r'):
        raise ValueError('Unknown differential-abundance method: ' + method)
    _validate_metadata(adata, sample_key, condition_key, celltype_key)
    work = adata.copy()
    kwargs = dict(sample_key=sample_key, condition_key=condition_key, celltype_key=celltype_key)
    backend, reason = method, ''
    if method == 'simple':
        table = run_simple_da(work, **kwargs, contrast=contrast, fdr=fdr)
    elif method == 'milo':
        result, table = run_milo_da(work, **kwargs, prop=prop, n_neighbors=n_neighbors,
            contrast=contrast, random_state=random_state)
        metadata = result if isinstance(result, dict) else result.uns
        backend = metadata.get('backend', 'milo')
        reason = metadata.get('fallback_reason', '')
    elif method == 'sccoda':
        result, table = run_sccoda_da(work, **kwargs, reference_cell_type=reference_cell_type,
            fdr=fdr, random_state=random_state)
        backend = result.uns.get('backend', 'sccoda')
        if backend == 'sccoda_direct':
            reason = 'pertpy unavailable; standalone sccoda used'
    else:
        table = _proportion_test(work, condition_key, celltype_key, contrast, n_permutations)
        backend = 'base_R'
    table.attrs[_RUN_KEY] = dict(requested_method=method, executed_method=backend,
        fallback_used=bool(reason), fallback_reason=reason, random_state=random_state,
        effective_random_state=42 if method == 'proportion_test_r' else
            (None if backend == 'sccoda_direct' else random_state))
    return table


def proportion_figure(proportions: pd.DataFrame):
    """Return a sample-by-cell-type proportion heatmap without writing files."""
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    image = ax.imshow(proportions.to_numpy(), aspect='auto', cmap='viridis')
    ax.set_xticks(range(len(proportions.columns)), proportions.columns, rotation=45)
    ax.set_yticks(range(len(proportions.index)), proportions.index)
    fig.colorbar(image, ax=ax, label='Proportion')
    fig.tight_layout()
    return fig


def run_info(table: pd.DataFrame) -> dict:
    """Return the requested method, executed backend, fallback reason and seed."""
    return deepcopy(table.attrs[_RUN_KEY])

def run_milo_da(
    adata: AnnData,
    *,
    sample_key: str,
    condition_key: str,
    celltype_key: str,
    prop: float = 0.1,
    n_neighbors: int = 30,
    contrast: str | None = None,
    random_state: int = 0,
) -> tuple[Any, pd.DataFrame]:
    """Run Milo differential abundance via the official pertpy implementation."""
    if sample_key not in adata.obs:
        raise ValueError(f"Missing sample key: {sample_key}")
    if condition_key not in adata.obs:
        raise ValueError(f"Missing condition key: {condition_key}")
    if celltype_key not in adata.obs:
        raise ValueError(f"Missing cell type key: {celltype_key}")
    if "neighbors" not in adata.uns:
        sc.pp.neighbors(adata, n_neighbors=n_neighbors, random_state=random_state)
    if "X_umap" not in adata.obsm:
        sc.tl.umap(adata, random_state=random_state)

    try:
        Milo = _load_pertpy_milo_class()
    except Exception as exc:  # pragma: no cover - exercised via smoke tests instead
        logger.warning("Falling back to internal Milo-like neighborhood DA because official Milo import failed: %s", exc)
        result, table = _run_internal_milo_like_da(
            adata,
            sample_key=sample_key,
            condition_key=condition_key,
            celltype_key=celltype_key,
            prop=prop,
            n_neighbors=n_neighbors,
            contrast=contrast,
        )
        result['fallback_reason'] = f'pertpy Milo unavailable: {exc}'
        return result, table

    working = adata.copy()
    if contrast:
        group_a, group_b = _resolve_condition_groups(
            working.obs[[sample_key, condition_key]].drop_duplicates().set_index(sample_key),
            condition_key,
            contrast,
        )
        keep_conditions = {group_a, group_b}
        working = working[working.obs[condition_key].astype(str).isin(keep_conditions)].copy()
        if "neighbors" not in working.uns:
            sc.pp.neighbors(working, n_neighbors=n_neighbors, random_state=random_state)
        if "X_umap" not in working.obsm:
            sc.tl.umap(working, random_state=random_state)
        working.obs[condition_key] = pd.Categorical(working.obs[condition_key].astype(str), categories=[group_a, group_b])
    else:
        working.obs[condition_key] = pd.Categorical(working.obs[condition_key].astype(str))

    milo = Milo()
    mdata = milo.load(working)
    milo.make_nhoods(mdata["rna"], prop=prop, seed=random_state)
    mdata = milo.count_nhoods(mdata, sample_col=sample_key)
    milo.add_covariate_to_nhoods_var(mdata, [condition_key], feature_key="rna")
    milo.da_nhoods(mdata, design=f"~ {condition_key}", solver="pydeseq2")
    milo.annotate_nhoods(mdata, anno_col=celltype_key)
    milo.build_nhood_graph(mdata)
    nhood = mdata["milo"].var.copy()
    nhood.index.name = "nhood"
    if hasattr(mdata["milo"], "uns"):
        mdata["milo"].uns["backend"] = "milo"
        mdata["milo"].uns["solver"] = "pydeseq2"
    if hasattr(mdata, "uns"):
        mdata.uns["backend"] = "milo"
        mdata.uns["solver"] = "pydeseq2"
    return mdata, nhood.reset_index()


def run_sccoda_da(
    adata: AnnData,
    *,
    sample_key: str,
    condition_key: str,
    celltype_key: str,
    reference_cell_type: str = "automatic",
    fdr: float = 0.05,
    random_state: int = 0,
) -> tuple[Any, pd.DataFrame]:
    """Run scCODA through pertpy when available."""

    try:
        import pertpy as pt
    except ImportError:
        return _run_sccoda_da_direct(
            adata,
            sample_key=sample_key,
            condition_key=condition_key,
            celltype_key=celltype_key,
            reference_cell_type=reference_cell_type,
        )

    model = pt.tl.Sccoda()
    mdata = model.load(
        adata,
        type="cell_level",
        generate_sample_level=True,
        cell_type_identifier=celltype_key,
        sample_identifier=sample_key,
        covariate_obs=[condition_key],
    )
    modality_key = "coda"
    model.prepare(mdata, modality_key=modality_key, formula=condition_key, reference_cell_type=reference_cell_type)
    model.run_nuts(mdata, modality_key=modality_key, rng_key=random_state)
    model.set_fdr(mdata, modality_key=modality_key, est_fdr=fdr)
    effect_df = model.get_effect_df(mdata, modality_key=modality_key).reset_index()
    if hasattr(mdata, "uns"):
        mdata.uns["backend"] = "sccoda_pertpy"
    return mdata, effect_df
