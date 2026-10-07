"""Summarize supplied splicing tests without performing new significance tests."""
import numpy as np
from skills.bulkrna._lib.splicing import core_analysis
from skills.bulkrna._lib.results import attach_info, read_info

__all__ = ['summarize', 'run_info', 'significant_events', 'volcano_figure']


def summarize(events, *, dpsi_cutoff=0.1, padj_cutoff=0.05):
    """Summarize upstream event tests without changing the table.

    :param events: DataFrame with gene, event_type, delta_psi and padj columns.
    :param dpsi_cutoff: CLI default 0.1; absolute delta-PSI must exceed it.
    :param padj_cutoff: CLI default 0.05; adjusted p values must be below it.
    :returns: Copy of events with diagnostics in attrs.
    :raises ValueError: Required columns, probabilities or thresholds are invalid.
    """
    required = {'gene', 'event_type', 'delta_psi', 'padj'}
    if required - set(events.columns):
        raise ValueError(f'Missing event columns: {sorted(required - set(events.columns))}')
    if not 0 <= dpsi_cutoff <= 1 or not 0 < padj_cutoff <= 1:
        raise ValueError('Invalid dpsi_cutoff or padj_cutoff')
    if not events['padj'].dropna().between(0, 1).all():
        raise ValueError('padj must be in [0, 1] or missing')
    if not events['delta_psi'].dropna().between(-1, 1).all():
        raise ValueError('delta_psi must be in [-1, 1] or missing')
    return attach_info(events, core_analysis(events, dpsi_cutoff=dpsi_cutoff, padj_cutoff=padj_cutoff))


def run_info(result, *, keep=True):
    """Read event counts and threshold diagnostics.

    :param result: DataFrame returned by summarize.
    :param keep: Default True; False removes diagnostic attrs.
    :returns: Diagnostic dictionary, empty after removal.
    """
    return read_info(result, keep=keep)


def significant_events(result):
    """Return events passing both strict thresholds.

    :param result: DataFrame returned by summarize, with diagnostics retained.
    :returns: New filtered DataFrame.
    :raises KeyError: Diagnostics are absent.
    """
    return run_info(result)['significant_events_df'].copy()


def volcano_figure(result):
    """Plot delta-PSI against upstream adjusted significance.

    :param result: Event table with delta_psi and padj.
    :returns: A matplotlib Figure, without writing files.
    :raises KeyError: Required columns are absent.
    """
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.scatter(result['delta_psi'], -np.log10(result['padj'].clip(lower=1e-300)))
    ax.set(xlabel='Delta PSI', ylabel='-log10 adjusted p')
    return fig
