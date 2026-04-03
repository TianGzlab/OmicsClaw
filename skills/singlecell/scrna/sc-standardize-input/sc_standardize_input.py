#!/usr/bin/env python3
"""Standardize single-cell AnnData input into the OmicsClaw canonical contract."""
from __future__ import annotations

import argparse
import logging
import shlex
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

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
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import (
    prepare_count_like_adata,
    record_standardized_input_contract,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-standardize-input"
SKILL_VERSION = "0.1.0"
METHOD_NAME = "canonical_ann_data"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-standardize-input/sc_standardize_input.py"


def _write_reproducibility(output_dir: Path, input_file: str | None, *, demo_mode: bool, species: str) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)

    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    elif input_file:
        command_parts.extend(["--input", input_file])
    else:
        command_parts.extend(["--input", "<input.h5ad>"])
    command_parts.extend(["--output", str(output_dir)])
    if species != "human":
        command_parts.extend(["--species", species])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")

    requirements = ["scanpy", "anndata", "numpy", "pandas"]
    try:
        from importlib.metadata import version as _get_version

        lines = [f"{pkg}=={_get_version(pkg)}" for pkg in requirements]
    except Exception:
        lines = requirements
    (repro_dir / "requirements.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_standardized_adata(adata, *, species: str):
    prepared = prepare_count_like_adata(adata, species=species)
    standardized = prepared.adata

    standardized.obs_names = standardized.obs_names.astype(str)
    standardized.var_names = standardized.var_names.astype(str)
    standardized.obs_names_make_unique()
    standardized.var_names_make_unique()

    if "gene_symbols" not in standardized.var.columns or standardized.var["gene_symbols"].astype(str).eq("").all():
        standardized.var["gene_symbols"] = standardized.var_names.astype(str)

    if "_omicsclaw_original_var_names" in standardized.var.columns and "feature_id" not in standardized.var.columns:
        standardized.var["feature_id"] = standardized.var["_omicsclaw_original_var_names"].astype(str)

    standardized.layers["counts"] = standardized.X.copy()
    contract = record_standardized_input_contract(
        standardized,
        expression_source=prepared.expression_source,
        gene_name_source=prepared.gene_name_source,
        warnings=prepared.warnings,
        standardizer_skill=SKILL_NAME,
    )
    return standardized, prepared, contract


def _write_report(output_dir: Path, summary: dict, input_file: str | None) -> None:
    header = generate_report_header(
        title="Single-Cell Input Standardization Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": METHOD_NAME,
            "Cells": str(summary["n_cells"]),
            "Genes": str(summary["n_genes"]),
            "Species": summary["species"],
        },
    )

    lines = [
        "## Summary\n",
        f"- **Method**: {METHOD_NAME}",
        f"- **Total cells**: {summary['n_cells']:,}",
        f"- **Total genes**: {summary['n_genes']:,}",
        f"- **Species hint**: {summary['species']}",
        f"- **Expression source selected**: {summary['expression_source']}",
        f"- **Gene identifiers selected**: {summary['gene_name_source']}",
        "- **Canonical counts layer**: `adata.layers['counts']`",
        "- **Canonical active matrix**: `adata.X` now points to count-like expression",
        "",
        "## Input Contract\n",
        "- `adata.X`: count-like matrix for downstream OmicsClaw skills",
        "- `adata.layers['counts']`: canonical raw counts copy",
        "- `adata.var_names`: standardized feature names used by OmicsClaw",
        "- `adata.var['gene_symbols']`: user-facing gene symbols when available",
        "- `adata.uns['omicsclaw_input_contract']`: provenance and standardization metadata",
        "",
        "## Warnings\n",
    ]

    warnings = summary.get("warnings", [])
    if warnings:
        for item in warnings:
            lines.append(f"- {item}")
    else:
        lines.append("- No standardization warnings were emitted.")

    lines.extend([
        "",
        "## Output Files\n",
        "- `standardized_input.h5ad` - canonical single-cell AnnData for downstream skills",
        "- `report.md` - standardization report",
        "- `result.json` - structured provenance and contract metadata",
        "",
        "## Next Step\n",
        "- You can now pass `standardized_input.h5ad` directly into downstream scRNA skills such as `sc-qc`, `sc-preprocessing`, `sc-doublet-detection`, and `sc-de`.",
    ])

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(lines) + "\n" + footer, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Standardize single-cell input into the OmicsClaw canonical AnnData contract")
    parser.add_argument("--input", dest="input_path", help="Input AnnData or count-like matrix path")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with demo data")
    parser.add_argument("--species", default="human", choices=["human", "mouse"], help="Species hint for gene symbol prefix detection")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, demo_path = sc_io.load_repo_demo_data("pbmc3k_raw")
        input_file = str(demo_path) if demo_path else None
    else:
        if not args.input_path:
            parser.error("--input required when not using --demo")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        adata = sc_io.smart_load(
            input_path,
            suggest_standardize=False,
            skill_name=SKILL_NAME,
            min_cells=0,
            min_genes=0,
        )
        input_file = str(input_path)

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    standardized, prepared, contract = _build_standardized_adata(adata, species=args.species)

    summary = {
        "method": METHOD_NAME,
        "n_cells": int(standardized.n_obs),
        "n_genes": int(standardized.n_vars),
        "species": args.species,
        "expression_source": prepared.expression_source,
        "gene_name_source": prepared.gene_name_source,
        "warnings": prepared.warnings,
        "counts_layer_present": "counts" in standardized.layers,
        "input_contract_version": contract.get("version", ""),
    }

    store_analysis_metadata(standardized, SKILL_NAME, METHOD_NAME, {"species": args.species})
    output_h5ad = output_dir / "standardized_input.h5ad"
    save_h5ad(standardized, output_h5ad)
    logger.info("Saved: %s", output_h5ad)

    _write_report(output_dir, summary, input_file)
    _write_reproducibility(output_dir, input_file, demo_mode=args.demo, species=args.species)

    result_data = {
        **summary,
        "input_contract": contract,
    }
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {"skill": SKILL_NAME, "summary": summary, "data": result_data}
    write_output_readme(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Canonicalize single-cell input into a stable AnnData contract for downstream OmicsClaw skills.",
        result_payload=result_payload,
        preferred_method=METHOD_NAME,
    )

    print(f"\n{'=' * 60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'=' * 60}")
    print(f"  Output directory: {output_dir}")
    print(f"  Cells standardized: {summary['n_cells']:,}")
    print(f"  Genes standardized: {summary['n_genes']:,}")
    print(f"  Expression source: {summary['expression_source']}")
    print(f"  Gene names source: {summary['gene_name_source']}")
    print("  Canonical output: standardized_input.h5ad")
    if summary["warnings"]:
        print(f"  Warnings: {len(summary['warnings'])}")


if __name__ == "__main__":
    main()
