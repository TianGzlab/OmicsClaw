"""Classify existing PTM-site localizations."""
import pandas as pd
from skills.proteomics._lib import ptm as core
from skills.proteomics._lib.table_info import attach, read_info

__all__ = ['classify_sites', 'run_info', 'class_figure', 'demo_data']


def classify_sites(data: pd.DataFrame, *, loc_threshold: float = 0.75) -> pd.DataFrame:
    """Return a new PTM table with localization confidence classes.

    :param data: Site rows with protein and ptm_type; localization_probability is optional.
    :param loc_threshold: CLI default 0.75 for Class I; Class II starts at 0.50.
    :returns: Classified sites with summary diagnostics in attrs.
    :raises ValueError: Required columns are absent or the threshold is outside [0.5, 1].
    """
    if not 0.5 <= loc_threshold <= 1:
        raise ValueError('loc_threshold must be in [0.5, 1]')
    if data.empty:
        raise ValueError('A nonempty PTM site table is required')
    result, summary = core.analyse_ptm_sites(data, loc_threshold)
    return attach(result, loc_threshold=loc_threshold, localization_checked='localization_probability' in data,
                  summary=summary)


def run_info(table: pd.DataFrame, *, keep: bool = True) -> dict:
    """Read PTM classification diagnostics.

    :param table: Classified PTM sites.
    :param keep: True preserves attrs; False removes diagnostics.
    :returns: A separate dictionary with localization threshold and summary.
    :raises TypeError: The input is not a DataFrame.
    """
    return read_info(table, keep=keep)


def class_figure(table: pd.DataFrame):
    """Plot site counts by localization class.

    :param table: Classified PTM sites containing site_class.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: site_class is absent.
    """
    from matplotlib.figure import Figure
    fig = Figure(figsize=(6,4))
    ax = fig.subplots()
    counts = table['site_class'].value_counts().sort_index()
    ax.bar(counts.index, counts.values)
    ax.set(ylabel='Sites')
    return fig


def demo_data(*, random_state: int = 42) -> pd.DataFrame:
    """Generate synthetic PTM sites in memory.

    :param random_state: CLI seed 42; change for another simulation.
    :returns: Two hundred synthetic site records.
    :raises ValueError: The seed is invalid.
    """
    return core.demo_data(random_state=random_state)
