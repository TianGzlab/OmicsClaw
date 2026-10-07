"""In-memory alignment summaries with explicit file readers."""
from pathlib import Path
import pandas as pd
from skills.genomics._lib import alignment as core
from skills.genomics._lib.results import attach_info, read_info, require_columns

__all__ = ["read_records", "analyze", "run_info", "distribution_figure"]


def read_records(path: str | Path) -> pd.DataFrame:
    """Read records through read_input(path, reader=library.read_records).

    :param path: Input file in the format documented under Inputs and outputs.

    :returns: Parsed records as a DataFrame.
    :raises ValueError: Input values or file structure cannot be parsed.
    """
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("@"):
                continue
            fields = line.strip().split("\t")
            if len(fields) >= 11:
                records.append({"flag": int(fields[1]), "mapq": int(fields[4]), "tlen": fields[8]})
    return pd.DataFrame(records, columns=["flag", "mapq", "tlen"])


def analyze(data: pd.DataFrame) -> pd.DataFrame:
    """Compute alignment summaries and return a new table, leaving data unchanged.

    :param data: Records containing flag, mapq, tlen.

    :returns: Result table with diagnostics and summary in attrs['run_info'].
    :raises ValueError: Required columns are absent or records are empty or invalid.
    """
    require_columns(data, ["flag","mapq","tlen"])
    summary = core.alignment_stats(data)
    result = pd.DataFrame([summary])
    return attach_info(result, summary, method="alignment")


def run_info(data: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return analysis diagnostics and summary.

    :param data: Result returned by analyze.
    :param keep: Keep diagnostics by default; the CLI passes False.
    :returns: Independent diagnostics dictionary.
    :raises ValueError: analyze has not populated diagnostics.
    """
    return read_info(data, keep=keep)


def distribution_figure(data: pd.DataFrame):
    """Plot mapping_rate_pct values without writing files.

    :param data: Result table containing mapping_rate_pct.
    :returns: Matplotlib Figure.
    :raises ValueError: The value column is absent or table is empty.
    """
    from matplotlib.figure import Figure
    require_columns(data, ["mapping_rate_pct"])
    fig = Figure(figsize=(6, 3))
    ax = fig.subplots()
    ax.hist(pd.to_numeric(data["mapping_rate_pct"], errors="raise"), bins=min(20, len(data)))
    ax.set(xlabel="mapping_rate_pct", ylabel="Records")
    return fig
