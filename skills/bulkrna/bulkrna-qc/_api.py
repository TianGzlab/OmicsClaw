"""Bulk count-matrix QC without file output."""
import pandas as pd
from skills.bulkrna._lib.qc import core_analysis
from skills.bulkrna._lib.results import attach_info, read_info, require_matrix

__all__ = ['assess', 'run_info', 'normalized_counts', 'library_figure']


def assess(counts):
    """Measure library size and detection on raw counts without changing input.

    :param counts: Gene-by-sample nonnegative integer DataFrame with unique labels.
    :returns: Sample-indexed DataFrame with QC metrics and diagnostic attrs.
    :raises ValueError: The matrix is invalid or a sample has no counts.
    """
    require_matrix(counts, counts=True, positive_libraries=True)
    info = core_analysis(counts)
    result = pd.DataFrame.from_dict(info['per_sample_stats'], orient='index')
    result.index.name = 'sample'
    return attach_info(result, info)


def run_info(result, *, keep=True):
    """Read QC diagnostics and auxiliary matrices.

    :param result: DataFrame returned by assess.
    :param keep: Default True; False removes diagnostics from result.attrs.
    :returns: A diagnostic dictionary, empty when no record remains.
    """
    return read_info(result, keep=keep)


def normalized_counts(result):
    """Return CPM for visualization, not differential-expression input.

    :param result: DataFrame returned by assess with its diagnostics retained.
    :returns: New gene-by-sample CPM DataFrame.
    :raises KeyError: QC diagnostics have been removed.
    """
    return run_info(result)['cpm'].copy()


def library_figure(result):
    """Plot total counts per sample without saving files.

    :param result: QC table returned by assess.
    :returns: A matplotlib Figure; the caller saves and closes it.
    :raises KeyError: total_counts is missing.
    """
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.bar(result.index.astype(str), result['total_counts'])
    ax.set(xlabel='Sample', ylabel='Total counts')
    ax.tick_params(axis='x', rotation=90)
    fig.tight_layout()
    return fig
