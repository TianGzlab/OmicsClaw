#!/usr/bin/env python3
"""Single-cell pseudotime and lineage inference."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import scanpy as sc

try:
    import anndata

    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

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
from omicsclaw.core.r_dependency_manager import check_r_tier, suggest_r_install
from omicsclaw.core.r_script_runner import RScriptRunner
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib import trajectory as sc_traj
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    get_matrix_contract,
    infer_x_matrix_kind,
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib.dependency_manager import install_hint, is_available
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_pseudotime
from skills.singlecell._lib.viz import (
    plot_fate_probability_heatmap,
    plot_pseudotime_distribution_by_group,
    plot_pseudotime_embedding,
    plot_slingshot_curves,
    plot_trajectory_gene_trends,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-pseudotime"
SKILL_VERSION = "0.5.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py"
R_SCRIPTS_DIR = _PROJECT_ROOT / "omicsclaw" / "r_scripts"

# R Enhanced renderers for this skill.
# Key   = renderer name registered in viz/r/registry.R R_PLOT_REGISTRY
# Value = output filename (written to figures/r_enhanced/)
R_ENHANCED_PLOTS: dict[str, str] = {
    "plot_pseudotime_lineage": "r_pseudotime_lineage.png",
    "plot_pseudotime_dynamic": "r_pseudotime_dynamic.png",
    "plot_pseudotime_heatmap": "r_pseudotime_heatmap.png",
    "plot_embedding_discrete": "r_embedding_discrete.png",
    "plot_embedding_feature": "r_embedding_feature.png",
    "plot_cell_density": "r_cell_density.png",
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

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "dpt": MethodConfig(
        name="dpt",
        description="Scanpy DPT on a graph built from the chosen representation",
        dependencies=("scanpy",),
    ),
    "palantir": MethodConfig(
        name="palantir",
        description="Palantir pseudotime with diffusion maps, entropy, and fate probabilities",
        dependencies=("palantir",),
    ),
    "via": MethodConfig(
        name="via",
        description="VIA graph-based pseudotime with terminal-state discovery",
        dependencies=("pyVIA",),
    ),
    "cellrank": MethodConfig(
        name="cellrank",
        description="CellRank macrostate and fate inference on a transition kernel",
        dependencies=("cellrank",),
    ),
    "slingshot_r": MethodConfig(
        name="slingshot_r",
        description="Slingshot lineage inference through the R bridge",
        dependencies=(),
    ),
    "monocle3_r": MethodConfig(
        name="monocle3_r",
        description="Monocle3 principal graph trajectory and pseudotime via R bridge",
        dependencies=(),
    ),
}

METHOD_PARAM_DEFAULTS: dict[str, dict[str, object]] = {
    "dpt": {
        "cluster_key": "leiden",
        "use_rep": None,
        "root_cluster": None,
        "root_cell": None,
        "n_neighbors": 15,
        "n_pcs": 50,
        "n_dcs": 10,
        "n_genes": 50,
        "corr_method": "pearson",
    },
    "palantir": {
        "cluster_key": "leiden",
        "use_rep": None,
        "root_cluster": None,
        "root_cell": None,
        "n_neighbors": 15,
        "n_pcs": 50,
        "n_genes": 50,
        "corr_method": "pearson",
        "palantir_knn": 30,
        "palantir_n_components": 10,
        "palantir_num_waypoints": 1200,
        "palantir_max_iterations": 25,
        "palantir_seed": 20,
    },
    "via": {
        "cluster_key": "leiden",
        "use_rep": None,
        "root_cluster": None,
        "root_cell": None,
        "n_neighbors": 15,
        "n_pcs": 50,
        "n_genes": 50,
        "corr_method": "pearson",
        "via_knn": 30,
        "via_seed": 20,
    },
    "cellrank": {
        "cluster_key": "leiden",
        "use_rep": None,
        "root_cluster": None,
        "root_cell": None,
        "n_neighbors": 15,
        "n_pcs": 50,
        "n_dcs": 10,
        "n_genes": 50,
        "corr_method": "pearson",
        "cellrank_n_states": 3,
        "cellrank_schur_components": 20,
        "cellrank_frac_to_keep": 0.3,
        "cellrank_use_velocity": False,
    },
    "slingshot_r": {
        "cluster_key": "leiden",
        "use_rep": None,
        "root_cluster": None,
        "root_cell": None,
        "end_clusters": None,
        "n_genes": 50,
        "corr_method": "pearson",
    },
    "monocle3_r": {
        "cluster_key": "leiden",
        "use_rep": None,
        "root_cluster": None,
        "root_cell": None,
        "n_genes": 50,
        "corr_method": "pearson",
    },
}

METHOD_PARAM_KEYS: dict[str, tuple[str, ...]] = {
    "dpt": ("n_neighbors", "n_pcs", "n_dcs"),
    "palantir": ("palantir_knn", "palantir_n_components", "palantir_num_waypoints", "palantir_max_iterations", "palantir_seed"),
    "via": ("via_knn", "via_seed"),
    "cellrank": ("cellrank_n_states", "cellrank_schur_components", "cellrank_frac_to_keep", "cellrank_use_velocity"),
    "slingshot_r": ("end_clusters",),
    "monocle3_r": (),
}


def _prepare_via_runtime() -> None:
    compat_aliases = {
        "bool8": np.bool_,
        "object0": np.object_,
        "int0": np.intp,
        "uint0": np.uintp,
        "uint": np.uint64,
        "float_": np.float64,
        "longfloat": np.longdouble,
        "singlecomplex": np.complex64,
        "complex_": np.complex128,
        "cfloat": np.complex128,
        "clongfloat": np.clongdouble,
        "longcomplex": np.clongdouble,
        "void0": np.void,
        "bytes0": np.bytes_,
        "str0": np.str_,
        "string_": np.bytes_,
        "unicode_": np.str_,
    }
    for alias, target in compat_aliases.items():
        if not hasattr(np, alias):
            setattr(np, alias, target)


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
            description="Single-cell pseudotime and lineage inference.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "dpt"),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Single-cell pseudotime and lineage inference.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "dpt"),
            notebook_path=notebook_path,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to write README.md: %s", exc)


def _candidate_reps(adata) -> list[str]:
    preferred = [key for key in ("X_umap", "X_harmony", "X_scvi", "X_scanvi", "X_scanorama", "X_pca") if key in adata.obsm]
    if preferred:
        return preferred
    return [str(key) for key in adata.obsm.keys() if str(key).startswith("X_") and str(key) not in {"X_umap", "X_tsne", "X_diffmap"}]


def _candidate_display_embeddings(adata) -> list[str]:
    preferred = [key for key in ("X_umap", "X_tsne", "X_phate", "X_diffmap", "X_pca") if key in adata.obsm]
    return preferred or [str(key) for key in adata.obsm.keys() if str(key).startswith("X_")]


def _resolve_use_rep(adata, requested: str | None) -> str:
    if requested:
        if requested not in adata.obsm:
            raise ValueError(f"Embedding `{requested}` was not found in adata.obsm.")
        return requested
    candidates = _candidate_reps(adata)
    if not candidates:
        raise ValueError("No suitable representation was found. Run `sc-preprocessing` or `sc-batch-integration` first.")
    return candidates[0]


def _resolve_display_embedding(adata, use_rep: str) -> str:
    candidates = _candidate_display_embeddings(adata)
    return candidates[0] if candidates else use_rep


def _resolve_root_cell(adata, root_cell: str | None) -> int | None:
    if root_cell is None:
        return None
    token = str(root_cell).strip()
    if token == "":
        return None
    if token in set(adata.obs_names.astype(str)):
        return int(np.where(adata.obs_names.astype(str) == token)[0][0])
    if token.isdigit():
        idx = int(token)
        if 0 <= idx < adata.n_obs:
            return idx
    raise ValueError(f"`--root-cell {root_cell}` was not found. Provide a valid obs_name or integer cell index.")


def _parse_end_clusters(end_clusters: str | None) -> list[str] | None:
    if not end_clusters:
        return None
    values = [token.strip() for token in str(end_clusters).split(",") if token.strip()]
    return values or None


def _ensure_normalized_demo(adata) -> None:
    ensure_input_contract(adata, standardized=True)
    contract = get_matrix_contract(adata)
    if contract.get("X") != "normalized_expression":
        propagate_singlecell_contracts(
            adata,
            adata,
            producer_skill=SKILL_NAME,
            x_kind="normalized_expression",
            raw_kind=contract.get("raw"),
            primary_cluster_key="leiden" if "leiden" in adata.obs.columns else None,
        )


def get_demo_data():
    adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
    if "leiden" not in adata.obs.columns:
        if "louvain" in adata.obs.columns:
            adata.obs["leiden"] = adata.obs["louvain"].astype(str)
        else:
            sc.pp.neighbors(adata)
            sc.tl.umap(adata)
            try:
                sc.tl.leiden(adata, resolution=0.8)
            except Exception:
                sc.tl.louvain(adata, resolution=0.8)
                adata.obs["leiden"] = adata.obs["louvain"].astype(str)
    _ensure_normalized_demo(adata)
    return adata


def _prepare_input_adata(input_path: Path):
    adata = sc_io.smart_load(input_path, skill_name=SKILL_NAME, preserve_all=True)
    ensure_input_contract(adata, source_path=str(input_path))
    return adata


def _ensure_neighbors_for_rep(adata, *, use_rep: str, n_neighbors: int, n_pcs: int) -> None:
    if use_rep == "X_pca":
        sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs)
    else:
        sc.pp.neighbors(adata, n_neighbors=n_neighbors, use_rep=use_rep)


def _build_pseudotime_points_table(adata, *, pseudotime_key: str, cluster_key: str, display_key: str) -> pd.DataFrame:
    coords = np.asarray(adata.obsm[display_key])
    return pd.DataFrame(
        {
            "cell_id": adata.obs_names.astype(str),
            "display_embedding": display_key,
            "coord1": coords[:, 0],
            "coord2": coords[:, 1],
            cluster_key: adata.obs[cluster_key].astype(str).to_numpy(),
            "pseudotime": pd.to_numeric(adata.obs[pseudotime_key], errors="coerce").to_numpy(),
        }
    )


def _build_fate_summary_table(adata, *, cluster_key: str, obsm_key: str) -> pd.DataFrame:
    if obsm_key not in adata.obsm:
        return pd.DataFrame()
    matrix = np.asarray(adata.obsm[obsm_key], dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] == 0:
        return pd.DataFrame()
    columns = [f"lineage_{i+1}" for i in range(matrix.shape[1])]
    frame = pd.DataFrame(matrix, columns=columns, index=adata.obs_names.astype(str))
    frame["group"] = adata.obs[cluster_key].astype(str).to_numpy()
    return frame.groupby("group", observed=False)[columns].mean().reset_index()


def _write_figure_data(
    output_dir: Path,
    *,
    points_df: pd.DataFrame,
    trajectory_genes: pd.DataFrame,
    summary_df: pd.DataFrame,
    fate_df: pd.DataFrame | None = None,
    curves_df: pd.DataFrame | None = None,
) -> dict[str, str]:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "pseudotime_points": "pseudotime_points.csv",
        "trajectory_genes": "trajectory_genes.csv",
        "summary": "trajectory_summary.csv",
    }
    points_df.to_csv(figure_data_dir / files["pseudotime_points"], index=False)
    trajectory_genes.to_csv(figure_data_dir / files["trajectory_genes"], index=False)
    summary_df.to_csv(figure_data_dir / files["summary"], index=False)

    if fate_df is not None and not fate_df.empty:
        files["fate_probabilities"] = "fate_probabilities.csv"
        fate_df.to_csv(figure_data_dir / files["fate_probabilities"], index=False)
    if curves_df is not None and not curves_df.empty:
        files["slingshot_curves"] = "slingshot_curves.csv"
        curves_df.to_csv(figure_data_dir / files["slingshot_curves"], index=False)

    manifest = {"skill": SKILL_NAME, "available_files": files}
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return files


def _write_figure_manifest(output_dir: Path, figure_paths: list[str]) -> None:
    manifest = {
        "skill": SKILL_NAME,
        "recipe_id": "standard-sc-pseudotime-gallery",
        "figures": [{"filename": Path(path).name, "path": str(path)} for path in figure_paths],
    }
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    (figures_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _write_tables(
    output_dir: Path,
    *,
    points_df: pd.DataFrame,
    trajectory_genes: pd.DataFrame,
    summary_df: pd.DataFrame,
    fate_df: pd.DataFrame | None = None,
    curves_df: pd.DataFrame | None = None,
) -> dict[str, str]:
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "trajectory_genes": "trajectory_genes.csv",
        "pseudotime_cells": "pseudotime_cells.csv",
        "summary": "trajectory_summary.csv",
    }
    trajectory_genes.to_csv(tables_dir / files["trajectory_genes"], index=False)
    points_df.to_csv(tables_dir / files["pseudotime_cells"], index=False)
    summary_df.to_csv(tables_dir / files["summary"], index=False)
    if fate_df is not None and not fate_df.empty:
        files["fate_probabilities"] = "fate_probabilities.csv"
        fate_df.to_csv(tables_dir / files["fate_probabilities"], index=False)
    if curves_df is not None and not curves_df.empty:
        files["slingshot_curves"] = "slingshot_curves.csv"
        curves_df.to_csv(tables_dir / files["slingshot_curves"], index=False)
    return files


def _write_report(output_dir: Path, *, summary: dict, params: dict, input_file: str | None, top_genes: pd.DataFrame) -> None:
    header = generate_report_header(
        title="Single-Cell Pseudotime Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": str(summary.get("method", "dpt")),
            "Backend": str(summary.get("backend", summary.get("method", "dpt"))),
            "Cells": str(summary.get("n_cells", "N/A")),
            "Clusters": str(summary.get("n_clusters", "N/A")),
            "Trajectory genes": str(summary.get("n_trajectory_genes", 0)),
        },
    )

    body = [
        "## Summary\n",
        f"- **Method**: `{summary.get('method', 'dpt')}`",
        f"- **Backend**: `{summary.get('backend', summary.get('method', 'dpt'))}`",
        f"- **Cluster key**: `{summary.get('cluster_key', 'leiden')}`",
        f"- **Graph / trajectory representation**: `{summary.get('use_rep', 'X_pca')}`",
        f"- **Display embedding**: `{summary.get('display_embedding', 'X_umap')}`",
        f"- **Root cluster**: `{summary.get('root_cluster', 'not set')}`",
        f"- **Root cell**: `{summary.get('root_cell_name', summary.get('root_cell', 'not set'))}`",
        f"- **Pseudotime range**: `{summary.get('pseudotime_min', 0):.3f}` to `{summary.get('pseudotime_max', 1):.3f}`",
        f"- **Trajectory genes exported**: `{summary.get('n_trajectory_genes', 0)}`",
        "",
        "## Beginner Notes\n",
        "- This skill should usually be run after `sc-clustering`, when cluster labels and a biologically plausible start state are known.",
        "- `method` changes the trajectory model itself; `corr_method` only changes how trajectory-associated genes are ranked afterwards.",
        "- `use_rep` is a first-class choice. If you clustered on Harmony or scVI embeddings, use the same representation here unless you have a strong reason to switch.",
        "",
        "## Effective Parameters\n",
        f"- `cluster_key`: {params['cluster_key']}",
        f"- `use_rep`: {params['use_rep']}",
        f"- `root_cluster`: {params.get('root_cluster')}",
        f"- `root_cell`: {params.get('root_cell')}",
        f"- `n_genes`: {params['n_genes']}",
        f"- `corr_method`: {params['corr_method']}",
    ]
    for key in METHOD_PARAM_KEYS.get(summary["method"], ()):
        body.append(f"- `{key}`: {params.get(key)}")

    body.extend(
        [
            "",
            "## What To Inspect First\n",
            "- `figures/pseudotime_embedding.png` — whether the inferred ordering is biologically plausible.",
            "- `figures/pseudotime_distribution_by_group.png` — whether different groups occupy distinct trajectory regions.",
            "- `tables/trajectory_genes.csv` — top genes associated with the inferred trajectory.",
            "- `processed.h5ad` — trajectory-aware object for downstream interpretation.",
            "",
            "## Top Trajectory Genes\n",
            "| Gene | Correlation | P-value |",
            "|------|-------------|---------|",
        ]
    )
    for _, row in top_genes.head(20).iterrows():
        body.append(f"| {row.get('gene','NA')} | {float(row.get('correlation', 0)):.3f} | {float(row.get('pvalue', 1)):.2e} |")

    body.extend(
        [
            "",
            "## Recommended Next Steps\n",
            "- Check marker and annotation context to decide whether the root choice should be revised.",
            "- Use `sc-pathway-scoring` to score lineage signatures along pseudotime.",
            "- Use `sc-enrichment` on trajectory-associated genes if you want statistical pathway interpretation.",
        ]
    )

    report = header + "\n".join(body) + "\n" + generate_report_footer()
    (output_dir / "report.md").write_text(report, encoding="utf-8")


def _write_reproducibility(output_dir: Path, *, params: dict, input_file: str | None, demo_mode: bool) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    elif input_file:
        command_parts.extend(["--input", input_file])
    command_parts.extend(["--output", str(output_dir), "--method", str(params["method"])])
    for key in (
        "cluster_key",
        "use_rep",
        "root_cluster",
        "root_cell",
        "end_clusters",
        "n_neighbors",
        "n_pcs",
        "n_dcs",
        "n_genes",
        "corr_method",
        "palantir_knn",
        "palantir_n_components",
        "palantir_num_waypoints",
        "palantir_max_iterations",
        "palantir_seed",
        "via_knn",
        "via_seed",
        "cellrank_n_states",
        "cellrank_schur_components",
        "cellrank_frac_to_keep",
    ):
        value = params.get(key)
        if value not in (None, "", False):
            command_parts.extend([f"--{key.replace('_', '-')}", str(value)])
    if params.get("cellrank_use_velocity"):
        command_parts.append("--cellrank-use-velocity")
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")

    packages = ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "seaborn"]
    if params["method"] == "palantir":
        packages.append("palantir")
    if params["method"] == "via":
        packages.append("pyVIA")
    if params["method"] == "cellrank":
        packages.append("cellrank")
    _write_repro_requirements(repro_dir, packages)


def _run_dpt(
    adata,
    *,
    use_rep: str,
    cluster_key: str,
    root_cluster: str | None,
    root_cell_idx: int | None,
    n_neighbors: int,
    n_pcs: int,
    n_dcs: int,
) -> tuple[object, dict]:
    _ensure_neighbors_for_rep(adata, use_rep=use_rep, n_neighbors=n_neighbors, n_pcs=n_pcs)
    sc_traj.run_paga_analysis(adata, cluster_key=cluster_key, n_neighbors=n_neighbors)
    diffmap_result = sc_traj.run_diffusion_map(adata, n_comps=max(15, n_dcs + 5), n_dcs=n_dcs)
    dpt_result = sc_traj.run_dpt_pseudotime(
        adata,
        root_cell_indices=[root_cell_idx] if root_cell_idx is not None else None,
        root_cluster=root_cluster,
        cluster_key=cluster_key,
        n_dcs=n_dcs,
    )
    summary = {
        "backend": "dpt",
        "pseudotime_key": "dpt_pseudotime",
        "root_cell": int(dpt_result["root_cells"][0]) if dpt_result["root_cells"] else None,
        "root_cell_name": str(adata.obs_names[int(dpt_result["root_cells"][0])]) if dpt_result["root_cells"] else None,
        "n_diffusion_components": int(diffmap_result["diffmap"].shape[1]),
    }
    return adata, summary


def _run_palantir(
    adata,
    *,
    use_rep: str,
    cluster_key: str,
    root_cluster: str | None,
    root_cell_idx: int | None,
    palantir_knn: int,
    palantir_n_components: int,
    palantir_num_waypoints: int,
    palantir_max_iterations: int,
    palantir_seed: int,
) -> tuple[object, dict]:
    early_cell = sc_traj.resolve_palantir_early_cell(
        adata,
        root_cell=root_cell_idx,
        root_cluster=root_cluster,
        cluster_key=cluster_key,
        use_rep=use_rep,
    )
    result = sc_traj.run_palantir_pseudotime(
        adata,
        early_cell=early_cell,
        use_rep=use_rep,
        knn=palantir_knn,
        n_components=palantir_n_components,
        num_waypoints=palantir_num_waypoints,
        max_iterations=palantir_max_iterations,
        seed=palantir_seed,
    )
    if "palantir_fate_probabilities" in adata.obsm:
        adata.obsm["trajectory_fate_probabilities"] = np.asarray(adata.obsm["palantir_fate_probabilities"], dtype=float)
    summary = {
        "backend": "palantir",
        "pseudotime_key": "palantir_pseudotime",
        "root_cell": int(np.where(adata.obs_names.astype(str) == str(early_cell))[0][0]),
        "root_cell_name": str(early_cell),
        "mean_entropy": float(np.nanmean(result["entropy"])) if result.get("entropy") is not None else None,
        "n_terminal_states": int(result["fate_probabilities"].shape[1]) if result.get("fate_probabilities") is not None else 0,
        "fate_obsm_key": "trajectory_fate_probabilities" if "trajectory_fate_probabilities" in adata.obsm else None,
    }
    return adata, summary


def _run_via(
    adata,
    *,
    use_rep: str,
    cluster_key: str,
    root_cluster: str | None,
    root_cell_idx: int | None,
    via_knn: int,
    via_seed: int,
    n_dcs: int,
) -> tuple[object, dict]:
    result = sc_traj.run_via_pseudotime(
        adata,
        root_cell=root_cell_idx,
        root_cluster=root_cluster,
        cluster_key=cluster_key,
        use_rep=use_rep,
        knn=via_knn,
        n_components=max(2, n_dcs),
        seed=via_seed,
    )
    if "via_fate_probabilities" in adata.obsm:
        adata.obsm["trajectory_fate_probabilities"] = np.asarray(adata.obsm["via_fate_probabilities"], dtype=float)
    summary = {
        "backend": result.get("method", "via"),
        "pseudotime_key": "via_pseudotime",
        "root_cell": int(result["root_cell"]),
        "root_cell_name": str(result["root_cell_name"]),
        "n_terminal_states": int(len(result.get("terminal_clusters", []))),
        "fate_obsm_key": "trajectory_fate_probabilities" if "trajectory_fate_probabilities" in adata.obsm else None,
    }
    return adata, summary


def _run_cellrank(
    adata,
    *,
    use_rep: str,
    cluster_key: str,
    root_cluster: str | None,
    root_cell_idx: int | None,
    n_neighbors: int,
    n_pcs: int,
    n_dcs: int,
    cellrank_n_states: int,
    cellrank_schur_components: int,
    cellrank_frac_to_keep: float,
    cellrank_use_velocity: bool,
) -> tuple[object, dict]:
    _ensure_neighbors_for_rep(adata, use_rep=use_rep, n_neighbors=n_neighbors, n_pcs=n_pcs)
    result = sc_traj.run_cellrank_pseudotime(
        adata,
        root_cell=root_cell_idx,
        root_cluster=root_cluster,
        cluster_key=cluster_key,
        n_states=cellrank_n_states,
        schur_components=cellrank_schur_components,
        frac_to_keep=cellrank_frac_to_keep,
        use_velocity=cellrank_use_velocity,
        n_dcs=n_dcs,
    )
    if result.get("fate_probabilities") is not None:
        adata.obsm["trajectory_fate_probabilities"] = np.asarray(result["fate_probabilities"], dtype=float)
    summary = {
        "backend": "cellrank",
        "pseudotime_key": "dpt_pseudotime",
        "root_cell": result.get("root_cell"),
        "root_cell_name": result.get("root_cell_name"),
        "n_terminal_states": int(len(result.get("terminal_states", []))),
        "n_macrostates": int(result.get("n_macrostates", 0)),
        "kernel_mode": result.get("kernel_mode"),
        "fate_obsm_key": "trajectory_fate_probabilities" if "trajectory_fate_probabilities" in adata.obsm else None,
    }
    return adata, summary


def _run_slingshot_r(
    adata,
    *,
    use_rep: str,
    cluster_key: str,
    root_cluster: str | None,
    end_clusters: list[str] | None,
) -> tuple[object, dict, pd.DataFrame]:
    required = ["slingshot", "SingleCellExperiment", "zellkonverter"]
    installed, missing = check_r_tier("singlecell-pseudotime")
    del installed  # quiet lint
    missing_required = [pkg for pkg in required if pkg in missing]
    if missing_required:
        raise ImportError(
            "Slingshot R dependencies are missing: "
            + ", ".join(missing_required)
            + "\nInstall with:\n"
            + suggest_r_install(missing_required)
        )

    runner = RScriptRunner(scripts_dir=R_SCRIPTS_DIR, timeout=7200)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_slingshot_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        save_h5ad(adata, input_h5ad, compression=None)
        runner.run_script(
            "sc_slingshot_pseudotime.R",
            args=[
                str(input_h5ad),
                str(output_dir),
                cluster_key,
                use_rep,
                root_cluster or "",
                ",".join(end_clusters or []),
            ],
            expected_outputs=["slingshot_pseudotime.csv", "slingshot_branches.csv", "slingshot_curves.csv"],
            output_dir=output_dir,
        )
        pseudotime_df = pd.read_csv(output_dir / "slingshot_pseudotime.csv")
        branch_df = pd.read_csv(output_dir / "slingshot_branches.csv")
        curves_df = pd.read_csv(output_dir / "slingshot_curves.csv")

    pseudotime_df["cell_id"] = pseudotime_df["cell_id"].astype(str)
    pseudotime_df = pseudotime_df.drop_duplicates(subset="cell_id", keep="first")
    pseudotime_df = pseudotime_df.set_index("cell_id").reindex(adata.obs_names.astype(str))
    adata.obs["slingshot_pseudotime"] = pd.to_numeric(pseudotime_df["slingshot_pseudotime"], errors="coerce").to_numpy()
    for col in pseudotime_df.columns:
        if col == "slingshot_pseudotime":
            continue
        adata.obs[f"slingshot_{col}"] = pd.to_numeric(pseudotime_df[col], errors="coerce").to_numpy()

    branch_df["cell_id"] = branch_df["cell_id"].astype(str)
    branch_df = branch_df.drop_duplicates(subset="cell_id", keep="first")
    branch_df = branch_df.set_index("cell_id").reindex(adata.obs_names.astype(str))
    for col in branch_df.columns:
        adata.obs[f"slingshot_branch_{col}"] = branch_df[col].astype(str).to_numpy()

    adata.uns["slingshot_trajectory"] = {
        "use_rep": use_rep,
        "cluster_key": cluster_key,
        "start_cluster": root_cluster,
        "end_clusters": end_clusters or [],
        "n_lineages": int(max(1, len([col for col in pseudotime_df.columns if col != "slingshot_pseudotime"]))),
    }
    summary = {
        "backend": "slingshot_r",
        "pseudotime_key": "slingshot_pseudotime",
        "root_cell": None,
        "root_cell_name": None,
        "n_lineages": int(max(1, len([col for col in pseudotime_df.columns if col != "slingshot_pseudotime"]))),
    }
    return adata, summary, curves_df


def _run_monocle3_r(
    adata,
    *,
    use_rep: str,
    cluster_key: str,
    root_cluster: str | None,
) -> tuple[object, dict, pd.DataFrame]:
    """Run Monocle3 principal graph pseudotime via R bridge."""
    import warnings

    required = ["monocle3", "SingleCellExperiment", "zellkonverter"]
    installed, missing = check_r_tier("singlecell-pseudotime")
    del installed
    missing_required = [pkg for pkg in required if pkg in missing]
    if missing_required:
        raise ImportError(
            "Monocle3 R dependencies are missing: "
            + ", ".join(missing_required)
            + "\nInstall with:\n"
            + suggest_r_install(missing_required)
        )

    runner = RScriptRunner(scripts_dir=R_SCRIPTS_DIR, timeout=2400)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_monocle3_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_sub = tmpdir / "output"
        output_sub.mkdir(parents=True, exist_ok=True)
        save_h5ad(adata, input_h5ad, compression=None)

        r_cluster_key = cluster_key
        r_use_rep = use_rep if use_rep else "X_umap"
        r_root_cluster = root_cluster or "auto"
        r_root_pr_nodes = "auto"

        runner.run_script(
            "sc_monocle3_r.R",
            args=[
                str(input_h5ad),
                str(output_sub),
                r_cluster_key,
                r_use_rep,
                r_root_cluster,
                r_root_pr_nodes,
            ],
            expected_outputs=["monocle3_pseudotime.csv"],
            output_dir=output_sub,
        )

        pt_csv = output_sub / "monocle3_pseudotime.csv"
        traj_csv = output_sub / "monocle3_trajectory.csv"

        pt_df = pd.read_csv(pt_csv) if pt_csv.exists() else pd.DataFrame()
        traj_df = pd.read_csv(traj_csv) if traj_csv.exists() else pd.DataFrame()

    n_with_pt = 0
    if not pt_df.empty and "monocle3_pseudotime" in pt_df.columns:
        pt_df["cell_id"] = pt_df["cell_id"].astype(str)
        pt_df = pt_df.drop_duplicates(subset="cell_id", keep="first")
        pt_df_indexed = pt_df.set_index("cell_id").reindex(adata.obs_names.astype(str))

        adata.obs["monocle3_pseudotime"] = pd.to_numeric(
            pt_df_indexed["monocle3_pseudotime"], errors="coerce"
        ).to_numpy()
        if "monocle3_cluster" in pt_df_indexed.columns:
            adata.obs["monocle3_cluster"] = (
                pt_df_indexed["monocle3_cluster"].astype(str).to_numpy()
            )
        if "monocle3_partition" in pt_df_indexed.columns:
            adata.obs["monocle3_partition"] = (
                pt_df_indexed["monocle3_partition"].astype(str).to_numpy()
            )
        n_with_pt = int(adata.obs["monocle3_pseudotime"].notna().sum())
    else:
        warnings.warn("Monocle3 pseudotime CSV was empty or missing expected columns")
        adata.obs["monocle3_pseudotime"] = np.nan

    if not traj_df.empty:
        adata.uns["monocle3_trajectory"] = traj_df.to_dict(orient="list")

    summary = {
        "backend": "monocle3_r",
        "pseudotime_key": "monocle3_pseudotime",
        "root_cell": None,
        "root_cell_name": None,
        "n_cells_with_pseudotime": n_with_pt,
    }
    return adata, summary, traj_df


def _render_figures(
    adata,
    *,
    output_dir: Path,
    method: str,
    cluster_key: str,
    use_rep: str,
    display_embedding: str,
    pseudotime_key: str,
    trajectory_genes: pd.DataFrame,
    root_cell_name: str | None,
    fate_summary_df: pd.DataFrame,
    curves_df: pd.DataFrame | None,
) -> list[str]:
    figures: list[str] = []
    figure_path = plot_pseudotime_embedding(
        adata,
        output_dir,
        obsm_key=display_embedding,
        pseudotime_key=pseudotime_key,
        title=f"{method.replace('_r', '').upper()} pseudotime",
        root_cell_name=root_cell_name,
    )
    if figure_path:
        figures.append(str(figure_path))

    distribution_df = pd.DataFrame(
        {
            cluster_key: adata.obs[cluster_key].astype(str).to_numpy(),
            pseudotime_key: pd.to_numeric(adata.obs[pseudotime_key], errors="coerce").to_numpy(),
        }
    )
    figure_path = plot_pseudotime_distribution_by_group(
        distribution_df,
        output_dir,
        group_col=cluster_key,
        pseudotime_col=pseudotime_key,
    )
    if figure_path:
        figures.append(str(figure_path))

    figure_path = sc_traj.plot_trajectory_gene_heatmap(
        adata,
        trajectory_genes,
        output_dir=output_dir / "figures",
        pseudotime_key=pseudotime_key,
        n_genes=min(30, len(trajectory_genes)),
        title="Trajectory-associated gene heatmap",
    )
    if figure_path:
        figures.append(str(figure_path))

    figure_path = plot_trajectory_gene_trends(
        adata,
        trajectory_genes,
        output_dir,
        pseudotime_key=pseudotime_key,
    )
    if figure_path:
        figures.append(str(figure_path))

    if method == "dpt":
        figure_path = sc_traj.plot_paga_graph(
            adata,
            output_dir=output_dir / "figures",
            cluster_key=cluster_key,
            title="PAGA connectivity graph",
        )
        if figure_path:
            figures.append(str(figure_path))
        figures.extend(sc_traj.plot_diffusion_components(adata, output_dir=output_dir / "figures", n_components=3))

    if not fate_summary_df.empty:
        figure_path = plot_fate_probability_heatmap(fate_summary_df, output_dir)
        if figure_path:
            figures.append(str(figure_path))

    if curves_df is not None and not curves_df.empty:
        if method == "monocle3_r" and {"x_start", "y_start", "x_end", "y_end"}.issubset(curves_df.columns):
            # Monocle3 trajectory edges overlay on pseudotime embedding
            try:
                import matplotlib.pyplot as plt

                fig_dir = output_dir / "figures"
                fig_dir.mkdir(parents=True, exist_ok=True)
                emb_key = display_embedding
                if emb_key in adata.obsm:
                    coords = adata.obsm[emb_key][:, :2]
                    pt_vals = pd.to_numeric(adata.obs[pseudotime_key], errors="coerce").to_numpy()
                    fig, ax = plt.subplots(1, 1, figsize=(8, 6))
                    sc_plot = ax.scatter(
                        coords[:, 0], coords[:, 1], c=pt_vals, cmap="viridis",
                        s=5, alpha=0.6, edgecolors="none",
                    )
                    for _, row in curves_df.iterrows():
                        ax.plot(
                            [row["x_start"], row["x_end"]],
                            [row["y_start"], row["y_end"]],
                            color="black", linewidth=1.5, alpha=0.8,
                        )
                    plt.colorbar(sc_plot, ax=ax, label="Monocle3 pseudotime")
                    ax.set_title("Monocle3 trajectory graph")
                    ax.set_xlabel(f"{emb_key.replace('X_', '').upper()} 1")
                    ax.set_ylabel(f"{emb_key.replace('X_', '').upper()} 2")
                    traj_path = fig_dir / "monocle3_trajectory_graph.png"
                    fig.savefig(traj_path, dpi=150, bbox_inches="tight")
                    plt.close(fig)
                    figures.append(str(traj_path))
            except Exception as exc:
                logger.warning("Failed to plot monocle3 trajectory overlay: %s", exc)
        else:
            points_df = _build_pseudotime_points_table(adata, pseudotime_key=pseudotime_key, cluster_key=cluster_key, display_key=use_rep)
            figure_path = plot_slingshot_curves(
                points_df,
                curves_df,
                output_dir,
                basis_name=use_rep.replace("X_", "").upper(),
                group_col=cluster_key,
            )
            if figure_path:
                figures.append(str(figure_path))

    return figures


def _summary_table(summary: dict) -> pd.DataFrame:
    rows = []
    for key, value in summary.items():
        if isinstance(value, (dict, list)):
            continue
        rows.append({"metric": key, "value": value})
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Single-Cell Pseudotime")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="dpt", choices=list(METHOD_REGISTRY.keys()))
    parser.add_argument("--cluster-key", default="leiden")
    parser.add_argument("--use-rep", default=None)
    parser.add_argument("--root-cluster", default=None)
    parser.add_argument("--root-cell", default=None, help="Root cell obs_name or integer index")
    parser.add_argument("--end-clusters", default=None, help="Comma-separated terminal clusters for methods that support them")
    parser.add_argument("--n-neighbors", type=int, default=15)
    parser.add_argument("--n-pcs", type=int, default=50)
    parser.add_argument("--n-dcs", type=int, default=10)
    parser.add_argument("--n-genes", type=int, default=50)
    parser.add_argument("--corr-method", default="pearson", choices=["pearson", "spearman"])
    parser.add_argument("--palantir-knn", type=int, default=30)
    parser.add_argument("--palantir-n-components", type=int, default=10)
    parser.add_argument("--palantir-num-waypoints", type=int, default=1200)
    parser.add_argument("--palantir-max-iterations", type=int, default=25)
    parser.add_argument("--palantir-seed", type=int, default=20)
    parser.add_argument("--via-knn", type=int, default=30)
    parser.add_argument("--via-seed", type=int, default=20)
    parser.add_argument("--cellrank-n-states", type=int, default=3)
    parser.add_argument("--cellrank-schur-components", type=int, default=20)
    parser.add_argument("--cellrank-frac-to-keep", type=float, default=0.3)
    parser.add_argument("--cellrank-use-velocity", action="store_true")
    parser.add_argument(
        "--r-enhanced", action="store_true",
        help="Generate R Enhanced ggplot2 figures in addition to standard Python plots."
    )
    args = parser.parse_args()

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.positive("n_neighbors", args.n_neighbors, min_val=2)
    v.positive("n_pcs", args.n_pcs, min_val=1)
    v.positive("n_dcs", args.n_dcs, min_val=1)
    v.positive("n_genes", args.n_genes, min_val=1)
    v.positive("palantir_knn", args.palantir_knn, min_val=2)
    v.positive("palantir_num_waypoints", args.palantir_num_waypoints, min_val=1)
    v.positive("via_knn", args.via_knn, min_val=2)
    v.check()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata = get_demo_data()
        input_file = None
        # Auto-select root cluster for demo mode if not explicitly provided
        if args.root_cluster is None and args.root_cell is None:
            cluster_col = args.cluster_key
            if cluster_col in adata.obs.columns:
                args.root_cluster = str(adata.obs[cluster_col].value_counts().idxmax())
                logger.info("[demo] Auto-selected root cluster: %s", args.root_cluster)
    else:
        if not args.input_path:
            parser.error("--input is required unless --demo is used")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        adata = _prepare_input_adata(input_path)
        input_file = str(input_path)
    logger.info("Input object: %s cells x %s genes", adata.n_obs, adata.n_vars)

    if args.method == "via":
        _prepare_via_runtime()
    method = validate_method_choice(args.method, METHOD_REGISTRY)
    apply_preflight(
        preflight_sc_pseudotime(
            adata,
            method=method,
            cluster_key=args.cluster_key,
            use_rep=args.use_rep,
            root_cluster=args.root_cluster,
            root_cell=args.root_cell,
            source_path=input_file,
        ),
        logger,
        demo_mode=args.demo,
    )

    if args.cluster_key not in adata.obs.columns:
        raise ValueError(f"`{args.cluster_key}` was not found in adata.obs.")

    x_kind = get_matrix_contract(adata).get("X") or infer_x_matrix_kind(adata)
    if x_kind != "normalized_expression":
        raise ValueError("`sc-pseudotime` expects normalized expression. Run `sc-preprocessing` first.")

    use_rep = _resolve_use_rep(adata, args.use_rep)
    display_embedding = _resolve_display_embedding(adata, use_rep)
    root_cell_idx = _resolve_root_cell(adata, args.root_cell)
    end_clusters = _parse_end_clusters(args.end_clusters)
    logger.info("Running %s with cluster_key=%s, use_rep=%s, display_embedding=%s", method, args.cluster_key, use_rep, display_embedding)

    params = dict(METHOD_PARAM_DEFAULTS[method])
    params.update(
        {
            "method": method,
            "cluster_key": args.cluster_key,
            "use_rep": use_rep,
            "root_cluster": args.root_cluster,
            "root_cell": args.root_cell,
            "end_clusters": args.end_clusters,
            "n_neighbors": args.n_neighbors,
            "n_pcs": args.n_pcs,
            "n_dcs": args.n_dcs,
            "n_genes": args.n_genes,
            "corr_method": args.corr_method,
            "palantir_knn": args.palantir_knn,
            "palantir_n_components": args.palantir_n_components,
            "palantir_num_waypoints": args.palantir_num_waypoints,
            "palantir_max_iterations": args.palantir_max_iterations,
            "palantir_seed": args.palantir_seed,
            "via_knn": args.via_knn,
            "via_seed": args.via_seed,
            "cellrank_n_states": args.cellrank_n_states,
            "cellrank_schur_components": args.cellrank_schur_components,
            "cellrank_frac_to_keep": args.cellrank_frac_to_keep,
            "cellrank_use_velocity": bool(args.cellrank_use_velocity),
        }
    )

    working = adata.copy()
    curves_df = pd.DataFrame()
    method_summary: dict[str, object]
    if method == "dpt":
        logger.info("Starting DPT workflow...")
        working, method_summary = _run_dpt(
            working,
            use_rep=use_rep,
            cluster_key=args.cluster_key,
            root_cluster=args.root_cluster,
            root_cell_idx=root_cell_idx,
            n_neighbors=args.n_neighbors,
            n_pcs=args.n_pcs,
            n_dcs=args.n_dcs,
        )
    elif method == "palantir":
        logger.info("Starting Palantir workflow...")
        working, method_summary = _run_palantir(
            working,
            use_rep=use_rep,
            cluster_key=args.cluster_key,
            root_cluster=args.root_cluster,
            root_cell_idx=root_cell_idx,
            palantir_knn=args.palantir_knn,
            palantir_n_components=args.palantir_n_components,
            palantir_num_waypoints=args.palantir_num_waypoints,
            palantir_max_iterations=args.palantir_max_iterations,
            palantir_seed=args.palantir_seed,
        )
    elif method == "via":
        logger.info("Starting VIA workflow...")
        working, method_summary = _run_via(
            working,
            use_rep=use_rep,
            cluster_key=args.cluster_key,
            root_cluster=args.root_cluster,
            root_cell_idx=root_cell_idx,
            via_knn=args.via_knn,
            via_seed=args.via_seed,
            n_dcs=args.n_dcs,
        )
    elif method == "cellrank":
        logger.info("Starting CellRank workflow...")
        working, method_summary = _run_cellrank(
            working,
            use_rep=use_rep,
            cluster_key=args.cluster_key,
            root_cluster=args.root_cluster,
            root_cell_idx=root_cell_idx,
            n_neighbors=args.n_neighbors,
            n_pcs=args.n_pcs,
            n_dcs=args.n_dcs,
            cellrank_n_states=args.cellrank_n_states,
            cellrank_schur_components=args.cellrank_schur_components,
            cellrank_frac_to_keep=args.cellrank_frac_to_keep,
            cellrank_use_velocity=bool(args.cellrank_use_velocity),
        )
    elif method == "monocle3_r":
        logger.info("Starting Monocle3 R workflow...")
        working, method_summary, curves_df = _run_monocle3_r(
            working,
            use_rep=use_rep,
            cluster_key=args.cluster_key,
            root_cluster=args.root_cluster,
        )
    else:
        logger.info("Starting Slingshot R workflow...")
        working, method_summary, curves_df = _run_slingshot_r(
            working,
            use_rep=use_rep,
            cluster_key=args.cluster_key,
            root_cluster=args.root_cluster,
            end_clusters=end_clusters,
        )

    pseudotime_key = str(method_summary["pseudotime_key"])
    working.obs["pseudotime"] = pd.to_numeric(working.obs[pseudotime_key], errors="coerce")
    working.uns["omicsclaw_pseudotime"] = {
        "method": method,
        "pseudotime_key": pseudotime_key,
        "display_embedding": display_embedding,
        "use_rep": use_rep,
        "cluster_key": args.cluster_key,
        "root_cluster": args.root_cluster,
        "root_cell": method_summary.get("root_cell"),
        "root_cell_name": method_summary.get("root_cell_name"),
    }

    trajectory_genes = sc_traj.find_trajectory_genes(
        working,
        pseudotime_key=pseudotime_key,
        n_genes=args.n_genes,
        method=args.corr_method,
    )
    logger.info("Trajectory gene ranking complete: %s genes", len(trajectory_genes))

    fate_summary_df = pd.DataFrame()
    fate_obsm_key = method_summary.get("fate_obsm_key")
    if isinstance(fate_obsm_key, str):
        fate_summary_df = _build_fate_summary_table(working, cluster_key=args.cluster_key, obsm_key=fate_obsm_key)

    figures = _render_figures(
        working,
        output_dir=output_dir,
        method=method,
        cluster_key=args.cluster_key,
        use_rep=use_rep,
        display_embedding=display_embedding,
        pseudotime_key=pseudotime_key,
        trajectory_genes=trajectory_genes,
        root_cell_name=method_summary.get("root_cell_name"),
        fate_summary_df=fate_summary_df,
        curves_df=curves_df,
    )
    _write_figure_manifest(output_dir, figures)
    logger.info("Rendered %s trajectory figures", len(figures))

    summary = {
        "method": method,
        "backend": method_summary.get("backend", method),
        "cluster_key": args.cluster_key,
        "use_rep": use_rep,
        "display_embedding": display_embedding,
        "root_cluster": args.root_cluster,
        "root_cell": method_summary.get("root_cell"),
        "root_cell_name": method_summary.get("root_cell_name"),
        "n_cells": int(working.n_obs),
        "n_clusters": int(working.obs[args.cluster_key].astype(str).nunique()),
        "n_trajectory_genes": int(len(trajectory_genes)),
        "pseudotime_min": float(np.nanmin(pd.to_numeric(working.obs[pseudotime_key], errors="coerce"))),
        "pseudotime_max": float(np.nanmax(pd.to_numeric(working.obs[pseudotime_key], errors="coerce"))),
        **{key: value for key, value in method_summary.items() if key not in {"pseudotime_key", "root_cell", "root_cell_name", "backend", "fate_obsm_key"}},
    }

    points_df = _build_pseudotime_points_table(working, pseudotime_key=pseudotime_key, cluster_key=args.cluster_key, display_key=display_embedding)
    summary_df = _summary_table(summary)
    table_files = _write_tables(
        output_dir,
        points_df=points_df,
        trajectory_genes=trajectory_genes,
        summary_df=summary_df,
        fate_df=fate_summary_df,
        curves_df=curves_df,
    )
    figure_data_files = _write_figure_data(
        output_dir,
        points_df=points_df,
        trajectory_genes=trajectory_genes,
        summary_df=summary_df,
        fate_df=fate_summary_df,
        curves_df=curves_df,
    )

    # Write gene_expression.csv for R DynamicPlot (top trajectory genes x all cells)
    try:
        import scipy.sparse as sp

        top_genes_list = trajectory_genes.head(10)["gene"].tolist()
        if top_genes_list and hasattr(working, "X"):
            gene_idx = [i for i, g in enumerate(working.var_names) if g in top_genes_list]
            if gene_idx:
                X_sub = working.X[:, gene_idx]
                if sp.issparse(X_sub):
                    X_sub = X_sub.toarray()
                gene_names = [working.var_names[i] for i in gene_idx]
                gene_expr_rows = []
                for ci, cell_id in enumerate(working.obs_names):
                    for gi, gene_name in enumerate(gene_names):
                        gene_expr_rows.append(
                            {"cell_id": str(cell_id), "gene": gene_name, "expression": float(X_sub[ci, gi])}
                        )
                gene_expr_df = pd.DataFrame(gene_expr_rows)
                gene_expr_path = output_dir / "figure_data" / "gene_expression.csv"
                gene_expr_df.to_csv(gene_expr_path, index=False)
                figure_data_files["gene_expression"] = "gene_expression.csv"
    except Exception as _exc:
        logger.warning("Could not write gene_expression.csv for R DynamicPlot: %s", _exc)

    propagate_singlecell_contracts(
        adata,
        working,
        producer_skill=SKILL_NAME,
        x_kind="normalized_expression",
        raw_kind=get_matrix_contract(working).get("raw"),
        primary_cluster_key=args.cluster_key,
    )
    store_analysis_metadata(working, SKILL_NAME, method, params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(working, output_h5ad)
    logger.info("Saved processed object to %s", output_h5ad)

    _write_report(output_dir, summary=summary, params=params, input_file=input_file, top_genes=trajectory_genes)
    _write_reproducibility(output_dir, params=params, input_file=input_file, demo_mode=bool(args.demo))

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "params": params,
        "output_files": {
            "processed_h5ad": "processed.h5ad",
            "report": "report.md",
            "tables": table_files,
            "figure_data": figure_data_files,
            "figures": [Path(path).name for path in figures],
        },
        "visualization": {
            "display_embedding": display_embedding,
            "pseudotime_key": pseudotime_key,
        },
    }
    result_data["next_steps"] = [
        {"skill": "sc-velocity", "reason": "RNA velocity analysis for dynamic trajectories", "priority": "optional"},
        {"skill": "sc-gene-programs", "reason": "Discover gene programs along the trajectory", "priority": "optional"},
    ]
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    write_replot_hint(output_dir, SKILL_NAME, R_ENHANCED_PLOTS)
    result_payload = load_result_json(output_dir) or {"skill": SKILL_NAME, "summary": summary, "data": result_data}
    write_standard_run_artifacts(output_dir, result_payload, summary)

    # R Enhanced figures (only when --r-enhanced flag is set)
    r_enhanced_figures = _render_r_enhanced(
        output_dir=output_dir,
        figure_data_dir=output_dir / "figure_data",
        r_enhanced=args.r_enhanced,
    )
    if r_enhanced_figures:
        result_data["r_enhanced_figures"] = r_enhanced_figures

    print(f"\n{'=' * 60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'=' * 60}")
    print(f"  Method: {method}")
    print(f"  Graph representation: {use_rep}")
    print(f"  Display embedding: {display_embedding}")
    print(f"  Trajectory genes: {len(trajectory_genes)}")
    print(f"  Output: {output_dir}")

    # --- Next-step guidance ---
    print()
    print(">> Next steps:")
    print(f"  - sc-velocity:      python omicsclaw.py run sc-velocity --input {output_dir}/processed.h5ad --output <dir>")
    print(f"  - sc-gene-programs: python omicsclaw.py run sc-gene-programs --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()
