#!/usr/bin/env python3
"""Prepare perturbation-ready AnnData objects for downstream sc-perturb analysis."""

from __future__ import annotations

import argparse
import logging
import shlex
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

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
from skills.singlecell._lib.adata_utils import canonicalize_singlecell_adata, store_analysis_metadata
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.perturbation import (
    DEFAULT_CONTROL_PATTERNS,
    annotate_perturbation_obs,
    collapse_sgrna_assignments,
    keep_gene_expression_features,
    load_sgrna_mapping,
    make_demo_perturb_adata,
    make_demo_perturb_mapping,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-perturb-prep"
SKILL_VERSION = "0.1.0"
METHOD_NAME = "mapping_tsv"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-perturb-prep/sc_perturb_prep.py"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a perturbation-ready AnnData with sgRNA assignments.")
    parser.add_argument("--input", type=str, default=None, help="Input h5ad, 10x h5, or 10x matrix directory")
    parser.add_argument("--output", type=str, required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run a synthetic perturbation-prep demo")
    parser.add_argument("--mapping-file", type=str, default=None, help="Cell barcode to sgRNA mapping TSV/CSV")
    parser.add_argument("--barcode-column", type=str, default=None, help="Barcode column name in the mapping file")
    parser.add_argument("--sgrna-column", type=str, default=None, help="sgRNA / guide column name in the mapping file")
    parser.add_argument("--target-column", type=str, default=None, help="Optional target-gene column name in the mapping file")
    parser.add_argument("--sep", type=str, default=None, help="Explicit mapping-file separator, e.g. '\\t' or ','")
    parser.add_argument("--delimiter", type=str, default="_", help="Delimiter used to infer target genes from sgRNA IDs")
    parser.add_argument("--gene-position", type=int, default=0, help="Token index used when inferring target genes from sgRNA IDs")
    parser.add_argument("--pert-key", type=str, default="perturbation", help="Output obs column name for perturbation labels")
    parser.add_argument("--sgrna-key", type=str, default="sgRNA", help="Output obs column name for sgRNA labels")
    parser.add_argument("--target-key", type=str, default="target_gene", help="Output obs column name for target genes")
    parser.add_argument("--control-patterns", type=str, default=",".join(DEFAULT_CONTROL_PATTERNS), help="Comma-separated patterns identifying non-targeting controls")
    parser.add_argument("--control-label", type=str, default="NT", help="Canonical control label stored in the perturbation column")
    parser.add_argument("--keep-multi-guide", action="store_true", help="Keep cells with multiple sgRNA assignments instead of dropping them")
    parser.add_argument("--species", type=str, default="human", choices=["human", "mouse"], help="Species hint for canonicalization")
    parser.add_argument("--r-enhanced", action="store_true",
        help="(Accepted for CLI consistency; no R Enhanced plots available for this skill.)")
    return parser.parse_args()


def _write_reproducibility(output_dir: Path, args: argparse.Namespace, input_file: str | None) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)

    command_parts = ["python", SCRIPT_REL_PATH]
    if args.demo:
        command_parts.append("--demo")
    elif input_file:
        command_parts.extend(["--input", input_file, "--mapping-file", args.mapping_file or "<mapping.tsv>"])
    else:
        command_parts.extend(["--input", "<input.h5ad>", "--mapping-file", "<mapping.tsv>"])
    command_parts.extend(["--output", str(output_dir)])
    if args.barcode_column:
        command_parts.extend(["--barcode-column", args.barcode_column])
    if args.sgrna_column:
        command_parts.extend(["--sgrna-column", args.sgrna_column])
    if args.target_column:
        command_parts.extend(["--target-column", args.target_column])
    if args.sep:
        command_parts.extend(["--sep", args.sep])
    if args.delimiter != "_":
        command_parts.extend(["--delimiter", args.delimiter])
    if args.gene_position != 0:
        command_parts.extend(["--gene-position", str(args.gene_position)])
    if args.pert_key != "perturbation":
        command_parts.extend(["--pert-key", args.pert_key])
    if args.sgrna_key != "sgRNA":
        command_parts.extend(["--sgrna-key", args.sgrna_key])
    if args.target_key != "target_gene":
        command_parts.extend(["--target-key", args.target_key])
    if args.control_patterns != ",".join(DEFAULT_CONTROL_PATTERNS):
        command_parts.extend(["--control-patterns", args.control_patterns])
    if args.control_label != "NT":
        command_parts.extend(["--control-label", args.control_label])
    if args.keep_multi_guide:
        command_parts.append("--keep-multi-guide")
    if args.species != "human":
        command_parts.extend(["--species", args.species])

    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")


def _write_report(output_dir: Path, summary: dict, params: dict, input_file: str | None, diagnostics: dict | None = None) -> None:
    header = generate_report_header(
        title="Single-Cell Perturbation Preparation Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": METHOD_NAME,
            "Perturbation key": str(params["pert_key"]),
            "Control label": str(params["control_label"]),
        },
    )
    lines = [
        "## Summary",
        "",
        f"- **Input cells**: {summary['n_cells_input']}",
        f"- **Assigned cells kept**: {summary['n_cells_assigned']}",
        f"- **Dropped multi-guide cells**: {summary['n_cells_multi_guide_dropped']}",
        f"- **Unique perturbation labels**: {summary['n_perturbations']}",
        f"- **Unique sgRNAs**: {summary['n_sgrnas']}",
        f"- **Removed non-gene features**: {summary['n_non_gene_features_removed']}",
        "",
        "## Interpretation",
        "",
        "- This skill does not infer guide identities from raw FASTQ by itself; it standardizes an expression object plus an upstream barcode-to-guide assignment table.",
        "- The output `processed.h5ad` is trimmed to gene-expression features and stores perturbation metadata in `.obs` for downstream `sc-perturb`.",
        "",
        "## Output Files",
        "",
        "- `processed.h5ad`",
        "- `tables/perturbation_assignments.csv`",
        "- `tables/assignment_status_counts.csv`",
        "- `tables/dropped_multi_guide_cells.csv` (when present)",
        "- `figures/perturbation_counts.png`",
    ]

    # Troubleshooting section for degenerate output
    if diagnostics:
        if diagnostics.get("zero_assigned"):
            lines.extend([
                "",
                "## Troubleshooting: Zero cells assigned",
                "",
                "### Cause 1: Barcode format mismatch",
                "The barcodes in the mapping file may not match `adata.obs_names` (e.g., '-1' suffix difference).",
                "",
                "### Cause 2: Wrong barcode column",
                "Try `--barcode-column <column_name>` if the mapping file uses a non-standard header.",
            ])
        elif diagnostics.get("all_control"):
            lines.extend([
                "",
                "## Troubleshooting: All cells labeled as control",
                "",
                "The `--control-patterns` may be too broad and matching all sgRNA names.",
                "Try narrowing the patterns: `--control-patterns NT,NTC`",
            ])
        elif diagnostics.get("single_perturbation"):
            lines.extend([
                "",
                "## Troubleshooting: Only one perturbation label detected",
                "",
                "Expected at least 2 labels (control + target). Check the mapping file contains multiple targets.",
            ])

    (output_dir / "report.md").write_text(header + "\n".join(lines) + "\n" + generate_report_footer(), encoding="utf-8")


def _build_demo_inputs() -> tuple[object, pd.DataFrame]:
    adata = make_demo_perturb_adata(seed=0)
    mapping = make_demo_perturb_mapping(adata)
    return adata, mapping


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    figures_dir = output_dir / "figures"
    tables_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)

    if args.demo:
        adata, mapping_df = _build_demo_inputs()
        input_file = None
        input_checksum = ""
    else:
        if not args.input:
            raise SystemExit("Provide --input or use --demo")
        if not args.mapping_file:
            raise SystemExit(
                "Perturbation preparation requires --mapping-file for real inputs. "
                "Generate barcode-to-guide assignments upstream first."
            )
        adata = sc_io.smart_load(args.input, preserve_all=True)
        mapping_df = load_sgrna_mapping(
            args.mapping_file,
            barcode_column=args.barcode_column,
            sgrna_column=args.sgrna_column,
            target_column=args.target_column,
            sep=args.sep,
        )
        input_file = args.input
        input_checksum = sha256_file(args.input)

    feature_filtered, feature_summary = keep_gene_expression_features(adata)
    control_patterns = tuple(token.strip() for token in args.control_patterns.split(",") if token.strip())
    assigned_df, dropped_df = collapse_sgrna_assignments(
        mapping_df,
        delimiter=args.delimiter,
        gene_position=args.gene_position,
        control_patterns=control_patterns,
        control_label=args.control_label,
        drop_multi_guide=not args.keep_multi_guide,
    )
    prepared_adata = annotate_perturbation_obs(
        feature_filtered,
        assigned_df,
        pert_key=args.pert_key,
        sgrna_key=args.sgrna_key,
        target_key=args.target_key,
    )
    standardized, prepared, contract = canonicalize_singlecell_adata(
        prepared_adata,
        species=args.species,
        standardizer_skill=SKILL_NAME,
    )
    standardized.obs[args.pert_key] = prepared_adata.obs[args.pert_key].astype(str).values
    standardized.obs[args.sgrna_key] = prepared_adata.obs[args.sgrna_key].astype(str).values
    standardized.obs[args.target_key] = prepared_adata.obs[args.target_key].astype(str).values
    standardized.obs["assignment_status"] = prepared_adata.obs["assignment_status"].astype(str).values
    standardized.obs["n_sgrnas"] = prepared_adata.obs["n_sgrnas"].astype(int).values

    store_analysis_metadata(
        standardized,
        SKILL_NAME,
        METHOD_NAME,
        {
            "pert_key": args.pert_key,
            "sgrna_key": args.sgrna_key,
            "target_key": args.target_key,
            "control_label": args.control_label,
            "control_patterns": list(control_patterns),
            "keep_multi_guide": bool(args.keep_multi_guide),
        },
    )
    standardized.uns["omicsclaw_perturbation_prep"] = {
        "mapping_method": METHOD_NAME,
        "n_cells_input": int(adata.n_obs),
        "n_cells_assigned": int(standardized.n_obs),
        "n_cells_multi_guide_dropped": int((dropped_df["assignment_status"] == "multi_guide").sum()) if not dropped_df.empty and "assignment_status" in dropped_df.columns else 0,
        "n_non_gene_features_removed": int(feature_summary["n_non_gene_features_removed"]),
        "feature_types": feature_summary["feature_types"],
        "expression_source": prepared.expression_source,
        "gene_name_source": prepared.gene_name_source,
        "input_contract": contract,
    }

    assignments_export = standardized.obs[[args.pert_key, args.sgrna_key, args.target_key, "assignment_status", "n_sgrnas"]].copy()
    assignments_export.to_csv(tables_dir / "perturbation_assignments.csv")

    status_counts = standardized.obs["assignment_status"].astype(str).value_counts().rename_axis("assignment_status").reset_index(name="n_cells")
    status_counts.to_csv(tables_dir / "assignment_status_counts.csv", index=False)

    perturb_counts = standardized.obs[args.pert_key].astype(str).value_counts().rename_axis("perturbation").reset_index(name="n_cells")
    perturb_counts.to_csv(tables_dir / "perturbation_counts.csv", index=False)

    if not dropped_df.empty:
        dropped_df.to_csv(tables_dir / "dropped_multi_guide_cells.csv", index=False)

    feature_table = pd.DataFrame(
        {
            "feature_type": feature_summary["feature_types"] or ["Gene Expression"],
        }
    )
    feature_table["n_features"] = feature_table["feature_type"].map(
        pd.Series(adata.var["feature_types"].astype(str).value_counts().to_dict()) if "feature_types" in adata.var.columns else {"Gene Expression": int(adata.n_vars)}
    ).fillna(0).astype(int)
    feature_table.to_csv(tables_dir / "feature_type_summary.csv", index=False)

    # Save figure data for downstream customization
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(exist_ok=True)
    perturb_counts.to_csv(figure_data_dir / "perturbation_counts.csv", index=False)
    status_counts.to_csv(figure_data_dir / "assignment_status_counts.csv", index=False)

    if not perturb_counts.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        perturb_counts.head(20).plot.bar(x="perturbation", y="n_cells", ax=ax, color="#1f78b4")
        ax.set_title("Cells per perturbation")
        ax.set_xlabel("Perturbation")
        ax.set_ylabel("Cells")
        fig.tight_layout()
        fig.savefig(figures_dir / "perturbation_counts.png", dpi=200)
        plt.close(fig)

    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(standardized, output_h5ad)

    # --- Degenerate output detection ---
    n_assigned = int(standardized.n_obs)
    n_perts = int(standardized.obs[args.pert_key].astype(str).nunique())
    n_control = int((standardized.obs[args.pert_key].astype(str) == args.control_label).sum())
    prep_diagnostics: dict = {
        "zero_assigned": n_assigned == 0,
        "all_control": n_assigned > 0 and n_control == n_assigned,
        "single_perturbation": n_perts <= 1,
        "suggested_actions": [],
    }
    if n_assigned == 0:
        prep_diagnostics["suggested_actions"] = [
            "Check that barcode format in mapping file matches adata.obs_names",
            "Try --barcode-column <column> if the mapping file uses a non-standard header",
            "Verify the mapping file is not empty or malformed",
        ]
        print()
        print("  *** ZERO cells were assigned after merging - no barcodes matched. ***")
        print("  This usually means the barcode format in the mapping file does not match adata.obs_names.")
        print()
        print("  How to fix:")
        print("    Option 1 - Check barcode format (e.g., '-1' suffix vs no suffix)")
        print("    Option 2 - Specify the barcode column explicitly:")
        print("      --barcode-column <column_name>")
        print()
    elif n_perts <= 1:
        prep_diagnostics["suggested_actions"] = [
            "Check the mapping file contains multiple perturbation targets",
            "Verify --control-patterns does not match all sgRNAs",
        ]
        print()
        print(f"  *** Only {n_perts} perturbation label(s) found - expected at least 2 (control + target). ***")
        print()
    elif prep_diagnostics["all_control"]:
        prep_diagnostics["suggested_actions"] = [
            "Verify --control-patterns is not too broad (matching all sgRNAs)",
            "Check that target-gene column or sgRNA naming convention is correct",
        ]
        print()
        print("  *** ALL cells were labeled as control - no perturbation targets detected. ***")
        print()

    summary = {
        "method": METHOD_NAME,
        "n_cells_input": int(adata.n_obs),
        "n_cells_assigned": int(standardized.n_obs),
        "n_cells_multi_guide_dropped": int((dropped_df["assignment_status"] == "multi_guide").sum()) if not dropped_df.empty and "assignment_status" in dropped_df.columns else 0,
        "n_perturbations": int(standardized.obs[args.pert_key].astype(str).nunique()),
        "n_sgrnas": int(standardized.obs[args.sgrna_key].astype(str).nunique()),
        "n_non_gene_features_removed": int(feature_summary["n_non_gene_features_removed"]),
        "feature_types_detected": feature_summary["feature_types"],
        "expression_source": prepared.expression_source,
    }
    params = {
        "pert_key": args.pert_key,
        "sgrna_key": args.sgrna_key,
        "target_key": args.target_key,
        "control_label": args.control_label,
        "control_patterns": list(control_patterns),
        "keep_multi_guide": bool(args.keep_multi_guide),
        "species": args.species,
        "demo_mode": bool(args.demo),
    }

    data_payload: dict = {
        "params": params,
        "outputs": {
            "processed_h5ad": str(output_h5ad),
            "assignments": str(tables_dir / "perturbation_assignments.csv"),
            "assignment_status_counts": str(tables_dir / "assignment_status_counts.csv"),
            "perturbation_counts": str(tables_dir / "perturbation_counts.csv"),
        },
        "matrix_contract": standardized.uns.get("omicsclaw_matrix_contract", {}),
    }
    if prep_diagnostics.get("suggested_actions"):
        data_payload["prep_diagnostics"] = prep_diagnostics

    data_payload["next_steps"] = [
        {"skill": "sc-perturb", "reason": "Run perturbation analysis on prepared data", "priority": "recommended"},
    ]
    write_result_json(
        output_dir,
        SKILL_NAME,
        SKILL_VERSION,
        summary,
        data_payload,
        input_checksum=input_checksum,
    )
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": {"params": params},
    }
    _write_report(output_dir, summary, params, input_file, prep_diagnostics)
    _write_reproducibility(output_dir, args, input_file)
    write_output_readme(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Prepare a perturbation-ready AnnData from expression data plus sgRNA assignments.",
        result_payload=result_payload,
        preferred_method=METHOD_NAME,
    )
    logger.info("Done: %s", output_dir)

    # --- Next-step guidance ---
    print()
    print(">> Next step: Run sc-perturb for perturbation analysis")
    print(f"  python omicsclaw.py run sc-perturb --input {output_dir}/processed.h5ad --output <dir>")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
