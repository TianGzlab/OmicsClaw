"""Summarize existing cross-link identifications and measured distances."""
import pandas as pd
import numpy as np
from skills.proteomics._lib import structural as core
from skills.proteomics._lib.table_info import attach, read_info

__all__ = ['analyse_crosslinks', 'run_info', 'distance_figure', 'demo_data']


def analyse_crosslinks(data: pd.DataFrame, *, fdr_threshold: float = 0.05,
                       crosslinker: str = 'DSS') -> pd.DataFrame:
    """Return filtered crosslinks with protein-pair and optional distance classifications.

    :param data: Crosslink rows with protein_a and protein_b, optional fdr and distance_angstrom.
    :param fdr_threshold: CLI default 0.05; filters only when an fdr column is present.
    :param crosslinker: CLI default DSS; BS3, DSSO and DSBU use 30 A, EDC uses 20 A.
    :returns: New crosslink table; absent distance evidence remains unchecked in run_info.
    :raises ValueError: Protein identifiers, crosslinker or confidence threshold are invalid.
    """
    if not {'protein_a','protein_b'} <= set(data.columns):
        raise ValueError('protein_a and protein_b columns are required')
    if data[['protein_a','protein_b']].isna().any().any():
        raise ValueError('protein_a and protein_b must contain identifiers for every row')
    if crosslinker not in core.CROSSLINKER_CONSTRAINTS or not 0 <= fdr_threshold <= 1:
        raise ValueError('Unknown crosslinker or fdr_threshold outside [0, 1]')
    if 'distance_angstrom' in data:
        distances = pd.to_numeric(data['distance_angstrom'], errors='raise')
        if np.isinf(distances).any() or (distances.dropna() < 0).any():
            raise ValueError('Distances must be finite, nonnegative or missing')
        data = data.assign(distance_angstrom=distances)
    result, summary = core.analyse_crosslinks(data, fdr_threshold, crosslinker)
    n_checked = int(result['distance_angstrom'].notna().sum()) if 'distance_angstrom' in result else 0
    checked = n_checked > 0
    if not checked:
        for key in ('n_constraint_satisfied','n_constraint_violated','constraint_satisfaction_rate'):
            summary[key] = None
    return attach(result, fdr_checked='fdr' in data, distance_checked=checked,
                  n_distance_checked=n_checked, n_distance_unchecked=len(result) - n_checked,
                  summary=summary)


def run_info(table: pd.DataFrame, *, keep: bool = True) -> dict:
    """Read crosslink analysis diagnostics.

    :param table: Output of analyse_crosslinks.
    :param keep: True preserves attrs; False removes diagnostics.
    :returns: A separate dictionary stating which optional checks ran.
    :raises TypeError: The input is not a DataFrame.
    """
    return read_info(table, keep=keep)


def distance_figure(table: pd.DataFrame):
    """Plot measured crosslink distances.

    :param table: Crosslinks containing distance_angstrom.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: distance_angstrom is absent.
    """
    from matplotlib.figure import Figure
    fig = Figure(figsize=(6,4))
    ax = fig.subplots()
    ax.hist(table['distance_angstrom'].dropna(), bins=25)
    ax.set(xlabel='Distance (angstrom)', ylabel='Crosslinks')
    return fig


def demo_data(*, random_state: int = 42) -> pd.DataFrame:
    """Generate synthetic crosslink records in memory.

    :param random_state: CLI seed 42; change for another simulation.
    :returns: Two hundred crosslinks with simulated distances and confidence.
    :raises ValueError: The seed is invalid.
    """
    return core.demo_data(random_state=random_state)
