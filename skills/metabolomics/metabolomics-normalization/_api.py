"""Normalize feature-by-sample intensity tables in memory."""
from skills.metabolomics._lib.normalization import dispatch_method

__all__ = ['normalize', 'run_info', 'distribution_figure']


def normalize(data, *, method='median'):
    """Return a normalized copy, preserving feature and sample labels.

    :param data: Numeric feature-by-sample DataFrame; NaNs retain method semantics.
    :param method: CLI default median; quantile, total, pqn or log are alternatives.
    :returns: A new DataFrame with method and dimensions in attrs['run_info'].
    :raises ValueError: The requested method is unknown.
    """
    result = dispatch_method(method, data.copy())
    result.attrs['run_info'] = {'method': method, 'n_features': len(data), 'n_samples': len(data.columns)}
    return result


def distribution_figure(data):
    """Plot normalized sample distributions without writing a file.

    :param data: Numeric feature-by-sample DataFrame.
    :returns: A matplotlib Figure.
    :raises ValueError: No numeric columns are available.
    """
    from skills.metabolomics._lib.library import distribution_figure as plot
    return plot(data)


def run_info(data, *, keep=True):
    """Read diagnostics attached to a returned table.

    :param data: DataFrame returned by this library.
    :param keep: Default True; use False in the CLI to remove diagnostics.
    :returns: An independent dictionary describing the run.
    :raises ValueError: The table carries no run_info.
    """
    from skills.metabolomics._lib.library import run_info as read
    return read(data, keep=keep)
