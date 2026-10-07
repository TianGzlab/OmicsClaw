"""Descriptive drug-associated gene expression and optional CaDRReS predictions."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile

__all__ = ["score_drug_targets", "builtin_drug_targets", "cadrres", "run_info", "top_drugs", "top_drugs_figure"]

_TARGETS = {
    "Cisplatin": ["ERCC1", "XPA", "BRCA1", "MLH1", "MSH2"],
    "Paclitaxel": ["TUBB", "TUBB3", "MAP4", "STMN1", "BCL2"],
    "Doxorubicin": ["TOP2A", "TOP2B", "ABCB1", "TP53", "BCL2"],
    "5-Fluorouracil": ["TYMS", "DPYD", "UMPS", "TK1", "RRM1"],
    "Gemcitabine": ["RRM1", "RRM2", "DCK", "CDA", "SLC29A1"],
    "Sorafenib": ["RAF1", "BRAF", "VEGFA", "KDR", "FLT4"],
    "Erlotinib": ["EGFR", "ERBB2", "ERBB3", "AKT1", "KRAS"],
    "Imatinib": ["ABL1", "BCR", "KIT", "PDGFRA", "PDGFRB"],
    "Temozolomide": ["MGMT", "MLH1", "MSH2", "MSH6", "ALKBH2"],
    "Olaparib": ["BRCA1", "BRCA2", "PARP1", "RAD51", "ATM"],
    "Vemurafenib": ["BRAF", "CRAF", "MAP2K1", "MAP2K2", "MAPK1"],
    "Lapatinib": ["EGFR", "ERBB2", "AKT1", "PIK3CA", "PTEN"],
    "Methotrexate": ["DHFR", "FPGS", "GGH", "SLC19A1", "TYMS"],
    "Venetoclax": ["BCL2", "BCL2L1", "MCL1", "BAX", "BAK1"],
    "Trametinib": ["MAP2K1", "MAP2K2", "MAPK1", "MAPK3", "BRAF"],
}


def builtin_drug_targets():
    """Return a copy of 15 illustrative drug-associated gene sets.

    These include targets, resistance and response-associated genes without
    direction or potency weights. They are not a validated response signature.
    """
    return deepcopy(_TARGETS)


def score_drug_targets(adata, *, cluster_key=None, drug_targets=None):
    """Return mean_target_expression for each drug-associated gene set and group.

    Averages X over available genes and cells, rounding to four decimals to
    preserve the CLI table. No model is fitted; this is neither correlation nor
    drug sensitivity, and high expression does not establish benefit. Pass
    normalized expression and a group key; None summarizes all cells together.
    """
    import numpy as np
    import pandas as pd

    targets_by_drug = builtin_drug_targets() if drug_targets is None else drug_targets
    if not adata.var_names.is_unique:
        raise ValueError("Gene names must be unique")
    if cluster_key is not None and cluster_key not in adata.obs:
        raise ValueError(f"Cluster column {cluster_key!r} is missing")
    labels = adata.obs[cluster_key] if cluster_key is not None else pd.Series('all', index=adata.obs_names)
    sample = list(adata.var_names[:500])
    mouse = bool(sample) and sum(g != g.upper() and g[0].isupper() for g in sample) / len(sample) > .5
    lower_map = {gene.lower(): gene for gene in adata.var_names}
    rows = []
    for drug, targets in targets_by_drug.items():
        adapted = [gene.capitalize() for gene in targets] if mouse else targets
        available = [gene for gene in adapted if gene in adata.var_names]
        if not available:
            available = [lower_map[gene.lower()] for gene in targets if gene.lower() in lower_map]
        if not available:
            continue
        for group in sorted(labels.dropna().unique()):
            expression = adata[labels == group, available].X
            mean = float(expression.mean())
            rows.append({'Drug': str(drug), 'Cluster': str(group), 'mean_target_expression': round(mean, 4),
                         'TargetGenes': len(available), 'TotalTargets': len(targets),
                         'OverlapPct': round(100 * len(available) / len(targets), 1)})
    if rows:
        result = pd.DataFrame(rows)
        result['Rank'] = result.groupby('Cluster')['mean_target_expression'].rank(ascending=False, method='min').astype(int)
        result = result.sort_values(['Cluster', 'Rank'])
    else:
        result = pd.DataFrame(columns=['Drug', 'Cluster', 'mean_target_expression', 'Rank', 'TargetGenes', 'TotalTargets', 'OverlapPct'])
    result.attrs['run_info'] = {'method': 'simple_correlation', 'score_column': 'mean_target_expression',
                                 'interpretation': 'Mean expression of drug-associated genes; not a drug sensitivity prediction.'}
    return result


def cadrres(adata, *, cluster_key, model_dir, drug_db="gdsc", n_drugs=10):
    """Return CaDRReS model scores using explicitly supplied trusted local models.

    Requires omicverse's Drug_Response adapter and a CaDRReS-Sc checkout beside
    model_dir or under the home directory. Models are not bundled or downloaded;
    upstream download locations have not been validated. Temporary predictions
    do not modify model_dir. Score units and direction depend on the model.
    """
    import pandas as pd

    model_dir = Path(model_dir)
    if drug_db not in {'gdsc', 'prism'}:
        raise ValueError("drug_db must be gdsc or prism")
    model_name = ('cadrres-wo-sample-bias_param_dict_all_genes.pickle' if drug_db == 'gdsc'
                  else 'cadrres-wo-sample-bias_param_dict_prism.pickle')
    missing = [name for name in (model_name, 'masked_drugs.csv') if not (model_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing trusted local CaDRReS model files in {model_dir}: {', '.join(missing)}. Models are not bundled.")
    if cluster_key not in adata.obs:
        raise ValueError(f"Cluster column {cluster_key!r} is missing")
    from omicverse.single._scdrug import Drug_Response

    scripts = model_dir.parent / 'CaDRReS-Sc'
    if not scripts.is_dir():
        scripts = Path.home() / 'CaDRReS-Sc'
    if not scripts.is_dir():
        raise FileNotFoundError("A local CaDRReS-Sc script checkout is required beside model_dir or in the home directory")
    copied = adata.copy()
    copied.obs['louvain'] = copied.obs[cluster_key].astype(str)
    with tempfile.TemporaryDirectory(prefix='omicsclaw_cadrres_') as directory:
        Drug_Response(adata=copied, scriptpath=str(scripts), modelpath=str(model_dir) + '/',
                      output=directory, model=drug_db.upper(), clusters='All', n_drugs=n_drugs)
        output = Path(directory) / ('IC50_prediction.csv' if drug_db == 'gdsc' else 'PRISM_prediction.csv')
        prediction = pd.read_csv(output, header=[0, 1], index_col=0)
    rows = [{'Drug': str(column[1] if isinstance(column, tuple) else column),
             'Cluster': str(group), 'Score': round(float(prediction.loc[group, column]), 4)}
            for group in prediction.index for column in prediction.columns]
    result = pd.DataFrame(rows, columns=['Drug', 'Cluster', 'Score'])
    result['Rank'] = result.groupby('Cluster')['Score'].rank(ascending=False, method='min').astype(int)
    result = result.sort_values(['Cluster', 'Rank'])
    result.attrs['run_info'] = {'method': 'cadrres', 'drug_db': drug_db, 'score_column': 'Score',
                                 'interpretation': 'Model output; inspect its units and direction before interpreting ranks.'}
    return result


def run_info(table, *, keep: bool = True):
    """Return score interpretation; keep=False removes the table's run record."""
    info = table.attrs.get('run_info', {}) if keep else table.attrs.pop('run_info', {})
    return deepcopy(info)


def top_drugs(table, *, n_top=10):
    """Return drug means across groups, ordered by decreasing descriptive/model score.

    Ranking model scores this way preserves the CLI order, not clinical benefit.
    """
    key = 'mean_target_expression' if 'mean_target_expression' in table else 'Score'
    return table.groupby('Drug')[key].mean().sort_values(ascending=False).head(n_top).reset_index()


def top_drugs_figure(table, *, n_top=10):
    """Return a Figure labelled with expression or model-score units, without saving."""
    import matplotlib.pyplot as plt

    top = top_drugs(table, n_top=n_top)
    key = 'mean_target_expression' if 'mean_target_expression' in top else 'Score'
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(top['Drug'], top[key])
    ax.invert_yaxis()
    ax.set(xlabel='Mean target expression' if key == 'mean_target_expression' else 'Mean model score',
           title='Drug-associated gene expression' if key == 'mean_target_expression' else 'CaDRReS model output')
    fig.tight_layout()
    return fig
