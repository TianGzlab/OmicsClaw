"""Protein abundance from peptide tables."""
import numpy as np
import pandas as pd
from skills.proteomics._lib import quantification as core
from skills.proteomics._lib.table_info import attach, read_info

__all__ = ['quantify', 'run_info', 'abundance_figure', 'demo_data']


def quantify(peptides: pd.DataFrame, *, method: str = 'lfq') -> pd.DataFrame:
    """Return a new protein abundance table without changing the peptides.

    :param peptides: PSM rows with protein and method-specific intensity or sequence columns.
    :param method: CLI default lfq sums intensity; spectral_count counts rows; ibaq divides by theoretical peptides.
    :returns: Protein abundances with diagnostics in attrs.
    :raises ValueError: Required columns or positive theoretical counts are missing.
    """
    if 'protein' not in peptides or peptides.empty:
        raise ValueError('A nonempty protein column is required')
    if method == 'ibaq':
        if not {'sequence', 'n_theoretical_peptides'} & set(peptides.columns):
            raise ValueError('iBAQ requires sequence or n_theoretical_peptides; observed peptides cannot substitute')
        if 'sequence' in peptides:
            if peptides['sequence'].isna().any() or peptides['sequence'].astype(str).str.len().eq(0).any():
                raise ValueError('sequence must contain a protein sequence for every row')
        else:
            counts = peptides['n_theoretical_peptides'].to_numpy(dtype=float)
            if not np.all(np.isfinite(counts) & (counts > 0) & (counts == np.floor(counts))):
                raise ValueError('n_theoretical_peptides must contain positive integer counts')
    result = core._dispatch_method(method, peptides)
    return attach(result, requested_method=method, executed_method=method, n_input=len(peptides),
                  summary={'method': method, 'n_proteins': len(result)})


def run_info(table: pd.DataFrame, *, keep: bool = True) -> dict:
    """Read the diagnostics attached to a returned table.

    :param table: Table returned by quantify.
    :param keep: True preserves attrs; the CLI uses False before serialization.
    :returns: A separate diagnostic dictionary.
    :raises TypeError: The input is not a DataFrame.
    """
    return read_info(table, keep=keep)


def abundance_figure(table: pd.DataFrame):
    """Plot the distribution of protein abundance.

    :param table: Output of quantify, including abundance.
    :returns: A matplotlib Figure; no files are written.
    :raises KeyError: The abundance column is absent.
    """
    from matplotlib.figure import Figure
    fig = Figure(figsize=(6, 4))
    ax = fig.subplots()
    ax.hist(table['abundance'], bins=30)
    ax.set(xlabel='Protein abundance', ylabel='Proteins')
    return fig


def demo_data(*, random_state: int = 42) -> pd.DataFrame:
    """Generate synthetic peptide data in memory.

    :param random_state: CLI seed 42; change to generate another simulation.
    :returns: Synthetic peptides with protein sequences for iBAQ.
    :raises ValueError: The seed is invalid.
    """
    return core.demo_data(random_state=random_state)
