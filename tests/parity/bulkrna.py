"""Bulk RNA CLI recordings and public function-library comparisons."""


def register(Case, Skill):
    names = ('qc', 'de', 'coexpression', 'deconvolution', 'batch-correction',
             'enrichment', 'splicing', 'survival', 'trajblend', 'geneid-mapping',
             'ppi-network', 'read-qc', 'read-alignment', 'cosinor-rhythm')
    entries = {}
    for name in names:
        skill = f'bulkrna-{name}'
        prefix = 'skills/bulkrna/run-derived' if name == 'cosinor-rhythm' else 'skills/bulkrna'
        cases = {'default': Case(('--demo',))}
        if name == 'cosinor-rhythm':
            cases['default'] = Case(('--demo',), root_tables=('cosinor_results.csv',))
        if name == 'de':
            cases['ttest'] = Case(('--demo', '--method', 'ttest'))
        elif name == 'enrichment':
            cases['default'] = Case(('--demo',), environment={'PYTHONHASHSEED': '0'})
            cases['gsea'] = Case(('--demo', '--method', 'gsea'), environment={'PYTHONHASHSEED': '0'})
        runner = f'tests.parity.bulkrna:api_{name.replace("-", "_")}' if name in {
            'qc', 'de', 'deconvolution', 'splicing', 'enrichment', 'cosinor-rhythm'} else None
        entries[skill] = Skill(f'{prefix}/{skill}/{skill.replace("-", "_")}.py', runner, cases)
    return entries


def _counts():
    import pandas as pd
    return pd.read_csv(Path(__file__).resolve().parents[2] / 'examples/demo_bulkrna_counts.csv', index_col=0)


def _library(name):
    from skills._sdk.notebook import load_skill
    return load_skill('bulkrna-' + name)


def api_qc(case, *, input_path=None):
    lib = _library('qc')
    result = lib.assess(_counts())
    info = lib.run_info(result)
    return {'tables': {'sample_stats.csv': result.reset_index(),
                       'cpm_normalized.csv': lib.normalized_counts(result).reset_index()},
            'summary': {k: v for k, v in info.items() if k not in ('gene_detection', 'sample_correlation_matrix', 'cpm')}}


def api_de(case, *, input_path=None):
    lib = _library('de')
    result = lib.differential_expression(_counts(), method='ttest' if case == 'ttest' else 'deseq2')
    info = lib.run_info(result)
    return {'tables': {'de_results.csv': result,
                       'de_significant.csv': result[(result.padj < .05) & (result.log2FoldChange.abs() > 1)]},
            'summary': {k: v for k, v in info.items() if k not in ('de_df', 'requested_method', 'executed_method', 'fallback_reason')}}


def api_deconvolution(case, *, input_path=None):
    lib = _library('deconvolution')
    result = lib.deconvolve(_counts(), signature=_generate_demo_signature())
    info = lib.run_info(result)
    return {'tables': {'proportions.csv': result.reset_index(),
                       'dominant_types.csv': pd.DataFrame(list(info['dominant_types'].items()), columns=['sample', 'dominant_cell_type'])},
            'summary': {k: v for k, v in info.items() if k != 'proportions_df'}}


def api_splicing(case, *, input_path=None):
    lib = _library('splicing')
    result = lib.summarize(_generate_demo_splicing_data())
    return {'tables': {'splicing_events.csv': result, 'significant_events.csv': lib.significant_events(result)},
            'summary': {k: v for k, v in lib.run_info(result).items() if k not in ('events_df', 'significant_events_df', 'top_events')}}


def api_enrichment(case, *, input_path=None):
    from skills.bulkrna._lib.enrichment import _generate_demo_de_results, _build_demo_gene_sets
    lib = _library('enrichment')
    result = lib.enrich(_generate_demo_de_results(), gene_sets=_build_demo_gene_sets(), method='gsea' if case == 'gsea' else 'ora')
    result = result.sort_values(['padj', 'pvalue', 'term']).reset_index(drop=True)
    return {'tables': {'enrichment_results.csv': result, 'enrichment_significant.csv': result[result.padj < .05]},
            'summary': {k: v for k, v in lib.run_info(result).items() if k not in ('enrichment_df', 'requested_method', 'executed_method', 'fallback_reason')}}


def api_cosinor_rhythm(case, *, input_path=None):
    data = pd.read_csv(Path(__file__).resolve().parents[2] / 'skills/bulkrna/run-derived/bulkrna-cosinor-rhythm/data/demo_input.csv', index_col=0)
    result = _library('cosinor-rhythm').fit(data)
    return {'tables': {'cosinor_results.csv': result}}


# Seeded input generators copied from the pre-migration CLI, not from outputs.
import logging
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
logger = logging.getLogger(__name__)
EVENT_TYPES = ("SE", "A5SS", "A3SS", "MXE", "RI")
def _generate_demo_signature() -> pd.DataFrame:
    """Create a synthetic cell type signature matrix (genes x cell_types).

    200 genes (GENE_001..GENE_200) and 5 cell types.  Each cell type has
    ~40 marker genes with high expression (200-500); remaining genes have
    low baseline expression (10-50).
    """
    rng = np.random.RandomState(42)
    genes = [f"GENE_{i:03d}" for i in range(1, 201)]
    cell_types = ["T_cells", "B_cells", "Macrophages", "Fibroblasts", "Epithelial"]

    # Low baseline expression for every gene in every cell type
    sig = rng.randint(10, 51, size=(200, 5)).astype(float)

    # Assign ~40 marker genes per cell type with high expression
    for ct_idx in range(5):
        start = ct_idx * 40
        end = start + 40
        sig[start:end, ct_idx] = rng.randint(200, 501, size=40).astype(float)

    df = pd.DataFrame(sig, index=genes, columns=cell_types)
    df.index.name = "gene"
    return df


def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Manual Benjamini-Hochberg FDR correction."""
    pv = np.asarray(pvalues, dtype=float)
    n = len(pv)
    if n == 0:
        return pv
    order = np.argsort(pv)
    sorted_p = pv[order]

    adjusted = np.empty(n, dtype=float)
    adjusted[-1] = sorted_p[-1]
    for i in range(n - 2, -1, -1):
        rank = i + 1
        adjusted[i] = min(sorted_p[i] * n / rank, adjusted[i + 1])
    adjusted = np.clip(adjusted, 0.0, 1.0)

    result = np.empty(n, dtype=float)
    result[order] = adjusted
    return result


def _generate_demo_splicing_data(n_events: int = 100) -> pd.DataFrame:
    """Generate synthetic splicing event data.

    Creates a DataFrame with columns: event_id, event_type, gene, psi_ctrl,
    psi_treat, delta_psi, pvalue, padj.  Approximately 20% of events are
    simulated as differentially spliced (shifted PSI by +/-0.2).
    """
    rng = np.random.RandomState(42)

    event_types = rng.choice(EVENT_TYPES, size=n_events)
    genes = [f"GENE_{rng.randint(1, 51):03d}" for _ in range(n_events)]
    event_ids = [
        f"{et}_{gene}_{i + 1}" for i, (et, gene) in enumerate(zip(event_types, genes))
    ]

    # Base PSI values for control (mean around 0.2-0.8)
    psi_ctrl = rng.uniform(0.2, 0.8, size=n_events)

    # Treatment PSI: ~20% of events get a shift of +/-0.2
    psi_treat = psi_ctrl.copy()
    n_diff = int(n_events * 0.2)
    diff_indices = rng.choice(n_events, size=n_diff, replace=False)
    shifts = rng.choice([-0.2, 0.2], size=n_diff)
    psi_treat[diff_indices] += shifts
    psi_treat = np.clip(psi_treat, 0.0, 1.0)

    # Add small noise to non-differential events
    noise = rng.normal(0, 0.02, size=n_events)
    non_diff_mask = np.ones(n_events, dtype=bool)
    non_diff_mask[diff_indices] = False
    psi_treat[non_diff_mask] += noise[non_diff_mask]
    psi_treat = np.clip(psi_treat, 0.0, 1.0)

    delta_psi = psi_treat - psi_ctrl

    # Compute p-values from synthetic replicates (3 per condition)
    pvalues = np.ones(n_events)
    for i in range(n_events):
        ctrl_reps = rng.normal(psi_ctrl[i], 0.03, size=3)
        treat_reps = rng.normal(psi_treat[i], 0.03, size=3)
        ctrl_reps = np.clip(ctrl_reps, 0.0, 1.0)
        treat_reps = np.clip(treat_reps, 0.0, 1.0)
        _, pval = stats.ttest_ind(ctrl_reps, treat_reps, equal_var=False)
        pvalues[i] = pval if not np.isnan(pval) else 1.0

    padj = _benjamini_hochberg(pvalues)

    df = pd.DataFrame({
        "event_id": event_ids,
        "event_type": event_types,
        "gene": genes,
        "psi_ctrl": np.round(psi_ctrl, 4),
        "psi_treat": np.round(psi_treat, 4),
        "delta_psi": np.round(delta_psi, 4),
        "pvalue": pvalues,
        "padj": padj,
    })

    logger.info("Generated %d synthetic splicing events (%d differential).", n_events, n_diff)
    return df
