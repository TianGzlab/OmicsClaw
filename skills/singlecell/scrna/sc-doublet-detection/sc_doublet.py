#!/usr/bin/env python3
"""Single-Cell Doublet Detection - Scrublet, DoubletFinder, scDblFinder."""

from __future__ import annotations

import argparse
import logging
import tempfile
import sys
from pathlib import Path
import h5py

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scanpy as sc

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    load_result_json,
    write_output_readme,
    write_result_json,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import store_analysis_metadata
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_doublet_detection
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_script_runner import RScriptRunner

from skills.singlecell._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-doublet-detection"
SKILL_VERSION = "0.4.0"


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
            description="Doublet detection and scoring for single-cell RNA-seq data.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "scrublet"),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Doublet detection and scoring for single-cell RNA-seq data.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "scrublet"),
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md: %s", exc)

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "scrublet": MethodConfig(
        name="scrublet",
        description="Scrublet — computational doublet detection",
        dependencies=("scrublet",),
    ),
    "doubletfinder": MethodConfig(
        name="doubletfinder",
        description="DoubletFinder — k-NN based doublet detection (R)",
        dependencies=(),
    ),
    "scdblfinder": MethodConfig(
        name="scdblfinder",
        description="scDblFinder — fast doublet detection (R/Bioconductor)",
        dependencies=(),
    ),
}


def _matrix_looks_count_like(matrix) -> bool:
    sample = matrix
    if hasattr(sample, "toarray"):
        sample = sample[: min(200, sample.shape[0]), : min(200, sample.shape[1])].toarray()
    else:
        sample = np.asarray(sample[: min(200, sample.shape[0]), : min(200, sample.shape[1])])
    if sample.size == 0:
        return True
    if np.nanmin(sample) < 0:
        return False
    frac_integer = float(np.mean(np.isclose(sample, np.round(sample), atol=1e-6)))
    return frac_integer > 0.98


def _get_count_like_matrix(adata):
    if "counts" in adata.layers:
        return adata.layers["counts"], "layers.counts"
    if _matrix_looks_count_like(adata.X):
        return adata.X, "adata.X"
    raise ValueError("Doublet detection requires raw count-like input; provide adata.layers['counts'] or count-like adata.X")


def _build_count_like_export_adata(adata):
    matrix, source = _get_count_like_matrix(adata)
    export = sc.AnnData(X=matrix.copy(), obs=adata.obs.copy(), var=adata.var.copy())
    export.obs_names = adata.obs_names.copy()
    export.var_names = adata.var_names.copy()
    return export, source


def _run_r_doublet_script(adata, *, script_name: str, output_csv: str, expected_doublet_rate: float, required_packages: list[str]):
    validate_r_environment(required_r_packages=required_packages)
    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)
    export, source = _build_count_like_export_adata(adata)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_doublet_r_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        export.write_h5ad(input_h5ad)
        with h5py.File(input_h5ad, "a") as handle:
            if "layers" in handle and len(handle["layers"].keys()) == 0:
                del handle["layers"]
        runner.run_script(
            script_name,
            args=[str(input_h5ad), str(output_dir), str(expected_doublet_rate)],
            expected_outputs=[output_csv],
            output_dir=output_dir,
        )
        df = pd.read_csv(output_dir / output_csv, index_col=0)
    return df, source


def run_doubletfinder(adata, expected_doublet_rate=0.06):
    df, _ = _run_r_doublet_script(
        adata,
        script_name="sc_doubletfinder.R",
        output_csv="doubletfinder_results.csv",
        expected_doublet_rate=expected_doublet_rate,
        required_packages=["Seurat", "DoubletFinder", "SingleCellExperiment", "zellkonverter"],
    )
    return df


def run_scdblfinder(adata, expected_doublet_rate=0.06):
    df, _ = _run_r_doublet_script(
        adata,
        script_name="sc_scdblfinder.R",
        output_csv="scdblfinder_results.csv",
        expected_doublet_rate=expected_doublet_rate,
        required_packages=["scDblFinder", "SingleCellExperiment", "zellkonverter"],
    )
    return df


def detect_doublets_scrublet(adata, expected_doublet_rate=0.06, threshold=None):
    import scrublet as scr

    counts_matrix, source = _get_count_like_matrix(adata)
    logger.info("Running Scrublet (expected_rate=%s, source=%s)", expected_doublet_rate, source)
    scrub = scr.Scrublet(counts_matrix, expected_doublet_rate=expected_doublet_rate)
    doublet_scores, predicted_doublets = scrub.scrub_doublets(
        min_counts=2, min_cells=3, min_gene_variability_pctl=85, n_prin_comps=30
    )
    adata.obs["doublet_score"] = doublet_scores
    adata.obs["predicted_doublet"] = predicted_doublets
    adata.obs["doublet_classification"] = np.where(predicted_doublets, "Doublet", "Singlet")

    if threshold is not None:
        adata.obs["predicted_doublet"] = adata.obs["doublet_score"] > threshold
        adata.obs["doublet_classification"] = np.where(adata.obs["predicted_doublet"], "Doublet", "Singlet")

    n_doublets = int(adata.obs["predicted_doublet"].sum())
    return {
        "method": "scrublet",
        "n_doublets": n_doublets,
        "doublet_rate": float(n_doublets / adata.n_obs),
        "expected_rate": expected_doublet_rate,
        "expression_source": source,
    }


def detect_doublets_doubletfinder(adata, expected_doublet_rate=0.06):
    try:
        df = run_doubletfinder(adata, expected_doublet_rate=expected_doublet_rate)
        executed_method = "doubletfinder"
        fallback_reason = None
    except Exception as exc:
        logger.warning("DoubletFinder runtime failed (%s). Falling back to scDblFinder.", exc)
        df = run_scdblfinder(adata, expected_doublet_rate=expected_doublet_rate)
        executed_method = "scdblfinder"
        fallback_reason = f"DoubletFinder runtime failed and wrapper fell back to scDblFinder: {exc}"
    df = df.reindex(adata.obs_names)
    adata.obs["doublet_score"] = pd.to_numeric(df["doublet_score"], errors="coerce").values
    adata.obs["doublet_classification"] = df["classification"].fillna("Singlet").astype(str).values
    adata.obs["predicted_doublet"] = df["predicted_doublet"].fillna(False).astype(bool).values
    n_doublets = int(adata.obs["predicted_doublet"].sum())
    return {
        "method": executed_method,
        "requested_method": "doubletfinder",
        "executed_method": executed_method,
        "fallback_used": fallback_reason is not None,
        "fallback_reason": fallback_reason,
        "n_doublets": n_doublets,
        "doublet_rate": float(n_doublets / adata.n_obs),
        "expected_rate": expected_doublet_rate,
    }


def detect_doublets_scdblfinder(adata, expected_doublet_rate=0.06):
    df = run_scdblfinder(adata, expected_doublet_rate=expected_doublet_rate)
    df = df.reindex(adata.obs_names)
    adata.obs["doublet_score"] = pd.to_numeric(df["doublet_score"], errors="coerce").values
    adata.obs["doublet_classification"] = df["classification"].fillna("singlet").astype(str).values
    adata.obs["predicted_doublet"] = df["predicted_doublet"].fillna(False).astype(bool).values
    n_doublets = int(adata.obs["predicted_doublet"].sum())
    return {
        "method": "scdblfinder",
        "n_doublets": n_doublets,
        "doublet_rate": float(n_doublets / adata.n_obs),
        "expected_rate": expected_doublet_rate,
    }


_METHOD_DISPATCH = {
    "scrublet": lambda adata, args: detect_doublets_scrublet(adata, args.expected_doublet_rate, args.threshold),
    "doubletfinder": lambda adata, args: detect_doublets_doubletfinder(adata, args.expected_doublet_rate),
    "scdblfinder": lambda adata, args: detect_doublets_scdblfinder(adata, args.expected_doublet_rate),
}


def generate_figures(adata, output_dir: Path) -> list[str]:
    figures = []
    try:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(adata.obs["doublet_score"].dropna(), bins=50, edgecolor="black")
        ax.set_xlabel("Doublet Score")
        ax.set_ylabel("Count")
        ax.set_title("Doublet Score Distribution")
        p = save_figure(fig, output_dir, "doublet_histogram.png")
        figures.append(str(p))
        plt.close()
    except Exception as exc:
        logger.warning("Doublet histogram failed: %s", exc)

    if "X_umap" not in adata.obsm:
        try:
            sc.pp.neighbors(adata)
            sc.tl.umap(adata)
        except Exception as exc:
            logger.warning("UMAP computation failed: %s", exc)

    if "X_umap" in adata.obsm:
        try:
            sc.pl.umap(adata, color="predicted_doublet", show=False)
            p = save_figure(plt.gcf(), output_dir, "umap_doublets.png")
            figures.append(str(p))
            plt.close()
        except Exception as exc:
            logger.warning("UMAP doublet plot failed: %s", exc)
    return figures


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    requested_method = str(summary.get("requested_method", params.get("method", summary["method"])))
    executed_method = str(summary.get("executed_method", summary["method"]))
    header = generate_report_header(
        title="Doublet Detection Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": executed_method,
            "Doublets detected": str(summary["n_doublets"]),
            "Doublet rate": f"{summary['doublet_rate']*100:.2f}%",
        },
    )
    body_lines = [
        "## Summary\n",
        f"- **Requested method**: {requested_method}",
        f"- **Executed method**: {executed_method}",
        f"- **Total cells**: {summary.get('n_cells', 'N/A')}",
        f"- **Doublets detected**: {summary['n_doublets']}",
        f"- **Doublet rate**: {summary['doublet_rate']*100:.2f}%",
        f"- **Expected rate**: {summary.get('expected_rate', 0)*100:.2f}%",
        "",
        "## Parameters\n",
    ]
    if summary.get("fallback_reason"):
        body_lines.insert(7, f"- **Fallback note**: {summary['fallback_reason']}")
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")
    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    pd.DataFrame([
        {"metric": "doublets_detected", "value": summary["n_doublets"]},
        {"metric": "doublet_rate", "value": summary["doublet_rate"]},
    ]).to_csv(tables_dir / "summary.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python sc_doublet.py --input <input.h5ad> --output {output_dir}"
    cmd += f" --method {params['method']}"
    cmd += f" --expected-doublet-rate {params['expected_doublet_rate']}"
    if params.get("threshold") is not None:
        cmd += f" --threshold {params['threshold']}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    _write_repro_requirements(
        repro_dir,
        ["scanpy", "anndata", "numpy", "pandas", "matplotlib"],
    )


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Doublet Detection")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default="scrublet")
    parser.add_argument("--expected-doublet-rate", type=float, default=0.06)
    parser.add_argument("--threshold", type=float, default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata = sc_io.load_repo_demo_data("pbmc3k_raw")[0]
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        sc_io.maybe_warn_standardize_first(adata, source_path=args.input_path, skill_name=SKILL_NAME)
        input_file = args.input_path

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback="scrublet")
    apply_preflight(
        preflight_sc_doublet_detection(
            adata,
            method=method,
            expected_doublet_rate=args.expected_doublet_rate,
            threshold=args.threshold,
            source_path=input_file,
        ),
        logger,
    )
    summary = _METHOD_DISPATCH[method](adata, args)
    summary.setdefault("requested_method", method)
    summary.setdefault("executed_method", summary.get("method", method))
    summary.setdefault("fallback_used", summary["requested_method"] != summary["executed_method"])
    summary["n_cells"] = int(adata.n_obs)

    params = {
        "method": method,
        "requested_method": summary["requested_method"],
        "executed_method": summary["executed_method"],
        "expected_doublet_rate": args.expected_doublet_rate,
    }
    if args.threshold is not None:
        params["threshold"] = args.threshold
    if summary.get("fallback_reason"):
        params["fallback_reason"] = summary["fallback_reason"]

    generate_figures(adata, output_dir)
    write_report(output_dir, summary, input_file, params)

    store_analysis_metadata(adata, SKILL_NAME, summary["executed_method"], params)
    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info("Saved to %s", output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "requested_method": summary["requested_method"],
        "executed_method": summary["executed_method"],
        "fallback_used": bool(summary.get("fallback_used")),
        "fallback_reason": summary.get("fallback_reason"),
        "params": params,
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }
    write_standard_run_artifacts(output_dir, result_payload, summary)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"Doublet detection complete: {summary['n_doublets']} doublets "
        f"({summary['doublet_rate']*100:.1f}%), requested={summary['requested_method']}, "
        f"executed={summary['executed_method']}"
    )


if __name__ == "__main__":
    main()
