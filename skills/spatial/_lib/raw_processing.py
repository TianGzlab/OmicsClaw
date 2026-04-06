"""Shared helpers for the spatial-raw-processing skill."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any

import anndata as ad
import numpy as np
import pandas as pd
import scipy.sparse as sp

from .exceptions import DataError, ParameterError

logger = logging.getLogger(__name__)

try:
    import yaml
except Exception:  # pragma: no cover - optional dependency path
    yaml = None

FASTQ_SUFFIXES = (".fastq", ".fq", ".fastq.gz", ".fq.gz", ".fastq.bz2", ".fq.bz2")
CONFIG_SUFFIXES = (".json", ".yaml", ".yml")
_FASTQ_ROLE_PATTERNS = {
    "read1": [r"(^|[._-])r1([._-]|$)", r"(^|[._-])read1([._-]|$)", r"(^|[._-])1([._-]|fastq|fq|$)"],
    "read2": [r"(^|[._-])r2([._-]|$)", r"(^|[._-])read2([._-]|$)", r"(^|[._-])2([._-]|fastq|fq|$)"],
}
_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)x(-?\d+(?:\.\d+)?)\s*$")


def normalize_config_keys(payload: dict[str, Any]) -> dict[str, Any]:
    return {str(key).strip().replace("-", "_"): value for key, value in payload.items()}


def _resolve_path(value: str | Path | None, *, base_dir: Path | None = None) -> str | None:
    if value in (None, ""):
        return None
    path = Path(value).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = (base_dir / path).resolve()
    return str(path)


def load_run_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    suffix = config_path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(text)
    else:
        if yaml is None:
            raise DataError("YAML config support requires PyYAML. Use JSON config or install pyyaml.")
        payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise DataError(f"Config file must define a dictionary of arguments: {config_path}")

    normalized = normalize_config_keys(payload)
    base_dir = config_path.parent.resolve()
    for key in (
        "input",
        "read1",
        "read2",
        "ids",
        "ref_map",
        "ref_annotation",
        "stpipeline_repo",
        "contaminant_index",
        "bin_path",
    ):
        normalized[key] = _resolve_path(normalized.get(key), base_dir=base_dir)
    return normalized


def is_fastq_path(path: str | Path) -> bool:
    return str(path).lower().endswith(FASTQ_SUFFIXES)


def detect_non_raw_spatial_input(path: str | Path) -> str | None:
    candidate = Path(path)
    name = candidate.name.lower()

    if candidate.is_dir():
        if any(child.is_dir() and child.name == "filtered_feature_bc_matrix" for child in candidate.iterdir()):
            return "This looks like a Space Ranger matrix directory. Use spatial-preprocess instead of spatial-raw-processing."
        lowered = {child.name.lower() for child in candidate.iterdir()}
        if any("feature_bc_matrix" in child for child in lowered):
            return "This directory already contains a count matrix. Use spatial-preprocess instead of spatial-raw-processing."
        xenium_tokens = ("cell_feature_matrix", "transcripts", "morphology", "cells")
        if sum(any(token in child for token in xenium_tokens) for child in lowered) >= 2:
            return "This looks like a Xenium-style output directory, not a sequencing FASTQ input. Use spatial-preprocess on the exported matrix or converted h5ad."
        if any(is_fastq_path(child.name) for child in lowered):
            return None
        return None

    if name.endswith((".h5ad", ".h5", ".hdf5", ".zarr", ".loom", ".mtx")):
        return "This input already looks like a matrix-level spatial dataset. Use spatial-preprocess instead of spatial-raw-processing."
    if name.endswith((".rds", ".rda", ".rdata", ".qs")):
        return "This looks like an R workspace or object export. Convert it to h5ad/matrix first, then run spatial-preprocess."
    if name.endswith(CONFIG_SUFFIXES) or is_fastq_path(candidate):
        return None
    return None


def _infer_read_role(path: Path) -> str | None:
    lowered = path.name.lower()
    for role, patterns in _FASTQ_ROLE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, lowered):
                return role
    return None


def _pair_key(path: Path) -> str:
    lowered = path.name.lower()
    lowered = re.sub(r"(^|[._-])r1([._-]|$)", r"\1readx\2", lowered)
    lowered = re.sub(r"(^|[._-])r2([._-]|$)", r"\1readx\2", lowered)
    lowered = re.sub(r"(^|[._-])read1([._-]|$)", r"\1readx\2", lowered)
    lowered = re.sub(r"(^|[._-])read2([._-]|$)", r"\1readx\2", lowered)
    lowered = re.sub(r"(^|[._-])1([._-]|fastq|fq|$)", r"\1readx\2", lowered)
    lowered = re.sub(r"(^|[._-])2([._-]|fastq|fq|$)", r"\1readx\2", lowered)
    return lowered


def discover_fastq_pair(path: str | Path) -> tuple[str, str]:
    candidate = Path(path)
    if candidate.is_file():
        if not is_fastq_path(candidate):
            raise DataError(f"Input file is not a FASTQ: {candidate}")
        directory = candidate.parent
        matches = [p for p in directory.iterdir() if p.is_file() and is_fastq_path(p)]
    elif candidate.is_dir():
        matches = [p for p in candidate.rglob("*") if p.is_file() and is_fastq_path(p)]
        if not matches:
            raise DataError(f"No FASTQ files found under: {candidate}")
    else:
        raise DataError(f"Input path not found: {candidate}")

    grouped: dict[str, dict[str, Path]] = {}
    for match in sorted(matches):
        role = _infer_read_role(match)
        if role is None:
            continue
        grouped.setdefault(_pair_key(match), {})[role] = match

    complete_pairs = [pair for pair in grouped.values() if {"read1", "read2"}.issubset(pair)]
    if candidate.is_file():
        role = _infer_read_role(candidate)
        key = _pair_key(candidate)
        if role is None or key not in grouped or len(grouped[key]) < 2:
            raise DataError(
                f"Could not infer the matching FASTQ pair for {candidate}. "
                "Provide --read1 and --read2 explicitly."
            )
        pair = grouped[key]
        return str(pair["read1"]), str(pair["read2"])

    if len(complete_pairs) == 1:
        pair = complete_pairs[0]
        return str(pair["read1"]), str(pair["read2"])

    if not complete_pairs:
        raise DataError(
            f"Could not identify a unique R1/R2 FASTQ pair under {candidate}. "
            "Use --read1 and --read2 explicitly."
        )

    raise DataError(
        f"Found multiple FASTQ pairs under {candidate}. Use --read1 and --read2 explicitly to select one pair."
    )


def merge_runtime_inputs(args: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if args.input_path and str(args.input_path).lower().endswith(CONFIG_SUFFIXES):
        merged.update(load_run_config(args.input_path))

    explicit_keys = (
        "input_path",
        "read1",
        "read2",
        "ids",
        "ref_map",
        "ref_annotation",
        "exp_name",
        "platform",
        "threads",
        "contaminant_index",
        "min_length_qual_trimming",
        "min_quality_trimming",
        "demultiplexing_mismatches",
        "demultiplexing_kmer",
        "umi_allowed_mismatches",
        "umi_start_position",
        "umi_end_position",
        "disable_clipping",
        "compute_saturation",
        "htseq_no_ambiguous",
        "transcriptome",
        "star_two_pass_mode",
        "stpipeline_repo",
        "bin_path",
    )
    for key in explicit_keys:
        value = getattr(args, key, None)
        if value is None:
            continue
        if isinstance(value, bool) and value is False:
            continue
        merged[key] = value
    return merged


def resolve_runtime_bundle(runtime_args: dict[str, Any]) -> dict[str, Any]:
    bundle = dict(runtime_args)
    input_path = bundle.get("input_path") or bundle.get("input")
    if input_path:
        guidance = detect_non_raw_spatial_input(input_path)
        if guidance and not is_fastq_path(input_path) and not str(input_path).lower().endswith(CONFIG_SUFFIXES):
            raise DataError(guidance)

    read1 = bundle.get("read1")
    read2 = bundle.get("read2")
    if not read1 and not read2 and input_path and not str(input_path).lower().endswith(CONFIG_SUFFIXES):
        read1, read2 = discover_fastq_pair(input_path)

    if not read1 or not read2:
        raise ParameterError("spatial-raw-processing requires a resolved FASTQ pair. Provide --input with a pair-containing path, or pass --read1 and --read2.")

    bundle["read1"] = str(Path(read1).expanduser().resolve())
    bundle["read2"] = str(Path(read2).expanduser().resolve())

    for key in ("ids", "ref_map", "ref_annotation", "stpipeline_repo", "contaminant_index", "bin_path"):
        if bundle.get(key):
            bundle[key] = str(Path(bundle[key]).expanduser().resolve())

    if not bundle.get("ids"):
        raise ParameterError("spatial-raw-processing requires --ids with barcode and coordinate mappings.")
    if not bundle.get("ref_map"):
        raise ParameterError("spatial-raw-processing requires --ref-map pointing to a STAR index.")
    if not bundle.get("transcriptome") and not bundle.get("ref_annotation"):
        raise ParameterError("spatial-raw-processing requires --ref-annotation unless --transcriptome is enabled.")

    if not bundle.get("exp_name"):
        base = Path(bundle["read1"]).name
        bundle["exp_name"] = re.sub(r"(_r?1|\.r?1)(?=\.)", "", base, flags=re.IGNORECASE)
        bundle["exp_name"] = re.sub(r"\.(fastq|fq)(\.gz|\.bz2)?$", "", bundle["exp_name"], flags=re.IGNORECASE)

    bundle.setdefault("platform", "visium")
    return bundle


def _format_coord_token(value: float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def read_ids_table(path: str | Path) -> pd.DataFrame:
    ids_path = Path(path)
    df = pd.read_csv(ids_path, sep=r"\s+", header=None, comment="#", names=["barcode", "array_col", "array_row"], engine="python")
    if df.empty:
        raise DataError(f"IDs file is empty: {ids_path}")

    df["barcode"] = df["barcode"].astype(str)
    df["array_col"] = pd.to_numeric(df["array_col"], errors="coerce")
    df["array_row"] = pd.to_numeric(df["array_row"], errors="coerce")
    if df[["array_col", "array_row"]].isna().any().any():
        raise DataError(f"IDs file must contain barcode, x, y columns: {ids_path}")

    df["coord_key"] = [f"{_format_coord_token(x)}x{_format_coord_token(y)}" for x, y in zip(df["array_col"], df["array_row"], strict=False)]
    if not df["coord_key"].is_unique:
        raise DataError(f"IDs file contains duplicated coordinate entries: {ids_path}")
    return df


def parse_coord_key(value: str) -> tuple[float, float] | None:
    match = _COORD_RE.match(str(value))
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def load_counts_table(path: str | Path) -> pd.DataFrame:
    counts_path = Path(path)
    if not counts_path.exists():
        raise DataError(f"Counts matrix not found: {counts_path}")
    counts_df = pd.read_table(counts_path, sep="\t", header=0, index_col=0)
    if counts_df.empty:
        raise DataError(f"Counts matrix is empty: {counts_path}")
    counts_df.index = counts_df.index.astype(str)
    counts_df.columns = counts_df.columns.astype(str)
    counts_df = counts_df.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return counts_df


def convert_st_pipeline_counts_to_adata(
    counts_path: str | Path,
    ids_path: str | Path,
    *,
    exp_name: str,
    platform: str,
    effective_params: dict[str, Any],
    stage_metrics: dict[str, Any] | None = None,
    saturation: dict[str, Any] | None = None,
) -> ad.AnnData:
    ids_df = read_ids_table(ids_path)
    counts_df = load_counts_table(counts_path)

    extra_coords = [coord for coord in counts_df.index if coord not in set(ids_df["coord_key"])]
    if extra_coords:
        extras = []
        for coord in extra_coords:
            parsed = parse_coord_key(coord)
            if parsed is None:
                continue
            extras.append({
                "barcode": f"unmapped_{coord}",
                "array_col": parsed[0],
                "array_row": parsed[1],
                "coord_key": coord,
            })
        if extras:
            ids_df = pd.concat([ids_df, pd.DataFrame(extras)], ignore_index=True)

    ids_df = ids_df.drop_duplicates(subset=["coord_key"], keep="first").reset_index(drop=True)
    reindexed = counts_df.reindex(ids_df["coord_key"], fill_value=0.0)
    detected_coords = set(counts_df.index)

    obs = ids_df.copy()
    obs["detected_by_stpipeline"] = obs["coord_key"].isin(detected_coords)
    obs["barcode"] = obs["barcode"].astype(str)
    obs_names = obs["barcode"].where(obs["barcode"].ne(""), obs["coord_key"])
    if not obs_names.is_unique:
        obs_names = obs["coord_key"]
    obs.index = obs_names.astype(str)

    matrix = sp.csr_matrix(reindexed.to_numpy(dtype=np.float32))
    var = pd.DataFrame(index=reindexed.columns.astype(str))
    var["gene_id"] = var.index.astype(str)
    var["gene_name"] = var["gene_id"]

    adata = ad.AnnData(X=matrix, obs=obs, var=var)
    adata.layers["counts"] = matrix.copy()
    adata.raw = adata.copy()
    adata.obsm["spatial"] = obs[["array_col", "array_row"]].to_numpy(dtype=float)

    total_counts = np.asarray(matrix.sum(axis=1)).ravel()
    n_genes = np.asarray((matrix > 0).sum(axis=1)).ravel()
    gene_total_counts = np.asarray(matrix.sum(axis=0)).ravel()
    gene_detected = np.asarray((matrix > 0).sum(axis=0)).ravel()

    adata.obs["total_counts"] = total_counts.astype(np.float32)
    adata.obs["n_genes_by_counts"] = n_genes.astype(np.int32)
    adata.obs["in_tissue"] = adata.obs["total_counts"] > 0
    adata.var["total_counts"] = gene_total_counts.astype(np.float32)
    adata.var["n_obs_by_counts"] = gene_detected.astype(np.int32)

    adata.uns["omicsclaw"] = {
        "skill": "spatial-raw-processing",
        "next_skill": "spatial-preprocess",
        "description": "Raw FASTQ processing via st_pipeline, standardized for downstream OmicsClaw preprocessing.",
    }
    adata.uns["st_pipeline"] = {
        "exp_name": exp_name,
        "platform": platform,
        "counts_matrix_path": str(Path(counts_path).resolve()),
        "ids_path": str(Path(ids_path).resolve()),
        "effective_params": effective_params,
        "stage_metrics": stage_metrics or {},
        "saturation": saturation or {},
    }

    return adata


def build_stage_summary_table(stage_metrics: dict[str, Any]) -> pd.DataFrame:
    if not stage_metrics:
        return pd.DataFrame(columns=["stage", "stage_label", "reads", "fraction_of_input"])

    input_reads = stage_metrics.get("input_reads_reverse") or stage_metrics.get("input_reads_forward") or 0
    stage_map = [
        ("input_reads_reverse", "Input read pairs"),
        ("reads_after_trimming_reverse", "After quality trimming"),
        ("reads_after_rRNA_trimming", "After contaminant filtering"),
        ("reads_after_mapping", "After STAR mapping"),
        ("reads_after_demultiplexing", "After barcode demultiplexing"),
        ("reads_after_annotation", "After annotation"),
        ("reads_after_duplicates_removal", "After UMI collapsing"),
    ]
    rows = []
    for key, label in stage_map:
        value = stage_metrics.get(key)
        if value in (None, ""):
            continue
        reads = float(value)
        rows.append({
            "stage": key,
            "stage_label": label,
            "reads": reads,
            "fraction_of_input": (reads / float(input_reads)) if input_reads else np.nan,
        })
    return pd.DataFrame(rows)


def build_run_summary_table(summary: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame([
        {"metric": key, "value": json.dumps(value) if isinstance(value, (dict, list)) else value}
        for key, value in summary.items()
        if value is not None
    ])


def build_spot_qc_table(adata: ad.AnnData) -> pd.DataFrame:
    obs = adata.obs.copy()
    obs.insert(0, "observation", obs.index.astype(str))
    return obs.reset_index(drop=True)


def build_gene_qc_table(adata: ad.AnnData) -> pd.DataFrame:
    var = adata.var.copy()
    var.insert(0, "gene", var.index.astype(str))
    return var.sort_values(by=["total_counts", "gene"], ascending=[False, True], kind="mergesort").reset_index(drop=True)


def build_top_gene_table(adata: ad.AnnData, *, top_n: int = 20) -> pd.DataFrame:
    gene_df = build_gene_qc_table(adata)
    return gene_df.head(top_n).reset_index(drop=True)


def build_spatial_export_table(adata: ad.AnnData) -> pd.DataFrame:
    coords = np.asarray(adata.obsm["spatial"])
    return pd.DataFrame(
        {
            "observation": adata.obs_names.astype(str),
            "barcode": adata.obs["barcode"].astype(str).to_numpy(),
            "coord_key": adata.obs["coord_key"].astype(str).to_numpy(),
            "x": coords[:, 0],
            "y": coords[:, 1],
            "detected_by_stpipeline": adata.obs["detected_by_stpipeline"].astype(bool).to_numpy(),
            "total_counts": adata.obs["total_counts"].to_numpy(),
            "n_genes_by_counts": adata.obs["n_genes_by_counts"].to_numpy(),
        }
    )


def build_saturation_table(saturation: dict[str, list[float]]) -> pd.DataFrame:
    if not saturation or not saturation.get("points"):
        return pd.DataFrame(columns=["reads_sampled", "genes_detected", "avg_genes_per_spot", "avg_reads_per_spot"])

    length = len(saturation["points"])
    return pd.DataFrame(
        {
            "reads_sampled": saturation.get("points", [])[:length],
            "reads_detected": saturation.get("reads", [np.nan] * length)[:length],
            "genes_detected": saturation.get("genes", [np.nan] * length)[:length],
            "avg_genes_per_spot": saturation.get("avg_genes", [np.nan] * length)[:length],
            "avg_reads_per_spot": saturation.get("avg_reads", [np.nan] * length)[:length],
        }
    )


def create_demo_upstream_outputs(output_dir: str | Path, *, exp_name: str) -> dict[str, Any]:
    from scripts.generate_demo_data import generate_demo_visium

    upstream_dir = Path(output_dir) / "upstream" / "st_pipeline"
    upstream_dir.mkdir(parents=True, exist_ok=True)

    adata = generate_demo_visium(n_spots=144, n_genes=80, n_domains=3)
    coords = np.asarray(adata.obsm["spatial"], dtype=int)
    coord_keys = [f"{int(x)}x{int(y)}" for x, y in coords]
    ids_df = pd.DataFrame(
        {
            "barcode": [f"DEMOBC_{i:04d}" for i in range(adata.n_obs)],
            "array_col": coords[:, 0],
            "array_row": coords[:, 1],
        }
    )
    ids_path = upstream_dir / f"{exp_name}_ids.tsv"
    ids_df.to_csv(ids_path, sep="\t", header=False, index=False)

    counts_df = pd.DataFrame(np.asarray(adata.X), index=coord_keys, columns=adata.var_names.astype(str))
    counts_path = upstream_dir / f"{exp_name}_stdata.tsv"
    counts_df.to_csv(counts_path, sep="\t")

    reads_path = upstream_dir / f"{exp_name}_reads.bed"
    with reads_path.open("w", encoding="utf-8") as handle:
        for idx, coord in enumerate(coord_keys[: min(adata.n_obs, 200)]):
            x, y = coord.split("x", 1)
            handle.write(f"chr1\t{1000 + idx}\t{1001 + idx}\tGene_{idx % adata.n_vars:03d}\t255\t+\tGene_{idx % adata.n_vars:03d}\t{x}\t{y}\n")

    total_counts = int(np.asarray(adata.X).sum())
    stage_metrics = {
        "input_reads_forward": 180000,
        "input_reads_reverse": 180000,
        "reads_after_trimming_forward": 172500,
        "reads_after_trimming_reverse": 172500,
        "reads_after_rRNA_trimming": 168400,
        "reads_after_mapping": 154200,
        "reads_after_demultiplexing": 148100,
        "reads_after_annotation": 143800,
        "reads_after_duplicates_removal": total_counts,
        "genes_found": int(adata.n_vars),
        "duplicates_found": int(143800 - total_counts),
        "pipeline_version": "demo",
        "mapper_tool": "STAR",
        "annotation_tool": "HTSeq",
        "demultiplex_tool": "Taggd",
        "barcodes_found": int(adata.n_obs),
        "max_genes_feature": int((np.asarray(adata.X) > 0).sum(axis=1).max()),
        "min_genes_feature": int((np.asarray(adata.X) > 0).sum(axis=1).min()),
        "max_reads_feature": float(np.asarray(adata.X).sum(axis=1).max()),
        "min_reads_feature": float(np.asarray(adata.X).sum(axis=1).min()),
        "average_gene_feature": float((np.asarray(adata.X) > 0).sum(axis=1).mean()),
        "average_reads_feature": float(np.asarray(adata.X).sum(axis=1).mean()),
        "std_reads_feature": float(np.asarray(adata.X).sum(axis=1).std()),
        "std_genes_feature": float((np.asarray(adata.X) > 0).sum(axis=1).std()),
    }
    saturation = {
        "points": [20000.0, 40000.0, 80000.0, 120000.0, 160000.0],
        "reads": [18500.0, 36000.0, 65000.0, 90500.0, float(total_counts)],
        "genes": [55.0, 67.0, 74.0, 79.0, 80.0],
        "avg_genes": [18.0, 26.0, 34.0, 39.0, 42.0],
        "avg_reads": [120.0, 220.0, 360.0, 470.0, 545.0],
    }

    stdout_lines = ["ST Pipeline, demo mode"]
    stdout_lines.extend(f"{key}: {value}" for key, value in stage_metrics.items())
    stdout_lines.extend(
        [
            f"Saturation points: {', '.join(str(v) for v in saturation['points'])}",
            f"Reads per saturation point: {', '.join(str(v) for v in saturation['reads'])}",
            f"Genes per saturation point: {', '.join(str(v) for v in saturation['genes'])}",
            f"Average genes/spot per saturation point: {', '.join(str(v) for v in saturation['avg_genes'])}",
            f"Average reads/spot per saturation point: {', '.join(str(v) for v in saturation['avg_reads'])}",
        ]
    )
    stdout_text = "\n".join(stdout_lines) + "\n"
    (upstream_dir / "st_pipeline.stdout.txt").write_text(stdout_text, encoding="utf-8")
    (upstream_dir / "st_pipeline.stderr.txt").write_text("", encoding="utf-8")
    (upstream_dir / f"{exp_name}_pipeline.log").write_text(stdout_text, encoding="utf-8")
    (upstream_dir / "omicsclaw_stpipeline_run.json").write_text(
        json.dumps(
            {
                "command": ["demo"],
                "runner": "omicsclaw demo",
                "repo_path": None,
                "returncode": 0,
                "counts_path": str(counts_path),
                "reads_path": str(reads_path),
                "pipeline_log": str(upstream_dir / f"{exp_name}_pipeline.log"),
                "stdout_path": str(upstream_dir / "st_pipeline.stdout.txt"),
                "stderr_path": str(upstream_dir / "st_pipeline.stderr.txt"),
                "stats": stage_metrics,
                "saturation": saturation,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return {
        "counts_path": str(counts_path),
        "reads_path": str(reads_path),
        "ids_path": str(ids_path),
        "pipeline_log": str(upstream_dir / f"{exp_name}_pipeline.log"),
        "stdout_path": str(upstream_dir / "st_pipeline.stdout.txt"),
        "stderr_path": str(upstream_dir / "st_pipeline.stderr.txt"),
        "stats": stage_metrics,
        "saturation": saturation,
    }
