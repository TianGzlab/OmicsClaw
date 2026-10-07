"""DataFrame diagnostics shared by metabolomics libraries."""
from copy import deepcopy


def run_info(data, *, keep=True):
    """Read diagnostics attached by the most recent library call.

    :param data: Returned DataFrame carrying attrs['run_info'].
    :param keep: Keep diagnostics by default; the CLI removes them with False.
    :returns: An independent diagnostic dictionary.
    :raises ValueError: No library diagnostics are present.
    """
    if 'run_info' not in data.attrs:
        raise ValueError('No run_info diagnostics on this table')
    return deepcopy(data.attrs['run_info'] if keep else data.attrs.pop('run_info'))


def distribution_figure(data):
    """Return numeric column distributions without file output."""
    from matplotlib.figure import Figure
    numeric = data.select_dtypes(include='number')
    if numeric.empty:
        raise ValueError('No numeric columns to plot')
    fig = Figure(figsize=(8, 4))
    ax = fig.subplots()
    ax.boxplot([numeric[c].dropna().to_numpy() for c in numeric], tick_labels=list(numeric))
    ax.set_ylabel('Intensity')
    ax.tick_params(axis='x', labelrotation=45)
    fig.tight_layout()
    return fig
