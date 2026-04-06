"""Adapter helpers for running the upstream st_pipeline repository.

This module keeps the OmicsClaw wrapper honest about what the upstream tool
actually does while still allowing local-repo execution without requiring a
global install.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from .exceptions import DependencyError, ProcessingError

logger = logging.getLogger(__name__)

_STAT_FIELDS = {
    "input_reads_forward",
    "input_reads_reverse",
    "reads_after_trimming_forward",
    "reads_after_trimming_reverse",
    "reads_after_rRNA_trimming",
    "reads_after_mapping",
    "reads_after_annotation",
    "reads_after_demultiplexing",
    "reads_after_duplicates_removal",
    "genes_found",
    "duplicates_found",
    "pipeline_version",
    "mapper_tool",
    "annotation_tool",
    "demultiplex_tool",
    "max_genes_feature",
    "min_genes_feature",
    "max_reads_feature",
    "min_reads_feature",
    "average_gene_feature",
    "average_genes_feature",
    "average_reads_feature",
    "std_reads_feature",
    "std_genes_feature",
    "barcodes_found",
}

_SATURATION_PREFIXES = {
    "points": "Saturation points:",
    "reads": "Reads per saturation point:",
    "genes": "Genes per saturation point:",
    "avg_genes": "Average genes/spot per saturation point:",
    "avg_reads": "Average reads/spot per saturation point:",
}


@dataclass(frozen=True)
class STPipelineEnvironment:
    """Runnable description for an st_pipeline entrypoint."""

    command: tuple[str, ...]
    env: dict[str, str] | None
    description: str
    repo_path: str | None = None


def _prepend_pythonpath(base_env: dict[str, str], repo_root: Path) -> dict[str, str]:
    env = dict(base_env)
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(repo_root) if not current else f"{repo_root}{os.pathsep}{current}"
    return env


def resolve_stpipeline_environment(
    *,
    repo_path: str | Path | None = None,
) -> STPipelineEnvironment:
    """Resolve how OmicsClaw should invoke st_pipeline."""

    candidate_repo = repo_path or os.getenv("OMICSCLAW_ST_PIPELINE_REPO")
    if candidate_repo:
        repo_root = Path(candidate_repo).expanduser().resolve()
        script_path = repo_root / "stpipeline" / "scripts" / "st_pipeline_run.py"
        if not script_path.exists():
            raise DependencyError(
                "Invalid st_pipeline repository path: "
                f"{repo_root}. Expected stpipeline/scripts/st_pipeline_run.py."
            )
        return STPipelineEnvironment(
            command=(sys.executable, "-m", "stpipeline.scripts.st_pipeline_run"),
            env=_prepend_pythonpath(os.environ, repo_root),
            description=f"local st_pipeline repo at {repo_root}",
            repo_path=str(repo_root),
        )

    binary = shutil.which("st_pipeline_run")
    if binary:
        return STPipelineEnvironment(
            command=(binary,),
            env=None,
            description=f"st_pipeline_run on PATH ({binary})",
        )

    if importlib.util.find_spec("stpipeline.scripts.st_pipeline_run") is not None:
        return STPipelineEnvironment(
            command=(sys.executable, "-m", "stpipeline.scripts.st_pipeline_run"),
            env=None,
            description="installed stpipeline Python package",
        )

    raise DependencyError(
        "st_pipeline is not available. Install the `stpipeline` package, or rerun "
        "with `--stpipeline-repo <repo_root>` / OMICSCLAW_ST_PIPELINE_REPO set "
        "to a local clone containing `stpipeline/scripts/st_pipeline_run.py`."
    )


def _append_flag(args: list[str], flag: str, value: Any) -> None:
    if value is None or value == "":
        return
    if isinstance(value, bool):
        if value:
            args.append(flag)
        return
    args.extend([flag, str(value)])


def _parse_scalar(value: str) -> Any:
    text = str(value or "").strip()
    if not text:
        return text
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if any(token in text for token in (".", "e", "E")):
            number = float(text)
            return int(number) if number.is_integer() else number
        return int(text)
    except ValueError:
        return text


def parse_stats_from_text(text: str) -> dict[str, Any]:
    """Extract the final Stats dataclass dump from st_pipeline stdout/stderr."""

    parsed: dict[str, Any] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key not in _STAT_FIELDS:
            continue
        parsed[key] = _parse_scalar(value)
    return parsed


def _parse_number_series(text: str) -> list[float]:
    values: list[float] = []
    for chunk in text.split(","):
        item = chunk.strip()
        if not item:
            continue
        try:
            values.append(float(item))
        except ValueError:
            continue
    return values


def parse_saturation_from_text(text: str) -> dict[str, list[float]]:
    """Extract saturation-curve metrics logged by st_pipeline."""

    parsed: dict[str, list[float]] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        for key, prefix in _SATURATION_PREFIXES.items():
            if prefix not in line:
                continue
            payload = line.split(prefix, 1)[1].strip()
            parsed[key] = _parse_number_series(payload)
    return parsed


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_stpipeline(
    *,
    read1: str | Path,
    read2: str | Path,
    ids_path: str | Path,
    ref_map: str | Path,
    ref_annotation: str | Path | None,
    exp_name: str,
    output_dir: str | Path,
    effective_params: dict[str, Any],
    repo_path: str | Path | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Run upstream st_pipeline and return standardized OmicsClaw metadata."""

    upstream_dir = Path(output_dir) / "upstream" / "st_pipeline"
    upstream_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = upstream_dir / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    environment = resolve_stpipeline_environment(repo_path=repo_path)
    pipeline_log = upstream_dir / f"{exp_name}_pipeline.log"
    stdout_path = upstream_dir / "st_pipeline.stdout.txt"
    stderr_path = upstream_dir / "st_pipeline.stderr.txt"

    command = list(environment.command)
    _append_flag(command, "--ids", Path(ids_path))
    _append_flag(command, "--ref-map", Path(ref_map))
    if not effective_params.get("transcriptome"):
        _append_flag(command, "--ref-annotation", Path(ref_annotation) if ref_annotation else None)
    _append_flag(command, "--expName", exp_name)
    _append_flag(command, "--output-folder", upstream_dir)
    _append_flag(command, "--temp-folder", temp_dir)
    _append_flag(command, "--log-file", pipeline_log)

    forwarded_order = [
        ("threads", "--threads"),
        ("contaminant_index", "--contaminant-index"),
        ("bin_path", "--bin-path"),
        ("min_length_qual_trimming", "--min-length-qual-trimming"),
        ("min_quality_trimming", "--min-quality-trimming"),
        ("remove_polyA", "--remove-polyA"),
        ("remove_polyT", "--remove-polyT"),
        ("remove_polyG", "--remove-polyG"),
        ("remove_polyC", "--remove-polyC"),
        ("remove_polyN", "--remove-polyN"),
        ("filter_AT_content", "--filter-AT-content"),
        ("filter_GC_content", "--filter-GC-content"),
        ("demultiplexing_mismatches", "--demultiplexing-mismatches"),
        ("demultiplexing_kmer", "--demultiplexing-kmer"),
        ("umi_allowed_mismatches", "--umi-allowed-mismatches"),
        ("umi_start_position", "--umi-start-position"),
        ("umi_end_position", "--umi-end-position"),
    ]
    for key, flag in forwarded_order:
        _append_flag(command, flag, effective_params.get(key))

    for key, flag in (
        ("disable_clipping", "--disable-clipping"),
        ("compute_saturation", "--compute-saturation"),
        ("htseq_no_ambiguous", "--htseq-no-ambiguous"),
        ("star_two_pass_mode", "--star-two-pass-mode"),
        ("transcriptome", "--transcriptome"),
    ):
        _append_flag(command, flag, bool(effective_params.get(key)))

    command.extend([str(Path(read1)), str(Path(read2))])

    logger.info("Running st_pipeline via %s", environment.description)
    logger.debug("st_pipeline command: %s", " ".join(command))

    try:
        proc = subprocess.run(
            command,
            env=environment.env,
            cwd=environment.repo_path or str(upstream_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProcessingError(
            f"st_pipeline timed out after {timeout_seconds}s while processing {read1} and {read2}."
        ) from exc
    except FileNotFoundError as exc:
        raise DependencyError(
            "Failed to launch st_pipeline. Confirm that `st_pipeline_run` or the "
            "configured repository path is valid."
        ) from exc

    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")

    log_text = pipeline_log.read_text(encoding="utf-8", errors="replace") if pipeline_log.exists() else ""
    combined_text = "\n".join(part for part in (proc.stdout or "", proc.stderr or "", log_text) if part)
    stats = parse_stats_from_text(combined_text)
    saturation = parse_saturation_from_text(combined_text)

    counts_path = upstream_dir / f"{exp_name}_stdata.tsv"
    reads_path = upstream_dir / f"{exp_name}_reads.bed"

    metadata = {
        "command": command,
        "runner": environment.description,
        "repo_path": environment.repo_path,
        "returncode": proc.returncode,
        "counts_path": str(counts_path),
        "reads_path": str(reads_path),
        "pipeline_log": str(pipeline_log),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stats": stats,
        "saturation": saturation,
    }
    _json_dump(upstream_dir / "omicsclaw_stpipeline_run.json", metadata)

    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout or "").splitlines()[-20:])
        raise ProcessingError(
            "st_pipeline_run failed with exit code "
            f"{proc.returncode}. Tail output:\n{tail}"
        )

    if not counts_path.exists():
        raise ProcessingError(
            f"st_pipeline completed but the expected counts matrix is missing: {counts_path}"
        )

    return metadata
