"""In-memory phasing summaries with explicit file readers."""
from pathlib import Path
import pandas as pd
from skills.genomics._lib import phasing as core
from skills.genomics._lib.results import attach_info, read_info, require_columns

__all__ = ["read_records", "analyze", "run_info", "distribution_figure"]


def read_records(path: str | Path) -> pd.DataFrame:
    """Read records through read_input(path, reader=library.read_records).

    :param path: Existing input file in the format documented under Inputs and outputs.
    :returns: Parsed records as a DataFrame.
    :raises ValueError: Input values or file structure cannot be parsed.
    """
    variants, _ = core.parse_phased_vcf(Path(path))
    return pd.DataFrame(variants, columns=["chrom", "pos", "ref", "alt", "gt", "is_phased", "is_het", "phase_set"])


def analyze(data: pd.DataFrame) -> pd.DataFrame:
    """Compute phasing summaries and return a new table, leaving data unchanged.

    A header-only VCF yields an empty table with zero-valued summary metrics.

    :param data: Records containing chrom, pos, gt, is_phased, is_het, phase_set.

    :returns: Result table with diagnostics and summary in attrs['run_info'].
    :raises ValueError: Required columns are absent or records are invalid.
    """
    require_columns(data, ["chrom","pos","gt","is_phased","is_het","phase_set"], allow_empty=True)
    result = data.copy(deep=True)
    summary = core.compute_phasing_stats(result.to_dict("records"), core.group_blocks(result))
    return attach_info(result, summary, method="phasing")


def run_info(data: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return the analysis diagnostics and summary.

    :param data: Result returned by analyze.
    :param keep: Keep diagnostics by default; the CLI passes False.
    :returns: Independent diagnostics dictionary.
    :raises ValueError: analyze has not populated diagnostics.
    """
    return read_info(data, keep=keep)


def distribution_figure(data: pd.DataFrame):
    """Plot pos values without writing files.

    :param data: Result table containing pos.
    :returns: Matplotlib Figure.
    :raises ValueError: The value column is absent or the table is empty.
    """
    from matplotlib.figure import Figure
    require_columns(data, ["pos"])
    fig = Figure(figsize=(6, 3))
    ax = fig.subplots()
    ax.hist(pd.to_numeric(data["pos"], errors="raise"), bins=min(20, len(data)))
    ax.set(xlabel="pos", ylabel="Records")
    return fig
