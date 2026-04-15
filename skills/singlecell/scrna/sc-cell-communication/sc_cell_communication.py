#!/usr/bin/env python3
"""Single-cell cell-cell communication analysis with builtin, LIANA, CellPhoneDB, CellChat, and NicheNet backends."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
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
    write_replot_hint,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    infer_qc_species,
    infer_x_matrix_kind,
    matrix_looks_count_like,
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib import dependency_manager as sc_dep_manager
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_cell_communication
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_dependency_manager import check_r_tier, suggest_r_install
from omicsclaw.core.r_script_runner import RScriptRunner

from skills.singlecell._lib.viz import (
    plot_cellchat_count_weight_heatmaps,
    plot_group_role_summary,
    plot_interaction_dotplot,
    plot_interaction_heatmap,
    plot_nichenet_ligands,
    plot_nichenet_ligand_receptor_heatmap,
    plot_nichenet_ligand_target_heatmap,
    plot_pathway_summary,
    plot_source_target_bubble,
    plot_top_interactions_bar,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-cell-communication"
SKILL_VERSION = "0.3.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-cell-communication/sc_cell_communication.py"

# R Enhanced renderers for this skill.
# Key   = renderer name registered in viz/r/registry.R R_PLOT_REGISTRY
# Value = output filename (written to figures/r_enhanced/)
R_ENHANCED_PLOTS: dict[str, str] = {
    "plot_ccc_heatmap": "r_ccc_heatmap.png",
    "plot_ccc_network": "r_ccc_network.png",
    "plot_ccc_bubble": "r_ccc_bubble.png",
    "plot_ccc_stat_bar": "r_ccc_stat_bar.png",
    "plot_ccc_stat_violin": "r_ccc_stat_violin.png",
    "plot_ccc_stat_scatter": "r_ccc_stat_scatter.png",
    "plot_ccc_bipartite": "r_ccc_bipartite.png",
    "plot_ccc_diff_network": "r_ccc_diff_network.png",
}


def _render_r_enhanced(
    output_dir: Path,
    figure_data_dir: Path,
    r_enhanced: bool,
) -> list[str]:
    """Run R Enhanced rendering pass. Always called after Python figures are complete."""
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths: list[str] = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths
SUMMARY_FRAME_KEYS = {
    "lr_df",
    "top_df",
    "ligand_activity_df",
    "ligand_target_links_df",
    "ligand_receptors_df",
    "pathway_df",
    "centrality_df",
    "count_matrix_df",
    "weight_matrix_df",
    "cpdb_means_df",
    "cpdb_pvalues_df",
    "cpdb_significant_df",
    "sender_receiver_df",
    "role_df",
    "pathway_summary_df",
}

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "builtin": MethodConfig(
        name="builtin",
        description="Built-in ligand-receptor scoring with a small curated database",
        dependencies=(),
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
        "cellchat_prob_type": "triMean",
        "cellchat_min_cells": 10,
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
        "nichenet_lfc_cutoff": 0.25,
    },
}
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
    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
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
    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
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


def _run_liana(adata, *, cell_type_key: str, species: str) -> pd.DataFrame:
    if not sc_dep_manager.is_available("liana"):
        raise ImportError(
            "`liana` is required for sc-cell-communication --method liana.\n"
            "Install: pip install -e \".[singlecell-communication]\""
        )
    import liana as li

    use_raw = False
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
    method: str,
    cell_type_key: str,
    species: str,
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
            counts_data=cellphonedb_counts_data,
            iterations=cellphonedb_iterations,
            threshold=cellphonedb_threshold,
            threads=cellphonedb_threads,
            pvalue=cellphonedb_pvalue,
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
    if method == "cellphonedb":
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


def _write_figure_data(output_dir: Path, *, top_df: pd.DataFrame, sender_receiver_df: pd.DataFrame, role_df: pd.DataFrame, pathway_summary_df: pd.DataFrame) -> list[str]:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    payloads = {
        "top_interactions.csv": top_df,
        "sender_receiver_summary.csv": sender_receiver_df,
        "group_role_summary.csv": role_df,
        "pathway_summary.csv": pathway_summary_df,
    }
    for filename, frame in payloads.items():
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frame.to_csv(figure_data_dir / filename, index=False)
            manifest[filename] = filename
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return sorted(manifest)


def generate_figures(output_dir: Path, summary: dict) -> list[str]:
    figures: list[str] = []
    top_df = summary.get("top_df", pd.DataFrame())
    lr_df = summary.get("lr_df", pd.DataFrame())
    ligand_activity_df = summary.get("ligand_activity_df", pd.DataFrame())
    ligand_target_links_df = summary.get("ligand_target_links_df", pd.DataFrame())
    ligand_receptors_df = summary.get("ligand_receptors_df", pd.DataFrame())
    sender_receiver_df = _build_sender_receiver_summary(lr_df)
    role_df = _build_group_role_summary(lr_df)
    pathway_summary_df = _build_pathway_summary(lr_df, summary.get("pathway_df"))

    for plotter, kwargs in (
        (plot_interaction_heatmap, {"lr_df": lr_df}),
        (plot_top_interactions_bar, {"lr_df": top_df}),
        (plot_interaction_dotplot, {"lr_df": top_df}),
        (plot_source_target_bubble, {"sender_receiver_df": sender_receiver_df}),
        (plot_group_role_summary, {"role_df": role_df}),
        (plot_pathway_summary, {"pathway_df": pathway_summary_df}),
    ):
        try:
            path = plotter(output_dir=output_dir, **kwargs)
            if path is not None:
                figures.append(str(path))
        except Exception as exc:
            logger.warning("%s failed: %s", plotter.__name__, exc)

    if isinstance(ligand_activity_df, pd.DataFrame) and not ligand_activity_df.empty:
        try:
            path = plot_nichenet_ligands(ligand_activity_df, output_dir)
            if path is not None:
                figures.append(str(path))
        except Exception as exc:
            logger.warning("NicheNet ligand plot failed: %s", exc)

    count_matrix_df = summary.get("count_matrix_df", pd.DataFrame())
    weight_matrix_df = summary.get("weight_matrix_df", pd.DataFrame())
    if isinstance(count_matrix_df, pd.DataFrame) and isinstance(weight_matrix_df, pd.DataFrame):
        try:
            path = plot_cellchat_count_weight_heatmaps(count_matrix_df, weight_matrix_df, output_dir)
            if path is not None:
                figures.append(str(path))
        except Exception as exc:
            logger.warning("CellChat count-vs-strength heatmap failed: %s", exc)

    ligand_receptor_source = (
        ligand_receptors_df
        if isinstance(ligand_receptors_df, pd.DataFrame) and not ligand_receptors_df.empty
        else lr_df
    )
    if isinstance(ligand_receptor_source, pd.DataFrame) and not ligand_receptor_source.empty:
        try:
            path = plot_nichenet_ligand_receptor_heatmap(ligand_receptor_source, output_dir)
            if path is not None:
                figures.append(str(path))
        except Exception as exc:
            logger.warning("NicheNet ligand-receptor heatmap failed: %s", exc)

    if isinstance(ligand_target_links_df, pd.DataFrame) and not ligand_target_links_df.empty:
        try:
            path = plot_nichenet_ligand_target_heatmap(ligand_target_links_df, output_dir)
            if path is not None:
                figures.append(str(path))
        except Exception as exc:
            logger.warning("NicheNet ligand-target heatmap failed: %s", exc)

    summary["sender_receiver_df"] = sender_receiver_df
    summary["role_df"] = role_df
    summary["pathway_summary_df"] = pathway_summary_df
    summary["figure_data_files"] = _write_figure_data(
        output_dir,
        top_df=top_df,
        sender_receiver_df=sender_receiver_df,
        role_df=role_df,
        pathway_summary_df=pathway_summary_df,
    )

    # Write figures/manifest.json
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    fig_manifest: dict[str, str] = {}
    for fig_path_str in figures:
        fig_p = Path(fig_path_str)
        if fig_p.exists():
            fig_manifest[fig_p.stem] = fig_p.name
    (figures_dir / "manifest.json").write_text(
        json.dumps({"skill": SKILL_NAME, "figures": fig_manifest}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

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
    if summary.get("expression_source"):
        body_lines.append(f"- **Expression source**: {summary['expression_source']}")
    if not summary.get("pathway_summary_df", pd.DataFrame()).empty:
        body_lines.append(
            f"- **Top pathways available**: {', '.join(summary['pathway_summary_df'].head(5)['pathway'].astype(str))}"
        )
    if not top_df.empty:
        body_lines.extend(["", "### Top Interactions\n"])
        body_lines.append("| Ligand | Receptor | Source | Target | Score |")
        body_lines.append("|--------|----------|--------|--------|-------|")
        for _, row in top_df.head(15).iterrows():
            body_lines.append(
                f"| {row['ligand']} | {row['receptor']} | {row['source']} | {row['target']} | {row['score']:.4f} |"
            )

    # Troubleshooting section when degenerate
    if summary.get("n_interactions_tested", 0) == 0:
        body_lines.extend([
            "",
            "## Troubleshooting: No Interactions Detected\n",
            "### Cause 1: Gene name mismatch",
            "The ligand-receptor database expects HGNC symbols (e.g., TGFB1, CXCL12) for human data.",
            "If your data uses Ensembl IDs, convert first:",
            "```",
            "python omicsclaw.py run bulkrna-geneid-mapping --input data.h5ad --from ensembl --to symbol --output mapped/",
            "```",
            "",
            "### Cause 2: Cell type labels are missing or numeric",
            f"Column `{summary['cell_type_key']}` may contain numeric cluster IDs instead of meaningful cell type names.",
            "Run annotation first:",
            "```",
            "python omicsclaw.py run sc-cell-annotation --input data.h5ad --output anno_out/",
            "```",
            "",
            "### Cause 3: Too few cells per group",
            "Some cell types may have too few cells for communication scoring. Try merging rare clusters.",
            "",
            "### Alternative methods",
            "- `--method liana` uses a larger curated LR database and may capture more interactions.",
            "- `--method cellphonedb` runs permutation-based significance testing (human only).",
        ])

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
    sender_receiver_df = summary.get("sender_receiver_df", pd.DataFrame())
    if isinstance(sender_receiver_df, pd.DataFrame) and not sender_receiver_df.empty:
        sender_receiver_df.to_csv(tables_dir / "sender_receiver_summary.csv", index=False)
    role_df = summary.get("role_df", pd.DataFrame())
    if isinstance(role_df, pd.DataFrame) and not role_df.empty:
        role_df.to_csv(tables_dir / "group_role_summary.csv", index=False)
    pathway_summary_df = summary.get("pathway_summary_df", pd.DataFrame())
    if isinstance(pathway_summary_df, pd.DataFrame) and not pathway_summary_df.empty:
        pathway_summary_df.to_csv(tables_dir / "pathway_summary.csv", index=False)
    pathway_df = summary.get("pathway_df", pd.DataFrame())
    if isinstance(pathway_df, pd.DataFrame) and not pathway_df.empty:
        pathway_df.to_csv(tables_dir / "cellchat_pathways.csv", index=False)
    centrality_df = summary.get("centrality_df", pd.DataFrame())
    if isinstance(centrality_df, pd.DataFrame) and not centrality_df.empty:
        centrality_df.to_csv(tables_dir / "cellchat_centrality.csv", index=False)
    count_matrix_df = summary.get("count_matrix_df", pd.DataFrame())
    if isinstance(count_matrix_df, pd.DataFrame) and not count_matrix_df.empty:
        count_matrix_df.to_csv(tables_dir / "cellchat_count_matrix.csv")
    weight_matrix_df = summary.get("weight_matrix_df", pd.DataFrame())
    if isinstance(weight_matrix_df, pd.DataFrame) and not weight_matrix_df.empty:
        weight_matrix_df.to_csv(tables_dir / "cellchat_weight_matrix.csv")
    cpdb_means_df = summary.get("cpdb_means_df", pd.DataFrame())
    if isinstance(cpdb_means_df, pd.DataFrame) and not cpdb_means_df.empty:
        cpdb_means_df.to_csv(tables_dir / "cellphonedb_means.csv", index=False)
    cpdb_pvalues_df = summary.get("cpdb_pvalues_df", pd.DataFrame())
    if isinstance(cpdb_pvalues_df, pd.DataFrame) and not cpdb_pvalues_df.empty:
        cpdb_pvalues_df.to_csv(tables_dir / "cellphonedb_pvalues.csv", index=False)
    cpdb_significant_df = summary.get("cpdb_significant_df", pd.DataFrame())
    if isinstance(cpdb_significant_df, pd.DataFrame) and not cpdb_significant_df.empty:
        cpdb_significant_df.to_csv(tables_dir / "cellphonedb_significant_means.csv", index=False)
    ligand_activity_df = summary.get("ligand_activity_df", pd.DataFrame())
    if isinstance(ligand_activity_df, pd.DataFrame) and not ligand_activity_df.empty:
        ligand_activity_df.to_csv(tables_dir / "nichenet_ligand_activities.csv", index=False)
    ligand_target_links_df = summary.get("ligand_target_links_df", pd.DataFrame())
    if isinstance(ligand_target_links_df, pd.DataFrame) and not ligand_target_links_df.empty:
        ligand_target_links_df.to_csv(tables_dir / "nichenet_ligand_target_links.csv", index=False)
    ligand_receptors_df = summary.get("ligand_receptors_df", pd.DataFrame())
    if isinstance(ligand_receptors_df, pd.DataFrame) and not ligand_receptors_df.empty:
        ligand_receptors_df.to_csv(tables_dir / "nichenet_ligand_receptors.csv", index=False)

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
    if params.get("method") == "cellphonedb":
        command += (
            f" --cellphonedb-counts-data {params.get('cellphonedb_counts_data', 'hgnc_symbol')}"
            f" --cellphonedb-iterations {params.get('cellphonedb_iterations', 1000)}"
            f" --cellphonedb-threshold {params.get('cellphonedb_threshold', 0.1)}"
            f" --cellphonedb-threads {params.get('cellphonedb_threads', 4)}"
            f" --cellphonedb-pvalue {params.get('cellphonedb_pvalue', 0.05)}"
        )
    if params.get("method") == "cellchat_r":
        command += (
            f" --cellchat-prob-type {params.get('cellchat_prob_type', 'triMean')}"
            f" --cellchat-min-cells {params.get('cellchat_min_cells', 10)}"
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
            f" --nichenet-lfc-cutoff {params.get('nichenet_lfc_cutoff', 0.25)}"
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


def _simple_log_normalize(adata) -> None:
    """Apply library-size normalization and log1p without relying on scanpy preprocessors."""
    import scipy.sparse as sp

    X = adata.X
    if sp.issparse(X):
        X = X.tocsr(copy=True).astype(np.float64)
        counts = np.asarray(X.sum(axis=1)).reshape(-1)
        counts[counts == 0] = 1.0
        scale = 1e4 / counts
        X = sp.diags(scale) @ X
        X.data = np.log1p(X.data)
        adata.X = X
    else:
        X = np.asarray(X, dtype=np.float64)
        counts = X.sum(axis=1)
        counts[counts == 0] = 1.0
        X = X * (1e4 / counts)[:, None]
        adata.X = np.log1p(X)


def _prepare_demo_communication_adata(method: str, *, cell_type_key: str):
    """Build a communication-ready demo object with aligned labels."""
    raw_adata, _ = sc_io.load_repo_demo_data("pbmc3k_raw")
    processed_demo, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
    fallback_key = "louvain" if "louvain" in processed_demo.obs else "leiden"
    labels = processed_demo.obs.reindex(raw_adata.obs_names)[fallback_key]
    adata = raw_adata.copy()
    valid_mask = labels.notna().to_numpy()
    adata = adata[valid_mask].copy()
    adata.obs[cell_type_key] = labels[valid_mask].astype(str).values

    if method != "nichenet_r":
        _simple_log_normalize(adata)
    return adata


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
    parser.add_argument("--cellchat-prob-type", default="triMean", choices=["triMean", "truncatedMean", "thresholdedMean", "median"])
    parser.add_argument("--cellchat-min-cells", type=int, default=10)
    parser.add_argument("--condition-key", default="condition")
    parser.add_argument("--condition-oi", default="stim")
    parser.add_argument("--condition-ref", default="ctrl")
    parser.add_argument("--receiver", default="")
    parser.add_argument("--senders", default="")
    parser.add_argument("--nichenet-top-ligands", type=int, default=20)
    parser.add_argument("--nichenet-expression-pct", type=float, default=0.10)
    parser.add_argument("--nichenet-lfc-cutoff", type=float, default=0.25)
    parser.add_argument(
        "--r-enhanced", action="store_true",
        help="Generate R Enhanced ggplot2 figures in addition to standard Python plots."
    )
    args = parser.parse_args()
    counts_data_explicit = "--cellphonedb-counts-data" in sys.argv

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.positive("cellphonedb_iterations", args.cellphonedb_iterations, min_val=1)
    v.in_range("cellphonedb_threshold", args.cellphonedb_threshold, low=0, high=1)
    v.positive("cellphonedb_threads", args.cellphonedb_threads, min_val=1)
    v.fraction("cellphonedb_pvalue", args.cellphonedb_pvalue)
    v.positive("cellchat_min_cells", args.cellchat_min_cells, min_val=1)
    v.positive("nichenet_top_ligands", args.nichenet_top_ligands, min_val=1)
    v.non_negative("nichenet_lfc_cutoff", args.nichenet_lfc_cutoff)
    v.check()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback=DEFAULT_METHOD)

    if args.demo:
        adata = _prepare_demo_communication_adata(method, cell_type_key=args.cell_type_key)
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
        adata = sc_io.smart_load(args.input_path, skill_name=SKILL_NAME, preserve_all=True)
        input_file = args.input_path

    ensure_input_contract(adata, source_path=input_file)
    if not args.species:
        args.species = infer_qc_species(adata)

    senders = [item.strip() for item in str(args.senders).split(",") if item.strip()]
    apply_preflight(
        preflight_sc_cell_communication(
            adata,
            method=method,
            cell_type_key=args.cell_type_key,
            species=args.species,
            counts_data=args.cellphonedb_counts_data,
            counts_data_explicit=counts_data_explicit,
            cellphonedb_iterations=args.cellphonedb_iterations,
            cellphonedb_threshold=args.cellphonedb_threshold,
            cellphonedb_threads=args.cellphonedb_threads,
            cellphonedb_pvalue=args.cellphonedb_pvalue,
            cellchat_prob_type=args.cellchat_prob_type,
            cellchat_min_cells=args.cellchat_min_cells,
            condition_key=args.condition_key,
            condition_oi=args.condition_oi,
            condition_ref=args.condition_ref,
            receiver=args.receiver,
            senders=senders,
            nichenet_top_ligands=args.nichenet_top_ligands,
            nichenet_expression_pct=args.nichenet_expression_pct,
            nichenet_lfc_cutoff=args.nichenet_lfc_cutoff,
            source_path=input_file,
        ),
        logger,
        demo_mode=args.demo,
    )
    summary = run_communication(
        adata,
        method=method,
        cell_type_key=args.cell_type_key,
        species=args.species,
        cellphonedb_counts_data=args.cellphonedb_counts_data,
        cellphonedb_iterations=args.cellphonedb_iterations,
        cellphonedb_threshold=args.cellphonedb_threshold,
        cellphonedb_threads=args.cellphonedb_threads,
        cellphonedb_pvalue=args.cellphonedb_pvalue,
        cellchat_prob_type=args.cellchat_prob_type,
        cellchat_min_cells=args.cellchat_min_cells,
        condition_key=args.condition_key,
        condition_oi=args.condition_oi,
        condition_ref=args.condition_ref,
        receiver=args.receiver,
        senders=senders,
        nichenet_top_ligands=args.nichenet_top_ligands,
        nichenet_expression_pct=args.nichenet_expression_pct,
        nichenet_lfc_cutoff=args.nichenet_lfc_cutoff,
    )
    # --- Degenerate output detection (UX guardrail) ---
    _n_interactions = summary.get("n_interactions_tested", 0)
    _degenerate = _n_interactions == 0
    if _degenerate:
        print()
        print("  *** NO interactions were detected - communication analysis produced empty results. ***")
        print("  This usually means the gene names in your data do not overlap with the ligand-receptor database,")
        print("  or the cell type grouping has too few cells per group.")
        print()
        print("  How to fix:")
        print(f"    Option 1 - Check that '--cell-type-key {args.cell_type_key}' has meaningful labels (not numeric IDs).")
        print("      Example: python omicsclaw.py run sc-cell-annotation --input data.h5ad --output anno_out/")
        print("    Option 2 - Use a richer method that queries a larger LR database:")
        print("      Example: python omicsclaw.py run sc-cell-communication --method liana --input data.h5ad --output out/")
        print("    Option 3 - Verify gene names are HGNC symbols (human) or standard gene symbols (mouse).")
        print("      If Ensembl IDs, convert first: python omicsclaw.py run bulkrna-geneid-mapping --input data.h5ad --from ensembl --to symbol --output mapped/")
        print()

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
    if method == "cellchat_r":
        params.update(
            {
                "cellchat_prob_type": args.cellchat_prob_type,
                "cellchat_min_cells": args.cellchat_min_cells,
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
                "nichenet_lfc_cutoff": args.nichenet_lfc_cutoff,
            }
        )

    generate_figures(output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    propagated_input, propagated_matrix = propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind=infer_x_matrix_kind(adata),
        raw_kind="raw_counts_snapshot" if adata.raw is not None else None,
        primary_cluster_key=args.cell_type_key,
    )
    metadata_params = {
        "requested_method": summary.get("requested_method", method),
        "executed_method": summary.get("executed_method", method),
        "fallback_used": summary.get("fallback_used", False),
        "fallback_reason": summary.get("fallback_reason", ""),
        "pvalue_available": summary.get("pvalue_available", True),
        "cell_type_key": args.cell_type_key,
        "species": args.species,
    }
    if method == "cellphonedb":
        metadata_params.update(
            {
                "cellphonedb_counts_data": args.cellphonedb_counts_data,
                "cellphonedb_iterations": args.cellphonedb_iterations,
                "cellphonedb_threshold": args.cellphonedb_threshold,
                "cellphonedb_threads": args.cellphonedb_threads,
                "cellphonedb_pvalue": args.cellphonedb_pvalue,
            }
        )
    if method == "cellchat_r":
        metadata_params.update(
            {
                "cellchat_prob_type": args.cellchat_prob_type,
                "cellchat_min_cells": args.cellchat_min_cells,
            }
        )
    if method == "nichenet_r":
        metadata_params.update(
            {
                "condition_key": args.condition_key,
                "condition_oi": args.condition_oi,
                "condition_ref": args.condition_ref,
                "receiver": args.receiver,
                "senders": senders,
                "nichenet_lfc_cutoff": args.nichenet_lfc_cutoff,
            }
        )
    store_analysis_metadata(adata, SKILL_NAME, summary.get("executed_method", method), metadata_params)

    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""

    # Communication diagnostics for bot/agent
    communication_diagnostics: dict[str, object] = {
        "no_interactions": _degenerate,
        "n_interactions_tested": _n_interactions,
        "n_significant": summary.get("n_significant", 0),
    }
    if _degenerate:
        communication_diagnostics["suggested_actions"] = [
            f"Check that '--cell-type-key {args.cell_type_key}' has meaningful cell type labels",
            "Try a richer method: --method liana",
            "Verify gene names are HGNC symbols (human) or standard symbols (mouse)",
            "Run sc-cell-annotation first if labels are missing",
        ]

    result_data = {
        "requested_method": summary.get("requested_method", method),
        "executed_method": summary.get("executed_method", method),
        "fallback_used": summary.get("fallback_used", False),
        "fallback_reason": summary.get("fallback_reason", ""),
        "pvalue_available": summary.get("pvalue_available", True),
        "score_semantics": summary.get("score_semantics"),
        "significance_semantics": summary.get("significance_semantics"),
        "available_figure_data": summary.get("figure_data_files", []),
        "communication_diagnostics": communication_diagnostics,
        "params": params,
        "input_contract": propagated_input,
        "matrix_contract": propagated_matrix,
    }
    result_data["next_steps"] = []
    write_result_json(
        output_dir,
        SKILL_NAME,
        SKILL_VERSION,
        {k: v for k, v in summary.items() if k not in SUMMARY_FRAME_KEYS},
        result_data,
        checksum,
    )
    write_replot_hint(output_dir, SKILL_NAME, R_ENHANCED_PLOTS)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": {k: v for k, v in summary.items() if k not in SUMMARY_FRAME_KEYS},
        "data": result_data,
    }
    write_standard_run_artifacts(output_dir, result_payload, summary)

    # R Enhanced figures (only when --r-enhanced flag is set)
    r_enhanced_figures = _render_r_enhanced(
        output_dir=output_dir,
        figure_data_dir=output_dir / "figure_data",
        r_enhanced=args.r_enhanced,
    )
    if r_enhanced_figures:
        result_data["r_enhanced_figures"] = r_enhanced_figures

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        "Communication analysis complete: "
        f"{summary['n_interactions_tested']} interactions tested "
        f"(requested={summary.get('requested_method', method)}, executed={summary.get('executed_method', method)})"
    )

    # --- Next-step guidance ---
    print()
    print(">> Analysis complete. Further exploration:")
    print(f"  - sc-grn: python omicsclaw.py run sc-grn --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()
