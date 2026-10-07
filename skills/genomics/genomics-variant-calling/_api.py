"""In-memory variant-calling summaries with explicit file readers."""
from pathlib import Path
import pandas as pd
from skills.genomics._lib import variant_calling as core
from skills.genomics._lib.results import attach_info, read_info, require_columns

__all__ = ["read_records", "analyze", "run_info", "distribution_figure"]


def read_records(path: str | Path) -> pd.DataFrame:
    """Read records through read_input(path, reader=library.read_records).

    :param path: Input file in the format documented under Inputs and outputs.

    :returns: Parsed records as a DataFrame.
    :raises ValueError: Input values or file structure cannot be parsed.
    """
    return core.parse_variants(Path(path))


def analyze(data: pd.DataFrame) -> pd.DataFrame:
    """Compute variant-calling summaries and return a new table, leaving data unchanged.

    :param data: Records containing chrom, pos, ref, alt, qual, filter, type.

    :returns: Result table with diagnostics and summary in attrs['run_info'].
    :raises ValueError: Required columns are absent or records are empty or invalid.
    """
    require_columns(data, ["chrom","pos","ref","alt","qual","filter","type"])
    result, summary = core.variant_stats(data.copy(deep=True))
    return attach_info(result, summary, method="variant-calling")


def run_info(data: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return analysis diagnostics and summary.

    :param data: Result returned by analyze.
    :param keep: Keep diagnostics by default; the CLI passes False.
    :returns: Independent diagnostics dictionary.
    :raises ValueError: analyze has not populated diagnostics.
    """
    return read_info(data, keep=keep)


def distribution_figure(data: pd.DataFrame):
    """Plot qual values without writing files.

    :param data: Result table containing qual.
    :returns: Matplotlib Figure.
    :raises ValueError: The value column is absent or table is empty.
    """
    from matplotlib.figure import Figure
    require_columns(data, ["qual"])
    fig = Figure(figsize=(6, 3))
    ax = fig.subplots()
    ax.hist(pd.to_numeric(data["qual"], errors="raise"), bins=min(20, len(data)))
    ax.set(xlabel="qual", ylabel="Records")
    return fig
