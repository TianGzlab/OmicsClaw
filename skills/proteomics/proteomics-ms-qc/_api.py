"""Quality control of protein intensity tables."""
import pandas as pd
from skills.proteomics._lib import ms_qc as core
from skills.proteomics._lib.table_info import attach, read_info

__all__ = ['quality_control', 'run_info', 'completeness_figure', 'demo_data']


def quality_control(data: pd.DataFrame) -> pd.DataFrame:
    """Return a one-row QC table without changing input intensities.

    :param data: Protein rows and numeric intensity columns; metadata-like names are excluded when possible.
    :returns: Scalar QC metrics; per-sample completeness and selected columns are in run_info.
    :raises ValueError: There are no proteins or numeric intensity columns.
    """
    if data.empty:
        raise ValueError('A nonempty protein intensity table is required')
    summary, _ = core.qc_proteomics(data)
    scalar = {k:v for k,v in summary.items() if k not in ('sample_columns','per_sample_completeness')}
    return attach(pd.DataFrame([scalar]), summary=summary)


def run_info(table: pd.DataFrame, *, keep: bool = True) -> dict:
    """Read QC diagnostics.

    :param table: Output of quality_control.
    :param keep: True preserves attrs; False removes diagnostics.
    :returns: A separate dictionary with selected sample columns and completeness.
    :raises TypeError: The input is not a DataFrame.
    """
    return read_info(table, keep=keep)


def completeness_figure(table: pd.DataFrame):
    """Plot detected protein percentages per sample.

    :param table: QC table retaining run_info attributes.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: QC diagnostics are absent.
    """
    from matplotlib.figure import Figure
    values = read_info(table)['summary']['per_sample_completeness']
    fig = Figure(figsize=(6,4))
    ax = fig.subplots()
    ax.bar(list(values), list(values.values()))
    ax.set(ylabel='Detected proteins (%)', ylim=(0,100))
    return fig


def demo_data(*, random_state: int = 42) -> pd.DataFrame:
    """Generate a synthetic protein intensity table.

    :param random_state: CLI seed 42; change for another simulation.
    :returns: One hundred proteins and five sample columns.
    :raises ValueError: The seed is invalid.
    """
    return core.demo_data(random_state=random_state)
