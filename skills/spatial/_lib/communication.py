"""Spatial cell-cell communication analysis functions.

Provides LIANA, CellPhoneDB, FastCCC, and CellChat (R) wrappers for
ligand-receptor analysis with method-specific parameter handling.

Input matrix convention:
  All four CCC methods use log-normalized expression in ``adata.X``.

  - liana:       ``adata.X`` or ``adata.raw`` (if available)
  - cellphonedb: ``adata.X`` (log-normalized; do not pass scaled matrices)
  - fastccc:     ``adata.X`` (current OmicsClaw wrapper writes an h5ad view)
  - cellchat_r:  ``adata.X`` (normalized + log-transformed)
"""

from __future__ import annotations

import logging
import os
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from omicsclaw.common.runtime_env import ensure_runtime_cache_dirs

ensure_runtime_cache_dirs()

from .dependency_manager import require

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("liana", "cellphonedb", "fastccc", "cellchat_r")
SUPPORTED_SPECIES = ("human", "mouse")
NORMALIZED_METHODS = SUPPORTED_METHODS

METHOD_PARAM_DEFAULTS = {
    "liana": {
        "expr_prop": 0.1,
        "min_cells": 5,
        "n_perms": 1000,
        "resource": "auto",
    },
    "cellphonedb": {
        "iterations": 1000,
        "threshold": 0.1,
    },
    "fastccc": {
        "single_unit_summary": "Mean",
        "complex_aggregation": "Minimum",
        "lr_combination": "Arithmetic",
        "min_percentile": 0.1,
    },
    "cellchat_r": {
        "prob_type": "triMean",
        "min_cells": 10,
    },
}

METHOD_SPECIES_SUPPORT = {
    "liana": {"human", "mouse"},
    "cellphonedb": {"human"},
    "fastccc": {"human"},
    "cellchat_r": {"human", "mouse"},
}

METHOD_RESULT_KEYS = {
    "liana": "liana_results",
    "cellphonedb": "cellphonedb_results",
    "fastccc": "fastccc_results",
    "cellchat_r": "cellchat_results",
}

CELLPHONEDB_REQUIRED_TABLES = (
    "gene_table.csv",
    "protein_table.csv",
    "complex_composition_table.csv",
    "complex_table.csv",
    "interaction_table.csv",
)

CELLPHONEDB_DB_ENV_VARS = (
    "OMICSCLAW_CELLPHONEDB_DB_PATH",
    "CELLPHONEDB_DB_PATH",
    "OMICSCLAW_CELLPHONEDB_ZIP",
    "OMICSCLAW_CELLPHONEDB_DB_DIR",
)


def _empty_lr_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["ligand", "receptor", "source", "target", "score", "pvalue"]
    )


def _is_cellphonedb_dir(path: Path) -> bool:
    return path.is_dir() and all((path / name).exists() for name in CELLPHONEDB_REQUIRED_TABLES)


def _iter_db_candidates() -> list[Path]:
    candidates: list[Path] = []

    for env_name in CELLPHONEDB_DB_ENV_VARS:
        value = os.getenv(env_name)
        if value:
            candidates.append(Path(value).expanduser())

    try:
        import cellphonedb

        package_root = Path(cellphonedb.__file__).resolve().parent
        candidates.extend(package_root.rglob("cellphonedb.zip"))
    except Exception:
        pass

    for user_root in (
        Path.home() / ".cpdb",
        Path.home() / ".cache" / "cellphonedb",
        Path.home() / ".local" / "share" / "cellphonedb",
    ):
        if not user_root.exists():
            continue
        candidates.extend(user_root.rglob("cellphonedb.zip"))
        for candidate in user_root.rglob("interaction_table.csv"):
            candidates.append(candidate.parent)

    seen: set[str] = set()
    deduped: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _find_cellphonedb_db_source() -> Path | None:
    for candidate in _iter_db_candidates():
        if candidate.is_file() and candidate.suffix == ".zip":
            return candidate
        if _is_cellphonedb_dir(candidate):
            return candidate
    return None


def _resolve_extracted_db_root(extract_root: Path) -> Path:
    if _is_cellphonedb_dir(extract_root):
        return extract_root
    for candidate in extract_root.rglob("interaction_table.csv"):
        parent = candidate.parent
        if _is_cellphonedb_dir(parent):
            return parent
    raise FileNotFoundError(
        "Extracted CellPhoneDB database did not contain the required CSV tables."
    )


def _materialize_cellphonedb_zip(source: Path, work_dir: Path) -> Path:
    if source.is_file() and source.suffix == ".zip":
        return source
    if not _is_cellphonedb_dir(source):
        raise FileNotFoundError(
            f"CellPhoneDB database source must be a .zip file or a directory with {CELLPHONEDB_REQUIRED_TABLES}"
        )

    zip_path = work_dir / "cellphonedb.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for csv_path in sorted(source.rglob("*.csv")):
            zf.write(csv_path, arcname=csv_path.name)
    return zip_path


def _materialize_fastccc_db_dir(source: Path, work_dir: Path) -> Path:
    if _is_cellphonedb_dir(source):
        return source
    if source.is_file() and source.suffix == ".zip":
        extract_root = work_dir / "cellphonedb_db"
        extract_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source) as zf:
            zf.extractall(extract_root)
        return _resolve_extracted_db_root(extract_root)
    raise FileNotFoundError(
        f"FastCCC requires a CellPhoneDB directory or zip archive. Got: {source}"
    )


def _require_cellphonedb_database() -> Path:
    source = _find_cellphonedb_db_source()
    if source is None:
        raise FileNotFoundError(
            "Could not locate a CellPhoneDB database. "
            "Set OMICSCLAW_CELLPHONEDB_DB_PATH to either a cellphonedb.zip file "
            "or an extracted CellPhoneDB directory."
        )
    return source


def _validate_species(method: str, species: str) -> str:
    species_lower = species.lower()
    if species_lower not in SUPPORTED_SPECIES:
        raise ValueError(
            f"Unsupported species '{species}'. Choose from: {SUPPORTED_SPECIES}."
        )
    supported = METHOD_SPECIES_SUPPORT[method]
    if species_lower not in supported:
        raise ValueError(
            f"Method '{method}' currently supports {sorted(supported)}, not '{species_lower}'."
        )
    return species_lower


def _split_cell_pair(pair: str, sep: str = "|") -> tuple[str, str]:
    parts = str(pair).split(sep, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return str(pair), ""


def _round_numeric(series: pd.Series, *, default: float) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default).astype(float).round(4)


def _standardize_lr_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _empty_lr_df()

    out = df.copy()
    for column in ("ligand", "receptor", "source", "target"):
        if column not in out.columns:
            out[column] = ""
        out[column] = out[column].fillna("").astype(str)

    if "score" not in out.columns:
        out["score"] = 0.0
    if "pvalue" not in out.columns:
        out["pvalue"] = 1.0
    out["score"] = _round_numeric(out["score"], default=0.0)
    out["pvalue"] = _round_numeric(out["pvalue"], default=1.0)

    keep_cols = ["ligand", "receptor", "source", "target", "score", "pvalue"]
    if "pathway" in out.columns:
        out["pathway"] = out["pathway"].fillna("").astype(str)
        keep_cols.append("pathway")
    return out[keep_cols].sort_values("score", ascending=False).reset_index(drop=True)


def _load_fastccc_interaction_lookup(db_dir: Path) -> pd.DataFrame:
    interactions = pd.read_csv(db_dir / "interaction_table.csv")[
        ["id_cp_interaction", "multidata_1_id", "multidata_2_id"]
    ].drop_duplicates()

    gene_table = pd.read_csv(db_dir / "gene_table.csv")
    protein_table = pd.read_csv(db_dir / "protein_table.csv")
    merged = gene_table.merge(
        protein_table,
        left_on="protein_id",
        right_on="id_protein",
        how="left",
    )
    id_to_symbol = dict(
        zip(merged["protein_multidata_id"].tolist(), merged["hgnc_symbol"].tolist())
    )

    complex_table = pd.read_csv(db_dir / "complex_table.csv")
    complex_composition = pd.read_csv(db_dir / "complex_composition_table.csv")
    complex_members = complex_table.merge(
        complex_composition,
        on="complex_multidata_id",
        how="left",
    )
    for complex_id, member_ids in complex_members.groupby("complex_multidata_id")["protein_multidata_id"]:
        symbols = [id_to_symbol.get(member_id, str(member_id)) for member_id in member_ids.tolist()]
        id_to_symbol[complex_id] = ",".join(symbols)

    lookup = interactions.rename(columns={"id_cp_interaction": "LRI_ID"}).copy()
    lookup["ligand"] = lookup["multidata_1_id"].map(lambda x: id_to_symbol.get(x, str(x)))
    lookup["receptor"] = lookup["multidata_2_id"].map(lambda x: id_to_symbol.get(x, str(x)))
    return lookup[["LRI_ID", "ligand", "receptor"]]


def _flatten_fastccc_results(
    interactions_strength: pd.DataFrame,
    pvals: pd.DataFrame,
    db_dir: Path,
) -> pd.DataFrame:
    if interactions_strength is None or interactions_strength.empty:
        return _empty_lr_df()

    pvals_aligned = pvals.reindex(
        index=interactions_strength.index,
        columns=interactions_strength.columns,
    )
    score_values = interactions_strength.to_numpy()
    row_idx, col_idx = np.where(np.isfinite(score_values) & (score_values > 0))
    if len(row_idx) == 0:
        return _empty_lr_df()

    cell_pairs = interactions_strength.index.to_numpy()
    interaction_ids = interactions_strength.columns.to_numpy()

    flat = pd.DataFrame(
        {
            "cell_pair": cell_pairs[row_idx],
            "LRI_ID": interaction_ids[col_idx],
            "score": score_values[row_idx, col_idx],
            "pvalue": pvals_aligned.to_numpy()[row_idx, col_idx],
        }
    )
    flat[["source", "target"]] = flat["cell_pair"].apply(
        lambda x: pd.Series(_split_cell_pair(x))
    )
    lookup = _load_fastccc_interaction_lookup(db_dir)
    flat = flat.merge(lookup, on="LRI_ID", how="left")
    return _standardize_lr_df(flat)


def _extract_cellphonedb_pair(row: pd.Series) -> tuple[str, str]:
    for left, right in (("gene_a", "gene_b"), ("partner_a", "partner_b")):
        if left in row.index and right in row.index:
            return str(row.get(left, "")), str(row.get(right, ""))

    pair = str(row.get("interacting_pair", ""))
    if "|" in pair:
        ligand, receptor = pair.split("|", 1)
        return ligand, receptor
    if "_" in pair:
        ligand, receptor = pair.split("_", 1)
        return ligand, receptor
    return pair, ""


def _run_liana(
    adata,
    *,
    cell_type_key: str = "leiden",
    species: str = "human",
    expr_prop: float = METHOD_PARAM_DEFAULTS["liana"]["expr_prop"],
    min_cells: int = METHOD_PARAM_DEFAULTS["liana"]["min_cells"],
    n_perms: int = METHOD_PARAM_DEFAULTS["liana"]["n_perms"],
    resource: str = METHOD_PARAM_DEFAULTS["liana"]["resource"],
) -> tuple[pd.DataFrame, dict]:
    """Run LIANA+ rank_aggregate."""
    li = require("liana", feature="LIANA+ cell communication")

    species = _validate_species("liana", species)
    if resource == "auto":
        resource_name = "mouseconsensus" if species == "mouse" else "consensus"
    else:
        resource_name = resource

    use_raw = adata.raw is not None
    logger.info(
        "Running LIANA rank_aggregate on %s with resource=%s, expr_prop=%s, min_cells=%d, n_perms=%d",
        "adata.raw" if use_raw else "adata.X",
        resource_name,
        expr_prop,
        min_cells,
        n_perms,
    )

    li.mt.rank_aggregate(
        adata,
        groupby=cell_type_key,
        use_raw=use_raw,
        resource_name=resource_name,
        expr_prop=expr_prop,
        min_cells=min_cells,
        n_perms=n_perms,
        verbose=True,
    )

    if "liana_res" not in adata.uns or adata.uns["liana_res"].empty:
        logger.warning("LIANA returned empty results.")
        return _empty_lr_df(), {
            "effective_params": {
                "liana_resource": resource_name,
                "liana_expr_prop": expr_prop,
                "liana_min_cells": min_cells,
                "liana_n_perms": n_perms,
            }
        }

    df = adata.uns["liana_res"].copy()
    rename_map = {}
    if "ligand_complex" in df.columns:
        rename_map["ligand_complex"] = "ligand"
    if "receptor_complex" in df.columns:
        rename_map["receptor_complex"] = "receptor"
    if "sender" in df.columns and "source" not in df.columns:
        rename_map["sender"] = "source"
    if "receiver" in df.columns and "target" not in df.columns:
        rename_map["receiver"] = "target"
    if rename_map:
        df = df.rename(columns=rename_map)

    if "magnitude_rank" in df.columns:
        df["score"] = 1.0 - pd.to_numeric(df["magnitude_rank"], errors="coerce")
    elif "lr_means" in df.columns:
        df["score"] = pd.to_numeric(df["lr_means"], errors="coerce")
    else:
        df["score"] = 0.0

    if "cellphone_pvals" in df.columns:
        df["pvalue"] = pd.to_numeric(df["cellphone_pvals"], errors="coerce")
    elif "specificity_rank" in df.columns:
        df["pvalue"] = pd.to_numeric(df["specificity_rank"], errors="coerce")
    else:
        df["pvalue"] = 1.0

    return _standardize_lr_df(df), {
        "effective_params": {
            "liana_resource": resource_name,
            "liana_expr_prop": expr_prop,
            "liana_min_cells": min_cells,
            "liana_n_perms": n_perms,
        }
    }


def _run_cellphonedb(
    adata,
    *,
    cell_type_key: str = "leiden",
    species: str = "human",
    iterations: int = METHOD_PARAM_DEFAULTS["cellphonedb"]["iterations"],
    threshold: float = METHOD_PARAM_DEFAULTS["cellphonedb"]["threshold"],
) -> tuple[pd.DataFrame, dict]:
    """Run CellPhoneDB statistical analysis."""
    require("cellphonedb", feature="CellPhoneDB cell communication")
    from cellphonedb.src.core.methods import cpdb_statistical_analysis_method

    species = _validate_species("cellphonedb", species)

    with tempfile.TemporaryDirectory(prefix="cpdb_omicsclaw_") as tmp:
        tmp_path = Path(tmp)
        db_source = _require_cellphonedb_database()
        cpdb_zip_path = _materialize_cellphonedb_zip(db_source, tmp_path)

        meta_df = pd.DataFrame(
            {"Cell": adata.obs_names, "cell_type": adata.obs[cell_type_key].astype(str).values}
        )
        meta_path = tmp_path / "meta.tsv"
        meta_df.to_csv(meta_path, sep="\t", index=False)

        logger.info(
            "Running CellPhoneDB statistical analysis with iterations=%d, threshold=%s",
            iterations,
            threshold,
        )
        result = cpdb_statistical_analysis_method.call(
            cpdb_file_path=str(cpdb_zip_path),
            meta_file_path=str(meta_path),
            counts_file_path=adata.copy(),
            counts_data="hgnc_symbol",
            output_path=str(tmp_path),
            iterations=iterations,
            threshold=threshold,
            threads=4,
        )

    means_df = result.get("means")
    pvalues_df = result.get("pvalues")
    if means_df is None or means_df.empty:
        logger.warning("CellPhoneDB returned empty results.")
        return _empty_lr_df(), {
            "effective_params": {
                "cellphonedb_iterations": iterations,
                "cellphonedb_threshold": threshold,
            }
        }

    if pvalues_df is not None and not pvalues_df.empty:
        pvalues_df = pvalues_df.reindex(means_df.index)

    records: list[dict] = []
    for _, row in means_df.iterrows():
        ligand, receptor = _extract_cellphonedb_pair(row)
        for col in means_df.columns:
            if "|" not in col:
                continue
            pair = str(col).split("|", 1)
            if len(pair) != 2:
                continue
            score = pd.to_numeric(row.get(col), errors="coerce")
            if pd.isna(score) or float(score) <= 0:
                continue
            pvalue = 1.0
            if pvalues_df is not None and col in pvalues_df.columns and row.name in pvalues_df.index:
                pvalue = pvalues_df.loc[row.name, col]
            records.append(
                {
                    "ligand": ligand,
                    "receptor": receptor,
                    "source": pair[0],
                    "target": pair[1],
                    "score": score,
                    "pvalue": pvalue,
                }
            )

    return _standardize_lr_df(pd.DataFrame(records)), {
        "effective_params": {
            "cellphonedb_iterations": iterations,
            "cellphonedb_threshold": threshold,
        }
    }


def _run_fastccc(
    adata,
    *,
    cell_type_key: str = "leiden",
    species: str = "human",
    single_unit_summary: str = METHOD_PARAM_DEFAULTS["fastccc"]["single_unit_summary"],
    complex_aggregation: str = METHOD_PARAM_DEFAULTS["fastccc"]["complex_aggregation"],
    lr_combination: str = METHOD_PARAM_DEFAULTS["fastccc"]["lr_combination"],
    min_percentile: float = METHOD_PARAM_DEFAULTS["fastccc"]["min_percentile"],
) -> tuple[pd.DataFrame, dict]:
    """Run FastCCC via its public ``statistical_analysis_method`` API."""
    require("fastccc", feature="FastCCC cell communication")
    import fastccc

    species = _validate_species("fastccc", species)

    with tempfile.TemporaryDirectory(prefix="fastccc_omicsclaw_") as tmp:
        tmp_path = Path(tmp)
        db_source = _require_cellphonedb_database()
        fastccc_db_dir = _materialize_fastccc_db_dir(db_source, tmp_path)

        input_path = tmp_path / "fastccc_input.h5ad"
        adata.write_h5ad(input_path)

        result_dir = tmp_path / "fastccc_results"
        result_dir.mkdir(exist_ok=True)

        logger.info(
            "Running FastCCC with single_unit_summary=%s, complex_aggregation=%s, lr_combination=%s, min_percentile=%s",
            single_unit_summary,
            complex_aggregation,
            lr_combination,
            min_percentile,
        )
        interactions_strength, pvals, _percents = fastccc.statistical_analysis_method(
            database_file_path=str(fastccc_db_dir),
            celltype_file_path="",
            counts_file_path=str(input_path),
            convert_type="hgnc_symbol",
            single_unit_summary=single_unit_summary,
            complex_aggregation=complex_aggregation,
            LR_combination=lr_combination,
            min_percentile=min_percentile,
            meta_key=cell_type_key,
            save_path=str(result_dir),
        )

        lr_df = _flatten_fastccc_results(interactions_strength, pvals, fastccc_db_dir)

    return lr_df, {
        "effective_params": {
            "fastccc_single_unit_summary": single_unit_summary,
            "fastccc_complex_aggregation": complex_aggregation,
            "fastccc_lr_combination": lr_combination,
            "fastccc_min_percentile": min_percentile,
        }
    }


def _run_cellchat_r(
    adata,
    *,
    cell_type_key: str = "leiden",
    species: str = "human",
    prob_type: str = METHOD_PARAM_DEFAULTS["cellchat_r"]["prob_type"],
    min_cells: int = METHOD_PARAM_DEFAULTS["cellchat_r"]["min_cells"],
) -> tuple[pd.DataFrame, dict]:
    """Run CellChat via an R subprocess."""
    import pandas as pd

    from omicsclaw.core.dependency_manager import validate_r_environment
    from omicsclaw.core.r_script_runner import RScriptRunner
    from omicsclaw.core.r_utils import read_r_result_csv

    species = _validate_species("cellchat_r", species)
    validate_r_environment(
        required_r_packages=["CellChat", "SingleCellExperiment", "zellkonverter"]
    )

    scripts_dir = Path(__file__).resolve().parents[3] / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_cellchat_sp_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_path = tmpdir / "input.h5ad"
        adata.write_h5ad(input_path)

        output_dir = tmpdir / "output"
        output_dir.mkdir()

        runner.run_script(
            "sc_cellchat.R",
            args=[
                str(input_path),
                str(output_dir),
                cell_type_key,
                species,
                prob_type,
                str(min_cells),
            ],
            expected_outputs=["cellchat_results.csv"],
            output_dir=output_dir,
        )

        df = read_r_result_csv(output_dir / "cellchat_results.csv", index_col=None)
        extra_tables: dict[str, pd.DataFrame] = {}
        optional_tables = {
            "cellchat_pathways_df": ("cellchat_pathways.csv", None),
            "cellchat_centrality_df": ("cellchat_centrality.csv", None),
            "cellchat_count_matrix_df": ("cellchat_count_matrix.csv", 0),
            "cellchat_weight_matrix_df": ("cellchat_weight_matrix.csv", 0),
        }
        for table_key, (filename, index_col) in optional_tables.items():
            table_path = output_dir / filename
            if table_path.exists():
                extra_tables[table_key] = pd.read_csv(table_path, index_col=index_col)

    if df.empty:
        return _empty_lr_df(), {
            "effective_params": {
                "cellchat_prob_type": prob_type,
                "cellchat_min_cells": min_cells,
            },
            "extra_tables": extra_tables,
        }

    df = df.rename(columns={"prob": "score", "pval": "pvalue"})
    return _standardize_lr_df(df), {
        "effective_params": {
            "cellchat_prob_type": prob_type,
            "cellchat_min_cells": min_cells,
        },
        "extra_tables": extra_tables,
    }


def aggregate_by_pathway(lr_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate communication results by cell-type pair and pathway when present."""
    if lr_df.empty or "source" not in lr_df.columns or "target" not in lr_df.columns:
        return pd.DataFrame()

    group_cols = ["source", "target"]
    has_pathway = "pathway" in lr_df.columns and lr_df["pathway"].fillna("").astype(str).ne("").any()
    if has_pathway:
        group_cols.append("pathway")

    records = []
    for keys, grp in lr_df.groupby(group_cols, observed=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        key_map = dict(zip(group_cols, keys))
        best = grp.loc[grp["score"].idxmax()] if "score" in grp.columns and not grp["score"].isna().all() else grp.iloc[0]
        record = {
            "source": key_map["source"],
            "target": key_map["target"],
            "n_interactions": int(len(grp)),
            "mean_score": float(pd.to_numeric(grp["score"], errors="coerce").fillna(0.0).mean()),
            "top_ligand": str(best.get("ligand", "")),
            "top_receptor": str(best.get("receptor", "")),
        }
        if has_pathway:
            record["pathway"] = key_map["pathway"]
        records.append(record)

    sort_cols = ["mean_score"]
    return pd.DataFrame(records).sort_values(sort_cols, ascending=False).reset_index(drop=True)


def classify_signaling_roles(lr_df: pd.DataFrame) -> pd.DataFrame:
    """Classify each cell type's signaling role."""
    if lr_df.empty:
        return pd.DataFrame()

    all_types = set()
    if "source" in lr_df.columns:
        all_types.update(lr_df["source"].unique())
    if "target" in lr_df.columns:
        all_types.update(lr_df["target"].unique())

    records = []
    for ct in sorted(all_types, key=str):
        out_mask = lr_df["source"] == ct if "source" in lr_df.columns else pd.Series(False, index=lr_df.index)
        in_mask = lr_df["target"] == ct if "target" in lr_df.columns else pd.Series(False, index=lr_df.index)

        sender_score = float(pd.to_numeric(lr_df.loc[out_mask, "score"], errors="coerce").fillna(0.0).sum())
        receiver_score = float(pd.to_numeric(lr_df.loc[in_mask, "score"], errors="coerce").fillna(0.0).sum())
        n_out = int(out_mask.sum())
        n_in = int(in_mask.sum())
        hub_score = sender_score + receiver_score

        if sender_score > receiver_score * 1.5:
            role = "sender"
        elif receiver_score > sender_score * 1.5:
            role = "receiver"
        else:
            role = "balanced"

        records.append(
            {
                "cell_type": str(ct),
                "sender_score": round(sender_score, 4),
                "receiver_score": round(receiver_score, 4),
                "hub_score": round(hub_score, 4),
                "dominant_role": role,
                "n_outgoing": n_out,
                "n_incoming": n_in,
            }
        )

    return pd.DataFrame(records).sort_values("hub_score", ascending=False).reset_index(drop=True)


def _persist_results_to_adata(
    adata,
    *,
    method: str,
    lr_df: pd.DataFrame,
    pathway_df: pd.DataFrame,
    roles_df: pd.DataFrame,
    cell_type_key: str,
    species: str,
    effective_params: dict,
    extra_tables: dict[str, pd.DataFrame] | None = None,
) -> None:
    adata.uns["ccc_results"] = lr_df.copy()
    adata.uns[METHOD_RESULT_KEYS[method]] = lr_df.copy()
    adata.uns["communication_summary"] = pathway_df.copy()
    adata.uns["communication_signaling_roles"] = roles_df.copy()
    adata.uns["spatial_communication"] = {
        "method": method,
        "cell_type_key": cell_type_key,
        "species": species,
        "effective_params": effective_params,
        "result_key": METHOD_RESULT_KEYS[method],
        "available_extra_tables": sorted((extra_tables or {}).keys()),
    }

    for key, value in (extra_tables or {}).items():
        if isinstance(value, pd.DataFrame) and not value.empty:
            adata.uns[key] = value.copy()


def run_communication(
    adata,
    *,
    method: str = "liana",
    cell_type_key: str = "leiden",
    species: str = "human",
    method_params: dict | None = None,
) -> dict:
    """Run cell-cell communication analysis on a preprocessed AnnData object."""
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {SUPPORTED_METHODS}")
    if cell_type_key not in adata.obs.columns:
        raise ValueError(f"Cell type key '{cell_type_key}' not in adata.obs")

    method_params = method_params or {}
    species = _validate_species(method, species)

    n_cells, n_genes = adata.n_obs, adata.n_vars
    cell_types = sorted(adata.obs[cell_type_key].astype(str).unique().tolist(), key=str)

    dispatch = {
        "liana": lambda: _run_liana(adata, cell_type_key=cell_type_key, species=species, **method_params),
        "cellphonedb": lambda: _run_cellphonedb(adata, cell_type_key=cell_type_key, species=species, **method_params),
        "fastccc": lambda: _run_fastccc(adata, cell_type_key=cell_type_key, species=species, **method_params),
        "cellchat_r": lambda: _run_cellchat_r(adata, cell_type_key=cell_type_key, species=species, **method_params),
    }
    lr_df, method_meta = dispatch[method]()
    effective_params = method_meta.get("effective_params", {})
    extra_tables = method_meta.get("extra_tables", {})

    sig_df = lr_df[lr_df["pvalue"] < 0.05].copy() if not lr_df.empty else lr_df
    ranking_df = sig_df if not sig_df.empty else lr_df

    pathway_df = aggregate_by_pathway(ranking_df)
    roles_df = classify_signaling_roles(ranking_df)

    _persist_results_to_adata(
        adata,
        method=method,
        lr_df=lr_df,
        pathway_df=pathway_df,
        roles_df=roles_df,
        cell_type_key=cell_type_key,
        species=species,
        effective_params=effective_params,
        extra_tables=extra_tables,
    )

    return {
        "n_cells": int(n_cells),
        "n_genes": int(n_genes),
        "n_cell_types": int(len(cell_types)),
        "cell_types": cell_types,
        "cell_type_key": cell_type_key,
        "method": method,
        "species": species,
        "n_interactions_tested": int(len(lr_df)),
        "n_significant": int(len(sig_df)),
        "lr_df": lr_df,
        "top_df": ranking_df.head(50).copy() if not ranking_df.empty else ranking_df,
        "pathway_df": pathway_df,
        "signaling_roles_df": roles_df,
        "effective_params": effective_params,
        "extra_tables": extra_tables,
    }
