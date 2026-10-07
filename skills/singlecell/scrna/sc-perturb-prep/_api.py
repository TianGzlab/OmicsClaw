"""Attach supplied guide assignments without running a perturbation backend."""

from __future__ import annotations

from copy import deepcopy

__all__ = ["standardize_mapping", "collapse_assignments", "attach_assignments", "run_info",
           "assignment_summary", "perturbation_counts", "perturbation_counts_figure"]


def standardize_mapping(table, *, barcode_column=None, sgrna_column=None, target_column=None):
    """Return barcode, sgRNA and target_gene columns from a pandas table.

    Column names may be supplied explicitly. Missing target genes are inferred
    later from guide names; duplicate rows and empty barcode/guide rows are removed.
    """
    from skills.singlecell._lib.perturbation import load_sgrna_mapping
    import pandas as pd

    if not isinstance(table, pd.DataFrame):
        raise TypeError("table must be a pandas DataFrame; read the mapping file first")
    return load_sgrna_mapping(table, barcode_column=barcode_column,
                             sgrna_column=sgrna_column, target_column=target_column)


def collapse_assignments(mapping, *, delimiter="_", gene_position=0,
                         control_patterns=("NT", "NTC", "NON-TARGET", "NON_TARGET", "NEGATIVE_CONTROL", "NEG_CTRL"),
                         control_label="NT", drop_multi_guide=True):
    """Return (assigned, dropped) tables with one row per barcode.

    Controls match whole tokens, not substrings of gene names. Multiple guides
    are dropped by default; retained multi-guide cells keep their status.
    """
    from skills.singlecell._lib.perturbation import collapse_sgrna_assignments

    return collapse_sgrna_assignments(mapping, delimiter=delimiter, gene_position=gene_position,
                                     control_patterns=tuple(control_patterns), control_label=control_label,
                                     drop_multi_guide=drop_multi_guide)


def attach_assignments(adata, assignments, *, pert_key="perturbation", sgrna_key="sgRNA",
                       target_key="target_gene", species="human"):
    """Return a gene-expression AnnData with assignments on matching cells.

    The input is unchanged. Gene features and the expression matrix are
    canonicalized using the single-cell input contract; no pertpy is needed.
    """
    from skills.singlecell._lib.adata_utils import canonicalize_singlecell_adata
    from skills.singlecell._lib.perturbation import annotate_perturbation_obs, keep_gene_expression_features

    if assignments.empty or not adata.obs_names.astype(str).isin(assignments['barcode'].astype(str)).any():
        raise ValueError("No assignment barcode matches adata.obs_names")
    filtered, feature_summary = keep_gene_expression_features(adata)
    prepared = annotate_perturbation_obs(filtered, assignments, pert_key=pert_key,
                                        sgrna_key=sgrna_key, target_key=target_key)
    result, sources, contract = canonicalize_singlecell_adata(
        prepared, species=species, standardizer_skill="sc-perturb-prep")
    for key in (pert_key, sgrna_key, target_key, 'assignment_status'):
        result.obs[key] = prepared.obs[key].astype(str).values
    result.obs['n_sgrnas'] = prepared.obs['n_sgrnas'].astype(int).values
    result.uns['sc_perturb_prep_run_info'] = {
        'n_cells_input': int(adata.n_obs), 'n_cells_assigned': int(result.n_obs),
        'n_non_gene_features_removed': feature_summary['n_non_gene_features_removed'],
        'feature_types': feature_summary['feature_types'], 'expression_source': sources.expression_source,
        'gene_name_source': sources.gene_name_source, 'input_contract': contract,
        'pert_key': pert_key, 'sgrna_key': sgrna_key, 'target_key': target_key,
    }
    return result


def run_info(adata):
    """Return a copy of preparation counts, feature types and input provenance."""
    return deepcopy(adata.uns.get('sc_perturb_prep_run_info', {}))


def assignment_summary(adata):
    """Return assignment_status and n_cells columns for the retained cells."""
    return adata.obs['assignment_status'].astype(str).value_counts().rename_axis('assignment_status').reset_index(name='n_cells')


def perturbation_counts(adata, *, pert_key="perturbation"):
    """Return perturbation and n_cells columns, ordered by decreasing cell count."""
    return adata.obs[pert_key].astype(str).value_counts().rename_axis('perturbation').reset_index(name='n_cells')


def perturbation_counts_figure(adata, *, pert_key="perturbation", n_top=20):
    """Return a Figure of cell counts for up to n_top perturbations; save it separately."""
    import matplotlib.pyplot as plt

    table = perturbation_counts(adata, pert_key=pert_key).head(n_top)
    fig, ax = plt.subplots(figsize=(8, 4))
    table.plot.bar(x='perturbation', y='n_cells', ax=ax, color='#1f78b4')
    ax.set(title='Cells per perturbation', xlabel='Perturbation', ylabel='Cells')
    fig.tight_layout()
    return fig
