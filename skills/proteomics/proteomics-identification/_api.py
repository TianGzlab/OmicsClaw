"""Filter and summarize existing peptide identifications."""
from pathlib import Path
import warnings
import pandas as pd
from skills.proteomics._lib import identification as core
from skills.proteomics._lib.table_info import attach, read_info

__all__ = ['read_table', 'filter_identifications', 'run_info', 'score_figure', 'demo_data']


def read_table(path: str | Path) -> pd.DataFrame:
    """Read peptide CSV/TSV; pass this function as reader= to read_input.

    :param path: Peptide table; txt and tsv suffixes select tab separation.
    :returns: Table with common MaxQuant column names normalized.
    :raises OSError: The file cannot be read.
    """
    return core.load_identification_results(Path(path))


def filter_identifications(data: pd.DataFrame, *, fdr_threshold: float = 0.01,
                           n_spectra: int | None = None) -> pd.DataFrame:
    """Filter peptide confidence values and return a new table.

    :param data: Existing peptide/protein rows with optional qvalue, q-value, q_value, PEP, pep or fdr.
    :param fdr_threshold: CLI default 0.01; PEP thresholding is not a global FDR estimate.
    :param n_spectra: Total spectra; CLI default None uses retained PSM count, not an observed identification rate.
    :returns: Filtered rows with the actual confidence column and summary in attrs.
    :raises ValueError: Threshold or spectrum count is invalid.
    """
    if not 0 <= fdr_threshold <= 1 or (n_spectra is not None and n_spectra < 0):
        raise ValueError('Confidence threshold must be in [0, 1] and n_spectra nonnegative')
    column = next((c for c in ('qvalue','q-value','q_value','PEP','pep','fdr') if c in data), None)
    if column is None:
        warnings.warn('No FDR/q-value column found; returning unfiltered identifications', UserWarning, stacklevel=2)
    result = core.filter_by_fdr(data.copy(), fdr_threshold)
    return attach(result, requested_method='confidence_filter',
                  executed_method='unfiltered' if column is None else 'confidence_filter',
                  fallback_reason='No confidence column' if column is None else None,
                  filter_column=column, spectra_count_estimated=n_spectra is None,
                  summary=core.compute_summary(result, n_spectra=n_spectra))


def run_info(table: pd.DataFrame, *, keep: bool = True) -> dict:
    """Read identification diagnostics.

    :param table: Filtered peptide table.
    :param keep: True preserves attrs; False removes diagnostics.
    :returns: A separate dictionary with filter provenance and summary.
    :raises TypeError: The input is not a DataFrame.
    """
    return read_info(table, keep=keep)


def score_figure(table: pd.DataFrame):
    """Plot peptide identification scores.

    :param table: Peptide table including score.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: score is absent.
    """
    from matplotlib.figure import Figure
    fig = Figure(figsize=(6,4))
    ax = fig.subplots()
    ax.hist(table['score'].dropna(), bins=25)
    ax.set(xlabel='Search score', ylabel='PSMs')
    return fig


def demo_data(*, random_state: int = 42) -> pd.DataFrame:
    """Simulate identifications for one thousand spectra.

    :param random_state: CLI seed 42; change for another simulation.
    :returns: Synthetic peptide identifications, not a search-engine result.
    :raises ValueError: The seed is invalid.
    """
    return core.demo_data(random_state=random_state)
