"""In-memory variant-annotation summaries with explicit file readers."""
from pathlib import Path
import pandas as pd
from skills.genomics._lib import variant_annotation as core
from skills.genomics._lib.results import attach_info, read_info, require_columns

__all__ = ["read_records", "analyze", "run_info", "distribution_figure"]


def read_records(path: str | Path) -> pd.DataFrame:
    """Read records through read_input(path, reader=library.read_records).

    :param path: Existing input file in the format documented under Inputs and outputs.
    :returns: Parsed records as a DataFrame.
    :raises ValueError: Input values or file structure cannot be parsed.
    """
    return pd.read_csv(path)


def analyze(data: pd.DataFrame) -> pd.DataFrame:
    """Compute variant-annotation summaries and return a new table, leaving data unchanged.

    :param data: Records containing impact, consequence, gene, cadd_phred.

    :returns: Result table with diagnostics and summary in attrs['run_info'].
    :raises ValueError: Required columns are absent or records are empty or invalid.
    """
    require_columns(data, ["impact","consequence","gene","cadd_phred"])
    result = data.copy(deep=True)
    if (result.consequence == "missense_variant").any():
        require_columns(result, ["sift_prediction", "polyphen_prediction"])
    summary = core.compute_annotation_stats(result)
    return attach_info(result, summary, method="variant-annotation")


def run_info(data: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return the analysis diagnostics and summary.

    :param data: Result returned by analyze.
    :param keep: Keep diagnostics by default; the CLI passes False.
    :returns: Independent diagnostics dictionary.
    :raises ValueError: analyze has not populated diagnostics.
    """
    return read_info(data, keep=keep)


def distribution_figure(data: pd.DataFrame):
    """Plot cadd_phred values without writing files.

    :param data: Result table containing cadd_phred.
    :returns: Matplotlib Figure.
    :raises ValueError: The value column is absent or the table is empty.
    """
    from matplotlib.figure import Figure
    require_columns(data, ["cadd_phred"])
    fig = Figure(figsize=(6, 3))
    ax = fig.subplots()
    ax.hist(pd.to_numeric(data["cadd_phred"], errors="raise"), bins=min(20, len(data)))
    ax.set(xlabel="cadd_phred", ylabel="Records")
    return fig
