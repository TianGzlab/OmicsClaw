"""Impute and normalize metabolomics feature tables."""
from skills.metabolomics._lib.quantification import quantify_features, _detect_sample_cols

__all__ = ['quantify', 'run_info', 'distribution_figure']


def quantify(data, *, impute='min', normalize='tic'):
    """Return imputed and normalized intensities with metadata preserved.

    :param data: Feature table with sample/intensity columns; zeros and NaNs are missing.
    :param impute: CLI default min (half global positive minimum); median or knn also work.
    :param normalize: CLI default tic; median or log are alternatives.
    :returns: A new DataFrame with missing-value counts in attrs['run_info'].
    :raises ValueError: Samples are absent, have no positive observations or a method is unknown.
    :raises ImportError: KNN requires scikit-learn; use install_skill_deps.
    """
    if impute == 'knn':
        try:
            from sklearn.impute import KNNImputer
        except ImportError as exc:
            raise ImportError('Install scikit-learn with install_skill_deps for knn') from exc
    result, info = quantify_features(data, impute_method=impute, norm_method=normalize)
    result.attrs['run_info'] = info
    return result


def distribution_figure(data):
    """Plot sample intensities, excluding numeric feature metadata.

    :param data: The input or quantified feature table.
    :returns: A matplotlib Figure.
    :raises ValueError: No numeric sample columns are available.
    """
    from skills.metabolomics._lib.library import distribution_figure as plot
    return plot(data[_detect_sample_cols(data)])


def run_info(data, *, keep=True):
    """Read diagnostics attached to a returned table.

    :param data: DataFrame returned by this library.
    :param keep: Default True; use False in the CLI to remove diagnostics.
    :returns: An independent dictionary describing the run.
    :raises ValueError: The table carries no run_info.
    """
    from skills.metabolomics._lib.library import run_info as read
    return read(data, keep=keep)
