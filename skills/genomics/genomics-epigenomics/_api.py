"""In-memory epigenomics summaries with explicit file readers."""
from pathlib import Path
import pandas as pd
from skills.genomics._lib import epigenomics as core
from skills.genomics._lib.results import attach_info, read_info, require_columns

__all__ = ["read_records", "analyze", "run_info", "distribution_figure"]


def read_records(path: str | Path) -> pd.DataFrame:
    """Read records through read_input(path, reader=library.read_records).

    :param path: Existing input file in the format documented under Inputs and outputs.
    :returns: Parsed records as a DataFrame.
    :raises ValueError: Input values or file structure cannot be parsed.
    """
    path = Path(path)
    return core.parse_peaks_csv(path) if path.suffix.lower() == ".csv" else core.parse_peaks_bed(path)


def analyze(data: pd.DataFrame, *, assay: str = "chip-seq") -> pd.DataFrame:
    """Compute epigenomics summaries and return a new table, leaving data unchanged.

    :param data: Records containing chrom, start, end.
    :param assay: CLI default chip-seq; atac-seq and cut-tag change descriptive expectations.
    :returns: Result table with diagnostics and summary in attrs['run_info'].
    :raises ValueError: Required columns are absent or records are empty or invalid.
    """
    require_columns(data, ["chrom","start","end"])
    if assay not in {"chip-seq", "atac-seq", "cut-tag"}:
        raise ValueError("Unsupported assay")
    result = data.copy(deep=True)
    result["width"] = result.end - result.start
    if (result.width <= 0).any() or (result.start < 0).any():
        raise ValueError("Peaks require 0 <= start < end")
    summary = core.compute_peak_stats(result, assay=assay)
    return attach_info(result, summary, method="epigenomics")


def run_info(data: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return the analysis diagnostics and summary.

    :param data: Result returned by analyze.
    :param keep: Keep diagnostics by default; the CLI passes False.
    :returns: Independent diagnostics dictionary.
    :raises ValueError: analyze has not populated diagnostics.
    """
    return read_info(data, keep=keep)


def distribution_figure(data: pd.DataFrame):
    """Plot width values without writing files.

    :param data: Result table containing width.
    :returns: Matplotlib Figure.
    :raises ValueError: The value column is absent or the table is empty.
    """
    from matplotlib.figure import Figure
    require_columns(data, ["width"])
    fig = Figure(figsize=(6, 3))
    ax = fig.subplots()
    ax.hist(pd.to_numeric(data["width"], errors="raise"), bins=min(20, len(data)))
    ax.set(xlabel="width", ylabel="Records")
    return fig
