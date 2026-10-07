"""Segment genomic copy ratios without file output."""
from pathlib import Path
import numpy as np
import pandas as pd
from skills.genomics._lib import cnv
from skills.genomics._lib.results import attach_info, read_info, require_columns

__all__ = ["read_bins", "analyze", "run_info", "copy_ratio_figure"]


def read_bins(path: str | Path) -> pd.DataFrame:
    """Read a bin CSV through read_input(path, reader=library.read_bins).

    :param path: CSV containing chrom, start, end and log2_ratio.
    :returns: Bin table.
    :raises ValueError: The CSV cannot be parsed.
    """
    return pd.read_csv(path)


def analyze(data: pd.DataFrame, *, method: str = "cbs", alpha: float = 0.01) -> pd.DataFrame:
    """Return new CNV segments from bin-level log2 ratios; leave data unchanged.

    :param data: Bins with chrom, start, end and finite log2_ratio.
    :param method: CLI default cbs, or none to classify individual bins.
    :param alpha: CLI default 0.01; smaller values require stronger splits.
    :returns: Segments with cn_state, estimated_cn and attrs['run_info'].
    :raises ValueError: Columns, coordinates, method or alpha are invalid.
    """
    require_columns(data, ["chrom", "start", "end", "log2_ratio"])
    if method not in {"cbs", "none"}:
        raise ValueError("method must be cbs or none")
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie between zero and one")
    if not np.isfinite(data[["start", "end", "log2_ratio"]].to_numpy(dtype=float)).all():
        raise ValueError("Coordinates and log2_ratio must be finite")
    if (data.start < 0).any() or (data.end <= data.start).any():
        raise ValueError("Bins require 0 <= start < end")
    result, summary = cnv.run_cnv_analysis(data, method=method, alpha=alpha)
    return attach_info(result, summary, method=method)


def run_info(data: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return analysis diagnostics and numeric summary.

    :param data: Result returned by analyze.
    :param keep: Keep diagnostics by default; the CLI passes False.
    :returns: Independent copy of run diagnostics.
    :raises ValueError: analyze has not populated diagnostics.
    """
    return read_info(data, keep=keep)


def copy_ratio_figure(data: pd.DataFrame):
    """Plot segment log2 ratios in table order without writing a file.

    :param data: Segment table returned by analyze.
    :returns: Matplotlib Figure.
    :raises ValueError: log2_ratio is absent or the table is empty.
    """
    from matplotlib.figure import Figure
    require_columns(data, ["log2_ratio"])
    fig = Figure(figsize=(7, 3))
    ax = fig.subplots()
    ax.scatter(range(len(data)), data.log2_ratio)
    ax.axhline(0, color="gray")
    ax.set(xlabel="Segment", ylabel="Log2 copy ratio")
    return fig
