"""NNLS deconvolution of supplied bulk and reference matrices."""
from skills.bulkrna._lib.deconvolution import core_analysis
from skills.bulkrna._lib.results import attach_info, read_info, require_matrix

__all__ = ['deconvolve', 'run_info', 'proportions_figure']


def deconvolve(counts, *, signature):
    """Estimate sample proportions without changing either input.

    :param counts: Nonnegative gene-by-sample expression DataFrame.
    :param signature: Required gene-by-cell-type reference, matching the CLI --reference.
    :returns: Sample-by-cell-type DataFrame; diagnostics contain residuals and shared genes.
    :raises ValueError: Matrices have invalid values, duplicate labels or no shared genes.
    """
    require_matrix(counts, positive_libraries=True)
    require_matrix(signature, positive_libraries=True)
    info = core_analysis(counts, signature)
    return attach_info(info['proportions_df'], info)


def run_info(result, *, keep=True):
    """Read reference overlap and reconstruction diagnostics.

    :param result: DataFrame returned by deconvolve.
    :param keep: Default True; False removes diagnostics from attrs.
    :returns: Diagnostic dictionary, empty after removal.
    """
    return read_info(result, keep=keep)


def proportions_figure(result):
    """Plot estimated cell-type proportions per sample.

    :param result: Sample-by-cell-type DataFrame from deconvolve.
    :returns: A matplotlib Figure, without writing files.
    :raises ValueError: The table cannot be plotted as numeric proportions.
    """
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    result.plot.bar(stacked=True, ax=ax)
    ax.set(ylabel='Estimated proportion', xlabel='Sample')
    fig.tight_layout()
    return fig
