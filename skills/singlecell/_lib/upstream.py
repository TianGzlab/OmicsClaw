"""Shared upstream helpers for scRNA-seq raw-read and counting workflows."""

from __future__ import annotations

import gzip
import logging
import os
import re
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .adata_utils import (
    record_matrix_contract,
    record_standardized_input_contract,
    store_analysis_metadata,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_RESOURCE_ROOT = _PROJECT_ROOT / "resources" / "singlecell" / "references"

_FASTQ_SUFFIXES = (".fastq.gz", ".fq.gz", ".fastq", ".fq")
_COMMON_ADAPTER_SEEDS = (
    "AGATCGGAAGAG",
    "CTGTCTCTTATA",
    "AAGCAGTGGTAT",
    "TTTTTTTTTTTTTTT",
)
_STARSOLO_CHEMISTRY = {
    "10xv2": {"cb_start": 1, "cb_len": 16, "umi_start": 17, "umi_len": 10},
    "10xv3": {"cb_start": 1, "cb_len": 16, "umi_start": 17, "umi_len": 12},
    "10xv4": {"cb_start": 1, "cb_len": 16, "umi_start": 17, "umi_len": 12},
}
_STARSOLO_DEFAULT_WHITELIST = {
    "10xv2": ("737K-august-2016.txt", "737K-august-2016.txt.gz"),
    "10xv3": ("3M-february-2018.txt", "3M-february-2018.txt.gz"),
}
_REFERENCE_SUBDIRS = {
    "cellranger": "cellranger",
    "starsolo": "starsolo",
    "simpleaf": "simpleaf",
    "kb_python": "kb",
}


@dataclass(frozen=True)
class FastqSample:
    """One logical FASTQ sample, possibly spread across multiple lanes."""

    sample_id: str
    read1_files: tuple[Path, ...]
    read2_files: tuple[Path, ...] = ()

    @property
    def is_paired(self) -> bool:
        return bool(self.read2_files)

    def all_files(self) -> list[Path]:
        return [*self.read1_files, *self.read2_files]


@dataclass(frozen=True)
class CommandExecution:
    """Small record of one external command invocation."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    cwd: str


@dataclass(frozen=True)
class CountArtifacts:
    """Stable paths produced by one counting backend run."""

    method: str
    run_dir: Path
    filtered_matrix_dir: Path | None
    filtered_h5: Path | None
    raw_matrix_dir: Path | None
    raw_h5: Path | None
    summary_csv: Path | None
    html_summary: Path | None
    bam_path: Path | None
    log_path: Path | None


def _import_scanpy():
    import scanpy as sc

    return sc


def _import_sparse_helpers():
    from scipy import sparse
    from scipy.io import mmread

    return sparse, mmread


def recommended_resource_dir(kind: str) -> Path:
    """Return the conventional project-local resource directory for one upstream asset type."""
    if kind in _REFERENCE_SUBDIRS:
        return _RESOURCE_ROOT / _REFERENCE_SUBDIRS[kind]
    if kind == "whitelist":
        return _RESOURCE_ROOT / "whitelists"
    if kind == "gtf":
        return _RESOURCE_ROOT / "gtf"
    if kind == "t2g":
        return _RESOURCE_ROOT / "kb"
    return _RESOURCE_ROOT


def _find_single_candidate(directory: Path, predicate) -> Path | None:
    if not directory.exists():
        return None
    candidates = sorted(path for path in directory.iterdir() if predicate(path))
    return candidates[0] if len(candidates) == 1 else None


def auto_reference_path(method: str) -> Path | None:
    """Auto-detect exactly one project-local reference for a given backend."""
    directory = recommended_resource_dir(method)
    if method in {"cellranger", "starsolo"}:
        return _find_single_candidate(directory, lambda path: path.is_dir())
    return _find_single_candidate(directory, lambda path: path.exists())


def auto_t2g_path() -> Path | None:
    """Auto-detect exactly one project-local transcript-to-gene map."""
    directory = recommended_resource_dir("t2g")
    return _find_single_candidate(directory, lambda path: path.is_file() and "t2g" in path.name.lower())


def auto_gtf_path() -> Path | None:
    """Auto-detect exactly one project-local GTF file."""
    directory = recommended_resource_dir("gtf")
    return _find_single_candidate(directory, lambda path: path.is_file() and path.name.lower().endswith((".gtf", ".gtf.gz")))


def ensure_existing_path(
    path: str | Path,
    *,
    flag: str,
    label: str,
    recommended_dir: str | Path | None = None,
    expect_directory: bool | None = None,
) -> Path:
    """Validate a user-supplied path and raise a user-facing error with a concrete local-storage hint."""
    resolved = Path(path).expanduser()
    if not resolved.exists():
        message = [f"{label} not found: {resolved}."]
        message.append(f"Pass `{flag}` to an existing local path.")
        if recommended_dir is not None:
            message.append(f"Recommended project-local location: `{Path(recommended_dir)}`.")
        raise FileNotFoundError(" ".join(message))
    if expect_directory is True and not resolved.is_dir():
        raise ValueError(f"{label} must be a directory: {resolved}")
    if expect_directory is False and not resolved.is_file():
        raise ValueError(f"{label} must be a file: {resolved}")
    return resolved.resolve()


def reference_setup_guidance(method: str) -> str:
    """Return a beginner-facing setup hint for one counting reference type."""
    local_dir = recommended_resource_dir(method)
    if method == "cellranger":
        return textwrap.dedent(
            f"""
            Download guidance:
            - Official docs: https://www.10xgenomics.com/support/software/cell-ranger/latest/analysis/running-pipelines/cr-gex-count
            - Official reference pages: https://www.10xgenomics.com/support/software/cell-ranger/latest/release-notes/cr-reference-release-notes
            - Recommended local directory: `{local_dir}`
            - Easiest workflow: manually download a matching 10x transcriptome reference tarball, then unpack it into `{local_dir}`.
            - Example:
              mkdir -p {local_dir}
              tar -xf refdata-gex-GRCh38-2020-A.tar.gz -C {local_dir}
            - Or pass the unpacked reference directly with `--reference /abs/path/to/refdata-gex-...`.
            """
        ).strip()
    if method == "starsolo":
        return textwrap.dedent(
            f"""
            Download guidance:
            - STARsolo docs: https://github.com/alexdobin/STAR/blob/master/docs/STARsolo.md
            - Recommended local directory: `{local_dir}`
            - Easiest workflow: reuse the same FASTA and GTF you used for Cell Ranger or downloaded from 10x, then build a STAR genome directory.
            - Example:
              mkdir -p {local_dir}/GRCh38_star
              STAR --runMode genomeGenerate --runThreadN 16 --genomeDir {local_dir}/GRCh38_star --genomeFastaFiles /path/to/genome.fa --sjdbGTFfile /path/to/genes.gtf
            - Or pass an existing STAR genome directory directly with `--reference /abs/path/to/star_index`.
            """
        ).strip()
    if method == "simpleaf":
        return textwrap.dedent(
            f"""
            Download guidance:
            - simpleaf docs: https://simpleaf.readthedocs.io/en/latest/quant-command.html
            - Recommended local directory: `{local_dir}`
            - If your lab already has a simpleaf index, move or symlink it into `{local_dir}`.
            - Otherwise build one following the official simpleaf indexing workflow, then pass it with `--reference` or keep it under `{local_dir}` for auto-detection.
            """
        ).strip()
    if method == "kb_python":
        return textwrap.dedent(
            f"""
            Download guidance:
            - kb-python docs: https://kb-python.readthedocs.io/en/stable/autoapi/kb_python/count/
            - kb-python repository: https://github.com/pachterlab/kb_python
            - Recommended local directory: `{local_dir}`
            - If you already have a kallisto index, move or symlink it into `{local_dir}`.
            - You will also need a transcript-to-gene map (`t2g`), either from your existing kb reference prep or from the official kb reference-building workflow.
            """
        ).strip()
    return f"Recommended local directory: `{local_dir}`"


def whitelist_setup_guidance() -> str:
    """Return a beginner-facing setup hint for STARsolo barcode whitelist files."""
    local_dir = recommended_resource_dir("whitelist")
    return textwrap.dedent(
        f"""
        Whitelist guidance:
        - STARsolo docs: https://github.com/alexdobin/STAR/blob/master/docs/STARsolo.md
        - Recommended local directory: `{local_dir}`
        - For 10x v3 / v4, a common whitelist is `3M-february-2018.txt`.
        - Example download:
          mkdir -p {local_dir}
          curl -L -o {local_dir}/3M-february-2018.txt.gz https://github.com/10XGenomics/cellranger/raw/master/lib/python/cellranger/barcodes/3M-february-2018.txt.gz
          gunzip -f {local_dir}/3M-february-2018.txt.gz
        - For 10x v2, use `737K-august-2016.txt` from the same Cell Ranger barcode directory.
        - Or pass a local whitelist directly with `--whitelist /abs/path/to/barcodes.txt`.
        """
    ).strip()


def t2g_setup_guidance() -> str:
    """Return a beginner-facing setup hint for kb transcript-to-gene maps."""
    local_dir = recommended_resource_dir("t2g")
    return textwrap.dedent(
        f"""
        Transcript-to-gene guidance:
        - kb-python docs: https://kb-python.readthedocs.io/en/stable/autoapi/kb_python/count/
        - kb-python repository: https://github.com/pachterlab/kb_python
        - Recommended local directory: `{local_dir}`
        - Easiest workflow: reuse a `t2g` file generated during kb reference preparation, then move it into `{local_dir}`.
        - Example:
          mkdir -p {local_dir}
          mv t2g.txt {local_dir}/
        - Or pass it directly with `--t2g /abs/path/to/t2g.txt`.
        """
    ).strip()


def gtf_setup_guidance() -> str:
    """Return a beginner-facing setup hint for GTF annotation files."""
    local_dir = recommended_resource_dir("gtf")
    return textwrap.dedent(
        f"""
        GTF guidance:
        - velocyto docs: https://velocyto.org/velocyto.py/tutorial/cli.html
        - Recommended local directory: `{local_dir}`
        - Easiest workflow: reuse the same `genes.gtf` that matches your Cell Ranger or STAR reference.
        - Example:
          mkdir -p {local_dir}
          cp /path/to/refdata-gex-.../genes/genes.gtf {local_dir}/
        - Or pass it directly with `--gtf /abs/path/to/genes.gtf`.
        """
    ).strip()


def _strip_fastq_suffix(name: str) -> str:
    for suffix in _FASTQ_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _parse_fastq_name(path: Path) -> tuple[str, str | None]:
    stem = _strip_fastq_suffix(path.name)
    patterns = (
        r"^(?P<sample>.+?)(?:_S\d+)?(?:_L\d{3})?_(?P<read>R[12])(?:_\d+)?$",
        r"^(?P<sample>.+?)(?:_L\d{3})?_(?P<read>[12])$",
        r"^(?P<sample>.+?)[._-](?P<read>R[12])$",
        r"^(?P<sample>.+?)[._-](?P<read>[12])$",
    )
    for pattern in patterns:
        match = re.match(pattern, stem, flags=re.IGNORECASE)
        if match:
            sample = match.group("sample")
            read = match.group("read").upper()
            read = "R1" if read in {"1", "R1"} else "R2"
            return sample, read
    return stem, None


def discover_fastq_samples(
    input_path: str | Path,
    *,
    read2: str | Path | None = None,
    sample: str | None = None,
) -> list[FastqSample]:
    """Discover one or more FASTQ samples from a file or directory."""
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"FASTQ input not found: {path}")

    if path.is_file():
        sample_id, read_label = _parse_fastq_name(path)
        if read2:
            read2_path = Path(read2)
            if not read2_path.exists():
                raise FileNotFoundError(f"Read 2 FASTQ not found: {read2_path}")
            return [FastqSample(sample or sample_id, (path,), (read2_path,))]

        if read_label == "R1":
            for suffix_a, suffix_b in (
                ("_R1_001", "_R2_001"),
                ("_R1", "_R2"),
                ("_1", "_2"),
                (".R1", ".R2"),
                ("-R1", "-R2"),
            ):
                candidate = path.with_name(path.name.replace(suffix_a, suffix_b))
                if candidate.exists():
                    return [FastqSample(sample or sample_id, (path,), (candidate,))]
        return [FastqSample(sample or sample_id, (path,), ())]

    fastqs = sorted(
        candidate for candidate in path.iterdir()
        if candidate.is_file() and any(candidate.name.endswith(suffix) for suffix in _FASTQ_SUFFIXES)
    )
    if not fastqs:
        raise ValueError(f"No FASTQ files found under: {path}")

    grouped: dict[str, dict[str, list[Path]]] = {}
    for fastq in fastqs:
        sample_id, read_label = _parse_fastq_name(fastq)
        if sample and sample_id != sample:
            continue
        grouped.setdefault(sample_id, {"R1": [], "R2": [], "single": []})
        if read_label in {"R1", "R2"}:
            grouped[sample_id][read_label].append(fastq)
        else:
            grouped[sample_id]["single"].append(fastq)

    samples: list[FastqSample] = []
    for sample_id, lanes in sorted(grouped.items()):
        read1_files = tuple(sorted(lanes["R1"] or lanes["single"]))
        read2_files = tuple(sorted(lanes["R2"]))
        if not read1_files:
            continue
        samples.append(FastqSample(sample_id, read1_files, read2_files))

    if not samples:
        raise ValueError(f"No FASTQ samples matched under: {path}")
    return samples


def choose_fastq_sample(samples: list[FastqSample], sample: str | None = None) -> FastqSample:
    """Choose one sample, raising if the choice is ambiguous."""
    if sample:
        for item in samples:
            if item.sample_id == sample:
                return item
        raise ValueError(f"Sample `{sample}` was not found. Available samples: {', '.join(s.sample_id for s in samples)}")
    if len(samples) != 1:
        raise ValueError(
            "Multiple FASTQ samples were found. Pass `--sample` to choose one of: "
            + ", ".join(item.sample_id for item in samples)
        )
    return samples[0]


def _open_fastq(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="ignore")
    return path.open("r", encoding="utf-8", errors="ignore")


def summarize_fastq_file(path: str | Path, *, max_reads: int = 20000) -> tuple[dict[str, Any], pd.DataFrame]:
    """Compute lightweight FASTQ QC metrics from a sampled subset."""
    fastq_path = Path(path)
    total_reads = 0
    total_bases = 0
    gc_bases = 0
    q20_bases = 0
    q30_bases = 0
    quality_sum = 0.0
    adapter_reads = 0
    read_lengths: list[int] = []
    position_quality_sums: list[float] = []
    position_counts: list[int] = []

    with _open_fastq(fastq_path) as handle:
        while total_reads < max_reads:
            header = handle.readline()
            if not header:
                break
            sequence = handle.readline().strip()
            handle.readline()
            quality = handle.readline().strip()
            if not quality:
                break
            if len(sequence) != len(quality):
                continue

            total_reads += 1
            read_len = len(sequence)
            read_lengths.append(read_len)
            total_bases += read_len
            gc_bases += sequence.upper().count("G") + sequence.upper().count("C")
            if any(seed in sequence for seed in _COMMON_ADAPTER_SEEDS):
                adapter_reads += 1

            qualities = [max(ord(char) - 33, 0) for char in quality]
            quality_sum += float(sum(qualities))
            q20_bases += sum(score >= 20 for score in qualities)
            q30_bases += sum(score >= 30 for score in qualities)

            if len(position_quality_sums) < read_len:
                missing = read_len - len(position_quality_sums)
                position_quality_sums.extend([0.0] * missing)
                position_counts.extend([0] * missing)
            for idx, score in enumerate(qualities):
                position_quality_sums[idx] += score
                position_counts[idx] += 1

    if total_reads == 0 or total_bases == 0:
        raise ValueError(f"No valid FASTQ records were sampled from {fastq_path}")

    per_base = pd.DataFrame(
        {
            "position": np.arange(1, len(position_quality_sums) + 1, dtype=int),
            "mean_quality": [
                position_quality_sums[idx] / position_counts[idx]
                if position_counts[idx] else 0.0
                for idx in range(len(position_quality_sums))
            ],
        }
    )

    metrics = {
        "file": fastq_path.name,
        "path": str(fastq_path),
        "sampled_reads": int(total_reads),
        "mean_read_length": float(np.mean(read_lengths)),
        "median_read_length": float(np.median(read_lengths)),
        "gc_pct": float(100.0 * gc_bases / total_bases),
        "q20_pct": float(100.0 * q20_bases / total_bases),
        "q30_pct": float(100.0 * q30_bases / total_bases),
        "mean_quality": float(quality_sum / total_bases),
        "adapter_seed_pct": float(100.0 * adapter_reads / total_reads),
    }
    return metrics, per_base


def summarize_fastq_samples(
    samples: list[FastqSample],
    *,
    max_reads_per_file: int = 20000,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Summarize all FASTQ files into per-file, per-position, and per-sample tables."""
    per_file_rows: list[dict[str, Any]] = []
    per_base_rows: list[dict[str, Any]] = []

    for sample in samples:
        for read_label, files in (("R1", sample.read1_files), ("R2", sample.read2_files)):
            for fastq in files:
                metrics, curve = summarize_fastq_file(fastq, max_reads=max_reads_per_file)
                metrics["sample_id"] = sample.sample_id
                metrics["read_label"] = read_label
                per_file_rows.append(metrics)
                curve = curve.copy()
                curve["sample_id"] = sample.sample_id
                curve["read_label"] = read_label
                curve["file"] = fastq.name
                per_base_rows.extend(curve.to_dict(orient="records"))

    per_file_df = pd.DataFrame(per_file_rows)
    per_base_df = pd.DataFrame(per_base_rows)
    if per_file_df.empty:
        raise ValueError("No FASTQ summary rows were generated.")

    per_sample_df = (
        per_file_df
        .groupby("sample_id", dropna=False)
        .agg(
            files=("file", "count"),
            sampled_reads=("sampled_reads", "sum"),
            mean_read_length=("mean_read_length", "mean"),
            gc_pct=("gc_pct", "mean"),
            q20_pct=("q20_pct", "mean"),
            q30_pct=("q30_pct", "mean"),
            mean_quality=("mean_quality", "mean"),
            adapter_seed_pct=("adapter_seed_pct", "mean"),
        )
        .reset_index()
    )
    return per_file_df, per_base_df, per_sample_df


def tool_available(name: str) -> bool:
    """Return True when an external command-line tool is on PATH."""
    return shutil.which(name) is not None


def run_command(
    command: list[str],
    *,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> CommandExecution:
    """Run one external command and capture stdout/stderr."""
    workdir = Path(cwd or ".").resolve()
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(workdir),
        env=env or os.environ.copy(),
    )
    execution = CommandExecution(
        command=tuple(str(part) for part in command),
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        cwd=str(workdir),
    )
    if check and result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(command)}\n"
            f"{stderr[:3000]}"
        )
    return execution


def run_fastqc(inputs: list[Path], output_dir: str | Path, *, threads: int = 4) -> CommandExecution | None:
    """Run FastQC when available."""
    if not inputs or not tool_available("fastqc"):
        return None
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    command = ["fastqc", "--quiet", "--threads", str(max(int(threads), 1)), "--outdir", str(outdir)]
    command.extend(str(path) for path in inputs)
    return run_command(command, cwd=outdir)


def run_multiqc(search_dir: str | Path, output_dir: str | Path) -> CommandExecution | None:
    """Run MultiQC on a FastQC output directory when available."""
    if not tool_available("multiqc"):
        return None
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    command = [
        "multiqc",
        str(search_dir),
        "--module",
        "fastqc",
        "--outdir",
        str(outdir),
        "--filename",
        "multiqc_report.html",
        "--force",
        "--quiet",
    ]
    return run_command(command, cwd=outdir)


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return text or "run"


def detect_cellranger_outs(path: str | Path) -> Path | None:
    """Return the Cell Ranger `outs/` directory when it can be recognized."""
    candidate = Path(path)
    if (candidate / "outs").is_dir():
        candidate = candidate / "outs"
    if (candidate / "filtered_feature_bc_matrix.h5").exists() or (candidate / "filtered_feature_bc_matrix").is_dir():
        return candidate
    return None


def detect_starsolo_output(path: str | Path) -> Path | None:
    """Return the STARsolo run directory when it can be recognized."""
    candidate = Path(path)
    if (candidate / "Solo.out" / "Gene").is_dir():
        return candidate
    if candidate.name == "Gene" and (candidate / "filtered").is_dir() and (candidate.parent.name == "Solo.out" or candidate.parent.is_dir()):
        return candidate.parent.parent if candidate.parent.name == "Solo.out" else candidate.parent
    if candidate.name == "filtered" and (candidate / "matrix.mtx").exists():
        gene_dir = candidate.parent
        if gene_dir.name == "Gene":
            return gene_dir.parent.parent if gene_dir.parent.name == "Solo.out" else gene_dir.parent
    return None


def load_count_output_directory(path: str | Path):
    """Load Cell Ranger / STARsolo filtered matrices when detected."""
    target = Path(path)
    cellranger_outs = detect_cellranger_outs(target)
    if cellranger_outs is not None:
        return load_count_adata_from_artifacts(inspect_cellranger_run(cellranger_outs.parent))

    starsolo_dir = detect_starsolo_output(target)
    if starsolo_dir is not None:
        return load_count_adata_from_artifacts(inspect_starsolo_run(starsolo_dir))

    return None


def _read_10x_mtx(path: Path):
    sc = _import_scanpy()
    try:
        return sc.read_10x_mtx(path, var_names="gene_symbols", cache=False)
    except Exception:
        return sc.read_10x_mtx(path, var_names="gene_ids", cache=False)


def inspect_cellranger_run(run_dir: str | Path) -> CountArtifacts:
    """Inspect a completed Cell Ranger count run."""
    run_dir = Path(run_dir)
    outs_dir = detect_cellranger_outs(run_dir)
    if outs_dir is None:
        raise FileNotFoundError(f"Could not locate Cell Ranger outs directory under: {run_dir}")

    return CountArtifacts(
        method="cellranger",
        run_dir=run_dir,
        filtered_matrix_dir=outs_dir / "filtered_feature_bc_matrix" if (outs_dir / "filtered_feature_bc_matrix").is_dir() else None,
        filtered_h5=outs_dir / "filtered_feature_bc_matrix.h5" if (outs_dir / "filtered_feature_bc_matrix.h5").exists() else None,
        raw_matrix_dir=outs_dir / "raw_feature_bc_matrix" if (outs_dir / "raw_feature_bc_matrix").is_dir() else None,
        raw_h5=outs_dir / "raw_feature_bc_matrix.h5" if (outs_dir / "raw_feature_bc_matrix.h5").exists() else None,
        summary_csv=outs_dir / "metrics_summary.csv" if (outs_dir / "metrics_summary.csv").exists() else None,
        html_summary=outs_dir / "web_summary.html" if (outs_dir / "web_summary.html").exists() else None,
        bam_path=outs_dir / "possorted_genome_bam.bam" if (outs_dir / "possorted_genome_bam.bam").exists() else None,
        log_path=run_dir / "_log" if (run_dir / "_log").exists() else None,
    )


def inspect_starsolo_run(run_dir: str | Path) -> CountArtifacts:
    """Inspect a completed STARsolo run directory."""
    run_dir = Path(run_dir)
    starsolo_dir = detect_starsolo_output(run_dir)
    if starsolo_dir is None:
        raise FileNotFoundError(f"Could not locate STARsolo output under: {run_dir}")

    gene_dir = starsolo_dir / "Solo.out" / "Gene"
    return CountArtifacts(
        method="starsolo",
        run_dir=starsolo_dir,
        filtered_matrix_dir=gene_dir / "filtered" if (gene_dir / "filtered").is_dir() else None,
        filtered_h5=None,
        raw_matrix_dir=gene_dir / "raw" if (gene_dir / "raw").is_dir() else None,
        raw_h5=None,
        summary_csv=gene_dir / "Summary.csv" if (gene_dir / "Summary.csv").exists() else None,
        html_summary=None,
        bam_path=starsolo_dir / "Aligned.sortedByCoord.out.bam" if (starsolo_dir / "Aligned.sortedByCoord.out.bam").exists() else None,
        log_path=starsolo_dir / "Log.final.out" if (starsolo_dir / "Log.final.out").exists() else None,
    )


def load_count_adata_from_artifacts(artifacts: CountArtifacts):
    """Load the filtered matrix AnnData for a counting backend run."""
    sc = _import_scanpy()
    if artifacts.filtered_h5 and artifacts.filtered_h5.exists():
        adata = sc.read_10x_h5(artifacts.filtered_h5)
    elif artifacts.filtered_matrix_dir and artifacts.filtered_matrix_dir.exists():
        adata = _read_10x_mtx(artifacts.filtered_matrix_dir)
    else:
        raise FileNotFoundError(f"No filtered matrix output was found for {artifacts.method} under {artifacts.run_dir}")
    return adata


def load_raw_count_adata_from_artifacts(artifacts: CountArtifacts):
    """Load the raw matrix AnnData for a counting backend run when present."""
    sc = _import_scanpy()
    if artifacts.raw_h5 and artifacts.raw_h5.exists():
        return sc.read_10x_h5(artifacts.raw_h5)
    if artifacts.raw_matrix_dir and artifacts.raw_matrix_dir.exists():
        return _read_10x_mtx(artifacts.raw_matrix_dir)
    return None


def standardize_count_adata(
    adata,
    *,
    skill_name: str,
    method: str,
    source_label: str,
    warnings: list[str] | None = None,
):
    """Stabilize a count matrix as a downstream-ready AnnData contract."""
    standardized = adata.copy()
    standardized.obs_names = standardized.obs_names.astype(str)
    standardized.var_names = standardized.var_names.astype(str)
    standardized.obs_names_make_unique()
    standardized.var_names_make_unique()

    if "gene_symbols" not in standardized.var.columns:
        standardized.var["gene_symbols"] = standardized.var_names.astype(str)

    standardized.layers["counts"] = standardized.X.copy()
    standardized.raw = standardized.copy()
    contract = record_standardized_input_contract(
        standardized,
        expression_source=source_label,
        gene_name_source="var.gene_symbols" if "gene_symbols" in standardized.var.columns else "var_names",
        warnings=warnings or [],
        standardizer_skill=skill_name,
    )
    matrix_contract = record_matrix_contract(
        standardized,
        x_kind="raw_counts",
        raw_kind="raw_counts_snapshot",
        layers={"counts": "raw_counts"},
        producer_skill=skill_name,
    )
    store_analysis_metadata(standardized, skill_name, method, {"source_label": source_label})
    contract["matrix_contract"] = matrix_contract
    return standardized, contract


def parse_summary_table(path: str | Path | None) -> dict[str, Any]:
    """Parse a small metrics/summary file into a flat dictionary when possible."""
    if path is None:
        return {}
    table_path = Path(path)
    if not table_path.exists():
        return {}

    try:
        if table_path.suffix.lower() == ".csv":
            df = pd.read_csv(table_path)
            if df.shape[0] == 1:
                return {str(col): df.iloc[0][col] for col in df.columns}
            if df.shape[1] == 2:
                return {str(row[0]): row[1] for row in df.itertuples(index=False, name=None)}
    except Exception:
        pass

    parsed: dict[str, Any] = {}
    for line in table_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "," in line:
            parts = [part.strip() for part in line.split(",", 1)]
        elif "\t" in line:
            parts = [part.strip() for part in line.split("\t", 1)]
        elif "|" in line:
            parts = [part.strip() for part in line.split("|", 1)]
        else:
            parts = [part.strip() for part in line.split(":", 1)]
        if len(parts) != 2:
            continue
        key, value = parts
        if key and value:
            parsed[key] = value
    return parsed


def resolve_starsolo_geometry(chemistry: str) -> dict[str, int]:
    """Return barcode/UMI geometry for the supported STARsolo chemistries."""
    normalized = chemistry.strip().lower()
    if normalized not in _STARSOLO_CHEMISTRY:
        raise ValueError(
            "The current STARsolo wrapper supports `10xv2`, `10xv3`, and `10xv4` chemistries."
        )
    return _STARSOLO_CHEMISTRY[normalized]


def guess_starsolo_whitelist(reference: str | Path, chemistry: str) -> Path | None:
    """Best-effort lookup of a barcode whitelist in common local locations."""
    normalized = chemistry.strip().lower()
    filenames = _STARSOLO_DEFAULT_WHITELIST.get(normalized, ())
    if not filenames:
        return None

    ref = Path(reference).resolve()
    search_dirs = [
        ref / "barcodes",
        ref.parent / "barcodes",
        ref.parent.parent / "barcodes",
        recommended_resource_dir("whitelist"),
    ]
    cellranger_bin = shutil.which("cellranger")
    if cellranger_bin:
        cellranger_root = Path(cellranger_bin).resolve().parent.parent
        search_dirs.append(cellranger_root / "lib" / "python" / "cellranger" / "barcodes")

    for directory in search_dirs:
        for filename in filenames:
            candidate = directory / filename
            if candidate.exists():
                return candidate
    return None


def run_cellranger_count(
    sample: FastqSample,
    *,
    fastq_dir: str | Path,
    reference: str | Path,
    output_dir: str | Path,
    threads: int = 8,
    chemistry: str = "auto",
) -> tuple[CountArtifacts, CommandExecution]:
    """Run Cell Ranger count with a compact wrapper contract."""
    if not tool_available("cellranger"):
        raise RuntimeError("`cellranger` is not installed or not on PATH.")

    artifacts_root = Path(output_dir) / "artifacts" / "cellranger"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    run_id = _slugify(sample.sample_id)
    command = [
        "cellranger",
        "count",
        f"--id={run_id}",
        f"--fastqs={Path(fastq_dir).resolve()}",
        f"--transcriptome={Path(reference).resolve()}",
        f"--sample={sample.sample_id}",
        f"--localcores={max(int(threads), 1)}",
        "--create-bam=true",
        "--nosecondary",
    ]
    if chemistry and chemistry != "auto":
        command.append(f"--chemistry={chemistry}")

    execution = run_command(command, cwd=artifacts_root)
    return inspect_cellranger_run(artifacts_root / run_id), execution


def run_starsolo_count(
    sample: FastqSample,
    *,
    reference: str | Path,
    output_dir: str | Path,
    threads: int = 8,
    chemistry: str,
    whitelist: str | Path,
    features: tuple[str, ...] = ("Gene",),
) -> tuple[CountArtifacts, CommandExecution]:
    """Run STARsolo for one sample with a compact 10x-focused contract."""
    if not tool_available("STAR"):
        raise RuntimeError("`STAR` is not installed or not on PATH.")
    if not sample.is_paired:
        raise ValueError("The current STARsolo wrapper expects paired-end FASTQ input.")

    geometry = resolve_starsolo_geometry(chemistry)
    out_dir = Path(output_dir) / "artifacts" / "starsolo" / _slugify(sample.sample_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    read2 = ",".join(str(path.resolve()) for path in sample.read2_files)
    read1 = ",".join(str(path.resolve()) for path in sample.read1_files)

    command = [
        "STAR",
        "--genomeDir",
        str(Path(reference).resolve()),
        "--runThreadN",
        str(max(int(threads), 1)),
        "--readFilesIn",
        read2,
        read1,
        "--soloType",
        "CB_UMI_Simple",
        "--soloCBwhitelist",
        str(Path(whitelist).resolve()),
        "--soloCBstart",
        str(geometry["cb_start"]),
        "--soloCBlen",
        str(geometry["cb_len"]),
        "--soloUMIstart",
        str(geometry["umi_start"]),
        "--soloUMIlen",
        str(geometry["umi_len"]),
        "--soloBarcodeReadLength",
        "0",
        "--soloCellFilter",
        "EmptyDrops_CR",
        "--soloCBmatchWLtype",
        "1MM_multi_Nbase_pseudocounts",
        "--soloUMIfiltering",
        "MultiGeneUMI_CR",
        "--soloUMIdedup",
        "1MM_CR",
        "--soloFeatures",
        *features,
        "--outSAMtype",
        "BAM",
        "SortedByCoordinate",
        "--outFileNamePrefix",
        f"{out_dir.as_posix()}/",
    ]
    if all(path.name.endswith(".gz") for path in sample.all_files()):
        command.extend(["--readFilesCommand", "zcat"])
    if chemistry in {"10xv3", "10xv4"}:
        command.extend(["--clipAdapterType", "CellRanger4", "--outFilterScoreMin", "30"])

    execution = run_command(command, cwd=out_dir)
    return inspect_starsolo_run(out_dir), execution


def find_starsolo_velocyto_dir(path: str | Path) -> Path | None:
    """Locate STARsolo Velocyto output files."""
    target = Path(path)
    direct_candidates = [
        target / "Solo.out" / "Velocyto" / "raw",
        target / "Solo.out" / "Velocyto",
        target,
    ]
    for candidate in direct_candidates:
        if (candidate / "spliced.mtx").exists() and (candidate / "unspliced.mtx").exists():
            return candidate
    for candidate in target.rglob("spliced.mtx"):
        parent = candidate.parent
        if (parent / "unspliced.mtx").exists() and (parent / "barcodes.tsv").exists():
            return parent
    return None


def load_starsolo_velocyto_dir(path: str | Path):
    """Load STARsolo Velocyto matrices into an AnnData object."""
    import anndata as ad
    sparse, mmread = _import_sparse_helpers()

    velo_dir = find_starsolo_velocyto_dir(path)
    if velo_dir is None:
        raise FileNotFoundError(f"Could not locate STARsolo Velocyto matrices under: {path}")

    barcodes = pd.read_csv(velo_dir / "barcodes.tsv", sep="\t", header=None)[0].astype(str).tolist()
    features_path = velo_dir / "features.tsv"
    if not features_path.exists():
        features_path = velo_dir / "genes.tsv"
    features = pd.read_csv(features_path, sep="\t", header=None)
    gene_ids = features.iloc[:, 0].astype(str)
    gene_symbols = features.iloc[:, 1].astype(str) if features.shape[1] > 1 else gene_ids
    feature_type = features.iloc[:, 2].astype(str) if features.shape[1] > 2 else pd.Series(["Gene Expression"] * len(gene_ids))

    spliced = sparse.csr_matrix(mmread(velo_dir / "spliced.mtx")).transpose().tocsr()
    unspliced = sparse.csr_matrix(mmread(velo_dir / "unspliced.mtx")).transpose().tocsr()
    ambiguous_path = velo_dir / "ambiguous.mtx"
    ambiguous = (
        sparse.csr_matrix(mmread(ambiguous_path)).transpose().tocsr()
        if ambiguous_path.exists() else sparse.csr_matrix(spliced.shape, dtype=spliced.dtype)
    )

    total = spliced + unspliced + ambiguous
    adata = ad.AnnData(X=total)
    adata.obs_names = pd.Index(barcodes, dtype="object")
    adata.var_names = pd.Index(gene_symbols, dtype="object")
    adata.var["gene_ids"] = gene_ids.to_numpy()
    adata.var["gene_symbols"] = gene_symbols.to_numpy()
    adata.var["feature_types"] = feature_type.to_numpy()
    adata.layers["counts"] = total.copy()
    adata.layers["spliced"] = spliced
    adata.layers["unspliced"] = unspliced
    adata.layers["ambiguous"] = ambiguous
    return adata, velo_dir


def load_loom_velocity(path: str | Path):
    """Load a velocyto loom file using Scanpy's loom reader."""
    sc = _import_scanpy()
    loom_path = Path(path)
    if not loom_path.exists():
        raise FileNotFoundError(f"Loom file not found: {loom_path}")
    adata = sc.read_loom(loom_path, sparse=True, cleanup=True)
    if "spliced" not in adata.layers or "unspliced" not in adata.layers:
        raise ValueError(f"{loom_path} did not expose `spliced` and `unspliced` layers after loading.")
    if "counts" not in adata.layers:
        total = adata.layers["spliced"] + adata.layers["unspliced"]
        if "ambiguous" in adata.layers:
            total = total + adata.layers["ambiguous"]
        adata.layers["counts"] = total.copy()
        adata.X = total.copy()
    return adata


def detect_cellranger_bam_and_barcodes(path: str | Path) -> tuple[Path, Path]:
    """Find a Cell Ranger BAM and barcode whitelist from a run directory."""
    outs_dir = detect_cellranger_outs(path)
    if outs_dir is None:
        raise FileNotFoundError(f"Could not locate Cell Ranger outputs under: {path}")

    bam_path = outs_dir / "possorted_genome_bam.bam"
    if not bam_path.exists():
        raise FileNotFoundError(f"Cell Ranger BAM not found: {bam_path}")

    barcode_candidates = [
        outs_dir / "filtered_feature_bc_matrix" / "barcodes.tsv.gz",
        outs_dir / "filtered_feature_bc_matrix" / "barcodes.tsv",
        outs_dir / "raw_feature_bc_matrix" / "barcodes.tsv.gz",
        outs_dir / "raw_feature_bc_matrix" / "barcodes.tsv",
    ]
    for candidate in barcode_candidates:
        if candidate.exists():
            return bam_path, candidate
    raise FileNotFoundError(f"Could not locate Cell Ranger barcode whitelist under: {outs_dir}")


def run_velocyto_from_bam(
    *,
    bam_path: str | Path,
    barcode_path: str | Path,
    gtf_path: str | Path,
    output_dir: str | Path,
    sample_id: str,
    threads: int = 4,
) -> tuple[Path, CommandExecution]:
    """Run velocyto against a BAM plus barcode whitelist to create a loom file."""
    if not tool_available("velocyto"):
        raise RuntimeError("`velocyto` is not installed or not on PATH.")

    out_dir = Path(output_dir) / "artifacts" / "velocyto"
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "velocyto",
        "run",
        "-b",
        str(Path(barcode_path).resolve()),
        "-o",
        str(out_dir.resolve()),
        "-e",
        str(sample_id),
        "-@",
        str(max(int(threads), 1)),
        str(Path(bam_path).resolve()),
        str(Path(gtf_path).resolve()),
    ]
    execution = run_command(command, cwd=out_dir)

    loom_candidates = sorted(out_dir.glob("*.loom"))
    if not loom_candidates:
        raise FileNotFoundError(f"velocyto completed but no loom file was found under {out_dir}")
    return loom_candidates[0], execution


def _normalized_barcode_index(values: pd.Index) -> pd.Index:
    return pd.Index([re.sub(r"-1$", "", str(value)) for value in values], dtype="object")


def merge_velocity_layers(base_adata, velocity_adata):
    """Merge spliced/unspliced layers into a base AnnData object by shared cells and genes."""
    exact_cells = base_adata.obs_names.intersection(velocity_adata.obs_names)
    if len(exact_cells) == 0:
        base_norm = _normalized_barcode_index(base_adata.obs_names)
        velo_norm = _normalized_barcode_index(velocity_adata.obs_names)
        base_map = {base_norm[idx]: base_adata.obs_names[idx] for idx in range(len(base_norm))}
        velo_map = {velo_norm[idx]: velocity_adata.obs_names[idx] for idx in range(len(velo_norm))}
        shared_norm = pd.Index(sorted(set(base_map) & set(velo_map)), dtype="object")
        exact_cells = pd.Index([base_map[item] for item in shared_norm], dtype="object")
        velocity_cells = pd.Index([velo_map[item] for item in shared_norm], dtype="object")
    else:
        velocity_cells = exact_cells

    shared_genes = base_adata.var_names.intersection(velocity_adata.var_names)
    if len(exact_cells) == 0 or len(shared_genes) == 0:
        raise ValueError("Could not align the velocity matrices with the base AnnData object.")

    merged = base_adata[exact_cells, shared_genes].copy()
    velocity_view = velocity_adata[velocity_cells, shared_genes].copy()
    for layer_name in ("spliced", "unspliced", "ambiguous", "counts"):
        if layer_name in velocity_view.layers:
            merged.layers[layer_name] = velocity_view.layers[layer_name].copy()

    merged.uns.setdefault("omicsclaw_velocity_prep", {})
    merged.uns["omicsclaw_velocity_prep"]["shared_cells"] = int(merged.n_obs)
    merged.uns["omicsclaw_velocity_prep"]["shared_genes"] = int(merged.n_vars)
    return merged
