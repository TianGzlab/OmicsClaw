"""Peak detection from tabular chromatographic signals."""
from skills.metabolomics._lib.peaks import detect_peaks_table

__all__ = ['detect_peaks', 'run_info', 'peaks_figure']


def detect_peaks(data, *, sample_cols=None, prominence=1e4, height=None, distance=5):
    """Detect per-sample peaks after sorting rows by retention time.

    :param data: DataFrame with mz, rt and numeric sample intensities.
    :param sample_cols: Explicit columns; None uses the CLI intensity/sample name detection.
    :param prominence: CLI default 10000; adjust to the intensity scale.
    :param height: CLI default None; optionally require a minimum peak height.
    :param distance: CLI default 5; minimum separation in sorted row positions, not seconds.
    :returns: A new peak DataFrame with diagnostics in attrs['run_info'].
    :raises ValueError: No sample columns match or peak parameters are invalid.
    """
    result = detect_peaks_table(data, sample_cols=sample_cols, prominence=prominence, height=height, distance=distance)
    result.attrs['run_info'] = {'n_points': len(data), 'n_samples': result['sample'].nunique(),
                              'n_peaks': len(result), 'mean_prominence': float(result['prominence'].mean()) if len(result) else 0.}
    return result


def peaks_figure(data):
    """Plot detected peak intensity against retention time.

    :param data: Peak table returned by detect_peaks.
    :returns: A matplotlib Figure.
    :raises KeyError: Required peak columns are absent.
    """
    from matplotlib.figure import Figure
    fig = Figure(figsize=(7, 4))
    ax = fig.subplots()
    for sample, rows in data.groupby('sample', sort=False):
        ax.scatter(rows['rt'], rows['intensity'], label=sample)
    ax.set(xlabel='Retention time', ylabel='Peak intensity')
    if len(data):
        ax.legend()
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
