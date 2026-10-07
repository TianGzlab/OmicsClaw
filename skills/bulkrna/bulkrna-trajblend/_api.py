"""Place bulk samples against an observed, pseudotimed reference."""
from pathlib import Path
import numpy as np
import pandas as pd
from skills.bulkrna._lib import trajblend as core
from skills.bulkrna._lib.results import attach_info, read_info, require_matrix

__all__ = ['read_reference', 'map_trajectory', 'fractions', 'run_info', 'trajectory_figure', 'fractions_figure', 'demo_data']


def read_reference(path: str | Path, *, cell_type_key: str = 'cell_type',
                   pseudotime_key: str = 'pseudotime') -> tuple:
    """Read a reference with annotations; pass this function as reader= to read_input.

    :param path: H5AD with expression in X, or cell-by-gene CSV/TSV with annotation columns.
    :param cell_type_key: CLI default cell_type; change for a named annotation column.
    :param pseudotime_key: CLI default pseudotime; supply an observed reference trajectory value.
    :returns: Cell-by-gene DataFrame, indexed cell-type Series and indexed pseudotime Series.
    :raises ValueError: Required annotations are missing.
    :raises ImportError: H5AD reading needs anndata; install it with install_skill_deps.
    """
    path = Path(path)
    if path.suffix == '.h5ad':
        try:
            import anndata as ad
        except ImportError as exc:
            raise ImportError('anndata is required; use install_skill_deps for bulkrna-trajblend') from exc
        adata = ad.read_h5ad(path)
        metadata = adata.obs
        values = adata.X.toarray() if hasattr(adata.X,'toarray') else adata.X
        reference = pd.DataFrame(values,index=adata.obs_names,columns=adata.var_names)
    else:
        metadata = pd.read_csv(path,index_col=0,sep='\t' if path.suffix in ('.tsv','.txt') else ',')
        reference = metadata.drop(columns=[cell_type_key,pseudotime_key],errors='ignore')
    if not {cell_type_key,pseudotime_key} <= set(metadata.columns):
        raise ValueError(f'Reference requires {cell_type_key} and {pseudotime_key}; missing annotations are not inferred')
    return reference,metadata[cell_type_key].copy(),metadata[pseudotime_key].copy()


def map_trajectory(bulk: pd.DataFrame, *, reference: pd.DataFrame, labels: pd.Series,
                   pseudotime: pd.Series, k: int = 15, random_state: int = 42) -> pd.DataFrame:
    """Return bulk pseudotime estimates from NNLS and joint PCA/kNN placement.

    :param bulk: Sample-by-gene nonnegative expression on a scale comparable with the reference.
    :param reference: Cell-by-gene expression with at least fifty shared genes.
    :param labels: Cell-type labels indexed by reference cell identifiers.
    :param pseudotime: Observed reference pseudotime indexed by cell identifiers; never synthesized.
    :param k: CLI default 15 nearest reference cells; reduce for a smaller reference.
    :param random_state: CLI seed 42 forwarded to PCA; change to assess randomized-solver sensitivity.
    :returns: New sample-indexed pseudotime table; fractions and embeddings remain in attrs.
    :raises ValueError: Matrices, annotations, gene overlap or neighbor count are invalid.
    :raises ImportError: Missing scipy/scikit-learn; use install_skill_deps.
    """
    require_matrix(bulk)
    require_matrix(reference)
    if not isinstance(labels,pd.Series) or not labels.index.is_unique:
        raise ValueError('labels must be a uniquely cell-indexed Series')
    if not isinstance(pseudotime,pd.Series) or not pseudotime.index.is_unique:
        raise ValueError('pseudotime must be a uniquely cell-indexed Series')
    labels = labels.reindex(reference.index)
    pseudotime = pseudotime.reindex(reference.index)
    if labels.isna().any() or pseudotime.isna().any() or not np.isfinite(pseudotime.to_numpy(dtype=float)).all():
        raise ValueError('Every reference cell needs a label and finite observed pseudotime')
    if not 1 <= k <= len(reference):
        raise ValueError('k must be between one and the number of reference cells')
    if len(bulk.columns.intersection(reference.columns)) < 50:
        raise ValueError('At least 50 common genes are required')
    try:
        proportions = core.estimate_fractions(bulk,reference,labels)
        result,ref_pcs,bulk_pcs,_ = core.map_bulk_to_trajectory(bulk,reference,pseudotime.to_numpy(),k=k,random_state=random_state)
    except ImportError as exc:
        raise ImportError('scipy and scikit-learn are required; use install_skill_deps for bulkrna-trajblend') from exc
    return attach_info(result,{'method':'nnls-pca-knn','random_state':random_state,'k':k,
                       'fractions':proportions,'reference_pcs':ref_pcs,'bulk_pcs':bulk_pcs,
                       'reference_pseudotime':pseudotime.to_numpy(),'reference_labels':labels,
                       'pseudotime_std_meaning':'neighbor spread, not calibrated uncertainty'})


def fractions(result: pd.DataFrame) -> pd.DataFrame:
    """Return the estimated cell-type fractions.

    :param result: Output of map_trajectory retaining attrs.
    :returns: A separate sample-by-cell-type DataFrame.
    :raises KeyError: Fraction diagnostics are absent.
    """
    return read_info(result)['fractions']


def run_info(result: pd.DataFrame, *, keep: bool = True) -> dict:
    """Read placement diagnostics and plot data.

    :param result: Output of map_trajectory.
    :param keep: True preserves attrs; False removes diagnostics before serialization.
    :returns: Separate method, seed, fractions, embedding and annotation values.
    :raises TypeError: The result is not a DataFrame.
    """
    return read_info(result,keep=keep)


def trajectory_figure(result: pd.DataFrame):
    """Plot bulk and reference PCA coordinates colored by reference pseudotime.

    :param result: Placement result retaining its diagnostic attrs.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: Embedding diagnostics are absent.
    """
    from matplotlib.figure import Figure
    info = read_info(result)
    ref,bulk = info['reference_pcs'],info['bulk_pcs']
    fig = Figure(figsize=(7,5)); ax = fig.subplots()
    points = ax.scatter(ref[:,0],ref[:,1],c=info['reference_pseudotime'],s=8,alpha=.4)
    ax.scatter(bulk[:,0],bulk[:,1],c='red',marker='*',s=70)
    fig.colorbar(points,ax=ax,label='Reference pseudotime')
    ax.set(xlabel='PC1',ylabel='PC2')
    return fig


def fractions_figure(result: pd.DataFrame):
    """Plot sample-by-cell-type proportions.

    :param result: Placement result retaining its diagnostic attrs.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: Fraction diagnostics are absent.
    """
    from matplotlib.figure import Figure
    table = fractions(result)
    fig = Figure(figsize=(7,4)); ax = fig.subplots()
    image = ax.imshow(table,aspect='auto',vmin=0,vmax=1)
    ax.set_xticks(range(len(table.columns)),table.columns,rotation=45)
    ax.set_yticks(range(len(table)),table.index)
    fig.colorbar(image,ax=ax,label='Fraction')
    fig.tight_layout()
    return fig


def demo_data(*, random_state: int = 42) -> tuple:
    """Generate synthetic bulk mixtures and an annotated reference in memory.

    :param random_state: CLI seed 42; change for another simulation without global RNG mutation.
    :returns: Bulk table, reference table, cell-type Series and pseudotime Series.
    :raises ValueError: The seed is invalid.
    """
    bulk,reference,labels,time = core.demo_data(random_state=random_state)
    return bulk,reference,labels,pd.Series(time,index=reference.index,name='pseudotime')
