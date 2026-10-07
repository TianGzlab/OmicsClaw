"""Ligand-receptor scoring and backend tables without CLI report side effects."""

from __future__ import annotations

import logging
import tempfile
from copy import deepcopy
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError

from skills._sdk import deps as sc_dep_manager
from skills._sdk.deps import validate_r_environment
from skills._sdk.r_dependency_manager import check_r_tier, suggest_r_install
from skills._sdk.r_script_runner import RScriptRunner
from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR
from skills.singlecell._lib.adata_utils import infer_x_matrix_kind, matrix_looks_count_like

__all__ = ['communicate', 'builtin_lr', 'liana_lr', 'cellphonedb_lr', 'cellchat_lr',
           'nichenet_ligands', 'sender_receiver_summary', 'group_role_summary',
           'pathway_summary', 'top_interactions', 'backend_tables',
           'interaction_heatmap_figure', 'run_info']
logger = logging.getLogger(__name__)
_RUN_KEY = 'omicsclaw_sc_cell_communication_run'
_TABLES_KEY = 'omicsclaw_sc_cell_communication_tables'

OUTPUT_COLUMNS = ["ligand", "receptor", "source", "target", "score", "pvalue", "pathway"]


CELLPHONEDB_DB_VERSION = "v4.1.0"


NICHENET_RESOURCE_URLS = {
    "lr_network_human_21122021.rds": "https://zenodo.org/record/7074291/files/lr_network_human_21122021.rds",
    "weighted_networks_nsga2r_final.rds": "https://zenodo.org/record/7074291/files/weighted_networks_nsga2r_final.rds",
}


def _empty_lr_table() -> pd.DataFrame:
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def _cellphonedb_cache_path() -> Path:
    return Path.home() / ".cache" / "omicsclaw" / "cellphonedb" / CELLPHONEDB_DB_VERSION / "cellphonedb.zip"


def _nichenet_cache_paths() -> dict[str, Path]:
    cache_dir = Path.home() / ".cache" / "omicsclaw" / "nichenet"
    return {name: cache_dir / name for name in NICHENET_RESOURCE_URLS}


def _build_expression_export_adata(adata, *, expect_normalized: bool) -> tuple[object, str]:
    """Return the expression matrix export best aligned with method semantics."""
    if expect_normalized:
        if infer_x_matrix_kind(adata) != "normalized_expression":
            raise ValueError(
                "This communication method expects normalized expression in `adata.X`. Run `sc-preprocessing` first."
            )
        return adata.copy(), "adata.X"
    if "counts" in adata.layers and adata.layers["counts"].shape == adata.shape:
        export = adata.copy()
        export.X = adata.layers["counts"].copy()
        return export, "layers.counts"
    if adata.raw is not None and adata.raw.shape == adata.shape and matrix_looks_count_like(adata.raw.X):
        export = adata.copy()
        export.X = adata.raw.X.copy()
        export.var = adata.raw.var.copy()
        export.var_names = adata.raw.var_names.astype(str)
        return export, "adata.raw"
    if matrix_looks_count_like(adata.X):
        return adata.copy(), "adata.X"
    raise ValueError(
        "This communication method requires a raw count-like matrix in `layers['counts']`, aligned `adata.raw`, or count-like `adata.X`."
    )


def _resolve_cellphonedb_database() -> Path:
    """Ensure the official CellPhoneDB database zip exists locally."""
    from cellphonedb.utils import db_utils

    db_path = _cellphonedb_cache_path()
    cache_dir = db_path.parent
    cache_dir.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        logger.info("Downloading CellPhoneDB database %s...", CELLPHONEDB_DB_VERSION)
        db_utils.download_database(str(cache_dir), CELLPHONEDB_DB_VERSION)
    if not db_path.exists():
        raise FileNotFoundError(f"CellPhoneDB database not found at {db_path}")
    return db_path


BUILTIN_LR = [
    ("TGFB1", "TGFBR1"),
    ("TGFB1", "TGFBR2"),
    ("CXCL12", "CXCR4"),
    ("CCL5", "CCR5"),
    ("CXCL8", "CXCR1"),
    ("CXCL8", "CXCR2"),
    ("IL7", "IL7R"),
    ("CSF1", "CSF1R"),
    ("EGF", "EGFR"),
    ("HGF", "MET"),
    ("JAG1", "NOTCH1"),
    ("DLL4", "NOTCH1"),
]


def _build_cellchat_input_adata(adata):
    return _build_expression_export_adata(adata, expect_normalized=True)


def _build_nichenet_input_adata(adata):
    return _build_expression_export_adata(adata, expect_normalized=False)


def _prepare_cellphonedb_input_adata(adata, *, cell_type_key: str):
    export, source = _build_cellchat_input_adata(adata)
    export = export.copy()
    export.obs = export.obs.copy()

    cell_names = export.obs_names.astype(str).str.replace("-", "_", regex=False)
    export.obs_names = cell_names

    labels = export.obs[cell_type_key].astype(str)
    numeric_like = labels.str.fullmatch(r"\d+(\.\d+)?").fillna(False)
    labels = labels.where(~numeric_like, "cluster_" + labels)
    export.obs[cell_type_key] = labels.values

    meta = pd.DataFrame({"Cell": export.obs_names.astype(str), "cell_type": labels.astype(str).values})
    notes = {
        "renamed_cells": bool((cell_names != adata.obs_names.astype(str)).any()),
        "renamed_numeric_clusters": bool(numeric_like.any()),
        "expression_source": source,
    }
    return export, meta, notes


def run_cellchat(
    adata,
    *,
    cell_type_key: str,
    species: str,
    prob_type: str,
    min_cells: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    installed, missing = check_r_tier("singlecell-communication")
    if any(pkg in missing for pkg in ("CellChat", "SingleCellExperiment", "zellkonverter")):
        raise ImportError(
            "CellChat R dependencies are missing: "
            + ", ".join(pkg for pkg in ("CellChat", "SingleCellExperiment", "zellkonverter") if pkg in missing)
            + "\nInstall with:\n"
            + suggest_r_install([pkg for pkg in ("CellChat", "SingleCellExperiment", "zellkonverter") if pkg in missing])
        )
    validate_r_environment(required_r_packages=["CellChat", "SingleCellExperiment", "zellkonverter"])
    scripts_dir = _SDK_R_SCRIPTS_DIR
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=7200)
    export, source = _build_cellchat_input_adata(adata)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_cellchat_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        basilisk_dir = tmpdir / "basilisk"
        r_home = tmpdir / "r_home"
        xdg_cache = tmpdir / "xdg_cache"
        output_dir.mkdir(parents=True, exist_ok=True)
        for path in (basilisk_dir, r_home, xdg_cache):
            path.mkdir(parents=True, exist_ok=True)
        export.write_h5ad(input_h5ad)
        runner.run_script(
            "sc_cellchat.R",
            args=[str(input_h5ad), str(output_dir), cell_type_key, species, prob_type, str(int(min_cells))],
            expected_outputs=["cellchat_results.csv"],
            output_dir=output_dir,
            env={
                "BASILISK_EXTERNAL_DIR": str(basilisk_dir),
                "HOME": str(r_home),
                "XDG_CACHE_HOME": str(xdg_cache),
                "ZELLKONVERTER_USE_BASILISK": "FALSE",
                "OMICSCLAW_NICHENET_CACHE": str(Path.home() / ".cache" / "omicsclaw" / "nichenet"),
            },
        )
        try:
            df = pd.read_csv(output_dir / "cellchat_results.csv")
        except EmptyDataError:
            df = pd.DataFrame(columns=["ligand", "receptor", "source", "target", "score", "pvalue", "pathway"])
        extras = {}
        for name in (
            "cellchat_pathways.csv",
            "cellchat_centrality.csv",
            "cellchat_count_matrix.csv",
            "cellchat_weight_matrix.csv",
        ):
            path = output_dir / name
            if path.exists():
                try:
                    extras[name] = pd.read_csv(path, index_col=0 if name.endswith("_matrix.csv") else None)
                except Exception:
                    continue
    notes = {
        "expression_source": source,
        "cellchat_prob_type": prob_type,
        "cellchat_min_cells": int(min_cells),
        "pathway_df": extras.get("cellchat_pathways.csv", pd.DataFrame()),
        "centrality_df": extras.get("cellchat_centrality.csv", pd.DataFrame()),
        "count_matrix_df": extras.get("cellchat_count_matrix.csv", pd.DataFrame()),
        "weight_matrix_df": extras.get("cellchat_weight_matrix.csv", pd.DataFrame()),
    }
    return df, notes


def run_nichenet(
    adata,
    *,
    cell_type_key: str,
    species: str,
    condition_key: str,
    condition_oi: str,
    condition_ref: str,
    receiver: str,
    senders: list[str],
    top_ligands: int,
    expression_pct: float,
    lfc_cutoff: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    if species != "human":
        raise ValueError("The current NicheNet wrapper only supports species='human'.")

    installed, missing = check_r_tier("singlecell-communication")
    if any(pkg in missing for pkg in ("nichenetr", "Seurat", "SingleCellExperiment", "zellkonverter")):
        raise ImportError(
            "NicheNet R dependencies are missing: "
            + ", ".join(pkg for pkg in ("nichenetr", "Seurat", "SingleCellExperiment", "zellkonverter") if pkg in missing)
            + "\nInstall with:\n"
            + suggest_r_install([pkg for pkg in ("nichenetr", "Seurat", "SingleCellExperiment", "zellkonverter") if pkg in missing])
        )
    validate_r_environment(required_r_packages=["nichenetr", "Seurat", "SingleCellExperiment", "zellkonverter"])
    scripts_dir = _SDK_R_SCRIPTS_DIR
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=7200)
    export, source = _build_nichenet_input_adata(adata)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_nichenet_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        basilisk_dir = tmpdir / "basilisk"
        r_home = tmpdir / "r_home"
        xdg_cache = tmpdir / "xdg_cache"
        cache_dir = Path.home() / ".cache" / "omicsclaw" / "nichenet"
        lr_network_path = cache_dir / "lr_network_human_21122021.rds"
        weighted_networks_path = cache_dir / "weighted_networks_nsga2r_final.rds"
        output_dir.mkdir(parents=True, exist_ok=True)
        for path in (basilisk_dir, r_home, xdg_cache):
            path.mkdir(parents=True, exist_ok=True)
        export.write_h5ad(input_h5ad)
        runner.run_script(
            "sc_nichenet.R",
            args=[
                str(input_h5ad),
                str(output_dir),
                cell_type_key,
                condition_key,
                condition_oi,
                condition_ref,
                receiver,
                ",".join(senders),
                str(int(top_ligands)),
                str(float(expression_pct)),
                str(float(lfc_cutoff)),
                str(lr_network_path),
                str(weighted_networks_path),
            ],
            expected_outputs=[
                "nichenet_ligand_activities.csv",
                "nichenet_ligand_target_links.csv",
                "nichenet_lr_network.csv",
            ],
            output_dir=output_dir,
            env={
                "BASILISK_EXTERNAL_DIR": str(basilisk_dir),
                "HOME": str(r_home),
                "XDG_CACHE_HOME": str(xdg_cache),
                "ZELLKONVERTER_USE_BASILISK": "FALSE",
            },
        )
        ligand_activities = pd.read_csv(output_dir / "nichenet_ligand_activities.csv")
        ligand_target_links = pd.read_csv(output_dir / "nichenet_ligand_target_links.csv")
        lr_network = pd.read_csv(output_dir / "nichenet_lr_network.csv")

    if lr_network.empty:
        lr_df = _empty_lr_table()
    else:
        lr_df = pd.DataFrame(
            {
                "ligand": lr_network["ligand"].astype(str),
                "receptor": lr_network["receptor"].astype(str),
                "source": lr_network["source"].astype(str),
                "target": lr_network["target"].astype(str),
                "score": pd.to_numeric(lr_network["score"], errors="coerce").fillna(0.0),
                "pvalue": np.nan,
                "pathway": "NicheNet",
            }
        ).sort_values("score", ascending=False).reset_index(drop=True)

    notes = {
        "expression_source": source,
        "receiver": receiver,
        "senders": senders,
        "n_prioritized_ligands": int(len(ligand_activities)),
        "nichenet_lfc_cutoff": float(lfc_cutoff),
    }
    ligand_receptors_path = output_dir / "nichenet_ligand_receptors.csv"
    ligand_receptors_df = pd.read_csv(ligand_receptors_path) if ligand_receptors_path.exists() else pd.DataFrame()
    notes["ligand_receptors_df"] = ligand_receptors_df
    return lr_df, ligand_activities, ligand_target_links, notes


def run_cellphonedb(
    adata,
    *,
    cell_type_key: str,
    species: str,
    counts_data: str,
    iterations: int,
    threshold: float,
    threads: int,
    pvalue: float,
    random_state: int = 0,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if species != "human":
        raise ValueError("The current CellPhoneDB wrapper only supports species='human'.")

    if not sc_dep_manager.is_available("cellphonedb"):
        raise ImportError(
            "`cellphonedb` is required for sc-cell-communication --method cellphonedb.\n"
            "Install: pip install -e \".[singlecell-communication]\""
        )
    from cellphonedb.src.core.methods import cpdb_statistical_analysis_method

    cpdb_file_path = _resolve_cellphonedb_database()
    export, meta_df, notes = _prepare_cellphonedb_input_adata(adata, cell_type_key=cell_type_key)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_cellphonedb_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        counts_path = tmpdir_path / "input.h5ad"
        meta_path = tmpdir_path / "meta.tsv"
        output_dir = tmpdir_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        export.write_h5ad(counts_path)
        meta_df.to_csv(meta_path, sep="\t", index=False)
        try:
            cpdb_statistical_analysis_method.call(
                cpdb_file_path=str(cpdb_file_path),
                meta_file_path=str(meta_path),
                counts_file_path=str(counts_path),
                counts_data=counts_data,
                output_path=str(output_dir),
                iterations=int(iterations),
                threshold=float(threshold),
                threads=int(threads),
                pvalue=float(pvalue),
                score_interactions=True,
                debug_seed=int(random_state),
            )
        except KeyError as exc:
            if exc.args != ("significant_means",):
                raise
            logger.info("CellPhoneDB reported no significant interactions for this dataset.")
            notes["no_significant_interactions"] = True
            return _empty_lr_table(), notes
        notes["cpdb_means_df"] = _read_cpdb_table(_resolve_cpdb_output_file(output_dir, "means") or Path(""))
        notes["cpdb_pvalues_df"] = _read_cpdb_table(_resolve_cpdb_output_file(output_dir, "pvalues") or Path(""))
        notes["cpdb_significant_df"] = _read_cpdb_table(_resolve_cpdb_output_file(output_dir, "significant_means") or Path(""))
        lr_df = _parse_cellphonedb_results(output_dir)
    return lr_df, notes


def _group_means(adata, cell_type_key: str) -> pd.DataFrame:
    X = adata.X
    var_names = adata.var_names
    if hasattr(X, "toarray"):
        X = X.toarray()
    df = pd.DataFrame(X, index=adata.obs_names, columns=var_names)
    groups = adata.obs[cell_type_key].astype(str)
    return df.groupby(groups).mean()


def _run_builtin(adata, *, cell_type_key: str, species: str) -> pd.DataFrame:
    means = _group_means(adata, cell_type_key)
    records = []
    for ligand, receptor in BUILTIN_LR:
        if ligand not in means.columns or receptor not in means.columns:
            continue
        for source in means.index:
            for target in means.index:
                score = float(means.loc[source, ligand] * means.loc[target, receptor])
                if score <= 0:
                    continue
                records.append(
                    {
                        "ligand": ligand,
                        "receptor": receptor,
                        "source": source,
                        "target": target,
                        "score": score,
                        "pvalue": np.nan,
                        "pathway": "builtin",
                    }
                )
    df = pd.DataFrame(records)
    if df.empty:
        return _empty_lr_table()
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def _run_liana(adata, *, cell_type_key: str, species: str, random_state: int = 1337) -> pd.DataFrame:
    if not sc_dep_manager.is_available("liana"):
        raise ImportError(
            "`liana` is required for sc-cell-communication --method liana.\n"
            "Install: pip install -e \".[singlecell-communication]\""
        )
    import liana as li

    use_raw = False
    logger.info("Running LIANA rank_aggregate (use_raw=%s)", use_raw)
    li.mt.rank_aggregate(adata, groupby=cell_type_key, use_raw=use_raw, verbose=True, seed=random_state)
    df = adata.uns["liana_res"].copy()
    col_map = {}
    if "ligand_complex" in df.columns:
        col_map["ligand_complex"] = "ligand"
    if "receptor_complex" in df.columns:
        col_map["receptor_complex"] = "receptor"
    if "sender" in df.columns and "source" not in df.columns:
        col_map["sender"] = "source"
    if "receiver" in df.columns and "target" not in df.columns:
        col_map["receiver"] = "target"
    if col_map:
        df = df.rename(columns=col_map)
    if "magnitude_rank" in df.columns:
        df["score"] = 1.0 - df["magnitude_rank"]
    elif "lr_means" in df.columns:
        df["score"] = df["lr_means"]
    else:
        df["score"] = 0.0
    df["pvalue"] = np.nan
    if "specificity_rank" not in df:
        df["specificity_rank"] = np.nan
    for col in ["ligand", "receptor", "source", "target", "score", "pvalue"]:
        if col not in df.columns:
            df[col] = ""
    out = df[["ligand", "receptor", "source", "target", "score", "pvalue", "specificity_rank"]].copy()
    out["pathway"] = "liana"
    return out.sort_values("score", ascending=False).reset_index(drop=True)


def _read_cpdb_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, sep="\t")
    except EmptyDataError:
        return pd.DataFrame()


def _resolve_cpdb_output_file(output_dir: Path, keyword: str) -> Path | None:
    exact = output_dir / f"{keyword}.txt"
    if exact.exists():
        return exact
    matches = sorted(output_dir.glob(f"*{keyword}*.txt"))
    return matches[-1] if matches else None


def _interaction_names_from_cpdb_row(row: pd.Series) -> tuple[str, str]:
    ligand = str(row.get("gene_a") or row.get("partner_a") or "").strip()
    receptor = str(row.get("gene_b") or row.get("partner_b") or "").strip()
    if ligand and receptor:
        return ligand, receptor
    pair = str(row.get("interacting_pair", "")).strip()
    if "_" in pair:
        left, right = pair.split("_", 1)
        return left, right
    return ligand or pair or "unknown_ligand", receptor or "unknown_receptor"


def _parse_cellphonedb_results(output_dir: Path) -> pd.DataFrame:
    significant_df = _read_cpdb_table(_resolve_cpdb_output_file(output_dir, "significant_means") or Path(""))
    means_df = _read_cpdb_table(_resolve_cpdb_output_file(output_dir, "means") or Path(""))
    pvalues_df = _read_cpdb_table(_resolve_cpdb_output_file(output_dir, "pvalues") or Path(""))
    score_df = significant_df if not significant_df.empty else means_df
    if score_df.empty:
        return _empty_lr_table()

    pair_cols = [column for column in score_df.columns if "|" in column]
    if not pair_cols:
        return _empty_lr_table()

    pvalues_lookup = pvalues_df.reset_index(drop=True) if not pvalues_df.empty else pd.DataFrame()
    records: list[dict[str, object]] = []
    for idx, row in score_df.reset_index(drop=True).iterrows():
        ligand, receptor = _interaction_names_from_cpdb_row(row)
        pathway = row.get("classification") or row.get("annotation_strategy") or "CellPhoneDB"
        pvalue_row = pvalues_lookup.iloc[idx] if idx < len(pvalues_lookup) else None
        for pair_col in pair_cols:
            score = pd.to_numeric(pd.Series([row.get(pair_col)]), errors="coerce").iloc[0]
            if pd.isna(score) or float(score) <= 0:
                continue
            source, target = pair_col.split("|", 1)
            if pvalue_row is not None and pair_col in pvalue_row.index:
                pair_pvalue = pd.to_numeric(pd.Series([pvalue_row[pair_col]]), errors="coerce").iloc[0]
            else:
                pair_pvalue = np.nan
            records.append(
                {
                    "ligand": ligand,
                    "receptor": receptor,
                    "source": source,
                    "target": target,
                    "score": float(score),
                    "pvalue": float(pair_pvalue) if not pd.isna(pair_pvalue) else 1.0,
                    "pathway": str(pathway),
                }
            )

    if not records:
        return _empty_lr_table()
    return pd.DataFrame(records).sort_values(["pvalue", "score"], ascending=[True, False]).reset_index(drop=True)


def _run_cellchat_r(
    adata,
    *,
    cell_type_key: str,
    species: str,
    prob_type: str,
    min_cells: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    df, notes = run_cellchat(
        adata,
        cell_type_key=cell_type_key,
        species=species,
        prob_type=prob_type,
        min_cells=min_cells,
    )
    if df.empty:
        return _empty_lr_table(), notes
    if "pathway" not in df.columns:
        df["pathway"] = "CellChat"
    return df.sort_values("score", ascending=False).reset_index(drop=True), notes


def run_communication(
    adata,
    *,
    method: str = "builtin",
    cell_type_key: str = "cell_type",
    species: str = "human",
    cellphonedb_counts_data: str = "hgnc_symbol",
    cellphonedb_iterations: int = 1000,
    cellphonedb_threshold: float = 0.1,
    cellphonedb_threads: int = 4,
    cellphonedb_pvalue: float = 0.05,
    cellchat_prob_type: str = "triMean",
    cellchat_min_cells: int = 10,
    condition_key: str | None = None,
    condition_oi: str | None = None,
    condition_ref: str | None = None,
    receiver: str | None = None,
    senders: list[str] | None = None,
    nichenet_top_ligands: int = 20,
    nichenet_expression_pct: float = 0.10,
    nichenet_lfc_cutoff: float = 0.25,
    liana_random_state: int = 1337,
    cellphonedb_random_state: int = 0,
) -> dict:
    if cell_type_key not in adata.obs.columns:
        raise ValueError(f"Cell type key '{cell_type_key}' not in adata.obs: {list(adata.obs.columns)}")

    dispatch = {
        "builtin": lambda: _run_builtin(adata, cell_type_key=cell_type_key, species=species),
        "liana": lambda: _run_liana(adata, cell_type_key=cell_type_key, species=species, random_state=liana_random_state),
        "cellphonedb": lambda: run_cellphonedb(
            adata,
            cell_type_key=cell_type_key,
            species=species,
            counts_data=cellphonedb_counts_data,
            iterations=cellphonedb_iterations,
            threshold=cellphonedb_threshold,
            threads=cellphonedb_threads,
            pvalue=cellphonedb_pvalue,
            random_state=cellphonedb_random_state,
        ),
        "cellchat_r": lambda: _run_cellchat_r(
            adata,
            cell_type_key=cell_type_key,
            species=species,
            prob_type=cellchat_prob_type,
            min_cells=cellchat_min_cells,
        ),
        "nichenet_r": lambda: run_nichenet(
            adata,
            cell_type_key=cell_type_key,
            species=species,
            condition_key=condition_key or "",
            condition_oi=condition_oi or "",
            condition_ref=condition_ref or "",
            receiver=receiver or "",
            senders=senders or [],
            top_ligands=nichenet_top_ligands,
            expression_pct=nichenet_expression_pct,
            lfc_cutoff=nichenet_lfc_cutoff,
        ),
    }
    cpdb_notes: dict[str, object] = {}
    nichenet_notes: dict[str, object] = {}
    cellchat_notes: dict[str, object] = {}
    ligand_activity_df = pd.DataFrame()
    ligand_target_links_df = pd.DataFrame()
    result = dispatch[method]()
    if method == "cellphonedb":
        lr_df, cpdb_notes = result
    elif method == "cellchat_r":
        lr_df, cellchat_notes = result
    elif method == "nichenet_r":
        lr_df, ligand_activity_df, ligand_target_links_df, nichenet_notes = result
    else:
        lr_df = result
    pvalue_series = pd.to_numeric(lr_df["pvalue"], errors="coerce") if not lr_df.empty else pd.Series(dtype=float)
    pvalue_available = bool(pvalue_series.notna().any()) if not lr_df.empty else False
    sig_df = lr_df[pvalue_series.notna() & (pvalue_series < 0.05)] if not lr_df.empty else lr_df
    summary = {
        "method": method,
        "requested_method": method,
        "executed_method": method,
        "fallback_used": False,
        "fallback_reason": "",
        "cell_type_key": cell_type_key,
        "species": species,
        "n_cells": int(adata.n_obs),
        "n_cell_types": int(adata.obs[cell_type_key].astype(str).nunique()),
        "n_interactions_tested": int(len(lr_df)),
        "n_significant": int(len(sig_df)),
        "pvalue_available": pvalue_available,
        "lr_df": lr_df,
        "top_df": lr_df.head(50) if not lr_df.empty else lr_df,
        "cellphonedb_renamed_cells": cpdb_notes.get("renamed_cells", False),
        "cellphonedb_prefixed_numeric_clusters": cpdb_notes.get("renamed_numeric_clusters", False),
        "expression_source": cpdb_notes.get(
            "expression_source",
            cellchat_notes.get("expression_source", nichenet_notes.get("expression_source", "adata.X")),
        ),
        "ligand_activity_df": ligand_activity_df,
        "ligand_target_links_df": ligand_target_links_df,
        "ligand_receptors_df": nichenet_notes.get("ligand_receptors_df", pd.DataFrame()),
        "pathway_df": cellchat_notes.get("pathway_df", pd.DataFrame()),
        "centrality_df": cellchat_notes.get("centrality_df", pd.DataFrame()),
        "count_matrix_df": cellchat_notes.get("count_matrix_df", pd.DataFrame()),
        "weight_matrix_df": cellchat_notes.get("weight_matrix_df", pd.DataFrame()),
        "cpdb_means_df": cpdb_notes.get("cpdb_means_df", pd.DataFrame()),
        "cpdb_pvalues_df": cpdb_notes.get("cpdb_pvalues_df", pd.DataFrame()),
        "cpdb_significant_df": cpdb_notes.get("cpdb_significant_df", pd.DataFrame()),
    }
    if method == "builtin":
        summary["score_semantics"] = (
            "Builtin score is a lightweight ligand mean x receptor mean heuristic across grouped cells."
        )
        summary["significance_semantics"] = (
            "Builtin results leave pvalue empty (NaN) because this heuristic backend does not run a statistical significance test; treat ranked scores as a sanity-check only."
        )
        summary["pvalue_available"] = False
        summary["n_significant"] = 0
    if method == "liana":
        summary["significance_semantics"] = "specificity_rank is a consensus rank, not a p-value; pvalue is NaN."
        summary["random_state"] = liana_random_state
    if method == "cellphonedb":
        summary["random_state"] = cellphonedb_random_state
        summary["score_semantics"] = (
            "CellPhoneDB score comes from the official statistical-analysis output reshaped into the OmicsClaw contract."
        )
        summary["significance_semantics"] = (
            "CellPhoneDB p values come from permutation-based significance testing on the selected grouping column."
        )
    if method == "cellchat_r":
        summary["score_semantics"] = (
            "CellChat score reflects communication probability inferred from normalized expression and the CellChat database."
        )
        summary["significance_semantics"] = (
            "CellChat first computes interaction probabilities, then pathway-level aggregation and centrality summaries; interpret pathway/role plots together with the LR table."
        )
    if method == "nichenet_r":
        summary["score_semantics"] = (
            "NicheNet score is ligand activity prioritization at the receiver cell type, not a permutation-derived communication probability."
        )
        summary["significance_semantics"] = (
            "NicheNet prioritizes ligands using activity scores and ligand-target links; pvalue is left empty in the shared LR table."
        )
        summary["pvalue_available"] = False
        summary["n_significant"] = 0
        summary["receiver"] = nichenet_notes.get("receiver", receiver or "")
        summary["senders"] = nichenet_notes.get("senders", senders or [])
        summary["n_prioritized_ligands"] = int(nichenet_notes.get("n_prioritized_ligands", len(ligand_activity_df)))
    return summary


def _build_sender_receiver_summary(lr_df: pd.DataFrame) -> pd.DataFrame:
    frame = lr_df.copy()
    if frame.empty:
        return pd.DataFrame(columns=["source", "target", "score", "n_interactions"])
    frame["score"] = pd.to_numeric(frame["score"], errors="coerce").fillna(0.0)
    summary = (
        frame.groupby(["source", "target"], as_index=False)
        .agg(score=("score", "mean"), n_interactions=("ligand", "count"))
        .sort_values(["score", "n_interactions"], ascending=[False, False])
    )
    return summary


def _build_group_role_summary(lr_df: pd.DataFrame) -> pd.DataFrame:
    frame = lr_df.copy()
    if frame.empty:
        return pd.DataFrame(columns=["cell_type", "outgoing_score", "incoming_score"])
    frame["score"] = pd.to_numeric(frame["score"], errors="coerce").fillna(0.0)
    outgoing = frame.groupby("source")["score"].sum().rename("outgoing_score")
    incoming = frame.groupby("target")["score"].sum().rename("incoming_score")
    role = pd.concat([outgoing, incoming], axis=1).fillna(0.0).reset_index().rename(columns={"index": "cell_type"})
    role = role.rename(columns={"source": "cell_type"}) if "source" in role.columns else role
    if "cell_type" not in role.columns:
        role = role.rename(columns={role.columns[0]: "cell_type"})
    return role.sort_values(["outgoing_score", "incoming_score"], ascending=False).reset_index(drop=True)


def _build_pathway_summary(lr_df: pd.DataFrame, pathway_df: pd.DataFrame | None = None) -> pd.DataFrame:
    if isinstance(pathway_df, pd.DataFrame) and not pathway_df.empty and "pathway" in pathway_df.columns:
        frame = pathway_df.copy()
        score_col = "prob" if "prob" in frame.columns else "score"
        frame[score_col] = pd.to_numeric(frame[score_col], errors="coerce").fillna(0.0)
        return (
            frame.groupby("pathway", as_index=False)[score_col]
            .mean()
            .rename(columns={score_col: "score"})
            .sort_values("score", ascending=False)
        )
    frame = lr_df.copy()
    if frame.empty or "pathway" not in frame.columns:
        return pd.DataFrame(columns=["pathway", "score"])
    frame["score"] = pd.to_numeric(frame["score"], errors="coerce").fillna(0.0)
    return frame.groupby("pathway", as_index=False)["score"].mean().sort_values("score", ascending=False)

def communicate(adata, *, method: str = 'builtin', cell_type_key: str = 'cell_type',
                species: str = 'human', cellphonedb_counts_data: str = 'hgnc_symbol',
                cellphonedb_iterations: int = 1000, cellphonedb_threshold: float = 0.1,
                cellphonedb_threads: int = 4, cellphonedb_pvalue: float = 0.05,
                cellchat_prob_type: str = 'triMean', cellchat_min_cells: int = 10,
                condition_key: str | None = None, condition_oi: str | None = None,
                condition_ref: str | None = None, receiver: str | None = None,
                senders: list[str] | None = None, nichenet_top_ligands: int = 20,
                nichenet_expression_pct: float = 0.10, nichenet_lfc_cutoff: float = 0.25,
                liana_random_state: int = 1337, cellphonedb_random_state: int = 0) -> pd.DataFrame:
    """Return ranked ligand-receptor interactions without changing the input.

    builtin multiplies grouped ligand and receptor means and supplies no
    p-values. LIANA retains specificity_rank as a rank, not a significance
    statistic, and ignores species as in the existing wrapper. CellPhoneDB
    uses debug_seed=0 by default; its database may download on first use.
    R methods use temporary H5AD exchange files. NicheNet needs its two
    local resource files. Optional backend imports occur only when selected.
    Backend-specific tables and diagnostics are accessible through helpers.
    """
    if method not in ('builtin', 'liana', 'cellphonedb', 'cellchat_r', 'nichenet_r'):
        raise ValueError('Unknown communication method: ' + method)
    parameters = dict(locals())
    parameters.pop('adata')
    summary = run_communication(adata.copy(), **parameters)
    table = summary.pop('lr_df')
    frames = {key: summary.pop(key) for key in list(summary) if isinstance(summary[key], pd.DataFrame)}
    table.attrs[_RUN_KEY] = summary
    table.attrs[_TABLES_KEY] = {key: value.to_json(orient='table') for key, value in frames.items()}
    return table


def builtin_lr(adata, *, cell_type_key: str = 'cell_type', species: str = 'human') -> pd.DataFrame:
    """Return the curated mean-product heuristic; pvalue is always NaN."""
    return communicate(adata, method='builtin', cell_type_key=cell_type_key, species=species)


def liana_lr(adata, *, cell_type_key: str = 'cell_type', species: str = 'human', random_state: int = 1337) -> pd.DataFrame:
    """Return LIANA consensus scores and specificity ranks; neither is a p-value."""
    return communicate(adata, method='liana', cell_type_key=cell_type_key, species=species, liana_random_state=random_state)


def cellphonedb_lr(adata, *, cell_type_key: str = 'cell_type', species: str = 'human',
                   counts_data: str = 'hgnc_symbol', iterations: int = 1000,
                   threshold: float = 0.1, threads: int = 4,
                   pvalue: float = 0.05, random_state: int = 0) -> pd.DataFrame:
    """Run CellPhoneDB permutations with an explicit debug_seed; database may download."""
    return communicate(adata, method='cellphonedb', cell_type_key=cell_type_key, species=species,
        cellphonedb_counts_data=counts_data, cellphonedb_iterations=iterations,
        cellphonedb_threshold=threshold, cellphonedb_threads=threads,
        cellphonedb_pvalue=pvalue, cellphonedb_random_state=random_state)


def cellchat_lr(adata, *, cell_type_key: str = 'cell_type', species: str = 'human',
                prob_type: str = 'triMean', min_cells: int = 10) -> pd.DataFrame:
    """Run CellChat in R on normalized X; require the existing R dependency stack."""
    return communicate(adata, method='cellchat_r', cell_type_key=cell_type_key, species=species,
        cellchat_prob_type=prob_type, cellchat_min_cells=min_cells)


def nichenet_ligands(adata, *, cell_type_key: str = 'cell_type', species: str = 'human',
                     condition_key: str, condition_oi: str, condition_ref: str,
                     receiver: str, senders: list[str], top_ligands: int = 20,
                     expression_pct: float = 0.1, lfc_cutoff: float = 0.25) -> pd.DataFrame:
    """Run NicheNet and return LR scores; backend_tables includes ligand activities."""
    return communicate(adata, method='nichenet_r', cell_type_key=cell_type_key, species=species,
        condition_key=condition_key, condition_oi=condition_oi, condition_ref=condition_ref,
        receiver=receiver, senders=senders, nichenet_top_ligands=top_ligands,
        nichenet_expression_pct=expression_pct, nichenet_lfc_cutoff=lfc_cutoff)


def sender_receiver_summary(table: pd.DataFrame) -> pd.DataFrame:
    """Return mean scores and interaction counts for each sender-receiver pair."""
    return _build_sender_receiver_summary(table)


def group_role_summary(table: pd.DataFrame) -> pd.DataFrame:
    """Return summed incoming and outgoing interaction scores for each cell type."""
    return _build_group_role_summary(table)


def pathway_summary(table: pd.DataFrame, *, pathways: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return mean pathway scores, using CellChat pathway results when supplied."""
    return _build_pathway_summary(table, pathways)


def top_interactions(table: pd.DataFrame, *, n: int = 50) -> pd.DataFrame:
    """Return the first n interactions in the backend's existing ranked order."""
    return table.head(n).copy()


def backend_tables(table: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return copies of backend-specific tables, including optional R summaries."""
    return {key: pd.read_json(StringIO(value), orient='table') for key, value in table.attrs[_TABLES_KEY].items()}


def interaction_heatmap_figure(table: pd.DataFrame):
    """Return a sender-by-receiver mean-score heatmap without writing files."""
    import matplotlib.pyplot as plt
    values = sender_receiver_summary(table).pivot(index='source', columns='target', values='score').fillna(0)
    fig, ax = plt.subplots()
    if not values.empty:
        image = ax.imshow(values.to_numpy(), aspect='auto')
        ax.set_xticks(range(len(values.columns)), values.columns, rotation=45)
        ax.set_yticks(range(len(values.index)), values.index)
        fig.colorbar(image, ax=ax, label='Mean score')
    fig.tight_layout()
    return fig


def run_info(table: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return backend provenance; keep=False removes the table's run record."""
    info = table.attrs.get(_RUN_KEY, {}) if keep else table.attrs.pop(_RUN_KEY, {})
    return deepcopy(info)
