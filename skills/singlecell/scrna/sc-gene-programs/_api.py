"""NMF and cNMF programs, with explicit backend provenance."""

from __future__ import annotations

import json
import logging
import pandas as pd

from skills.singlecell._lib.gene_programs import run_cnmf_programs, run_nmf_programs

__all__ = ['find_programs', 'program_weights', 'top_program_genes', 'program_correlation', 'usage_figure', 'run_info']
_RUN_KEY = 'omicsclaw_sc_gene_programs_run'


def find_programs(adata, *, method: str = 'cnmf', n_programs: int = 6,
                  n_iter: int = 400, layer: str | None = None,
                  top_genes: int = 30, random_state: int = 0):
    """Return a copy with per-cell usage in obsm['X_gene_programs'].

    cNMF uses counts when available; missing cNMF falls back to sklearn NMF,
    recorded by run_info. NMF uses X unless layer is set. Negative values are
    clipped to zero by the existing solver. n_iter limits each factorization's
    iterations, not the number of cNMF replicates. Both methods use random_state.
    Program weights and ranked genes are available through the table helpers.
    """
    if method not in ('cnmf', 'nmf'):
        raise ValueError('method must be cnmf or nmf')
    if n_programs < 2 or n_iter < 1 or top_genes < 1:
        raise ValueError('n_programs >= 2, n_iter >= 1 and top_genes >= 1 are required')
    work = adata.copy()
    executed, reason = method, ''
    if method == 'cnmf':
        try:
            import cnmf  # noqa: F401
        except ImportError as exc:
            executed, reason = 'nmf', f'cnmf unavailable: {exc}'
            logging.getLogger(__name__).warning('%s; using sklearn NMF', reason)
    runner = run_cnmf_programs if executed == 'cnmf' else run_nmf_programs
    result = runner(work, n_programs=n_programs, seed=random_state,
                    max_iter=n_iter, layer=layer, top_genes=top_genes)
    work.obsm['X_gene_programs'] = result['usage'].to_numpy()
    work.uns['gene_programs'] = {
        'method': executed, 'program_names': result['usage'].columns.tolist(),
        'top_genes_csv': 'tables/top_program_genes.csv',
    }
    work.uns['gene_program_weights'] = result['weights'].copy()
    work.uns['gene_program_top_genes'] = result['top_genes'].copy()
    if 'spectra_tpm' in result:
        work.uns['gene_program_tpm'] = result['spectra_tpm'].copy()
    info = {key: value for key, value in result.items()
            if key not in ('model', 'usage', 'weights', 'top_genes', 'spectra_tpm')}
    info.update(requested_method=method, executed_method=executed,
                fallback_used=executed != method, fallback_reason=reason,
                random_state=random_state)
    work.uns[_RUN_KEY] = json.dumps(info)
    return work


def program_weights(adata) -> pd.DataFrame:
    """Return program-by-gene weights from find_programs."""
    return adata.uns['gene_program_weights'].copy()


def top_program_genes(adata, *, n: int | None = None) -> pd.DataFrame:
    """Return ranked genes and weights; n optionally limits genes per program."""
    table = adata.uns['gene_program_top_genes'].copy()
    return table if n is None else table.groupby('program', sort=False).head(n).copy()


def program_correlation(adata) -> pd.DataFrame:
    """Return Pearson correlations between per-cell program usages."""
    return pd.DataFrame(adata.obsm['X_gene_programs'], columns=adata.uns['gene_programs']['program_names']).corr()


def usage_figure(adata):
    """Return a heatmap figure of cells by program usage, without writing files."""
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    image = ax.imshow(adata.obsm['X_gene_programs'], aspect='auto', cmap='viridis')
    ax.set(xlabel='Program', ylabel='Cell')
    fig.colorbar(image, ax=ax, label='Usage')
    fig.tight_layout()
    return fig


def run_info(adata, *, keep: bool = True) -> dict:
    """Return methods and solver diagnostics; keep=False removes the run record."""
    raw = adata.uns.get(_RUN_KEY, '{}') if keep else adata.uns.pop(_RUN_KEY, '{}')
    return json.loads(raw)
