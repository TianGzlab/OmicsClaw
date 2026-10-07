"""In-memory vcf-operations summaries with explicit file readers."""
from pathlib import Path
import pandas as pd
from skills.genomics._lib import vcf_operations as core
from skills.genomics._lib.results import attach_info, read_info, require_columns

__all__ = ["read_records", "analyze", "run_info", "distribution_figure"]


def read_records(path: str | Path) -> pd.DataFrame:
    """Read records through read_input(path, reader=library.read_records).

    :param path: Input file in the format documented under Inputs and outputs.

    :returns: Parsed records as a DataFrame.
    :raises ValueError: Input values or file structure cannot be parsed.
    """
    records, headers = core.parse_vcf(Path(path))
    result = pd.DataFrame(records)
    result.attrs["vcf_headers"] = headers
    return result


def analyze(data: pd.DataFrame, *, min_qual: float = 0.0, min_dp: int = 0) -> pd.DataFrame:
    """Compute vcf-operations summaries and return a new table, leaving data unchanged.

    :param data: Records containing chrom, pos, ref, alt, qual, filter, dp, type.
    :param min_qual: CLI default 0 keeps all QUAL values; raise to filter.
    :param min_dp: CLI default 0 keeps all INFO/DP values; FORMAT/DP is ignored.
    :returns: Result table with diagnostics and summary in attrs['run_info'].
    :raises ValueError: Required columns are absent or records are empty or invalid.
    """
    require_columns(data, ["chrom","pos","ref","alt","qual","filter","dp","type"])
    if min_qual < 0 or min_dp < 0:
        raise ValueError("min_qual and min_dp must be nonnegative")
    result = data.loc[(data.qual >= min_qual) & (data.dp >= min_dp)].copy(deep=True)
    if result.empty:
        raise ValueError("No variants pass the requested filters")
    summary = core.compute_vcf_stats(result.to_dict("records"))
    return attach_info(result, summary, method="vcf-operations")


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
