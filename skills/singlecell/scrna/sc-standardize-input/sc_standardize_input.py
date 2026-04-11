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
    canonicalize_singlecell_adata,
    infer_qc_species,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-standardize-input"
SKILL_VERSION = "0.2.0"
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
    return canonicalize_singlecell_adata(
        adata,
        species=species,
        standardizer_skill=SKILL_NAME,
    )


def _detect_diagnostics(summary: dict) -> dict:
    """Detect degenerate or suspicious output and return diagnostic info."""
    diagnostics: dict = {
        "degenerate": False,
        "issues": [],
        "suggested_actions": [],
    }

    if summary["n_cells"] == 0:
        diagnostics["degenerate"] = True
        diagnostics["issues"].append("No cells in output")
        diagnostics["suggested_actions"].extend([
            "Check that the input file contains cell barcodes/observations",
            "If using a count matrix CSV, ensure cells are rows (or use --transpose if genes are rows)",
        ])

    if summary["n_genes"] == 0:
        diagnostics["degenerate"] = True
        diagnostics["issues"].append("No genes in output")
        diagnostics["suggested_actions"].extend([
            "Check that the input file contains gene/feature columns",
            "If using a count matrix CSV, ensure genes are columns (or use --transpose if genes are rows)",
        ])

    if summary.get("warnings"):
        for w in summary["warnings"]:
            if "No mitochondrial genes" in w:
                diagnostics["issues"].append("No mitochondrial genes detected")
                diagnostics["suggested_actions"].append(
                    "If data is mouse, use: --species mouse"
                )
            if "No ribosomal genes" in w:
                diagnostics["issues"].append("No ribosomal genes detected")

    if summary.get("species_auto_detected") and summary.get("species_auto_detected") != summary.get("species"):
        diagnostics["issues"].append(
            f"Auto-detected species ({summary['species_auto_detected']}) differs from "
            f"specified species ({summary['species']})"
        )
        diagnostics["suggested_actions"].append(
            f"Consider using: --species {summary['species_auto_detected']}"
        )

    return diagnostics


def _print_ux_guidance(summary: dict, diagnostics: dict) -> None:
    """Print actionable guidance to stdout when issues are detected."""
    if diagnostics["degenerate"]:
        print()
        print("  *** STANDARDIZATION PRODUCED DEGENERATE OUTPUT ***")
        print(f"  Cells: {summary['n_cells']}, Genes: {summary['n_genes']}")
        print()
        print("  How to fix:")
        for i, action in enumerate(diagnostics["suggested_actions"], 1):
            print(f"    Option {i}: {action}")
        print()

    elif diagnostics["issues"]:
        print()
        print("  Warnings detected during standardization:")
        for issue in diagnostics["issues"]:
            print(f"    - {issue}")
        if diagnostics["suggested_actions"]:
            print()
            print("  Suggestions:")
            for i, action in enumerate(diagnostics["suggested_actions"], 1):
                print(f"    {i}. {action}")
        print()


def _write_report(output_dir: Path, summary: dict, input_file: str | None, diagnostics: dict) -> None:
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
    ]

    if summary.get("species_auto_detected"):
        lines.append(f"- **Species auto-detected**: {summary['species_auto_detected']}")

    lines.extend([
        f"- **Expression source selected**: {summary['expression_source']}",
        f"- **Gene identifiers selected**: {summary['gene_name_source']}",
        "- **Canonical counts layer**: `adata.layers['counts']`",
        "- **Canonical active matrix**: `adata.X` now points to raw count-like expression",
        "- **Canonical raw snapshot**: `adata.raw` stores a count-like snapshot so downstream skills can inspect provenance explicitly",
        "",
        "## Input Contract\n",
        "- `adata.X`: raw count-like matrix for downstream OmicsClaw skills that need counts",
        "- `adata.layers['counts']`: canonical raw counts copy",
        "- `adata.raw`: count-like snapshot aligned to the standardized object",
        "- `adata.var_names`: standardized feature names used by OmicsClaw",
        "- `adata.var['gene_symbols']`: user-facing gene symbols when available",
        "- `adata.uns['omicsclaw_input_contract']`: provenance and standardization metadata",
        "- `adata.uns['omicsclaw_matrix_contract']`: explicit matrix semantics for `X`, `raw`, and `layers`",
        "",
        "## Warnings\n",
    ])

    warnings = summary.get("warnings", [])
    if warnings:
        for item in warnings:
            lines.append(f"- {item}")
    else:
        lines.append("- No standardization warnings were emitted.")

    # Troubleshooting section when diagnostics detect issues
    if diagnostics.get("degenerate") or diagnostics.get("issues"):
        lines.extend([
            "",
            "## Troubleshooting\n",
        ])
        if diagnostics["degenerate"]:
            lines.append("### Degenerate Output Detected\n")
            lines.append("The standardization produced an empty or near-empty object. Common causes:\n")
            lines.append("1. **Wrong input format**: The file may not contain single-cell data.")
            lines.append("2. **Transposed matrix**: Genes and cells may be swapped in a CSV/TSV input.")
            lines.append("3. **Corrupted file**: The input file may be incomplete or damaged.\n")

        if diagnostics["issues"]:
            lines.append("### Issues Detected\n")
            for issue in diagnostics["issues"]:
                lines.append(f"- {issue}")
            lines.append("")

        if diagnostics["suggested_actions"]:
            lines.append("### Suggested Fixes\n")
            for i, action in enumerate(diagnostics["suggested_actions"], 1):
                lines.append(f"{i}. {action}")
            lines.append("")

    lines.extend([
        "",
        "## Output Files\n",
        "- `processed.h5ad` - canonical single-cell AnnData for downstream skills",
        "- `report.md` - standardization report",
        "- `result.json` - structured provenance and contract metadata",
        "",
        "## Next Step\n",
        "- You can now pass `processed.h5ad` directly into downstream scRNA skills such as `sc-qc`, `sc-preprocessing`, `sc-doublet-detection`, and `sc-de`.",
    ])

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(lines) + "\n" + footer, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Standardize single-cell input into the OmicsClaw canonical AnnData contract")
    parser.add_argument("--input", dest="input_path", help="Input AnnData or count-like matrix path")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with demo data")
    parser.add_argument("--species", default="auto", choices=["human", "mouse", "auto"], help="Species hint (default: auto-detect from gene names)")
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
            raise FileNotFoundError(
                f"Input file not found: {input_path}\n"
                "\n"
                "Supported input formats:\n"
                "  - .h5ad (AnnData)\n"
                "  - .h5 (10X Genomics HDF5)\n"
                "  - .loom (Loom format)\n"
                "  - .csv / .tsv (count matrix)\n"
                "  - directory (10X mtx output)\n"
                "\n"
                "Example:\n"
                f"  python omicsclaw.py run sc-standardize-input --input your_data.h5ad --output {output_dir}\n"
                "  python omicsclaw.py run sc-standardize-input --demo --output /tmp/demo"
            )
        adata = sc_io.smart_load(
            input_path,
            suggest_standardize=False,
            skill_name=SKILL_NAME,
            min_cells=0,
            min_genes=0,
        )
        input_file = str(input_path)

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)

    # Species auto-detection
    species_auto_detected = infer_qc_species(adata, default="human")
    if args.species == "auto":
        species = species_auto_detected
        logger.info("Auto-detected species: %s", species)
    else:
        species = args.species
        if species != species_auto_detected:
            logger.warning(
                "Specified species '%s' differs from auto-detected '%s'. "
                "Using specified value. If QC metrics look wrong, try: --species %s",
                species, species_auto_detected, species_auto_detected,
            )

    # Preflight: check input is not empty
    if adata.n_obs == 0:
        print()
        print("  *** INPUT FILE CONTAINS NO CELLS ***")
        print("  The loaded object has 0 observations (cells).")
        print()
        print("  How to fix:")
        print("    Option 1: Check that the input file is a valid single-cell dataset")
        print("    Option 2: If using a CSV, cells should be rows and genes should be columns")
        print(f"    Option 3: Try the demo first: python omicsclaw.py run sc-standardize-input --demo --output {output_dir}")
        print()

    if adata.n_vars == 0:
        print()
        print("  *** INPUT FILE CONTAINS NO GENES ***")
        print("  The loaded object has 0 variables (genes/features).")
        print()
        print("  How to fix:")
        print("    Option 1: Check that the input file is a valid single-cell dataset")
        print("    Option 2: If using a CSV, genes should be columns and cells should be rows")
        print()

    try:
        standardized, prepared, contract = _build_standardized_adata(adata, species=species)
    except ValueError as exc:
        # Enhance the error message with actionable guidance
        print()
        print("  *** STANDARDIZATION FAILED: no count-like matrix found ***")
        print(f"  Error: {exc}")
        print()
        print("  How to fix:")
        print("    Option 1: Ensure your data has raw counts in adata.X, adata.layers['counts'], or adata.raw")
        print("    Option 2: If your data is already normalized (log-transformed), you may need to provide")
        print("              the original raw count matrix separately")
        print("    Option 3: Check if your data was exported from a tool that stores counts in a non-standard location")
        print(f"    Option 4: Try the demo: python omicsclaw.py run sc-standardize-input --demo --output {output_dir}")
        print()
        raise

    matrix_contract = {
        "X": "raw_counts",
        "raw": "raw_counts_snapshot",
        "layers": {"counts": "raw_counts"},
        "producer_skill": SKILL_NAME,
    }
    standardized.uns["omicsclaw_matrix_contract"] = matrix_contract

    summary = {
        "method": METHOD_NAME,
        "n_cells": int(standardized.n_obs),
        "n_genes": int(standardized.n_vars),
        "species": species,
        "species_auto_detected": species_auto_detected,
        "expression_source": prepared.expression_source,
        "gene_name_source": prepared.gene_name_source,
        "warnings": prepared.warnings,
        "counts_layer_present": "counts" in standardized.layers,
        "input_contract_version": contract.get("version", ""),
    }

    # Detect degenerate output and build diagnostics
    diagnostics = _detect_diagnostics(summary)

    store_analysis_metadata(standardized, SKILL_NAME, METHOD_NAME, {"species": species})
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(standardized, output_h5ad)
    logger.info("Saved: %s", output_h5ad)

    _write_report(output_dir, summary, input_file, diagnostics)
    _write_reproducibility(output_dir, input_file, demo_mode=args.demo, species=species)

    result_data = {
        **summary,
        "input_contract": contract,
        "matrix_contract": matrix_contract,
        "standardization_diagnostics": diagnostics,
    }
    result_data["next_steps"] = [
        {"skill": "sc-qc", "reason": "Compute QC metrics on standardized data", "priority": "recommended"},
    ]
    result_data["preprocessing_state_after"] = "standardized"
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

    # Print UX guidance if issues detected
    _print_ux_guidance(summary, diagnostics)

    print(f"\n{'=' * 60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'=' * 60}")
    print(f"  Output directory: {output_dir}")
    print(f"  Cells standardized: {summary['n_cells']:,}")
    print(f"  Genes standardized: {summary['n_genes']:,}")
    print(f"  Species: {species}" + (f" (auto-detected)" if args.species == "auto" else ""))
    print(f"  Expression source: {summary['expression_source']}")
    print(f"  Gene names source: {summary['gene_name_source']}")
    print("  Canonical output: processed.h5ad")
    if summary["warnings"]:
        print(f"  Warnings: {len(summary['warnings'])}")
    if diagnostics["issues"]:
        print(f"  Issues: {len(diagnostics['issues'])} (see report.md for details)")
    print()
    print("▶ Next step: Run sc-qc for quality assessment")
    print(f"  python omicsclaw.py run sc-qc --input {output_h5ad} --output <dir>")


if __name__ == "__main__":
    main()
