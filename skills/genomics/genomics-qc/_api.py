"""In-memory qc summaries with explicit file readers."""
from pathlib import Path
import pandas as pd
from skills.genomics._lib import qc as core
from skills.genomics._lib.results import attach_info, read_info, require_columns

__all__ = ["read_records", "analyze", "run_info", "distribution_figure"]


def read_records(path: str | Path, *, max_reads: int = 500_000) -> pd.DataFrame:
    """Read records through read_input(path, reader=library.read_records).

    :param path: Input file in the format documented under Inputs and outputs.
    :param max_reads: CLI default 500000 limits records materialized in memory.
    :returns: Parsed records as a DataFrame.
    :raises ValueError: Input values or file structure cannot be parsed.
    """
    records = []
    import gzip
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as handle:
        for _ in range(max_reads):
            header = handle.readline()
            if not header:
                break
            sequence = handle.readline().strip()
            plus = handle.readline()
            quality = handle.readline().strip()
            if not header.startswith("@") or not plus.startswith("+") or len(sequence) != len(quality) or not sequence:
                raise ValueError("Malformed or truncated FASTQ record")
            records.append({"sequence": sequence, "quality": quality})
    return pd.DataFrame(records, columns=["sequence", "quality"])


def analyze(data: pd.DataFrame, *, max_reads: int = 500_000) -> pd.DataFrame:
    """Compute qc summaries and return a new table, leaving data unchanged.

    :param data: Records containing sequence, quality.
    :param max_reads: CLI default 500000 limits the analyzed reads.
    :returns: Result table with diagnostics and summary in attrs['run_info'].
    :raises ValueError: Required columns are absent or records are empty or invalid.
    """
    require_columns(data, ["sequence","quality"])
    if max_reads <= 0:
        raise ValueError("max_reads must be positive")
    if (data.sequence.str.len() != data.quality.str.len()).any() or (data.sequence.str.len() == 0).any():
        raise ValueError("Sequence and quality lengths must match and be nonzero")
    summary = core.qc_records(data, max_reads=max_reads)
    result = pd.DataFrame([{k: v for k, v in summary.items() if k not in ("per_base_quality", "read_length_hist")}])
    return attach_info(result, summary, method="qc")


def run_info(data: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return analysis diagnostics and summary.

    :param data: Result returned by analyze.
    :param keep: Keep diagnostics by default; the CLI passes False.
    :returns: Independent diagnostics dictionary.
    :raises ValueError: analyze has not populated diagnostics.
    """
    return read_info(data, keep=keep)


def distribution_figure(data: pd.DataFrame):
    """Plot mean_quality values without writing files.

    :param data: Result table containing mean_quality.
    :returns: Matplotlib Figure.
    :raises ValueError: The value column is absent or table is empty.
    """
    from matplotlib.figure import Figure
    require_columns(data, ["mean_quality"])
    fig = Figure(figsize=(6, 3))
    ax = fig.subplots()
    ax.hist(pd.to_numeric(data["mean_quality"], errors="raise"), bins=min(20, len(data)))
    ax.set(xlabel="mean_quality", ylabel="Records")
    return fig
