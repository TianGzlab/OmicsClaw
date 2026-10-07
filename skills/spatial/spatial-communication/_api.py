"""Ligand-receptor inference and tables for spatial analysis steps."""
from skills.spatial._lib.communication import run_communication
from skills.spatial._lib.inference_result import store_info, read_info

__all__ = ['communicate', 'interactions', 'run_info', 'roles_figure']
_INFO = '_spatial_communication_run_info'


def communicate(adata, *, method='liana', cell_type_key='leiden', species='human',
                random_state=None, **parameters):
    """Infer ligand-receptor interactions and return the same AnnData.

    LIANA uses raw when present, otherwise X. Other backends read normalized
    X. Coordinates support CLI maps; these methods do not impose distance filters.

    :param adata: Log-normalized expression with cell-type labels; modified in place.
    :param method: CLI default liana; cellphonedb, fastccc or cellchat_r also supported.
    :param cell_type_key: CLI default leiden; obs column defining populations.
    :param species: CLI default human; mouse supported by LIANA and CellChat.
    :param random_state: None keeps LIANA seed 1337 and CellChat seed 1; CellPhoneDB uses 0.
    :param parameters: Native backend keywords in references/parameters.md.
    :returns: The same AnnData with canonical ccc_results and role summaries in uns.
    :raises ValueError: Method, labels, species or numeric controls are invalid.
    :raises ImportError: Optional backend is missing; use install_skill_deps.
    :raises FileNotFoundError: CellPhoneDB/FastCCC's local database is missing.
    """
    if cell_type_key not in adata.obs or adata.obs[cell_type_key].nunique() < 2:
        raise ValueError('At least two cell types are required in cell_type_key')
    if adata.obs[cell_type_key].isna().any():
        raise ValueError('Cell-type labels must not contain missing values')
    for key in ('expr_prop', 'threshold', 'min_percentile'):
        if key in parameters and not 0 <= parameters[key] <= 1:
            raise ValueError(f'{key} must be in [0, 1]')
    for key in ('min_cells', 'n_perms', 'iterations'):
        if key in parameters and parameters[key] < 1:
            raise ValueError(f'{key} must be positive')
    if method in ('liana', 'cellphonedb', 'cellchat_r'):
        seed = {'liana': 1337, 'cellphonedb': 0, 'cellchat_r': 1}[method] if random_state is None else random_state
        parameters['random_state'] = seed
    try:
        summary = run_communication(adata, method=method, cell_type_key=cell_type_key,
                                    species=species, method_params=parameters)
    except ImportError as exc:
        package = 'CellChat' if method == 'cellchat_r' else method
        raise ImportError(f'{package} backend is unavailable; use install_skill_deps') from exc
    store_info(adata, _INFO, summary)
    return adata


def run_info(adata, *, keep=True):
    """Read the last run's diagnostics and optional backend tables.

    :param adata: AnnData returned by communicate.
    :param keep: Default True; False removes transient diagnostics for CLI serialization.
    :returns: Summary dictionary including tested/significant counts and extra_tables.
    :raises ValueError: No communication run is recorded.
    """
    info = read_info(adata, _INFO, keep=keep)
    if not info:
        raise ValueError('Run communicate before requesting its results')
    return info


def interactions(adata, *, significant_only=False):
    """Return ligand-receptor scores; unmeasured p values remain missing.

    :param adata: AnnData returned by communicate.
    :param significant_only: Default False; True selects real p values below 0.05.
    :returns: A new DataFrame with ligand, receptor, source, target, score and pvalue.
    :raises ValueError: No run is recorded.
    """
    table = run_info(adata)['lr_df'].copy()
    return table[table['pvalue'] < 0.05].copy() if significant_only else table


def roles_figure(adata, *, n_top=20):
    """Plot population sender and receiver scores without file writes.

    :param adata: AnnData returned by communicate.
    :param n_top: Default 20 populations; use fewer for a smaller figure.
    :returns: A matplotlib Figure, explicitly labelled when no scores exist.
    :raises ValueError: No run is recorded or n_top is not positive.
    """
    import matplotlib.pyplot as plt

    if n_top < 1:
        raise ValueError('n_top must be positive')
    table = run_info(adata)['signaling_roles_df'].head(n_top)
    fig, ax = plt.subplots()
    if table.empty:
        ax.text(0.5, 0.5, 'No interaction scores', ha='center')
    else:
        table.set_index('cell_type')[['sender_score', 'receiver_score']].plot.barh(ax=ax)
        ax.set_xlabel('Summed interaction score')
    return fig
