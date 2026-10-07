"""Two-group differential protein abundance."""
import pandas as pd
from skills.proteomics._lib import de as core
from skills.proteomics._lib.table_info import attach, read_info

__all__ = ['differential_abundance', 'significant', 'run_info', 'volcano_figure', 'demo_data']


def differential_abundance(data: pd.DataFrame, *, group1: list | None = None,
                           group2: list | None = None, method: str = 'ttest') -> pd.DataFrame:
    """Compare groups and return a new table with group2-minus-group1 log2 fold changes.

    :param data: Protein-indexed, sample-column linear intensities; nonpositive values are missing.
    :param group1: First group columns; None uses the first half as in the CLI.
    :param group2: Second group columns; None uses the second half as in the CLI.
    :param method: CLI default ttest; welch uses unequal variance and mann_whitney tests ranks.
    :returns: Per-protein statistics and BH-adjusted p values.
    :raises ValueError: Groups overlap, are empty, or the protein index is not unique.
    """
    if data.empty or not data.index.is_unique:
        raise ValueError('A nonempty table with unique protein identifiers is required')
    if (group1 is None) != (group2 is None):
        raise ValueError('Supply both groups or neither')
    if group1 is None:
        mid = data.shape[1] // 2
        group1, group2 = list(data.columns[:mid]), list(data.columns[mid:])
    if not group1 or not group2 or set(group1) & set(group2):
        raise ValueError('Groups must be nonempty and disjoint')
    if not (set(group1) | set(group2)) <= set(data.columns):
        raise ValueError('Every group sample must be a data column')
    result = core._dispatch_method(method, data, group1, group2)
    return attach(result, requested_method=method, executed_method=method,
                  group1=list(group1), group2=list(group2), n_tested=len(result))


def significant(results: pd.DataFrame, *, alpha: float = 0.05, log2fc_threshold: float = 0.0) -> pd.DataFrame:
    """Select significant proteins from an existing comparison.

    :param results: Differential abundance results with padj and log2fc.
    :param alpha: CLI default 0.05; strict upper bound on BH-adjusted p values.
    :param log2fc_threshold: CLI default 0 disables the absolute fold-change filter.
    :returns: A new table retaining selected rows.
    :raises ValueError: Thresholds are outside their allowed ranges.
    """
    if not 0 <= alpha <= 1 or log2fc_threshold < 0:
        raise ValueError('alpha must be in [0, 1] and log2fc_threshold nonnegative')
    mask = results['padj'] < alpha
    if log2fc_threshold > 0:
        mask &= results['log2fc'].abs() >= log2fc_threshold
    return results.loc[mask].copy()


def run_info(table: pd.DataFrame, *, keep: bool = True) -> dict:
    """Read comparison diagnostics.

    :param table: Output of differential_abundance.
    :param keep: True preserves attrs; False removes diagnostics.
    :returns: A separate diagnostic dictionary.
    :raises TypeError: The input is not a DataFrame.
    """
    return read_info(table, keep=keep)


def volcano_figure(results: pd.DataFrame):
    """Plot log2 fold change against adjusted significance.

    :param results: Differential abundance results.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: log2fc or padj is absent.
    """
    import numpy as np
    from matplotlib.figure import Figure
    fig = Figure(figsize=(6, 4))
    ax = fig.subplots()
    ax.scatter(results['log2fc'], -np.log10(results['padj'].clip(lower=1e-300)), s=12)
    ax.set(xlabel='log2 fold change (group2 / group1)', ylabel='-log10 adjusted p value')
    return fig


def demo_data(*, random_state: int = 42) -> pd.DataFrame:
    """Generate synthetic intensities with two ordered groups.

    :param random_state: CLI seed 42; change for another simulation.
    :returns: Protein rows and five control then five treatment columns.
    :raises ValueError: The seed is invalid.
    """
    return core.demo_data(random_state=random_state)
