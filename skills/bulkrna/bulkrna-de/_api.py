"""Bulk differential-expression tests on explicit raw count matrices."""
import numpy as np
from skills.bulkrna._lib.de import core_analysis
from skills.bulkrna._lib.results import attach_info, read_info, require_matrix

__all__ = ['differential_expression', 'run_info', 'volcano_figure']


def differential_expression(counts, *, method='deseq2', control_prefix='ctrl',
                            treat_prefix='treat', padj_cutoff=0.05, lfc_cutoff=1.0, min_count=10):
    """Compare treatment against control without changing the count matrix.

    :param counts: Gene-indexed DataFrame of nonnegative integer raw counts.
    :param method: CLI default deseq2 (R); ttest selects Welch tests.
    :param control_prefix: CLI default ctrl selects control columns.
    :param treat_prefix: CLI default treat selects treatment columns.
    :param padj_cutoff: CLI default 0.05; significance requires a smaller adjusted p.
    :param lfc_cutoff: CLI default 1.0; absolute log2 effect must exceed it.
    :param min_count: Legacy filtering default 10 for total counts across selected samples.
    :returns: DE DataFrame with effect estimates, p values and run diagnostics in attrs.
    :raises ValueError: Counts, method, groups or thresholds are invalid.
    :raises ImportError: R DESeq2 is missing; use install_skill_deps for DESeq2.
    """
    require_matrix(counts, counts=True)
    if method not in {'deseq2', 'ttest'}:
        raise ValueError('method must be deseq2 or ttest')
    if not 0 < padj_cutoff <= 1 or lfc_cutoff < 0 or min_count < 0:
        raise ValueError('Invalid significance or filtering threshold')
    ctrl = [c for c in counts if str(c).startswith(control_prefix)]
    treat = [c for c in counts if str(c).startswith(treat_prefix)]
    if not ctrl or not treat or set(ctrl) & set(treat):
        raise ValueError('Control and treatment groups must be nonempty and disjoint')
    if not (counts[ctrl + treat].sum(axis=1) >= min_count).any():
        raise ValueError('No genes remain after count filtering')
    if method == 'deseq2':
        from skills._sdk.deps import validate_r_environment
        try:
            validate_r_environment(required_r_packages=['DESeq2'])
        except Exception as exc:
            raise ImportError('R DESeq2 is required; use install_skill_deps for DESeq2') from exc
    info = core_analysis(counts.rename_axis('gene').reset_index(), method=method,
                         control_prefix=control_prefix, treat_prefix=treat_prefix,
                         padj_cutoff=padj_cutoff, lfc_cutoff=lfc_cutoff, min_count=min_count)
    return attach_info(info['de_df'], info)


def run_info(result, *, keep=True):
    """Read filtering, group and executed-method diagnostics.

    :param result: DataFrame returned by differential_expression.
    :param keep: Default True; False removes diagnostics from attrs.
    :returns: Diagnostic dictionary, empty after removal.
    """
    return read_info(result, keep=keep)


def volcano_figure(result):
    """Plot reported log2 effects and adjusted significance.

    :param result: DE DataFrame with log2FoldChange and padj.
    :returns: A matplotlib Figure without saving files.
    :raises KeyError: Required columns are absent.
    """
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.scatter(result['log2FoldChange'], -np.log10(result['padj'].clip(lower=1e-300)))
    ax.set(xlabel='Reported log2 fold change', ylabel='-log10 adjusted p')
    return fig
