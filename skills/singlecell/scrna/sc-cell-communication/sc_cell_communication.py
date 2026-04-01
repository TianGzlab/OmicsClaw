#!/usr/bin/env python3
"""Single-cell cell-cell communication analysis with builtin, LIANA, and CellChat backends."""

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
from skills.singlecell._lib.adata_utils import store_analysis_metadata
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_script_runner import RScriptRunner

from skills.singlecell._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-cell-communication"
SKILL_VERSION = "0.1.0"

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
    "cellchat_r": MethodConfig(
        name="cellchat_r",
        description="CellChat communication inference (R)",
        dependencies=(),
    ),
}

DEFAULT_METHOD = "builtin"


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
            preferred_method=summary.get("method", DEFAULT_METHOD),
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
            preferred_method=summary.get("method", DEFAULT_METHOD),
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
                        "pvalue": 1.0,
                        "pathway": "builtin",
                    }
                )
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=["ligand", "receptor", "source", "target", "score", "pvalue", "pathway"])
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


def _run_cellchat_r(adata, *, cell_type_key: str, species: str) -> pd.DataFrame:
    df = run_cellchat(adata, cell_type_key=cell_type_key, species=species)
    if df.empty:
        return pd.DataFrame(columns=["ligand", "receptor", "source", "target", "score", "pvalue", "pathway"])
    if "pathway" not in df.columns:
        df["pathway"] = "CellChat"
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def run_communication(adata, *, method: str, cell_type_key: str, species: str) -> dict:
    if cell_type_key not in adata.obs.columns:
        raise ValueError(f"Cell type key '{cell_type_key}' not in adata.obs: {list(adata.obs.columns)}")

    dispatch = {
        "builtin": lambda: _run_builtin(adata, cell_type_key=cell_type_key, species=species),
        "liana": lambda: _run_liana(adata, cell_type_key=cell_type_key, species=species),
        "cellchat_r": lambda: _run_cellchat_r(adata, cell_type_key=cell_type_key, species=species),
    }
    lr_df = dispatch[method]()
    sig_df = lr_df[lr_df["pvalue"] < 0.05] if not lr_df.empty else lr_df
    return {
        "method": method,
        "cell_type_key": cell_type_key,
        "species": species,
        "n_cells": int(adata.n_obs),
        "n_cell_types": int(adata.obs[cell_type_key].astype(str).nunique()),
        "n_interactions_tested": int(len(lr_df)),
        "n_significant": int(len(sig_df)),
        "lr_df": lr_df,
        "top_df": lr_df.head(50) if not lr_df.empty else lr_df,
    }


def generate_figures(output_dir: Path, summary: dict) -> list[str]:
    figures = []
    top_df = summary.get("top_df", pd.DataFrame())
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
            "Method": summary["method"],
            "Cell type key": summary["cell_type_key"],
        },
    )

    top_df = summary.get("top_df", pd.DataFrame())
    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Cell types**: {summary['n_cell_types']}",
        f"- **Method**: {summary['method']}",
        f"- **Interactions tested**: {summary['n_interactions_tested']}",
        f"- **Significant (p < 0.05)**: {summary['n_significant']}",
    ]
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

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = (
        f"python sc_cell_communication.py --input <input.h5ad> --output {output_dir}"
        f" --method {params.get('method', 'builtin')}"
        f" --cell-type-key {params.get('cell_type_key', 'cell_type')}"
        f" --species {params.get('species', 'human')}"
    )
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    _write_repro_requirements(
        repro_dir,
        ["scanpy", "anndata", "numpy", "pandas", "matplotlib"],
    )


def main():
    parser = argparse.ArgumentParser(description="Single-cell cell-cell communication")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default=DEFAULT_METHOD)
    parser.add_argument("--cell-type-key", default="cell_type")
    parser.add_argument("--species", default="human", choices=["human", "mouse"])
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
        if args.cell_type_key not in adata.obs.columns:
            fallback_key = "louvain" if "louvain" in adata.obs else "leiden"
            adata.obs[args.cell_type_key] = adata.obs[fallback_key].astype(str)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path

    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback=DEFAULT_METHOD)
    summary = run_communication(adata, method=method, cell_type_key=args.cell_type_key, species=args.species)
    params = {"method": method, "cell_type_key": args.cell_type_key, "species": args.species}

    generate_figures(output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {"params": params}
    write_result_json(
        output_dir,
        SKILL_NAME,
        SKILL_VERSION,
        {k: v for k, v in summary.items() if k not in {"lr_df", "top_df"}},
        result_data,
        checksum,
    )
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": {k: v for k, v in summary.items() if k not in {"lr_df", "top_df"}},
        "data": result_data,
    }
    write_standard_run_artifacts(output_dir, result_payload, summary)
    store_analysis_metadata(adata, SKILL_NAME, method, params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Communication analysis complete: {summary['n_interactions_tested']} interactions tested")


if __name__ == "__main__":
    main()
