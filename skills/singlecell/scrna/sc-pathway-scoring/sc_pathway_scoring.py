#!/usr/bin/env python3
"""Single-cell gene-set enrichment and pathway scoring."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

import pandas as pd
import scanpy as sc

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_output_readme,
    write_result_json,
)
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_script_runner import RScriptRunner
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import (
    GENE_SYMBOL_CANDIDATE_COLUMNS,
    ensure_input_contract,
    get_matrix_contract,
    infer_x_matrix_kind,
    matrix_kind_is_normalized,
    record_matrix_contract,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import (
    _format_candidates,
    _obs_candidates,
    apply_preflight,
    preflight_sc_pathway_scoring,
)
from skills.singlecell._lib.viz import (
    plot_enrichment_embedding_panels,
    plot_group_mean_dotplot,
    plot_group_mean_heatmap,
    plot_pathway_score_distributions,
    plot_top_gene_sets_bar,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-pathway-scoring"
SKILL_VERSION = "0.2.0"
DEFAULT_METHOD = "aucell_r"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-pathway-scoring/sc_pathway_scoring.py"

R_ENHANCED_PLOTS = {
    "plot_embedding_discrete": "r_embedding_discrete.png",
    "plot_embedding_feature": "r_embedding_feature.png",
    "plot_feature_violin": "r_feature_violin.png",
}
R_SCRIPTS_DIR = Path(__file__).resolve().parent / "rscripts"
SHARED_PARAM_KEYS = ("method", "gene_sets", "groupby", "top_pathways")
GENE_SET_DB_ALIASES = {
    "hallmark": {"human": "MSigDB_Hallmark_2020", "mouse": "MSigDB_Hallmark_2020"},
    "kegg": {"human": "KEGG_2021_Human", "mouse": "KEGG_2021_Mouse"},
    "reactome": {"human": "Reactome_2022", "mouse": "Reactome_2022"},
    "go_bp": {"human": "GO_Biological_Process_2023", "mouse": "GO_Biological_Process_2023"},
    "go_cc": {"human": "GO_Cellular_Component_2023", "mouse": "GO_Cellular_Component_2023"},
    "go_mf": {"human": "GO_Molecular_Function_2023", "mouse": "GO_Molecular_Function_2023"},
}

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "aucell_r": MethodConfig(
        name="aucell_r",
        description="AUCell gene-set activity scoring using the official Bioconductor package",
        dependencies=(),
    ),
    "score_genes_py": MethodConfig(
        name="score_genes_py",
        description="Scanpy/Seurat-style module scoring on normalized expression",
        dependencies=(),
    ),
    "aucell_py": MethodConfig(
        name="aucell_py",
        description="Pure Python AUCell gene-set scoring (no R required)",
        dependencies=(),
    ),
}

METHOD_PARAM_DEFAULTS: dict[str, dict[str, object]] = {
    "aucell_r": {
        "method": "aucell_r",
        "groupby": None,
        "top_pathways": 20,
        "aucell_auc_max_rank": None,
    },
    "score_genes_py": {
        "method": "score_genes_py",
        "groupby": None,
        "top_pathways": 20,
        "score_genes_ctrl_size": 50,
        "score_genes_n_bins": 25,
    },
    "aucell_py": {
        "method": "aucell_py",
        "groupby": None,
        "top_pathways": 20,
        "aucell_py_auc_threshold": 0.05,
    },
}

METHOD_PARAM_KEYS: dict[str, tuple[str, ...]] = {
    "aucell_r": ("aucell_auc_max_rank",),
    "score_genes_py": ("score_genes_ctrl_size", "score_genes_n_bins"),
    "aucell_py": ("aucell_py_auc_threshold",),
}


def _write_repro_requirements(repro_dir: Path, packages: list[str]) -> None:
    try:
        from importlib.metadata import PackageNotFoundError, version as get_version
    except ImportError:  # pragma: no cover
        PackageNotFoundError = Exception
        from importlib_metadata import version as get_version  # type: ignore

    lines: list[str] = []
    for pkg in packages:
        try:
            lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            continue
        except Exception:
            continue
    (repro_dir / "requirements.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_standard_run_artifacts(output_dir: Path, result_payload: dict, summary: dict) -> None:
    notebook_path = None
    try:
        from omicsclaw.common.notebook_export import write_analysis_notebook

        notebook_path = write_analysis_notebook(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Single-cell pathway and gene-set activity scoring.",
            result_payload=result_payload,
            preferred_method=summary.get("method", DEFAULT_METHOD),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Single-cell pathway and gene-set activity scoring.",
            result_payload=result_payload,
            preferred_method=summary.get("method", DEFAULT_METHOD),
            notebook_path=notebook_path,
        )
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Failed to write README.md: %s", exc)


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


def _resolve_groupby(adata, requested_groupby: str | None) -> tuple[str | None, list[str], str | None]:
    candidates = []
    for family in ("cell_type", "cluster"):
        for column in _obs_candidates(adata, family):
            if column not in candidates:
                candidates.append(column)

    if requested_groupby:
        return (requested_groupby if requested_groupby in adata.obs.columns else None), candidates, None

    if not candidates:
        return None, candidates, None

    auto_groupby = candidates[0]
    guidance = (
        f"No `--groupby` was provided, so grouped summaries will default to `{auto_groupby}`. "
        f"Other plausible label columns: {_format_candidates(candidates)}."
    )
    return auto_groupby, candidates, guidance


def _ensure_matrix_contract_for_output(adata) -> None:
    if get_matrix_contract(adata):
        return
    layers: dict[str, str | None] = {}
    if "counts" in adata.layers:
        layers["counts"] = "raw_counts"
    raw_kind = "raw_counts_snapshot" if adata.raw is not None else None
    record_matrix_contract(
        adata,
        x_kind=infer_x_matrix_kind(adata),
        raw_kind=raw_kind,
        layers=layers,
        producer_skill=SKILL_NAME,
    )


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


def _write_demo_gene_sets(adata, output_path: Path) -> Path:
    genes = [str(gene) for gene in adata.var_names[:60]]
    gene_sets = {
        "Demo_Set_A": genes[0:15],
        "Demo_Set_B": genes[15:30],
        "Demo_Set_C": genes[30:45],
        "Demo_Set_D": genes[45:60],
    }
    lines = ["\t".join([name, "demo"] + members) for name, members in gene_sets.items()]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
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
            args=[str(input_matrix), str(gene_sets_path), str(output_dir), str(effective_auc_max_rank)],
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


def summarize_scores(
    adata,
    scores_df: pd.DataFrame,
    *,
    groupby: str | None,
    top_pathways: int,
) -> dict[str, object]:
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


def generate_figures(output_dir: Path, adata, summary: dict) -> list[str]:
    figures: list[str] = []

    top_df = summary.get("top_pathways_df", pd.DataFrame())
    path = plot_top_gene_sets_bar(top_df, output_dir)
    if path:
        figures.append(str(path))

    group_means_df = summary.get("group_means_df", pd.DataFrame())
    group_high_fraction_df = summary.get("group_high_fraction_df", pd.DataFrame())
    path = plot_group_mean_heatmap(group_means_df, output_dir)
    if path:
        figures.append(str(path))
    path = plot_group_mean_dotplot(group_means_df, group_high_fraction_df, output_dir)
    if path:
        figures.append(str(path))

    long_df = summary.get("top_pathway_scores_long_df", pd.DataFrame())
    path = plot_pathway_score_distributions(long_df, output_dir)
    if path:
        figures.append(str(path))

    embedding_key = next((key for key in ("X_umap", "X_tsne", "X_phate", "X_diffmap") if key in adata.obsm), None)
    score_columns = list(summary.get("score_columns", []))
    path = plot_enrichment_embedding_panels(
        adata,
        output_dir,
        obsm_key=embedding_key or "",
        score_columns=score_columns,
        score_labels=adata.uns.get("sc_pathway_scoring", {}).get("score_column_labels", {}),
    )
    if path:
        figures.append(str(path))

    return figures


def _write_figure_data(output_dir: Path, summary: dict, overlap_df: pd.DataFrame) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}

    datasets = {
        "top_pathways.csv": summary.get("top_pathways_df", pd.DataFrame()),
        "group_mean_scores.csv": summary.get("group_means_df", pd.DataFrame()),
        "group_high_fraction.csv": summary.get("group_high_fraction_df", pd.DataFrame()),
        "top_pathway_scores_long.csv": summary.get("top_pathway_scores_long_df", pd.DataFrame()),
        "gene_set_overlap.csv": overlap_df,
    }
    for filename, data in datasets.items():
        if isinstance(data, pd.DataFrame) and not data.empty:
            output_path = figure_data_dir / filename
            keep_index = not isinstance(data.index, pd.RangeIndex)
            data.to_csv(output_path, index=keep_index)
            manifest[filename] = output_path.name

    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def write_report(output_dir: Path, summary: dict, params: dict, input_file: str | None) -> None:
    header = generate_report_header(
        title="Single-Cell Pathway Scoring Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Gene sets scored": str(summary["n_gene_sets"]),
            "Grouping column": str(summary.get("groupby") or "none"),
        },
    )
    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Gene sets requested**: {summary['n_gene_sets_requested']}",
        f"- **Gene sets scored**: {summary['n_gene_sets']}",
        f"- **Gene-set source**: {summary['gene_set_source']}",
        f"- **Grouping column**: {summary.get('groupby') or 'none'}",
        f"- **Expression source**: {summary['expression_source']}",
        f"- **Feature label source**: {summary['feature_label_source']}",
    ]
    if summary.get("effective_auc_max_rank") is not None:
        body_lines.append(f"- **Effective AUCell aucMaxRank**: {summary['effective_auc_max_rank']}")
    if summary.get("skipped_gene_sets"):
        body_lines.append(f"- **Skipped gene sets**: {', '.join(summary['skipped_gene_sets'])}")
    body_lines.extend(
        [
            "",
            "## What This Means\n",
            "- This skill scores pathway or gene-program activity per cell, then optionally summarizes those scores across a label column such as `cell_type` or `leiden`.",
            "- It is usually most interpretable after `sc-preprocessing`, and often after `sc-clustering` or `sc-cell-annotation` when grouped summaries matter.",
            "",
            "## Top Gene Sets\n",
            "| Gene set | Mean score | Mean absolute score |",
            "|----------|------------|---------------------|",
        ]
    )
    for _, row in summary["top_pathways_df"].head(15).iterrows():
        body_lines.append(
            f"| {row['gene_set']} | {row['mean_score']:.4f} | {row['mean_abs_score']:.4f} |"
        )
    body_lines.extend(["", "## Parameters\n"])
    for key, value in params.items():
        body_lines.append(f"- `{key}`: {value}")
    if summary.get("next_steps"):
        body_lines.extend(["", "## Usual Next Step\n"])
        body_lines.extend(f"- {line}" for line in summary["next_steps"])
    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer, encoding="utf-8")


def _next_step_guidance(groupby: str | None) -> list[str]:
    if groupby:
        return [
            f"If `{groupby}` reflects clusters or cell types, inspect the grouped pathway plots first, then continue to `sc-cell-annotation` or `sc-de` for biological interpretation.",
            "If these pathway scores highlight a condition effect, the usual follow-up is `sc-de` or a focused marker/pathway validation pass.",
        ]
    return [
        "This run produced per-cell pathway scores only. If you want cluster- or cell-type-level summaries next, run `sc-clustering` or `sc-cell-annotation` first and rerun with `--groupby`.",
    ]


def _render_r_enhanced(output_dir, figure_data_dir, r_enhanced):
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Single-cell pathway and gene-set scoring")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default=DEFAULT_METHOD, choices=list(METHOD_REGISTRY.keys()))
    parser.add_argument("--gene-sets", dest="gene_sets_path")
    parser.add_argument("--gene-set-db", dest="gene_set_db", default=None)
    parser.add_argument("--species", default="human")
    parser.add_argument("--groupby", default=None)
    parser.add_argument("--top-pathways", type=int, default=20)
    parser.add_argument("--aucell-auc-max-rank", type=int, default=None)
    parser.add_argument("--score-genes-ctrl-size", type=int, default=50)
    parser.add_argument("--score-genes-n-bins", type=int, default=25)
    # AUCell Python-specific
    parser.add_argument("--aucell-py-auc-threshold", type=float, default=0.05,
                        help="AUCell (Python) fraction of ranked genome for AUC (default 0.05)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for AUCell ranking (default: 42)")
    parser.add_argument("--r-enhanced", action="store_true", default=False, help="Generate R-enhanced figures via ggplot2 renderers")
    args = parser.parse_args()

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.positive("top_pathways", args.top_pathways, min_val=1)
    v.positive("score_genes_ctrl_size", args.score_genes_ctrl_size, min_val=1)
    v.positive("score_genes_n_bins", args.score_genes_n_bins, min_val=1)
    v.in_range("aucell_py_auc_threshold", args.aucell_py_auc_threshold, low=0, high=1, low_exclusive=True)
    v.check()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback=DEFAULT_METHOD)
    if args.demo:
        adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
        ensure_input_contract(adata, standardized=True)
        input_file = None
        gene_sets_path = _write_demo_gene_sets(adata, output_dir / "demo_gene_sets.gmt")
        gene_set_source = "demo_gmt"
        gene_sets = _read_gene_sets_gmt(gene_sets_path)
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        if not args.gene_sets_path and not args.gene_set_db:
            raise ValueError("--gene-sets or --gene-set-db is required unless --demo is used")
        input_file = args.input_path
        adata = sc_io.smart_load(args.input_path, skill_name=SKILL_NAME, preserve_all=True)
        if args.gene_sets_path:
            gene_sets_path = Path(args.gene_sets_path)
            if not gene_sets_path.exists():
                raise FileNotFoundError(f"Gene set file not found: {gene_sets_path}")
            gene_set_source = str(gene_sets_path)
            gene_sets = _read_gene_sets_gmt(gene_sets_path)
        else:
            gene_sets, resolved_library = _fetch_gene_sets_from_library(args.gene_set_db, species=args.species)
            gene_sets_path = _write_gene_sets_gmt(
                gene_sets,
                output_dir / f"resolved_{_slugify_gene_set_name(resolved_library)}.gmt",
            )
            gene_set_source = f"library:{resolved_library}"

    _ensure_matrix_contract_for_output(adata)
    feature_label_source, feature_labels, feature_label_mapping = _best_feature_label_mapping(adata, gene_sets)
    overlap_df = _build_gene_set_overlap_table(
        adata,
        gene_sets,
        feature_label_source=feature_label_source,
        feature_label_mapping=feature_label_mapping,
    )
    if overlap_df["n_matched_genes"].sum() <= 0:
        raise ValueError(
            "None of the supplied gene-set members matched the input features. Check gene identifiers or run a standardized object with consistent gene symbols."
        )

    resolved_groupby, groupby_candidates, auto_groupby_message = _resolve_groupby(adata, args.groupby)
    decision = preflight_sc_pathway_scoring(
        adata,
        method=method,
        gene_sets_path=str(gene_sets_path) if gene_sets_path else None,
        gene_set_db=args.gene_set_db,
        groupby=resolved_groupby,
        source_path=input_file,
    )
    if auto_groupby_message:
        decision.add_guidance(auto_groupby_message)
    if method == "aucell_r":
        try:
            validate_r_environment(required_r_packages=["AUCell", "GSEABase"])
        except ImportError as exc:
            decision.block(str(exc).strip())
    apply_preflight(decision, logger)

    shared_params = {
        "method": method,
        "groupby": resolved_groupby,
        "top_pathways": args.top_pathways,
        "gene_sets": str(gene_sets_path),
        "gene_set_db": args.gene_set_db,
        "species": args.species,
    }
    method_params_map = {
        "aucell_r": {"aucell_auc_max_rank": args.aucell_auc_max_rank},
        "score_genes_py": {
            "score_genes_ctrl_size": args.score_genes_ctrl_size,
            "score_genes_n_bins": args.score_genes_n_bins,
        },
        "aucell_py": {
            "aucell_py_auc_threshold": args.aucell_py_auc_threshold,
        },
    }
    method_params = method_params_map[method]
    params = dict(METHOD_PARAM_DEFAULTS[method])
    params.update(shared_params)
    params.update(method_params)

    skipped_gene_sets: list[str] = []
    effective_auc_max_rank: int | None = None
    if method == "aucell_r":
        scores_df, expression_source, effective_auc_max_rank = run_aucell(
            adata,
            gene_sets_path=gene_sets_path,
            feature_labels=feature_labels,
            auc_max_rank=args.aucell_auc_max_rank,
        )
    elif method == "aucell_py":
        scores_df, skipped_gene_sets = run_aucell_py(
            adata,
            gene_sets=gene_sets,
            feature_label_mapping=feature_label_mapping,
            auc_threshold=args.aucell_py_auc_threshold,
            seed=args.seed,
        )
        expression_source = "adata.X"
    else:
        scores_df, skipped_gene_sets = run_score_genes_py(
            adata,
            gene_sets=gene_sets,
            feature_label_mapping=feature_label_mapping,
            ctrl_size=args.score_genes_ctrl_size,
            n_bins=args.score_genes_n_bins,
        )
        expression_source = "adata.X"

    score_columns = attach_scores_to_adata(adata, scores_df, method=method)
    table_summary = summarize_scores(adata, scores_df, groupby=resolved_groupby, top_pathways=args.top_pathways)
    summary = {
        "method": method,
        "n_cells": int(adata.n_obs),
        "n_gene_sets_requested": int(len(gene_sets)),
        "n_gene_sets": int(scores_df.shape[1]),
        "gene_set_source": gene_set_source,
        "groupby": resolved_groupby,
        "expression_source": expression_source,
        "feature_label_source": feature_label_source,
        "effective_auc_max_rank": effective_auc_max_rank,
        "score_columns": score_columns,
        "skipped_gene_sets": skipped_gene_sets,
        "next_steps": _next_step_guidance(resolved_groupby),
        **table_summary,
    }

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    scores_df.reset_index().rename(columns={"index": "Cell"}).to_csv(tables_dir / "enrichment_scores.csv", index=False)
    overlap_df.to_csv(tables_dir / "gene_set_overlap.csv", index=False)
    summary["top_pathways_df"].to_csv(tables_dir / "top_pathways.csv", index=False)
    if not summary["group_means_df"].empty:
        summary["group_means_df"].to_csv(tables_dir / "group_mean_scores.csv")
    if not summary["group_high_fraction_df"].empty:
        summary["group_high_fraction_df"].to_csv(tables_dir / "group_high_fraction.csv")

    generate_figures(output_dir, adata, summary)
    _write_figure_data(output_dir, summary, overlap_df)
    write_report(output_dir, summary, params, input_file)

    store_analysis_metadata(adata, SKILL_NAME, method, params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    command_parts = [
        "python",
        SCRIPT_REL_PATH,
        "--output",
        str(output_dir),
        "--method",
        method,
        "--top-pathways",
        str(args.top_pathways),
        "--gene-sets",
        str(gene_sets_path),
    ]
    if input_file:
        command_parts.extend(["--input", input_file])
    if resolved_groupby:
        command_parts.extend(["--groupby", resolved_groupby])
    if method == "aucell_r" and args.aucell_auc_max_rank is not None:
        command_parts.extend(["--aucell-auc-max-rank", str(args.aucell_auc_max_rank)])
    if method == "score_genes_py":
        command_parts.extend(
            [
                "--score-genes-ctrl-size",
                str(args.score_genes_ctrl_size),
                "--score-genes-n-bins",
                str(args.score_genes_n_bins),
            ]
        )
    (repro_dir / "commands.sh").write_text("#!/bin/bash\n" + " ".join(command_parts) + "\n", encoding="utf-8")
    repro_packages = ["scanpy", "anndata", "pandas", "matplotlib"]
    _write_repro_requirements(repro_dir, repro_packages)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    summary_json = {
        key: value
        for key, value in summary.items()
        if key
        not in {
            "top_pathways_df",
            "group_means_df",
            "group_high_fraction_df",
            "top_pathway_scores_long_df",
        }
    }
    result_data = {"params": params}
    result_data["next_steps"] = []
    r_enhanced_figures = _render_r_enhanced(output_dir, output_dir / "figure_data", args.r_enhanced)
    result_data["r_enhanced_figures"] = r_enhanced_figures
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary_json, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary_json,
        "data": result_data,
    }
    write_standard_run_artifacts(output_dir, result_payload, summary)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"  Gene sets scored: {summary['n_gene_sets']}")

    # --- Next-step guidance ---
    print()
    print("▶ Analysis complete. Consider sc-de to compare scores between groups:")
    print(f"  python omicsclaw.py run sc-de --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()
