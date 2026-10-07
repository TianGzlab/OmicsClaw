"""Normalize protein-table column names and search-engine flags."""
from pathlib import Path
import pandas as pd
from skills.proteomics._lib import data_import as core
from skills.proteomics._lib.table_info import attach, read_info

__all__ = ['read_table', 'standardize', 'run_info', 'intensity_figure', 'demo_data']


def read_table(path: str | Path) -> pd.DataFrame:
    """Read a CSV or TSV; pass this function as reader= to read_input.

    :param path: Search-engine output file; the first line selects comma or tab separation.
    :returns: Unmodified input columns as a DataFrame.
    :raises OSError: The file cannot be read.
    """
    return pd.read_csv(path, sep=core._detect_separator(Path(path)))


def standardize(data: pd.DataFrame, *, format: str = 'maxquant') -> pd.DataFrame:
    """Return a standardized copy of a search-engine protein table.

    :param data: Original protein table with engine-specific column names.
    :param format: CLI default maxquant; fragpipe, diann and generic use their own mappings.
    :returns: Protein table; MaxQuant reverse, contaminant and site-only flags are filtered.
    :raises ValueError: The format is unsupported.
    """
    result = core._dispatch_import(format, data.copy())
    numeric = result.select_dtypes(include='number').columns
    intensity = [c for c in numeric if any(k in c.lower() for k in ('intensity','lfq','int_','abundance'))]
    return attach(result, n_input=len(data), n_filtered=len(data)-len(result),
                  summary={'format':format,'n_proteins':len(result),'n_columns':len(result.columns),'intensity_columns':len(intensity)})


def run_info(table: pd.DataFrame, *, keep: bool = True) -> dict:
    """Read import diagnostics.

    :param table: Standardized protein table.
    :param keep: True preserves attrs; False removes diagnostics.
    :returns: A separate diagnostic dictionary.
    :raises TypeError: The input is not a DataFrame.
    """
    return read_info(table, keep=keep)


def intensity_figure(table: pd.DataFrame):
    """Plot numeric column medians for checking an imported table.

    :param table: Standardized protein table; numeric metadata is included.
    :returns: A matplotlib Figure without writing files.
    :raises TypeError: The input is not a DataFrame.
    """
    from matplotlib.figure import Figure
    fig = Figure(figsize=(7,4))
    ax = fig.subplots()
    values = table.select_dtypes(include='number').median()
    ax.bar(values.index, values.values)
    ax.tick_params(axis='x', labelrotation=90)
    ax.set(ylabel='Median value')
    fig.tight_layout()
    return fig


def demo_data(*, random_state: int = 42) -> pd.DataFrame:
    """Generate a synthetic MaxQuant table in memory.

    :param random_state: CLI seed 42; change for another simulation.
    :returns: Two hundred protein rows, including five flagged rows.
    :raises ValueError: The seed is invalid.
    """
    return core.demo_data(random_state=random_state)
