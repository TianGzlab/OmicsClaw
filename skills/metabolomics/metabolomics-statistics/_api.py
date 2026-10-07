"""Two-group tests for feature-by-sample metabolomics tables."""
import warnings
import numpy as np
from skills.metabolomics._lib.statistics import dispatch_method, _benjamini_hochberg

__all__ = ['test_groups', 'run_info', 'volcano_figure']


def test_groups(data, *, method='ttest', alpha=.05, group1_prefix=None, group2_prefix=None, group1_cols=None, group2_cols=None):
    """Return two-group test statistics and BH-adjusted p values.

    :param data: Numeric feature-by-sample DataFrame with feature IDs as its index.
    :param method: CLI default ttest; wilcoxon (ranksums), anova or kruskal also work.
    :param alpha: CLI default .05; diagnostic significance threshold.
    :param group1_prefix: CLI default None; prefix selecting the reference samples.
    :param group2_prefix: CLI default None; prefix selecting the comparison samples.
    :param group1_cols: Explicit reference columns; supply together with group2_cols.
    :param group2_cols: Explicit comparison columns; overrides prefix selection.
    :returns: A new DataFrame with grouping and significance diagnostics.
    :raises ValueError: A group is empty, overlaps another or is only partly specified.
    """
    if not 0 < alpha <= 1:
        raise ValueError('alpha must be in (0, 1]')
    if (group1_cols is None) != (group2_cols is None):
        raise ValueError('Supply both group column lists')
    if group1_cols is not None:
        first, second = list(group1_cols), list(group2_cols)
        grouping = 'explicit'
    elif group1_prefix and group2_prefix:
        first = [c for c in data if c.startswith(group1_prefix)]
        second = [c for c in data if c.startswith(group2_prefix)]
        grouping = 'prefix'
    else:
        middle = len(data.columns) // 2
        first, second = list(data.columns[:middle]), list(data.columns[middle:])
        warnings.warn('No complete group prefixes; splitting columns at midpoint', UserWarning, stacklevel=2)
        grouping = 'midpoint'
    if not first or not second or set(first) & set(second):
        raise ValueError('Group columns must be nonempty and disjoint')
    result = dispatch_method(method, data, first, second)
    result['fdr'] = _benjamini_hochberg(result['pvalue'].values)
    count = int((result['fdr'] < alpha).sum())
    result.attrs['run_info'] = {'method': method, 'n_tested': len(result), 'n_significant': count,
                              'sig_rate': count / max(len(result), 1) * 100,
                              'grouping': grouping, 'group1': first, 'group2': second}
    return result


def volcano_figure(data):
    """Plot group2/group1 log2 fold change against BH-adjusted significance.

    :param data: Results from test_groups.
    :returns: A matplotlib Figure.
    :raises KeyError: log2fc or fdr is absent.
    """
    from matplotlib.figure import Figure
    fig = Figure(figsize=(6, 4))
    ax = fig.subplots()
    ax.scatter(data['log2fc'], -np.log10(data['fdr'].clip(lower=np.finfo(float).tiny)))
    ax.set(xlabel='log2(group2/group1)', ylabel='-log10(FDR)')
    return fig


def run_info(data, *, keep=True):
    """Read diagnostics attached to a returned table.

    :param data: DataFrame returned by this library.
    :param keep: Default True; use False in the CLI to remove diagnostics.
    :returns: An independent dictionary describing the run.
    :raises ValueError: The table carries no run_info.
    """
    from skills.metabolomics._lib.library import run_info as read
    return read(data, keep=keep)
