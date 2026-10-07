"""Per-cell pathway scoring without report or result-directory side effects."""

from __future__ import annotations

import json
import logging
import tempfile
from copy import deepcopy
from pathlib import Path

import pandas as pd
import scanpy as sc

from skills._sdk.deps import validate_r_environment
from skills._sdk.r_script_runner import RScriptRunner
from skills.singlecell._lib.adata_utils import (
    GENE_SYMBOL_CANDIDATE_COLUMNS, get_matrix_contract, infer_x_matrix_kind,
    matrix_kind_is_normalized,
)

__all__ = ['score_gene_sets', 'load_gene_sets', 'attach_scores', 'gene_set_overlap',
           'group_scores', 'top_pathways', 'score_summary', 'score_distribution_figure', 'run_info']
logger = logging.getLogger(__name__)
R_SCRIPTS_DIR = Path(__file__).parent / 'rscripts'
_RUN_KEY = 'omicsclaw_sc_pathway_scoring_run'

GENE_SET_DB_ALIASES = {
    "hallmark": {"human": "MSigDB_Hallmark_2020", "mouse": "MSigDB_Hallmark_2020"},
    "kegg": {"human": "KEGG_2021_Human", "mouse": "KEGG_2021_Mouse"},
    "reactome": {"human": "Reactome_2022", "mouse": "Reactome_2022"},
    "go_bp": {"human": "GO_Biological_Process_2023", "mouse": "GO_Biological_Process_2023"},
    "go_cc": {"human": "GO_Cellular_Component_2023", "mouse": "GO_Cellular_Component_2023"},
    "go_mf": {"human": "GO_Molecular_Function_2023", "mouse": "GO_Molecular_Function_2023"},
}


def _slugify_gene_set_name(name: str) -> str:
    chars = []
    for char in str(name):
        chars.append(char.lower() if char.isalnum() else "_")
    slug = "".join(chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "gene_set"


def _read_gene_sets_gmt(gene_sets_path: Path) -> dict[str, list[str]]:
    gene_sets: dict[str, list[str]] = {}
    for raw_line in gene_sets_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name = str(parts[0]).strip()
        members = [str(member).strip() for member in parts[2:] if str(member).strip()]
        if name and members:
            gene_sets[name] = members
    if not gene_sets:
        raise ValueError(f"No valid gene sets were parsed from {gene_sets_path}")
    return gene_sets


def _best_feature_label_mapping(adata, gene_sets: dict[str, list[str]]) -> tuple[str, pd.Index, dict[str, str]]:
    gene_universe = {str(gene) for members in gene_sets.values() for gene in members}
    candidates: list[tuple[str, pd.Index]] = [("var_names", pd.Index(adata.var_names.astype(str), dtype="object"))]
    for column in GENE_SYMBOL_CANDIDATE_COLUMNS:
        if column not in adata.var.columns:
            continue
        values = adata.var[column].fillna("").astype(str)
        if values.eq("").all():
            continue
        candidates.append((f"var.{column}", pd.Index(values, dtype="object")))

    best_source = "var_names"
    best_index = candidates[0][1]
    best_overlap = len(set(best_index) & gene_universe)

    for source, labels in candidates[1:]:
        overlap = len(set(labels) & gene_universe)
        if overlap > best_overlap:
            best_source = source
            best_index = labels
            best_overlap = overlap

    mapping: dict[str, str] = {}
    for feature_id, label in zip(adata.var_names.astype(str), best_index.astype(str)):
        if not label or label in mapping:
            continue
        mapping[str(label)] = str(feature_id)
    return best_source, best_index.astype(str), mapping


def _build_gene_set_overlap_table(
    adata,
    gene_sets: dict[str, list[str]],
    *,
    feature_label_source: str,
    feature_label_mapping: dict[str, str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for gene_set_name, members in gene_sets.items():
        matched_feature_ids = [feature_label_mapping[gene] for gene in members if gene in feature_label_mapping]
        rows.append(
            {
                "gene_set": gene_set_name,
                "n_input_genes": int(len(members)),
                "n_matched_genes": int(len(matched_feature_ids)),
                "feature_label_source": feature_label_source,
                "matched_feature_ids": ";".join(matched_feature_ids[:40]),
                "matched_input_genes": ";".join([gene for gene in members if gene in feature_label_mapping][:40]),
            }
        )
    overlap_df = pd.DataFrame(rows).sort_values(
        ["n_matched_genes", "gene_set"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return overlap_df


def _build_expression_export_adata(
    adata,
    *,
    feature_labels: pd.Index,
    prefer_x: bool,
) -> tuple[sc.AnnData, str]:
    if prefer_x or adata.raw is None or adata.raw.shape != adata.shape:
        export = adata.copy()
        export.var_names = pd.Index(feature_labels, dtype="object")
        export.var_names_make_unique()
        return export, "adata.X"

    export = sc.AnnData(X=adata.raw.X.copy(), obs=adata.obs.copy(), var=adata.raw.var.copy())
    export.obs_names = adata.obs_names.copy()
    export.var_names = pd.Index(feature_labels, dtype="object")
    export.var_names_make_unique()
    return export, "adata.raw"


def _write_expression_matrix_tsv(adata, output_path: Path) -> Path:
    matrix = adata.X
    if hasattr(matrix, "toarray"):
        matrix = matrix.toarray()
    expr_df = pd.DataFrame(
        matrix.T,
        index=adata.var_names.astype(str),
        columns=adata.obs_names.astype(str),
    )
    expr_df.to_csv(output_path, sep="\t")
    return output_path


def _normalize_species(species: str | None) -> str:
    normalized = str(species or "human").strip().lower()
    if normalized in {"human", "hs", "homo_sapiens", "homo sapiens"}:
        return "human"
    if normalized in {"mouse", "mm", "mus_musculus", "mus musculus"}:
        return "mouse"
    return normalized


def _gseapy_organism(species: str) -> str:
    normalized = _normalize_species(species)
    if normalized == "mouse":
        return "Mouse"
    return "Human"


def _resolve_gene_set_library_name(gene_set_db: str, species: str) -> str:
    normalized_db = str(gene_set_db).strip().lower()
    normalized_species = _normalize_species(species)
    alias = GENE_SET_DB_ALIASES.get(normalized_db)
    if alias:
        return alias.get(normalized_species, alias.get("human", gene_set_db))
    return str(gene_set_db).strip()


def _write_gene_sets_gmt(gene_sets: dict[str, list[str]], output_path: Path) -> Path:
    lines = []
    for name, members in gene_sets.items():
        clean_members = [str(member).strip() for member in members if str(member).strip()]
        if clean_members:
            lines.append("\t".join([str(name), "omicsclaw"] + clean_members))
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return output_path


def _fetch_gene_sets_from_library(gene_set_db: str, *, species: str) -> tuple[dict[str, list[str]], str]:
    try:
        import gseapy as gp
    except ImportError as exc:  # pragma: no cover - handled by preflight too
        raise ImportError(
            "`--gene-set-db` requires `gseapy`. Install it before using built-in pathway libraries."
        ) from exc

    resolved = _resolve_gene_set_library_name(gene_set_db, species)
    organism = _gseapy_organism(species)
    try:
        gene_sets = gp.get_library(name=resolved, organism=organism)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download or resolve gene-set library `{resolved}` for organism `{organism}`. "
            "Check network access, verify the library name, or provide a local `--gene-sets` GMT file instead."
        ) from exc
    if not gene_sets:
        raise ValueError(
            f"Gene-set library `{resolved}` returned no gene sets. Provide a different library key or a local GMT file."
        )
    return {str(name): [str(gene) for gene in genes] for name, genes in gene_sets.items()}, resolved


def run_aucell(
    adata,
    *,
    gene_sets_path: Path,
    feature_labels: pd.Index,
    auc_max_rank: int | None,
    random_state: int = 42,
) -> tuple[pd.DataFrame, str, int]:
    validate_r_environment(required_r_packages=["AUCell", "GSEABase"])
    runner = RScriptRunner(scripts_dir=R_SCRIPTS_DIR, timeout=7200)
    prefer_x = matrix_kind_is_normalized(get_matrix_contract(adata).get("X")) or infer_x_matrix_kind(adata) == "normalized_expression"
    export, source = _build_expression_export_adata(adata, feature_labels=feature_labels, prefer_x=prefer_x)
    effective_auc_max_rank = int(auc_max_rank) if auc_max_rank is not None else max(1, int(round(export.n_vars * 0.05)))
    with tempfile.TemporaryDirectory(prefix="omicsclaw_aucell_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        input_matrix = tmpdir_path / "expression_matrix.tsv"
        output_dir = tmpdir_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_expression_matrix_tsv(export, input_matrix)
        runner.run_script(
            "sc_aucell.R",
            args=[str(input_matrix), str(gene_sets_path), str(output_dir), str(effective_auc_max_rank), str(random_state)],
            expected_outputs=["aucell_scores.csv"],
            output_dir=output_dir,
        )
        scores_df = pd.read_csv(output_dir / "aucell_scores.csv")
    if "Cell" not in scores_df.columns:
        raise ValueError("AUCell output is missing the required 'Cell' column")
    return scores_df.set_index("Cell"), source, effective_auc_max_rank


def run_score_genes_py(
    adata,
    *,
    gene_sets: dict[str, list[str]],
    feature_label_mapping: dict[str, str],
    ctrl_size: int,
    n_bins: int,
    random_state: int = 42,
) -> tuple[pd.DataFrame, list[str]]:
    if not matrix_kind_is_normalized(get_matrix_contract(adata).get("X")) and infer_x_matrix_kind(adata) != "normalized_expression":
        raise ValueError("`score_genes_py` requires normalized expression in `adata.X`. Run `sc-preprocessing` first.")

    work = adata.copy()
    scores_df = pd.DataFrame(index=work.obs_names.astype(str))
    skipped: list[str] = []
    for gene_set_name, members in gene_sets.items():
        matched_feature_ids = [feature_label_mapping[gene] for gene in members if gene in feature_label_mapping]
        if not matched_feature_ids:
            skipped.append(gene_set_name)
            continue
        score_name = f"__temp_score__{_slugify_gene_set_name(gene_set_name)}"
        sc.tl.score_genes(
            work,
            gene_list=matched_feature_ids,
            score_name=score_name,
            use_raw=False,
            ctrl_size=min(max(int(ctrl_size), 1), max(len(matched_feature_ids), 1) * 5),
            n_bins=max(int(n_bins), 1),
            copy=False,
            random_state=random_state,
        )
        scores_df[gene_set_name] = pd.to_numeric(work.obs[score_name], errors="coerce")
    if scores_df.empty:
        raise ValueError("No gene sets had any overlap with the input features, so no enrichment scores could be computed.")
    return scores_df, skipped


def _rank_genes_per_cell(X, seed: int = 42) -> "np.ndarray":
    """Rank genes per cell in descending expression order (0 = highest).

    Pure numpy/scipy implementation adapted from omicverse AUCell.
    Returns an integer rank matrix of shape (n_cells, n_genes).
    """
    import numpy as np
    from scipy.sparse import issparse

    rng = np.random.default_rng(seed)
    n_cells, n_genes = X.shape

    # Shuffle columns to break ties randomly
    shuffle_order = rng.permutation(n_genes)

    rank_matrix = np.empty((n_cells, n_genes), dtype=np.int32)
    for i in range(n_cells):
        if issparse(X):
            row = X.getrow(i).toarray().ravel()
        else:
            row = np.asarray(X[i]).ravel()
        shuffled_row = row[shuffle_order]
        # argsort descending: highest expression gets rank 0
        sort_idx = np.argsort(-shuffled_row, kind="mergesort")
        ranks = np.empty(n_genes, dtype=np.int32)
        ranks[sort_idx] = np.arange(n_genes, dtype=np.int32)
        rank_matrix[i, shuffle_order] = ranks

    return rank_matrix


def _compute_auc_for_gene_set(
    rank_matrix: "np.ndarray",
    gene_indices: list[int],
    auc_threshold: float,
    n_genes: int,
) -> "np.ndarray":
    """Compute AUC of recovery curve for a single gene set across all cells.

    For each cell, the recovery curve is built by walking through the ranked
    gene list and accumulating hits from the gene set. The AUC is computed
    up to the rank cutoff determined by auc_threshold.

    Returns a 1D array of AUC values (one per cell).
    """
    import numpy as np

    n_cells = rank_matrix.shape[0]
    rank_cutoff = max(1, round(auc_threshold * n_genes))

    # Maximum possible AUC (all gene-set genes ranked at top)
    n_set = len(gene_indices)
    if n_set == 0:
        return np.zeros(n_cells, dtype=np.float64)

    # For each cell, count how many gene-set genes have rank < rank_cutoff
    # and compute recovery AUC
    aucs = np.empty(n_cells, dtype=np.float64)
    for cell_idx in range(n_cells):
        # Get ranks of gene-set genes in this cell
        gene_ranks = rank_matrix[cell_idx, gene_indices]
        # Only consider genes within the rank cutoff
        hits_within_cutoff = gene_ranks[gene_ranks < rank_cutoff]

        if len(hits_within_cutoff) == 0:
            aucs[cell_idx] = 0.0
            continue

        # Build recovery curve: at each position in the ranking,
        # how many gene-set genes have been recovered
        recovery = np.zeros(rank_cutoff, dtype=np.float64)
        for rank in hits_within_cutoff:
            recovery[rank] += 1.0
        recovery = np.cumsum(recovery)

        # Normalize by number of gene-set genes
        recovery = recovery / n_set

        # AUC = sum of recovery values / rank_cutoff (normalize to [0,1])
        aucs[cell_idx] = float(np.sum(recovery)) / rank_cutoff

    return aucs


def run_aucell_py(
    adata,
    *,
    gene_sets: dict[str, list[str]],
    feature_label_mapping: dict[str, str],
    auc_threshold: float = 0.05,
    seed: int = 42,
) -> tuple[pd.DataFrame, list[str]]:
    """Pure Python AUCell implementation.

    Adapted from omicverse's AUCell. Ranks genes per cell by expression,
    then computes recovery curve AUC for each gene set.

    Parameters
    ----------
    adata
        AnnData with expression data.
    gene_sets
        Dict mapping gene-set name -> list of gene labels.
    feature_label_mapping
        Dict mapping gene label -> feature ID in adata.var_names.
    auc_threshold
        Fraction of ranked genome for AUC calculation (default 0.05).

    Returns
    -------
    tuple[pd.DataFrame, list[str]]
        Scores DataFrame (cells x gene_sets) and list of skipped gene sets.
    """
    import numpy as np

    X = adata.X
    n_cells, n_genes = X.shape

    logger.info("AUCell (Python): ranking %d genes across %d cells ...", n_genes, n_cells)
    rank_matrix = _rank_genes_per_cell(X, seed=seed)

    # Build feature-name-to-index mapping
    var_names = list(adata.var_names.astype(str))
    var_to_idx = {name: idx for idx, name in enumerate(var_names)}

    scores_df = pd.DataFrame(index=adata.obs_names.astype(str))
    skipped: list[str] = []

    for gene_set_name, members in gene_sets.items():
        # Map gene labels to feature indices
        matched_ids = [feature_label_mapping[gene] for gene in members if gene in feature_label_mapping]
        gene_indices = [var_to_idx[fid] for fid in matched_ids if fid in var_to_idx]

        if not gene_indices:
            skipped.append(gene_set_name)
            continue

        aucs = _compute_auc_for_gene_set(rank_matrix, gene_indices, auc_threshold, n_genes)
        scores_df[gene_set_name] = aucs

    if scores_df.empty:
        raise ValueError(
            "No gene sets had any overlap with the input features. "
            "AUCell (Python) cannot compute scores."
        )

    logger.info(
        "AUCell (Python): scored %d gene sets (%d skipped).",
        scores_df.shape[1], len(skipped),
    )
    return scores_df, skipped


def attach_scores_to_adata(adata, scores_df: pd.DataFrame, *, method: str) -> list[str]:
    aligned = scores_df.reindex(adata.obs_names.astype(str))
    if aligned.isna().all().all():
        raise ValueError("Gene-set scores could not be aligned back to adata.obs_names")
    score_columns: list[str] = []
    gene_set_labels: dict[str, str] = {}
    for gene_set in aligned.columns:
        obs_key = f"enrich__{_slugify_gene_set_name(gene_set)}"
        adata.obs[obs_key] = pd.to_numeric(aligned[gene_set], errors="coerce")
        score_columns.append(obs_key)
        gene_set_labels[obs_key] = str(gene_set)
    adata.uns["sc_pathway_scoring"] = {
        "method": method,
        "score_columns": score_columns,
        "gene_sets": list(aligned.columns.astype(str)),
        "score_column_labels": gene_set_labels,
    }
    return score_columns


def score_summary(
    adata,
    scores_df: pd.DataFrame,
    *,
    groupby: str | None,
    top_pathways: int,
) -> dict[str, object]:
    """Return top pathways, grouped means, high fractions and long-form scores."""
    overall_mean = scores_df.mean(axis=0, numeric_only=True)
    overall_abs = scores_df.abs().mean(axis=0, numeric_only=True)
    top_df = (
        pd.DataFrame({"gene_set": overall_mean.index.astype(str), "mean_score": overall_mean.values, "mean_abs_score": overall_abs.values})
        .sort_values(["mean_abs_score", "gene_set"], ascending=[False, True], kind="mergesort")
        .head(top_pathways)
        .reset_index(drop=True)
    )

    group_means_df = pd.DataFrame()
    group_high_fraction_df = pd.DataFrame()
    long_df = pd.DataFrame()
    if groupby and groupby in adata.obs.columns:
        joined = scores_df.join(adata.obs[[groupby]])
        group_means_df = joined.groupby(groupby, observed=False).mean(numeric_only=True)
        threshold_map = scores_df.median(axis=0, numeric_only=True)
        high_fraction = joined.copy()
        for column in scores_df.columns:
            high_fraction[column] = pd.to_numeric(joined[column], errors="coerce") > float(threshold_map[column])
        group_high_fraction_df = high_fraction.groupby(groupby, observed=False).mean(numeric_only=True)
        selected_terms = [term for term in top_df["gene_set"].astype(str).tolist() if term in group_means_df.columns]
        if selected_terms:
            group_means_df = group_means_df.loc[:, selected_terms]
            group_high_fraction_df = group_high_fraction_df.loc[:, selected_terms]

    top_gene_sets = top_df["gene_set"].astype(str).tolist()[: min(6, len(top_df))]
    if top_gene_sets:
        long_df = (
            scores_df.loc[:, [gene_set for gene_set in top_gene_sets if gene_set in scores_df.columns]]
            .stack()
            .rename("score")
            .reset_index()
        )
        long_df.columns = ["cell_id", "gene_set", "score"]
        if groupby and groupby in adata.obs.columns:
            long_df["group"] = adata.obs.loc[long_df["cell_id"], groupby].astype(str).to_numpy()

    return {
        "top_pathways_df": top_df,
        "group_means_df": group_means_df,
        "group_high_fraction_df": group_high_fraction_df,
        "top_pathway_scores_long_df": long_df,
    }


def load_gene_sets(source, *, species: str = 'human') -> dict[str, list[str]]:
    """Read a GMT or JSON file, or download an Enrichr library.

    Aliases belong to this skill: mouse KEGG resolves to KEGG_2021_Mouse.
    Named libraries require gseapy and network access; local files do not.
    """
    path = Path(source)
    if path.is_file():
        if path.suffix.lower() == '.json':
            return {str(k): list(map(str, v)) for k, v in json.loads(path.read_text()).items()}
        return _read_gene_sets_gmt(path)
    return _fetch_gene_sets_from_library(str(source), species)[0]


def score_gene_sets(adata, gene_sets, *, method: str = 'aucell_r',
                    auc_max_rank: int | None = None, auc_threshold: float = 0.05,
                    ctrl_size: int = 50, n_bins: int = 25,
                    random_state: int = 42) -> pd.DataFrame:
    """Return cell-by-gene-set scores without changing adata.

    aucell_py ranks X, breaking ties with random_state; auc_threshold is the
    fraction of ranked genes used. score_genes_py requires normalized X and
    uses Scanpy control genes. aucell_r requires AUCell/GSEABase and uses
    normalized X or an aligned raw matrix. R exchange files are temporary.
    Gene sets with no matched features are skipped; all-unmatched input fails.
    API seeds default to 42. The historical score_genes CLI uses seed 0.
    """
    if method not in ('aucell_r', 'aucell_py', 'score_genes_py'):
        raise ValueError('Unknown pathway scoring method: ' + method)
    label_source, labels, mapping = _best_feature_label_mapping(adata, gene_sets)
    effective, source, skipped = None, 'adata.X', []
    if method == 'aucell_py':
        scores, skipped = run_aucell_py(adata, gene_sets=gene_sets,
            feature_label_mapping=mapping, auc_threshold=auc_threshold, seed=random_state)
    elif method == 'score_genes_py':
        scores, skipped = run_score_genes_py(adata, gene_sets=gene_sets,
            feature_label_mapping=mapping, ctrl_size=ctrl_size, n_bins=n_bins, random_state=random_state)
    else:
        with tempfile.TemporaryDirectory(prefix='omicsclaw_gene_sets_') as folder:
            path = Path(folder) / 'gene_sets.gmt'
            _write_gene_sets_gmt(gene_sets, path)
            scores, source, effective = run_aucell(adata, gene_sets_path=path,
                feature_labels=labels, auc_max_rank=auc_max_rank, random_state=random_state)
    scores.attrs[_RUN_KEY] = dict(method=method, expression_source=source,
        feature_label_source=label_source, effective_auc_max_rank=effective,
        skipped_gene_sets=skipped, random_state=random_state)
    return scores


def attach_scores(adata, scores: pd.DataFrame):
    """Return a copy with enrich__ columns and the scoring run record in uns."""
    work = adata.copy()
    info = run_info(scores)
    attach_scores_to_adata(work, scores, method=info['method'])
    work.uns[_RUN_KEY] = json.dumps(info)
    return work


def gene_set_overlap(adata, gene_sets) -> pd.DataFrame:
    """Return matched feature counts and identifiers for every requested gene set."""
    source, labels, mapping = _best_feature_label_mapping(adata, gene_sets)
    return _build_gene_set_overlap_table(adata, gene_sets, feature_label_mapping=mapping, feature_label_source=source)


def group_scores(adata, scores: pd.DataFrame, *, groupby: str) -> pd.DataFrame:
    """Return mean scores per obs group, retaining every scored gene set."""
    return score_summary(adata, scores, groupby=groupby, top_pathways=len(scores.columns))['group_means_df']


def top_pathways(scores: pd.DataFrame, *, n: int = 20) -> pd.DataFrame:
    """Rank gene sets by mean absolute cell score, breaking ties by name."""
    return pd.DataFrame({'gene_set': scores.columns.astype(str),
        'mean_score': scores.mean().values, 'mean_abs_score': scores.abs().mean().values
        }).sort_values(['mean_abs_score', 'gene_set'], ascending=[False, True],
        kind='mergesort').head(n).reset_index(drop=True)


def score_distribution_figure(scores: pd.DataFrame):
    """Return a boxplot of per-cell scores without writing files."""
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    scores.plot.box(ax=ax, rot=45)
    ax.set_ylabel('Gene-set score')
    fig.tight_layout()
    return fig


def run_info(result) -> dict:
    """Return the scoring method, seed, feature source and skipped sets."""
    if hasattr(result, 'uns'):
        return json.loads(result.uns[_RUN_KEY])
    return deepcopy(result.attrs[_RUN_KEY])
