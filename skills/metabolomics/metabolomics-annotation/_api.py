"""In-memory metabolite annotation by adduct mass tolerance."""
import numpy as np
from skills.metabolomics._lib.annotation import annotate_mz, ADDUCT_RULES

__all__ = ['annotate', 'run_info', 'mass_error_figure']


def annotate(data, *, database='hmdb', ppm=10., adducts=None, reference=None):
    """Match every observed m/z to all reference adducts within tolerance.

    :param data: Feature DataFrame with a numeric mz column.
    :param database: CLI default hmdb; other labels require an explicit reference.
    :param ppm: CLI default 10; nonnegative mass error tolerance in parts per million.
    :param adducts: CLI default None resolves to [M+H]+ and [M-H]-.
    :param reference: Optional DataFrame with name, neutral_mass, database_id and formula; None uses 15 demo metabolites.
    :returns: A new annotations DataFrame; attrs['run_info'] names the reference scope.
    :raises ValueError: Reference, observed masses, tolerance or adducts are invalid.
    """
    if reference is None and database != 'hmdb':
        raise ValueError('A non-HMDB database requires an explicit reference; only the HMDB demo is bundled')
    if not np.isfinite(ppm) or ppm < 0:
        raise ValueError('ppm must be finite and nonnegative')
    if 'mz' not in data or not len(data) or not np.isfinite(data['mz']).all() or (data['mz'] <= 0).any():
        raise ValueError('mz must contain positive finite observed masses')
    chosen = ['[M+H]+', '[M-H]-'] if adducts is None else list(adducts)
    if not chosen or any(a not in ADDUCT_RULES for a in chosen):
        raise ValueError('Unknown or empty adduct selection')
    rows = None
    if reference is not None:
        required = ['name', 'neutral_mass', 'database_id', 'formula']
        if not set(required).issubset(reference) or reference.empty:
            raise ValueError('reference requires name, neutral_mass, database_id and formula')
        masses = reference['neutral_mass'].to_numpy(dtype=float)
        if not np.isfinite(masses).all() or any((masses + ADDUCT_RULES[a] <= 0).any() for a in chosen):
            raise ValueError('reference adduct masses must be positive and finite')
        rows = list(reference[required].itertuples(index=False, name=None))
    result = annotate_mz(data['mz'], database=database, ppm=ppm, adducts=chosen, reference=rows)
    result.attrs['run_info'] = {'database': database, 'reference_scope': 'demo' if reference is None else 'provided',
                              'n_queries': data['mz'].nunique(), 'ppm': ppm, 'adducts': chosen}
    return result


def mass_error_figure(data):
    """Plot the ppm error of matched metabolite candidates.

    :param data: Annotation table returned by annotate.
    :returns: A matplotlib Figure.
    :raises KeyError: ppm_error is absent.
    """
    from matplotlib.figure import Figure
    fig = Figure(figsize=(6, 4))
    ax = fig.subplots()
    ax.hist(data['ppm_error'].dropna(), bins=15)
    ax.set(xlabel='Absolute mass error (ppm)', ylabel='Candidate matches')
    return fig


def run_info(data, *, keep=True):
    """Read diagnostics attached to a returned table.

    :param data: DataFrame returned by this library.
    :param keep: Default True; use False in the CLI to remove diagnostics.
    :returns: An independent dictionary describing the run.
    :raises ValueError: The table carries no run_info.
    """
    from skills.metabolomics._lib.library import run_info as read
    return read(data, keep=keep)
