"""Classify observed Perturb-seq signatures with pertpy Mixscape."""

from __future__ import annotations

import json

__all__ = ["mixscape", "run_info", "class_counts", "global_class_counts", "global_class_figure"]


def mixscape(adata, *, pert_key="perturbation", control="NT", split_by="replicate",
             n_neighbors=20, logfc_threshold=0.25, pval_cutoff=0.05,
             perturbation_type="KO", random_state=0):
    """Return an AnnData copy with Mixscape classes and posterior probabilities.

    Uses normalized expression, preserving count-like X in layers['counts']
    before log-normalization. split_by=None selects nearest-neighbour controls.
    Both pertpy stages receive random_state; a missing control or split column
    raises ValueError. Requires pertpy (validated with 1.0.3 and sklearn 1.7.2).
    """
    if pert_key not in adata.obs:
        raise ValueError(f"Perturbation column {pert_key!r} is missing")
    if control not in set(adata.obs[pert_key].astype(str)):
        raise ValueError(f"Control label {control!r} is missing from {pert_key!r}")
    if split_by and split_by not in adata.obs:
        raise ValueError(f"Split column {split_by!r} is missing; pass split_by=None to disable splitting")
    if n_neighbors < 2 or logfc_threshold < 0 or not 0 < pval_cutoff <= 1:
        raise ValueError("n_neighbors >= 2, logfc_threshold >= 0 and 0 < pval_cutoff <= 1 are required")
    if perturbation_type not in {'KO', 'OE'}:
        raise ValueError("perturbation_type must be KO or OE")
    import scanpy as sc
    from skills.singlecell._lib.perturbation import run_mixscape_workflow

    result = adata.copy()
    if 'X_pca' not in result.obsm:
        sc.pp.pca(result, random_state=random_state)
    backend = run_mixscape_workflow(
        result, pert_key=pert_key, control=control, split_by=split_by,
        n_neighbors=n_neighbors, logfc_threshold=logfc_threshold, pval_cutoff=pval_cutoff,
        perturbation_type=perturbation_type, random_state=random_state)
    info = {
        key: value for key, value in backend.items() if key not in {'class_counts', 'global_counts'}}
    info.update(random_state=int(random_state), pert_key=pert_key, control=control, split_by=split_by)
    result.uns['sc_perturb_run_info'] = json.dumps(info)
    return result


def run_info(adata, *, keep: bool = True):
    """Return method, seed and output columns; keep=False removes the run record."""
    key = 'sc_perturb_run_info'
    raw = adata.uns.get(key, '{}') if keep else adata.uns.pop(key, '{}')
    return json.loads(raw)


def class_counts(adata):
    """Return class and n_cells columns for target-specific Mixscape labels."""
    return adata.obs['mixscape_class'].astype(str).value_counts().rename_axis('class').reset_index(name='n_cells')


def global_class_counts(adata):
    """Return global_class and n_cells columns for control, KO/OE and NP cells."""
    return adata.obs['mixscape_class_global'].astype(str).value_counts().rename_axis('global_class').reset_index(name='n_cells')


def global_class_figure(adata):
    """Return a Figure of global Mixscape cell counts without saving files."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4))
    global_class_counts(adata).plot.bar(x='global_class', y='n_cells', ax=ax, color='#1f78b4')
    ax.set_title('Mixscape global classes')
    fig.tight_layout()
    return fig
