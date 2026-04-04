#!/usr/bin/env python3
"""Single-cell cell-cell communication analysis with builtin, LIANA, CellPhoneDB, CellChat, and NicheNet backends."""

from __future__ import annotations

import argparse
import tempfile
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scanpy as sc
from pandas.errors import EmptyDataError

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
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import matrix_looks_count_like, store_analysis_metadata
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_cell_communication
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_script_runner import RScriptRunner

from skills.singlecell._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-cell-communication"
SKILL_VERSION = "0.2.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-cell-communication/sc_cell_communication.py"

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "builtin": MethodConfig(
        name="builtin",
        description="Built-in ligand-receptor scoring with a small curated database",
        dependencies=("scanpy",),
    ),
    "liana": MethodConfig(
        name="liana",
        description="LIANA+ consensus ligand-receptor scoring",
        dependencies=("liana",),
    ),
    "cellphonedb": MethodConfig(
        name="cellphonedb",
        description="CellPhoneDB statistical analysis with official Python backend",
        dependencies=("cellphonedb",),
    ),
    "cellchat_r": MethodConfig(
        name="cellchat_r",
        description="CellChat communication inference (R)",
        dependencies=(),
    ),
    "nichenet_r": MethodConfig(
        name="nichenet_r",
        description="NicheNet ligand activity prioritization with the official R package",
        dependencies=(),
    ),
}

DEFAULT_METHOD = "builtin"
METHOD_PARAM_DEFAULTS: dict[str, dict[str, object]] = {
    "builtin": {
        "cell_type_key": "cell_type",
        "species": "human",
    },
    "liana": {
        "cell_type_key": "cell_type",
        "species": "human",
    },
    "cellphonedb": {
        "cell_type_key": "cell_type",
        "species": "human",
        "cellphonedb_counts_data": "hgnc_symbol",
        "cellphonedb_iterations": 1000,
        "cellphonedb_threshold": 0.1,
        "cellphonedb_threads": 4,
        "cellphonedb_pvalue": 0.05,
    },
    "cellchat_r": {
        "cell_type_key": "cell_type",
        "species": "human",
    },
    "nichenet_r": {
        "cell_type_key": "cell_type",
        "species": "human",
        "condition_key": "condition",
        "condition_oi": "stim",
        "condition_ref": "ctrl",
        "receiver": "",
        "senders": "",
        "nichenet_top_ligands": 20,
        "nichenet_expression_pct": 0.10,
    },
}
OUTPUT_COLUMNS = ["ligand", "receptor", "source", "target", "score", "pvalue", "pathway"]
CELLPHONEDB_DB_VERSION = "v4.1.0"


def _empty_lr_table() -> pd.DataFrame:
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def _resolve_cellphonedb_database() -> Path:
    """Ensure the official CellPhoneDB database zip exists locally."""
    from cellphonedb.utils import db_utils

    cache_dir = Path.home() / ".cache" / "omicsclaw" / "cellphonedb" / CELLPHONEDB_DB_VERSION
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / "cellphonedb.zip"
    if not db_path.exists():
        logger.info("Downloading CellPhoneDB database %s...", CELLPHONEDB_DB_VERSION)
        db_utils.download_database(str(cache_dir), CELLPHONEDB_DB_VERSION)
    if not db_path.exists():
        raise FileNotFoundError(f"CellPhoneDB database not found at {db_path}")
    return db_path


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
            description="Cell-cell communication analysis for annotated scRNA-seq data.",
            result_payload=result_payload,
            preferred_method=summary.get("executed_method", summary.get("method", DEFAULT_METHOD)),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Cell-cell communication analysis for annotated scRNA-seq data.",
            result_payload=result_payload,
            preferred_method=summary.get("executed_method", summary.get("method", DEFAULT_METHOD)),
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md: %s", exc)

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
    if adata.raw is not None and adata.raw.shape == adata.shape:
        export = sc.AnnData(X=adata.raw.X.copy(), obs=adata.obs.copy(), var=adata.raw.var.copy())
        export.obs_names = adata.obs_names.copy()
        export.var_names = adata.raw.var_names.copy()
        return export, "adata.raw"
    return adata.copy(), "adata.X"


def _build_nichenet_input_adata(adata):
    if "counts" in adata.layers and adata.layers["counts"].shape == adata.shape:
        export = sc.AnnData(X=adata.layers["counts"].copy(), obs=adata.obs.copy(), var=adata.var.copy())
        export.obs_names = adata.obs_names.copy()
        export.var_names = adata.var_names.copy()
        return export, "layers.counts"
    if adata.raw is not None and adata.raw.shape == adata.shape:
        export = sc.AnnData(X=adata.raw.X.copy(), obs=adata.obs.copy(), var=adata.raw.var.copy())
        export.obs_names = adata.obs_names.copy()
        export.var_names = adata.raw.var_names.copy()
        return export, "adata.raw"
    if matrix_looks_count_like(adata.X):
        return adata.copy(), "adata.X"
    raise ValueError(
        "NicheNet requires a raw count-like matrix in `layers['counts']`, `adata.raw`, or `adata.X`. "
        "Run `sc-standardize-input` or provide an object that still contains raw counts."
    )


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


def run_cellchat(adata, *, cell_type_key: str, species: str) -> pd.DataFrame:
    validate_r_environment(required_r_packages=["CellChat", "SingleCellExperiment", "zellkonverter"])
    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=7200)
    export, source = _build_cellchat_input_adata(adata)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_cellchat_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        export.write_h5ad(input_h5ad)
        runner.run_script(
            "sc_cellchat.R",
            args=[str(input_h5ad), str(output_dir), cell_type_key, species],
            expected_outputs=["cellchat_results.csv"],
            output_dir=output_dir,
        )
        try:
            df = pd.read_csv(output_dir / "cellchat_results.csv")
        except EmptyDataError:
            df = pd.DataFrame(columns=["ligand", "receptor", "source", "target", "score", "pvalue", "pathway"])
    if not df.empty:
        df["expression_source"] = source
    return df


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
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    if species != "human":
        raise ValueError("The current NicheNet wrapper only supports species='human'.")

    validate_r_environment(required_r_packages=["nichenetr", "Seurat", "SingleCellExperiment", "zellkonverter"])
    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=7200)
    export, source = _build_nichenet_input_adata(adata)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_nichenet_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
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
            ],
            expected_outputs=[
                "nichenet_ligand_activities.csv",
                "nichenet_ligand_target_links.csv",
                "nichenet_lr_network.csv",
            ],
            output_dir=output_dir,
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
    }
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
) -> tuple[pd.DataFrame, dict[str, object]]:
    if species != "human":
        raise ValueError("The current CellPhoneDB wrapper only supports species='human'.")

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
            )
        except KeyError as exc:
            if exc.args != ("significant_means",):
                raise
            logger.info("CellPhoneDB reported no significant interactions for this dataset.")
            notes["no_significant_interactions"] = True
            return _empty_lr_table(), notes
        lr_df = _parse_cellphonedb_results(output_dir)
    return lr_df, notes


def _group_means(adata, cell_type_key: str) -> pd.DataFrame:
    if adata.raw is not None:
        X = adata.raw.X
        var_names = adata.raw.var_names
    else:
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


def _run_liana(adata, *, cell_type_key: str, species: str) -> pd.DataFrame:
    import liana as li

    use_raw = adata.raw is not None
    logger.info("Running LIANA rank_aggregate (use_raw=%s)", use_raw)
    li.mt.rank_aggregate(adata, groupby=cell_type_key, use_raw=use_raw, verbose=True)
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
    df["pvalue"] = df.get("specificity_rank", 0.5)
    for col in ["ligand", "receptor", "source", "target", "score", "pvalue"]:
        if col not in df.columns:
            df[col] = ""
    out = df[["ligand", "receptor", "source", "target", "score", "pvalue"]].copy()
    out["pathway"] = "liana"
    return out.sort_values("score", ascending=False).reset_index(drop=True)


def _read_cpdb_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, sep="\t")
    except EmptyDataError:
        return pd.DataFrame()


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
    significant_df = _read_cpdb_table(output_dir / "significant_means.txt")
    means_df = _read_cpdb_table(output_dir / "means.txt")
    pvalues_df = _read_cpdb_table(output_dir / "pvalues.txt")
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


def _run_cellchat_r(adata, *, cell_type_key: str, species: str) -> pd.DataFrame:
    df = run_cellchat(adata, cell_type_key=cell_type_key, species=species)
    if df.empty:
        return _empty_lr_table()
    if "pathway" not in df.columns:
        df["pathway"] = "CellChat"
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def run_communication(
    adata,
    *,
    method: str,
    cell_type_key: str,
    species: str,
    condition_key: str | None = None,
    condition_oi: str | None = None,
    condition_ref: str | None = None,
    receiver: str | None = None,
    senders: list[str] | None = None,
    nichenet_top_ligands: int = 20,
    nichenet_expression_pct: float = 0.10,
) -> dict:
    if cell_type_key not in adata.obs.columns:
        raise ValueError(f"Cell type key '{cell_type_key}' not in adata.obs: {list(adata.obs.columns)}")

    dispatch = {
        "builtin": lambda: _run_builtin(adata, cell_type_key=cell_type_key, species=species),
        "liana": lambda: _run_liana(adata, cell_type_key=cell_type_key, species=species),
        "cellphonedb": lambda: run_cellphonedb(
            adata,
            cell_type_key=cell_type_key,
            species=species,
            counts_data=METHOD_PARAM_DEFAULTS["cellphonedb"]["cellphonedb_counts_data"],
            iterations=METHOD_PARAM_DEFAULTS["cellphonedb"]["cellphonedb_iterations"],
            threshold=METHOD_PARAM_DEFAULTS["cellphonedb"]["cellphonedb_threshold"],
            threads=METHOD_PARAM_DEFAULTS["cellphonedb"]["cellphonedb_threads"],
            pvalue=METHOD_PARAM_DEFAULTS["cellphonedb"]["cellphonedb_pvalue"],
        ),
        "cellchat_r": lambda: _run_cellchat_r(adata, cell_type_key=cell_type_key, species=species),
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
        ),
    }
    cpdb_notes: dict[str, object] = {}
    nichenet_notes: dict[str, object] = {}
    ligand_activity_df = pd.DataFrame()
    ligand_target_links_df = pd.DataFrame()
    result = dispatch[method]()
    if method == "cellphonedb":
        lr_df, cpdb_notes = result
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
        "expression_source": cpdb_notes.get("expression_source", nichenet_notes.get("expression_source", "")),
        "ligand_activity_df": ligand_activity_df,
        "ligand_target_links_df": ligand_target_links_df,
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
    if method == "cellphonedb":
        summary["score_semantics"] = (
            "CellPhoneDB score comes from the official statistical-analysis output reshaped into the OmicsClaw contract."
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


def generate_figures(output_dir: Path, summary: dict) -> list[str]:
    figures = []
    top_df = summary.get("top_df", pd.DataFrame())
    ligand_activity_df = summary.get("ligand_activity_df", pd.DataFrame())
    if isinstance(ligand_activity_df, pd.DataFrame) and not ligand_activity_df.empty:
        try:
            bar = ligand_activity_df.head(15).copy()
            ligand_col = "ligand" if "ligand" in bar.columns else "test_ligand"
            fig, ax = plt.subplots(figsize=(8, 5))
            ax.barh(bar[ligand_col].astype(str), bar["pearson"], color="#238b45")
            ax.set_xlabel("Ligand activity (pearson)")
            ax.set_title("Top NicheNet ligands")
            ax.invert_yaxis()
            fig.tight_layout()
            p = save_figure(fig, output_dir, "nichenet_top_ligands.png")
            figures.append(str(p))
            plt.close(fig)
        except Exception as exc:
            logger.warning("NicheNet ligand plot failed: %s", exc)
    if top_df.empty:
        return figures

    try:
        heat = top_df.groupby(["source", "target"])["score"].mean().unstack(fill_value=0)
        fig, ax = plt.subplots(figsize=(8, 6))
        im = ax.imshow(heat.values, aspect="auto")
        ax.set_xticks(range(len(heat.columns)))
        ax.set_xticklabels(heat.columns, rotation=45, ha="right")
        ax.set_yticks(range(len(heat.index)))
        ax.set_yticklabels(heat.index)
        ax.set_title("Mean Communication Score")
        fig.colorbar(im, ax=ax)
        p = save_figure(fig, output_dir, "interaction_heatmap.png")
        figures.append(str(p))
        plt.close(fig)
    except Exception as exc:
        logger.warning("Interaction heatmap failed: %s", exc)

    try:
        bar = top_df.head(15).copy()
        labels = [f"{r.source}->{r.target}:{r.ligand}-{r.receptor}" for r in bar.itertuples()]
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.barh(range(len(bar)), bar["score"].values)
        ax.set_yticks(range(len(bar)))
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.set_xlabel("Score")
        ax.set_title("Top Ligand-Receptor Interactions")
        fig.tight_layout()
        p = save_figure(fig, output_dir, "top_interactions.png")
        figures.append(str(p))
        plt.close(fig)
    except Exception as exc:
        logger.warning("Top interaction plot failed: %s", exc)

    return figures


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    header = generate_report_header(
        title="Single-Cell Cell-Cell Communication Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Requested method": summary.get("requested_method", summary["method"]),
            "Executed method": summary.get("executed_method", summary["method"]),
            "Cell type key": summary["cell_type_key"],
        },
    )

    top_df = summary.get("top_df", pd.DataFrame())
    if summary.get("pvalue_available", True):
        significance_label = str(summary["n_significant"])
    elif summary.get("executed_method") == "nichenet_r":
        significance_label = "N/A for NicheNet ligand prioritization"
    else:
        significance_label = "N/A for builtin heuristic backend"
    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Cell types**: {summary['n_cell_types']}",
        f"- **Requested method**: {summary.get('requested_method', summary['method'])}",
        f"- **Executed method**: {summary.get('executed_method', summary['method'])}",
        f"- **Interactions tested**: {summary['n_interactions_tested']}",
        f"- **Significant (p < 0.05)**: {significance_label}",
    ]
    if summary.get("fallback_reason"):
        body_lines.append(f"- **Fallback note**: {summary['fallback_reason']}")
    if summary.get("significance_semantics"):
        body_lines.append(f"- **Significance note**: {summary['significance_semantics']}")
    if summary.get("cellphonedb_renamed_cells"):
        body_lines.append("- **CellPhoneDB export note**: cell IDs containing `-` were rewritten to `_` for compatibility.")
    if summary.get("cellphonedb_prefixed_numeric_clusters"):
        body_lines.append("- **CellPhoneDB export note**: numeric cluster labels were prefixed with `cluster_` for compatibility.")
    if summary.get("receiver"):
        body_lines.append(f"- **Receiver cell type**: {summary['receiver']}")
    if summary.get("senders"):
        body_lines.append(f"- **Sender cell types**: {', '.join(summary['senders'])}")
    if summary.get("n_prioritized_ligands"):
        body_lines.append(f"- **Prioritized ligands**: {summary['n_prioritized_ligands']}")
    if not top_df.empty:
        body_lines.extend(["", "### Top Interactions\n"])
        body_lines.append("| Ligand | Receptor | Source | Target | Score |")
        body_lines.append("|--------|----------|--------|--------|-------|")
        for _, row in top_df.head(15).iterrows():
            body_lines.append(
                f"| {row['ligand']} | {row['receptor']} | {row['source']} | {row['target']} | {row['score']:.4f} |"
            )

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    lr_df = summary.get("lr_df", pd.DataFrame())
    if not lr_df.empty:
        lr_df.to_csv(tables_dir / "lr_interactions.csv", index=False)
        top_df.head(50).to_csv(tables_dir / "top_interactions.csv", index=False)
    ligand_activity_df = summary.get("ligand_activity_df", pd.DataFrame())
    if isinstance(ligand_activity_df, pd.DataFrame) and not ligand_activity_df.empty:
        ligand_activity_df.to_csv(tables_dir / "nichenet_ligand_activities.csv", index=False)
    ligand_target_links_df = summary.get("ligand_target_links_df", pd.DataFrame())
    if isinstance(ligand_target_links_df, pd.DataFrame) and not ligand_target_links_df.empty:
        ligand_target_links_df.to_csv(tables_dir / "nichenet_ligand_target_links.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    command = (
        f"python {SCRIPT_REL_PATH} "
        f"{'--demo' if params.get('demo_mode') else '--input <input.h5ad>'} "
        f"--output {output_dir} "
        f"--method {params.get('method', 'builtin')} "
        f"--cell-type-key {params.get('cell_type_key', 'cell_type')} "
        f"--species {params.get('species', 'human')}"
    )
    if params.get("method") == "nichenet_r":
        command += (
            f" --condition-key {params.get('condition_key', 'condition')}"
            f" --condition-oi {params.get('condition_oi', 'stim')}"
            f" --condition-ref {params.get('condition_ref', 'ctrl')}"
            f" --receiver {params.get('receiver', '<receiver>')}"
            f" --senders {params.get('senders', '<sender1,sender2>')}"
            f" --nichenet-top-ligands {params.get('nichenet_top_ligands', 20)}"
            f" --nichenet-expression-pct {params.get('nichenet_expression_pct', 0.1)}"
        )
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    _write_repro_requirements(
        repro_dir,
        ["scanpy", "anndata", "numpy", "pandas", "matplotlib"],
    )


def _configure_nichenet_demo(adata, *, cell_type_key: str, condition_key: str) -> tuple[str, list[str], str, str]:
    labels = adata.obs[cell_type_key].astype(str)
    counts = labels.value_counts()
    if counts.size < 2:
        raise ValueError("NicheNet demo requires at least two cell groups.")
    receiver = str(counts.index[0])
    senders = [str(label) for label in counts.index[1:4]]
    if not senders:
        senders = [str(counts.index[-1])]

    condition = np.array(["ctrl"] * adata.n_obs, dtype=object)
    receiver_idx = np.where((labels == receiver).to_numpy())[0]
    condition[receiver_idx[::2]] = "stim"
    adata.obs[condition_key] = pd.Categorical(condition)
    stim_idx = receiver_idx[::2]
    if len(stim_idx) > 0:
        gene_idx = np.arange(min(15, adata.n_vars))
        X = adata.X
        if hasattr(X, "tolil"):
            X = X.tolil(copy=True)
            block = X[np.ix_(stim_idx, gene_idx)].toarray()
            X[np.ix_(stim_idx, gene_idx)] = block + 6
            adata.X = X.tocsr()
        else:
            adata.X[np.ix_(stim_idx, gene_idx)] = adata.X[np.ix_(stim_idx, gene_idx)] + 6
    return receiver, senders, "stim", "ctrl"


def main():
    parser = argparse.ArgumentParser(description="Single-cell cell-cell communication")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default=DEFAULT_METHOD)
    parser.add_argument("--cell-type-key", default="cell_type")
    parser.add_argument("--species", default="human", choices=["human", "mouse"])
    parser.add_argument("--cellphonedb-counts-data", default="hgnc_symbol", choices=["ensembl", "gene_name", "hgnc_symbol"])
    parser.add_argument("--cellphonedb-iterations", type=int, default=1000)
    parser.add_argument("--cellphonedb-threshold", type=float, default=0.1)
    parser.add_argument("--cellphonedb-threads", type=int, default=4)
    parser.add_argument("--cellphonedb-pvalue", type=float, default=0.05)
    parser.add_argument("--condition-key", default="condition")
    parser.add_argument("--condition-oi", default="stim")
    parser.add_argument("--condition-ref", default="ctrl")
    parser.add_argument("--receiver", default="")
    parser.add_argument("--senders", default="")
    parser.add_argument("--nichenet-top-ligands", type=int, default=20)
    parser.add_argument("--nichenet-expression-pct", type=float, default=0.10)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback=DEFAULT_METHOD)

    if args.demo:
        if method == "nichenet_r":
            adata, _ = sc_io.load_repo_demo_data("pbmc3k_raw")
            processed_demo, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
            fallback_key = "louvain" if "louvain" in processed_demo.obs else "leiden"
            aligned_labels = processed_demo.obs.reindex(adata.obs_names)[fallback_key].astype(str)
            adata.obs[args.cell_type_key] = aligned_labels.values
        else:
            adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
            if args.cell_type_key not in adata.obs.columns:
                fallback_key = "louvain" if "louvain" in adata.obs else "leiden"
                adata.obs[args.cell_type_key] = adata.obs[fallback_key].astype(str)
        if method == "nichenet_r":
            demo_receiver, demo_senders, demo_oi, demo_ref = _configure_nichenet_demo(
                adata,
                cell_type_key=args.cell_type_key,
                condition_key=args.condition_key,
            )
            if not args.receiver:
                args.receiver = demo_receiver
            if not args.senders:
                args.senders = ",".join(demo_senders)
            if args.condition_oi == "stim":
                args.condition_oi = demo_oi
            if args.condition_ref == "ctrl":
                args.condition_ref = demo_ref
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        sc_io.maybe_warn_standardize_first(adata, source_path=args.input_path, skill_name=SKILL_NAME)
        input_file = args.input_path

    senders = [item.strip() for item in str(args.senders).split(",") if item.strip()]
    apply_preflight(
        preflight_sc_cell_communication(
            adata,
            method=method,
            cell_type_key=args.cell_type_key,
            species=args.species,
            counts_data=args.cellphonedb_counts_data,
            condition_key=args.condition_key,
            condition_oi=args.condition_oi,
            condition_ref=args.condition_ref,
            receiver=args.receiver,
            senders=senders,
            source_path=input_file,
        ),
        logger,
    )
    if method == "cellphonedb":
        METHOD_PARAM_DEFAULTS["cellphonedb"].update(
            {
                "cell_type_key": args.cell_type_key,
                "species": args.species,
                "cellphonedb_counts_data": args.cellphonedb_counts_data,
                "cellphonedb_iterations": args.cellphonedb_iterations,
                "cellphonedb_threshold": args.cellphonedb_threshold,
                "cellphonedb_threads": args.cellphonedb_threads,
                "cellphonedb_pvalue": args.cellphonedb_pvalue,
            }
        )
    summary = run_communication(
        adata,
        method=method,
        cell_type_key=args.cell_type_key,
        species=args.species,
        condition_key=args.condition_key,
        condition_oi=args.condition_oi,
        condition_ref=args.condition_ref,
        receiver=args.receiver,
        senders=senders,
        nichenet_top_ligands=args.nichenet_top_ligands,
        nichenet_expression_pct=args.nichenet_expression_pct,
    )
    params = {
        "method": method,
        "cell_type_key": args.cell_type_key,
        "species": args.species,
        "demo_mode": args.demo,
    }
    if method == "cellphonedb":
        params.update(
            {
                "cellphonedb_counts_data": args.cellphonedb_counts_data,
                "cellphonedb_iterations": args.cellphonedb_iterations,
                "cellphonedb_threshold": args.cellphonedb_threshold,
                "cellphonedb_threads": args.cellphonedb_threads,
                "cellphonedb_pvalue": args.cellphonedb_pvalue,
            }
        )
    if method == "nichenet_r":
        params.update(
            {
                "condition_key": args.condition_key,
                "condition_oi": args.condition_oi,
                "condition_ref": args.condition_ref,
                "receiver": args.receiver,
                "senders": ",".join(senders),
                "nichenet_top_ligands": args.nichenet_top_ligands,
                "nichenet_expression_pct": args.nichenet_expression_pct,
            }
        )

    generate_figures(output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "requested_method": summary.get("requested_method", method),
        "executed_method": summary.get("executed_method", method),
        "fallback_used": summary.get("fallback_used", False),
        "fallback_reason": summary.get("fallback_reason", ""),
        "pvalue_available": summary.get("pvalue_available", True),
        "score_semantics": summary.get("score_semantics"),
        "significance_semantics": summary.get("significance_semantics"),
        "params": params,
    }
    write_result_json(
        output_dir,
        SKILL_NAME,
        SKILL_VERSION,
        {k: v for k, v in summary.items() if k not in {"lr_df", "top_df", "ligand_activity_df", "ligand_target_links_df"}},
        result_data,
        checksum,
    )
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": {k: v for k, v in summary.items() if k not in {"lr_df", "top_df", "ligand_activity_df", "ligand_target_links_df"}},
        "data": result_data,
    }
    write_standard_run_artifacts(output_dir, result_payload, summary)
    metadata_params = {
        "requested_method": summary.get("requested_method", method),
        "executed_method": summary.get("executed_method", method),
        "fallback_used": summary.get("fallback_used", False),
        "fallback_reason": summary.get("fallback_reason", ""),
        "pvalue_available": summary.get("pvalue_available", True),
        "cell_type_key": args.cell_type_key,
        "species": args.species,
    }
    if method == "nichenet_r":
        metadata_params.update(
            {
                "condition_key": args.condition_key,
                "condition_oi": args.condition_oi,
                "condition_ref": args.condition_ref,
                "receiver": args.receiver,
                "senders": senders,
            }
        )
    store_analysis_metadata(adata, SKILL_NAME, summary.get("executed_method", method), metadata_params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        "Communication analysis complete: "
        f"{summary['n_interactions_tested']} interactions tested "
        f"(requested={summary.get('requested_method', method)}, executed={summary.get('executed_method', method)})"
    )


if __name__ == "__main__":
    main()
