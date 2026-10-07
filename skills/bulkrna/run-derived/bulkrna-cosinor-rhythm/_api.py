"""Descriptive fixed-period cosinor fits on a gene-indexed time course."""
import re
import numpy as np
from skills.bulkrna._lib.cosinor import calculate
from skills.bulkrna._lib.results import attach_info, read_info

__all__ = ['fit', 'run_info', 'rhythm_figure']


def fit(timecourse):
    """Fit a fixed 24-hour sinusoid independently to each gene.

    :param timecourse: Gene-indexed DataFrame with T00_R1-style sample columns.
    :returns: Parameter DataFrame with descriptive rhythmic flags and diagnostics.
    :raises ValueError: Empty data, missing time columns or infinite expression.
    """
    samples = [c for c in timecourse if re.fullmatch(r'T\d{2}_R\d+', str(c))]
    if timecourse.empty or not samples:
        raise ValueError('A nonempty time course with T00_R1-style columns is required')
    if timecourse.index.isna().any():
        raise ValueError('Gene identifiers must be present')
    values = timecourse[samples].to_numpy(dtype=float)
    if np.isinf(values).any():
        raise ValueError('Expression must be finite or missing')
    result, info = calculate(timecourse.copy().rename_axis('gene').reset_index())
    return attach_info(result, info)


def run_info(result, *, keep=True):
    """Read gene counts and time-column filtering decisions.

    :param result: DataFrame returned by fit.
    :param keep: Default True; False removes diagnostic attrs.
    :returns: Diagnostic dictionary, empty after removal.
    """
    return read_info(result, keep=keep)


def rhythm_figure(result):
    """Plot fitted amplitude against phase, without writing files.

    :param result: Parameter DataFrame returned by fit.
    :returns: matplotlib Figure.
    :raises KeyError: Parameter columns are missing.
    """
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.scatter(result['peak_phase_hours'], result['amplitude'])
    ax.set(xlabel='Peak phase (hours)', ylabel='Amplitude', xlim=(0, 24))
    return fig
