"""Descriptive knockout-edge scores and the optional scTenifoldKnk R backend."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile

__all__ = ["knockout_correlation", "sctenifoldknk", "run_info", "top_perturbed_genes", "perturbed_genes_figure"]


def knockout_correlation(adata, *, ko_gene, n_top_genes=2000):
    """Return descriptive edge-removal scores, not a causal knockout simulation.

    Select the most variable genes plus ko_gene, compute Pearson correlations
    from layers['counts'] (or X), and average absolute changes after zeroing the
    target row and column. Returns gene, dr_score and wt_ko_corr, with no p-values.
    The target's own score includes all its removed edges and is not comparable
    to another gene's single removed edge. The input AnnData is unchanged.
    """
    import numpy as np
    import pandas as pd

    if ko_gene not in adata.var_names:
        raise ValueError(f"Gene {ko_gene!r} is missing from adata.var_names")
    if n_top_genes < 1 or adata.n_obs < 2:
        raise ValueError("n_top_genes must be positive and at least two cells are required")
    if not adata.var_names.is_unique:
        raise ValueError("Gene names must be unique")
    matrix = adata.layers['counts'] if 'counts' in adata.layers else adata.X
    matrix = matrix.toarray() if hasattr(matrix, 'toarray') else matrix
    matrix = np.asarray(matrix, dtype=np.float64)
    ko_index = adata.var_names.get_loc(ko_gene)
    indices = np.argsort(matrix.var(axis=0))[::-1][:min(n_top_genes, adata.n_vars)]
    if ko_index not in indices:
        indices = np.append(indices, ko_index)
    indices = np.sort(indices)
    local = int(np.flatnonzero(indices == ko_index)[0])
    if len(indices) == 1:
        correlation = np.array([[float(matrix[:, ko_index].var() > 0)]])
    else:
        with np.errstate(divide='ignore', invalid='ignore'):
            correlation = np.nan_to_num(np.corrcoef(matrix[:, indices].T), nan=0.)
    removed = correlation.copy()
    removed[local, :] = 0.
    removed[:, local] = 0.
    result = pd.DataFrame({'gene': adata.var_names[indices].astype(str),
                           'dr_score': np.abs(correlation - removed).mean(axis=1),
                           'wt_ko_corr': np.abs(correlation[local, :])})
    result = result.sort_values('dr_score', ascending=False, kind='stable').reset_index(drop=True)
    result.attrs['run_info'] = {
        'method': 'grn_ko', 'ko_gene': str(ko_gene), 'n_genes': len(result),
        'matrix_source': "layers['counts']" if 'counts' in adata.layers else 'X',
        'interpretation': 'Descriptive correlation edge-removal score; not a causal knockout simulation or significance test.',
    }
    return result


def sctenifoldknk(adata, *, ko_gene, qc=False, qc_min_lib_size=0, qc_min_cells=10,
                  n_net=2, n_cells=100, n_comp=3, q=0.8, td_k=2, ma_dim=2,
                  n_cores=1, random_state=0):
    """Return scTenifoldKnk diffRegulation through a temporary CSV bridge.

    Uses layers['counts'] or X without changing the input. Requires Rscript and
    the scTenifoldKnk R package; missing packages and R failures propagate.
    random_state is passed to R set.seed before fitting the network.
    """
    import pandas as pd
    from skills._sdk.r_script_runner import RScriptRunner

    if ko_gene not in adata.var_names:
        raise ValueError(f"Gene {ko_gene!r} is missing from adata.var_names")
    matrix = adata.layers['counts'] if 'counts' in adata.layers else adata.X
    matrix = matrix.toarray() if hasattr(matrix, 'toarray') else matrix
    table = pd.DataFrame(matrix.T, index=adata.var_names.astype(str), columns=adata.obs_names.astype(str))
    with tempfile.TemporaryDirectory(prefix='omicsclaw_tenifold_') as directory:
        root = Path(directory)
        matrix_path, output = root / 'matrix.csv', root / 'diff_regulation.csv'
        table.to_csv(matrix_path)
        args = [str(matrix_path), str(output), str(ko_gene), str(bool(qc)).upper(),
                *map(str, (qc_min_lib_size, qc_min_cells, n_net, n_cells, n_comp,
                           q, td_k, ma_dim, n_cores, random_state))]
        RScriptRunner().run_script(str(Path(__file__).parent / 'rscripts' / 'sc_sctenifoldknk.R'),
                                   args=args, output_dir=root)
        result = pd.read_csv(output)
    result.attrs['run_info'] = {'method': 'sctenifoldknk', 'ko_gene': ko_gene,
                                 'random_state': int(random_state), 'n_genes': len(result)}
    return result


def run_info(table):
    """Return method, matrix source and interpretation from a returned result table."""
    return deepcopy(table.attrs.get('run_info', {}))


def top_perturbed_genes(table, *, n_top=15):
    """Return top correlation scores, or lowest adjusted p-values for scTenifoldKnk."""
    if n_top < 1:
        raise ValueError("n_top must be positive")
    key = 'dr_score' if 'dr_score' in table else 'p.adj'
    return table.sort_values(key, ascending=key != 'dr_score', kind='stable').head(n_top).copy()


def perturbed_genes_figure(table, *, n_top=15):
    """Return a Figure of descriptive edge scores or R differential-regulation FC."""
    import matplotlib.pyplot as plt

    top = top_perturbed_genes(table, n_top=n_top)
    key = 'dr_score' if 'dr_score' in top else 'FC'
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.barh(top['gene'].astype(str), top[key].astype(float), color='#b2182b')
    ax.set(xlabel='Correlation edge-removal score' if key == 'dr_score' else 'Differential regulation FC',
           title='Top descriptive associations' if key == 'dr_score' else 'scTenifoldKnk results')
    fig.tight_layout()
    return fig
