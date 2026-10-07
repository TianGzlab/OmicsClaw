"""Two-group metabolomics differential analysis."""
import numpy as np
from skills.metabolomics._lib.differential import run_univariate

__all__ = ['differential_expression', 'run_info', 'pca_figure']


def _groups(data, a, b):
    first = [c for c in data if c.startswith(a)]
    second = [c for c in data if c.startswith(b)]
    if not first or not second:
        raise ValueError(f'Could not find columns starting with {a!r} / {b!r}')
    if set(first) & set(second):
        raise ValueError('Group columns must be disjoint')
    return first, second


def differential_expression(data, *, group_a_prefix='ctrl', group_b_prefix='treat'):
    """Return Welch tests, treatment/control log2 fold changes and BH FDR.

    :param data: Feature table whose first column identifies features; other columns contain intensities.
    :param group_a_prefix: CLI default ctrl; prefix selecting control samples.
    :param group_b_prefix: CLI default treat; prefix selecting treatment samples.
    :returns: A new differential table with group sizes in attrs['run_info'].
    :raises ValueError: A group is absent or groups overlap.
    """
    a, b = _groups(data, group_a_prefix, group_b_prefix)
    result = run_univariate(data, a, b)
    result.attrs['run_info'] = {'n_features': len(data), 'n_group_a': len(a), 'n_group_b': len(b),
                              'n_significant_fdr05': int((result['fdr'] < .05).sum())}
    return result


def pca_figure(data, *, group_a_prefix='ctrl', group_b_prefix='treat', random_state=0):
    """Plot sample PCA from untransformed intensities; NaNs become zero.

    :param data: Feature table with the same sample columns as differential_expression.
    :param group_a_prefix: CLI default ctrl; control prefix.
    :param group_b_prefix: CLI default treat; treatment prefix.
    :param random_state: Default 0; seed forwarded to sklearn PCA.
    :returns: A matplotlib Figure with sample labels and explained variance axes.
    :raises ImportError: Install scikit-learn with install_skill_deps if unavailable.
    :raises ValueError: Groups are absent, overlap or the matrix is invalid.
    """
    try:
        from sklearn.decomposition import PCA
    except ImportError as exc:
        raise ImportError('Install scikit-learn with install_skill_deps for PCA') from exc
    from matplotlib.figure import Figure
    a, b = _groups(data, group_a_prefix, group_b_prefix)
    columns = a + b
    matrix = np.nan_to_num(data[columns].to_numpy(dtype=float).T, nan=0.)
    model = PCA(n_components=min(2, *matrix.shape), random_state=random_state)
    scores = model.fit_transform(matrix)
    fig = Figure(figsize=(8, 6))
    ax = fig.subplots()
    y = scores[:, 1] if scores.shape[1] > 1 else np.zeros(len(scores))
    ax.scatter(scores[:, 0], y, c=['steelblue'] * len(a) + ['coral'] * len(b), s=60, edgecolors='k', linewidths=.5)
    for i, name in enumerate(columns):
        ax.annotate(name, (scores[i, 0], y[i]), fontsize=7, alpha=.8)
    ax.set_xlabel(f'PC1 ({model.explained_variance_ratio_[0] * 100:.1f}%)')
    if scores.shape[1] > 1:
        ax.set_ylabel(f'PC2 ({model.explained_variance_ratio_[1] * 100:.1f}%)')
    ax.set_title('PCA Scores Plot')
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
