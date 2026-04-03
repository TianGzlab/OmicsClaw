#!/usr/bin/env python3
"""Single-Cell Differential Expression - Scanpy tests plus R pseudobulk DESeq2."""

from __future__ import annotations

import argparse
import logging
import tempfile
import sys
from pathlib import Path

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
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_de
from skills.singlecell._lib.pseudobulk import aggregate_to_pseudobulk, run_deseq2_analysis
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_script_runner import RScriptRunner

from skills.singlecell._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-de"
SKILL_VERSION = "0.4.0"

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "wilcoxon": MethodConfig(
        name="wilcoxon",
        description="Wilcoxon rank-sum test (scanpy built-in)",
        dependencies=("scanpy",),
    ),
    "t-test": MethodConfig(
        name="t-test",
        description="Welch's t-test (scanpy built-in)",
        dependencies=("scanpy",),
    ),
    "mast": MethodConfig(
        name="mast",
        description="MAST hurdle-model differential expression (R)",
        dependencies=(),
    ),
    "deseq2_r": MethodConfig(
        name="deseq2_r",
        description="DESeq2 pseudobulk differential expression (R)",
        dependencies=(),
    ),
}


def _validate_runtime_dependencies(method: str) -> None:
    if method == "mast":
        validate_r_environment(required_r_packages=["MAST", "SingleCellExperiment", "zellkonverter"])
    elif method == "deseq2_r":
        validate_r_environment(required_r_packages=["DESeq2", "SingleCellExperiment", "zellkonverter"])


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
            description="Differential expression analysis for single-cell RNA-seq data.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "wilcoxon"),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Differential expression analysis for single-cell RNA-seq data.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "wilcoxon"),
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md: %s", exc)


def run_de_scanpy(adata, groupby="leiden", method="wilcoxon", group1=None, group2=None):
    resolved_groupby = groupby
    if resolved_groupby not in adata.obs.columns:
        if resolved_groupby == "leiden" and "louvain" in adata.obs.columns:
            logger.warning("Column 'leiden' not found; falling back to legacy 'louvain' for DE demo compatibility")
            resolved_groupby = "louvain"
        else:
            raise ValueError(f"Column '{groupby}' not found in adata.obs")

    effective_method = method
    use_raw = adata.raw is not None and adata.raw.shape == adata.shape

    if group1 and group2:
        sc.tl.rank_genes_groups(adata, groupby=resolved_groupby, groups=[group1], reference=group2, method=effective_method, pts=True, use_raw=use_raw)
    else:
        sc.tl.rank_genes_groups(adata, groupby=resolved_groupby, method=effective_method, pts=True, use_raw=use_raw)

    result_df = sc.get.rank_genes_groups_df(adata, group=None)
    n_groups = len(result_df["group"].unique()) if "group" in result_df.columns else 0
    return result_df, {
        "method": method,
        "groupby": resolved_groupby,
        "n_groups": n_groups,
        "n_genes_tested": int(adata.n_vars),
    }


def _matrix_looks_count_like(matrix) -> bool:
    sample = matrix
    if hasattr(sample, "shape") and len(sample.shape) == 2:
        sample = sample[: min(sample.shape[0], 256), : min(sample.shape[1], 256)]
    if hasattr(sample, "toarray"):
        sample = sample.toarray()
    arr = np.asarray(sample)
    if arr.size == 0:
        return False
    if np.any(~np.isfinite(arr)) or np.any(arr < 0):
        return False
    return np.allclose(arr, np.round(arr), atol=1e-8)


def _resolve_deseq2_count_source(adata) -> tuple[str | None, str]:
    if "counts" in adata.layers:
        return "counts", "layers.counts"

    matrix_contract = adata.uns.get("omicsclaw_matrix_contract", {}) if isinstance(getattr(adata, "uns", {}), dict) else {}
    if matrix_contract.get("X") == "raw_counts":
        return None, "adata.X"

    if _matrix_looks_count_like(adata.X):
        return None, "adata.X"

    raise ValueError(
        "deseq2_r requires raw counts in adata.layers['counts'] or an unnormalized count-like adata.X matrix"
    )


def run_de_deseq2_r_method(adata, *, condition_key: str, group1: str, group2: str, sample_key: str, celltype_key: str):
    if not group1 or not group2:
        raise ValueError("R pseudobulk DESeq2 requires both --group1 and --group2")
    if sample_key not in adata.obs.columns:
        raise ValueError(f"sample_key '{sample_key}' not found in adata.obs")
    if celltype_key not in adata.obs.columns:
        raise ValueError(f"celltype_key '{celltype_key}' not found in adata.obs")

    layer, expression_source = _resolve_deseq2_count_source(adata)

    pb = aggregate_to_pseudobulk(
        adata,
        sample_key=sample_key,
        celltype_key=celltype_key,
        layer=layer,
    )
    if pb["counts"].empty:
        raise RuntimeError("Pseudobulk aggregation returned no sample-celltype combinations")

    sample_meta = adata.obs[[sample_key, condition_key]].drop_duplicates().rename(columns={sample_key: "sample"})
    de_results = run_deseq2_analysis(
        pb,
        sample_meta,
        formula="~ condition",
        contrast=["condition", group1, group2],
        celltype_key="celltype",
        use_rpy2=True,
    )
    if not de_results:
        raise RuntimeError("R pseudobulk DESeq2 returned no results")

    frames = []
    for cell_type, df in de_results.items():
        tmp = df.copy()
        tmp["cell_type"] = cell_type
        frames.append(tmp)
    full_df = pd.concat(frames, ignore_index=True)
    n_groups = full_df["cell_type"].nunique() if "cell_type" in full_df.columns else 0
    return full_df, {
        "method": "deseq2_r",
        "n_groups": int(n_groups),
        "n_genes_tested": int(full_df["gene"].nunique()) if "gene" in full_df.columns else 0,
        "expression_source": expression_source,
    }


def run_de_mast_method(adata, *, groupby: str, group1: str | None, group2: str | None):
    resolved_groupby = groupby
    if resolved_groupby not in adata.obs.columns:
        if resolved_groupby == "leiden" and "louvain" in adata.obs.columns:
            logger.warning("Column 'leiden' not found; falling back to legacy 'louvain' for MAST demo compatibility")
            resolved_groupby = "louvain"
        else:
            raise ValueError(f"Column '{groupby}' not found in adata.obs")
    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)
    if adata.raw is not None and adata.raw.shape == adata.shape:
        export = sc.AnnData(X=adata.raw.X.copy(), obs=adata.obs.copy(), var=adata.raw.var.copy())
        export.obs_names = adata.obs_names.copy()
        export.var_names = adata.raw.var_names.copy()
        expression_source = "adata.raw"
    else:
        export = sc.AnnData(X=adata.X.copy(), obs=adata.obs.copy(), var=adata.var.copy())
        export.obs_names = adata.obs_names.copy()
        export.var_names = adata.var_names.copy()
        expression_source = "adata.X"
    with tempfile.TemporaryDirectory(prefix="omicsclaw_mast_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        export.write_h5ad(input_h5ad)
        args = [str(input_h5ad), str(output_dir), resolved_groupby]
        if group1:
            args.append(group1)
        if group2:
            args.append(group2)
        runner.run_script(
            "sc_mast_de.R",
            args=args,
            expected_outputs=["mast_results.csv"],
            output_dir=output_dir,
        )
        full_df = pd.read_csv(output_dir / "mast_results.csv")
    n_groups = full_df["group"].nunique() if "group" in full_df.columns else 0
    return full_df, {
        "method": "mast",
        "groupby": resolved_groupby,
        "n_groups": int(n_groups),
        "n_genes_tested": int(full_df["gene"].nunique()) if "gene" in full_df.columns else 0,
        "expression_source": expression_source,
    }


def generate_figures(adata, output_dir: Path, n_top_genes=5) -> list[str]:
    figures = []
    try:
        sc.pl.rank_genes_groups_dotplot(adata, n_genes=n_top_genes, show=False)
        p = save_figure(plt.gcf(), output_dir, "marker_dotplot.png")
        figures.append(str(p))
        plt.close()
    except Exception as exc:
        logger.warning("Dotplot failed: %s", exc)

    try:
        sc.pl.rank_genes_groups(adata, n_genes=n_top_genes, show=False)
        p = save_figure(plt.gcf(), output_dir, "rank_genes_groups.png")
        figures.append(str(p))
        plt.close()
    except Exception as exc:
        logger.warning("Rank genes plot failed: %s", exc)
    return figures


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    requested_method = str(summary.get("requested_method", params.get("method", summary["method"])))
    executed_method = str(summary.get("executed_method", summary["method"]))
    header = generate_report_header(
        title="Differential Expression Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": executed_method,
            "Groups": str(summary["n_groups"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Requested method**: {requested_method}",
        f"- **Executed method**: {executed_method}",
        f"- **Groups compared**: {summary['n_groups']}",
        f"- **Genes tested**: {summary['n_genes_tested']}",
        f"- **Total cells**: {summary.get('n_cells', 'N/A')}",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python sc_de.py --input <input.h5ad> --output {output_dir}"
    cmd += f" --groupby {params['groupby']}"
    cmd += f" --method {params['method']}"
    cmd += f" --n-top-genes {params['n_top_genes']}"
    if params.get("group1") is not None:
        cmd += f" --group1 {params['group1']}"
    if params.get("group2") is not None:
        cmd += f" --group2 {params['group2']}"
    if params.get("sample_key") is not None:
        cmd += f" --sample-key {params['sample_key']}"
    if params.get("celltype_key") is not None:
        cmd += f" --celltype-key {params['celltype_key']}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    _write_repro_requirements(
        repro_dir,
        ["scanpy", "anndata", "numpy", "pandas", "matplotlib"],
    )


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Differential Expression")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--groupby", default="leiden", help="Group column for Scanpy DE or condition column for deseq2_r")
    parser.add_argument("--method", default="wilcoxon", choices=list(METHOD_REGISTRY.keys()))
    parser.add_argument("--n-top-genes", type=int, default=10)
    parser.add_argument("--group1", default=None)
    parser.add_argument("--group2", default=None)
    parser.add_argument("--sample-key", default=None, help="Sample/replicate column for pseudobulk R DE")
    parser.add_argument("--celltype-key", default="cell_type", help="Cell type column for pseudobulk R DE")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        sc_io.maybe_warn_standardize_first(adata, source_path=args.input_path, skill_name=SKILL_NAME)
        input_file = args.input_path

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    method = validate_method_choice(args.method, METHOD_REGISTRY)
    apply_preflight(
        preflight_sc_de(
            adata,
            method=method,
            groupby=args.groupby,
            group1=args.group1,
            group2=args.group2,
            sample_key=args.sample_key,
            celltype_key=args.celltype_key,
            source_path=input_file,
        ),
        logger,
    )
    _validate_runtime_dependencies(method)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    if method == "deseq2_r":
        full_df, summary = run_de_deseq2_r_method(
            adata,
            condition_key=args.groupby,
            group1=args.group1,
            group2=args.group2,
            sample_key=args.sample_key or "sample_id",
            celltype_key=args.celltype_key,
        )
        full_df.to_csv(tables_dir / "de_full.csv", index=False)
        sig_df = full_df.sort_values("padj", na_position="last")
        sig_df.to_csv(tables_dir / "markers_top.csv", index=False)
    elif method == "mast":
        full_df, summary = run_de_mast_method(adata, groupby=args.groupby, group1=args.group1, group2=args.group2)
        top_df = full_df.sort_values(["padj", "pvalue"], na_position="last").groupby("group").head(args.n_top_genes)
        full_df.to_csv(tables_dir / "de_full.csv", index=False)
        top_df.to_csv(tables_dir / "markers_top.csv", index=False)
    else:
        full_df, summary = run_de_scanpy(adata, args.groupby, method, args.group1, args.group2)
        top_df = full_df.groupby("group").head(args.n_top_genes)
        full_df.to_csv(tables_dir / "de_full.csv", index=False)
        top_df.to_csv(tables_dir / "markers_top.csv", index=False)
        generate_figures(adata, output_dir, min(5, args.n_top_genes))

    summary["n_cells"] = int(adata.n_obs)
    summary.setdefault("requested_method", method)
    summary.setdefault("executed_method", summary.get("method", method))
    summary.setdefault("fallback_used", summary["requested_method"] != summary["executed_method"])
    params = {
        "groupby": summary.get("groupby", args.groupby),
        "method": method,
        "requested_method": summary["requested_method"],
        "executed_method": summary["executed_method"],
        "n_top_genes": args.n_top_genes,
        "group1": args.group1,
        "group2": args.group2,
        "sample_key": args.sample_key,
        "celltype_key": args.celltype_key,
        "expression_source": summary.get("expression_source", ("adata.raw" if (adata.raw is not None and adata.raw.shape == adata.shape and method != "deseq2_r") else ("layers.counts" if "counts" in adata.layers else "adata.X"))),
    }

    write_report(output_dir, summary, input_file, params)

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
    store_analysis_metadata(adata, SKILL_NAME, summary["executed_method"], params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"DE complete: {summary['n_groups']} groups, "
        f"requested={summary['requested_method']}, executed={summary['executed_method']}"
    )


if __name__ == "__main__":
    main()
