"""In-memory assembly summaries with explicit file readers."""
from pathlib import Path
import pandas as pd
from skills.genomics._lib import assembly as core
from skills.genomics._lib.results import attach_info, read_info, require_columns

__all__ = ["read_records", "analyze", "run_info", "distribution_figure"]


def read_records(path: str | Path) -> pd.DataFrame:
    """Read records through read_input(path, reader=library.read_records).

    :param path: Existing input file in the format documented under Inputs and outputs.
    :returns: Parsed records as a DataFrame.
    :raises ValueError: Input values or file structure cannot be parsed.
    """
    return pd.DataFrame(core.parse_fasta(Path(path)), columns=["contig", "sequence"])


def analyze(data: pd.DataFrame, *, genome_size: int = 0) -> pd.DataFrame:
    """Compute assembly summaries and return a new table, leaving data unchanged.

    :param data: Records containing contig, sequence.
    :param genome_size: CLI default 0 omits completeness; otherwise expected genome bases.
    :returns: Result table with diagnostics and summary in attrs['run_info'].
    :raises ValueError: Required columns are absent or records are empty or invalid.
    """
    require_columns(data, ["contig","sequence"])
    if genome_size < 0:
        raise ValueError("genome_size must be nonnegative")
    sequences = list(data[["contig", "sequence"]].itertuples(index=False, name=None))
    summary = core.compute_assembly_stats(sequences, genome_size=genome_size)
    result = pd.DataFrame({"contig": data.contig, "length": data.sequence.str.len()}).sort_values("length", ascending=False)
    return attach_info(result, summary, method="assembly")


def run_info(data: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return the analysis diagnostics and summary.

    :param data: Result returned by analyze.
    :param keep: Keep diagnostics by default; the CLI passes False.
    :returns: Independent diagnostics dictionary.
    :raises ValueError: analyze has not populated diagnostics.
    """
    return read_info(data, keep=keep)


def distribution_figure(data: pd.DataFrame):
    """Plot length values without writing files.

    :param data: Result table containing length.
    :returns: Matplotlib Figure.
    :raises ValueError: The value column is absent or the table is empty.
    """
    from matplotlib.figure import Figure
    require_columns(data, ["length"])
    fig = Figure(figsize=(6, 3))
    ax = fig.subplots()
    ax.hist(pd.to_numeric(data["length"], errors="raise"), bins=min(20, len(data)))
    ax.set(xlabel="length", ylabel="Records")
    return fig
