#!/usr/bin/env python3
"""Spatial Raw Processing — run st_pipeline and standardize outputs."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.runtime_env import ensure_runtime_cache_dirs

ensure_runtime_cache_dirs("omicsclaw")

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    load_result_json,
    write_result_json,
    write_standard_run_artifacts,
)
from skills.spatial._lib.exceptions import (
    DataError,
    DependencyError,
    ParameterError,
    ProcessingError,
)
from skills.spatial._lib.raw_processing import (
    convert_st_pipeline_counts_to_adata,
    create_demo_upstream_outputs,
    is_fastq_path,
    merge_runtime_inputs,
    read_ids_table,
    resolve_runtime_bundle,
)
from skills.spatial._lib.raw_processing_contract import (
    RawProcessingContractSpec,
    build_summary,
    export_tables,
    generate_figures,
    prepare_raw_processing_gallery_context,
    write_report,
    write_reproducibility,
)
from skills.spatial._lib.stpipeline_adapter import run_stpipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-raw-processing"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-raw-processing/spatial_raw_processing.py"
SKILL_DESCRIPTION = (
    "Spatial transcriptomics raw FASTQ processing via st_pipeline with "
    "standardized OmicsClaw outputs and downstream handoff to spatial-preprocess."
)
DEFAULT_METHOD = "st_pipeline"
DEFAULT_EXP_NAME = "omicsclaw_spatial_raw"
STPIPELINE_DEFAULTS = {
    "threads": 4,
    "min_length_qual_trimming": 20,
    "min_quality_trimming": 20,
    "demultiplexing_mismatches": 2,
    "demultiplexing_kmer": 6,
    "umi_allowed_mismatches": 1,
    "umi_start_position": 18,
    "umi_end_position": 27,
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _clean_params(params: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in params.items():
        if key in {"input", "input_path"}:
            continue
        if value is None or value == "":
            continue
        if isinstance(value, bool) and value is False:
            continue
        cleaned[key] = value
    return cleaned


def _apply_effective_defaults(params: dict[str, Any]) -> dict[str, Any]:
    finalized = dict(params)
    for key, value in STPIPELINE_DEFAULTS.items():
        finalized.setdefault(key, value)
    finalized.setdefault("platform", "visium")
    finalized.setdefault("exp_name", DEFAULT_EXP_NAME)
    return finalized


def _collect_input_files(params: dict[str, Any]) -> list[Path]:
    files: list[Path] = []
    for key in ("read1", "read2", "ids", "ref_annotation"):
        raw_value = params.get(key)
        if not raw_value:
            continue
        path = Path(raw_value)
        if path.exists() and path.is_file():
            files.append(path)
    return files


def _collect_input_checksums(files: list[Path]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in files:
        if path.exists() and path.is_file():
            checksums[path.name] = f"sha256:{sha256_file(path)}"
    return checksums


def _validate_real_run_bundle(bundle: dict[str, Any]) -> None:
    for key in ("read1", "read2", "ids"):
        raw_value = bundle.get(key)
        if not raw_value:
            raise ParameterError(f"Missing required parameter: {key}")
        path = Path(raw_value)
        if not path.exists() or not path.is_file():
            raise DataError(f"Required file not found for {key}: {path}")

    if not is_fastq_path(bundle["read1"]) or not is_fastq_path(bundle["read2"]):
        raise DataError("Resolved read1/read2 inputs must be FASTQ files.")

    if Path(bundle["read1"]).resolve() == Path(bundle["read2"]).resolve():
        raise ParameterError("read1 and read2 resolved to the same file; provide a valid FASTQ pair.")

    ref_map = Path(bundle["ref_map"])
    if not ref_map.exists():
        raise DataError(f"STAR index directory not found: {ref_map}")
    if not ref_map.is_dir():
        raise DataError(f"--ref-map must point to a STAR index directory, not a file: {ref_map}")

    if bundle.get("ref_annotation"):
        ref_annotation = Path(bundle["ref_annotation"])
        if not ref_annotation.exists() or not ref_annotation.is_file():
            raise DataError(f"Reference annotation file not found: {ref_annotation}")

    read_ids_table(bundle["ids"])


# ---------------------------------------------------------------------------
# Shared output contract
# ---------------------------------------------------------------------------


CONTRACT_SPEC = RawProcessingContractSpec(
    skill_name=SKILL_NAME,
    skill_version=SKILL_VERSION,
    method=DEFAULT_METHOD,
    next_skill="spatial-preprocess",
    script_rel_path=SCRIPT_REL_PATH,
    r_visualization_template=(
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-raw-processing"
        / "r_visualization"
        / "raw_processing_publication_template.R"
    ),
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Spatial Raw Processing — run st_pipeline on barcoded spatial FASTQs "
            "and export a standardized raw_counts.h5ad for downstream preprocessing"
        )
    )
    parser.add_argument(
        "--input",
        dest="input_path",
        help="FASTQ file, directory containing one FASTQ pair, or JSON/YAML config.",
    )
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--read1", default=None)
    parser.add_argument("--read2", default=None)
    parser.add_argument("--ids", default=None)
    parser.add_argument("--ref-map", default=None)
    parser.add_argument("--ref-annotation", default=None)
    parser.add_argument("--exp-name", default=None)
    parser.add_argument(
        "--platform",
        default=None,
        help="Label recorded in outputs, for example visium, visium_hd, slideseq, or custom.",
    )
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument("--contaminant-index", default=None)
    parser.add_argument("--min-length-qual-trimming", type=int, default=None)
    parser.add_argument("--min-quality-trimming", type=int, default=None)
    parser.add_argument("--demultiplexing-mismatches", type=int, default=None)
    parser.add_argument("--demultiplexing-kmer", type=int, default=None)
    parser.add_argument("--umi-allowed-mismatches", type=int, default=None)
    parser.add_argument("--umi-start-position", type=int, default=None)
    parser.add_argument("--umi-end-position", type=int, default=None)
    parser.add_argument("--disable-clipping", action="store_true")
    parser.add_argument("--compute-saturation", action="store_true")
    parser.add_argument("--htseq-no-ambiguous", action="store_true")
    parser.add_argument("--transcriptome", action="store_true")
    parser.add_argument("--star-two-pass-mode", action="store_true")
    parser.add_argument("--stpipeline-repo", default=None)
    parser.add_argument("--bin-path", default=None)
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        bundle = _apply_effective_defaults(
            {
                "exp_name": args.exp_name or DEFAULT_EXP_NAME,
                "platform": args.platform or "visium",
            }
        )
        upstream_meta = create_demo_upstream_outputs(output_dir, exp_name=bundle["exp_name"])
        upstream_meta.setdefault("runner", "omicsclaw demo")
        upstream_meta.setdefault("repo_path", None)
        input_files: list[Path] = []
    else:
        runtime_bundle = resolve_runtime_bundle(merge_runtime_inputs(args))
        bundle = _apply_effective_defaults(runtime_bundle)
        _validate_real_run_bundle(bundle)
        upstream_meta = run_stpipeline(
            read1=bundle["read1"],
            read2=bundle["read2"],
            ids_path=bundle["ids"],
            ref_map=bundle["ref_map"],
            ref_annotation=bundle.get("ref_annotation"),
            exp_name=bundle["exp_name"],
            output_dir=output_dir,
            effective_params=bundle,
            repo_path=bundle.get("stpipeline_repo"),
        )
        input_files = _collect_input_files(bundle)

    ids_path = upstream_meta.get("ids_path") or bundle.get("ids")
    adata = convert_st_pipeline_counts_to_adata(
        upstream_meta["counts_path"],
        ids_path,
        exp_name=bundle["exp_name"],
        platform=bundle["platform"],
        effective_params=_clean_params(bundle),
        stage_metrics=upstream_meta.get("stats"),
        saturation=upstream_meta.get("saturation"),
    )
    adata.uns["omicsclaw_matrix_contract"] = {
        "X": "raw_counts",
        "raw": "raw_counts_snapshot",
        "layers": {"counts": "raw_counts"},
        "spatial_basis": "obsm['spatial']",
        "recommended_next_skill": CONTRACT_SPEC.next_skill,
        "upstream_method": CONTRACT_SPEC.method,
    }

    summary = build_summary(adata, bundle, upstream_meta, spec=CONTRACT_SPEC)
    gallery_context = prepare_raw_processing_gallery_context(adata, summary)
    visualization_contract = generate_figures(
        adata,
        output_dir,
        summary,
        spec=CONTRACT_SPEC,
        gallery_context=gallery_context,
    )
    export_tables(output_dir, gallery_context)

    output_h5ad = output_dir / "raw_counts.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info("Saved raw count object to %s", output_h5ad)

    params = _clean_params(bundle)
    write_report(
        output_dir,
        summary,
        params,
        upstream_meta,
        spec=CONTRACT_SPEC,
        input_files=input_files,
    )
    write_reproducibility(output_dir, params, spec=CONTRACT_SPEC, demo_mode=args.demo)

    input_checksums = _collect_input_checksums(input_files)
    result_data = {
        "method": CONTRACT_SPEC.method,
        "params": params,
        "effective_params": params,
        "input_checksums": input_checksums,
        "output_object": "raw_counts.h5ad",
        "upstream": {
            "runner": upstream_meta.get("runner"),
            "repo_path": upstream_meta.get("repo_path"),
            "counts_path": upstream_meta.get("counts_path"),
            "reads_path": upstream_meta.get("reads_path"),
            "pipeline_log": upstream_meta.get("pipeline_log"),
            "stdout_path": upstream_meta.get("stdout_path"),
            "stderr_path": upstream_meta.get("stderr_path"),
        },
        "visualization": visualization_contract,
        "recommended_next_step": {
            "skill": CONTRACT_SPEC.next_skill,
            "input": str(output_h5ad),
            "description": "Run matrix-level QC, normalization, HVG selection, embedding, and clustering on the raw count object.",
        },
    }
    primary_checksum = sha256_file(input_files[0]) if input_files else ""
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary,
        data=result_data,
        input_checksum=primary_checksum,
    )

    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }
    write_standard_run_artifacts(
        output_dir,
        skill_alias=SKILL_NAME,
        description=SKILL_DESCRIPTION,
        result_payload=result_payload,
        preferred_method=CONTRACT_SPEC.method,
        script_path=Path(__file__).resolve(),
        actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
    )

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"  Next: run {CONTRACT_SPEC.next_skill} on "
        f"{output_h5ad} to generate a normalized/clustering-ready spatial object"
    )


if __name__ == "__main__":
    try:
        main()
    except (DataError, DependencyError, ParameterError, ProcessingError) as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc
