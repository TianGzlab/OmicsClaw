"""
mapping.py — Bulk Hi-C Step 2: reads → ``.pairs`` (4DN / pairtools workflow).

Per sample, both mates are mapped *independently* (``bwa mem -SP5M``: skip
mate-rescue and pairing — chimeric Hi-C molecules must not be "rescued"), then
``pairtools`` extracts, sorts, and deduplicates ligation junctions into a
bgzipped, pairix-indexed ``.pairs`` file:

    bwa-mem2 mem -SP5M -t N <index> R1 R2
      | pairtools parse --min-mapq 30 --walks-policy 5unique
                        --max-inter-align-gap 30 --drop-sam --add-columns mapq
                        --chroms-path <chrom.sizes> --assembly <genome>
      | pairtools sort --nproc N --tmpdir <tmp> -o <sorted.pairs.gz>
    pairtools dedup --output-stats <stats> --output <nodups.pairs.gz> <sorted>
    pairix <nodups.pairs.gz>

The dedup ``--output-stats`` file is the QC source (total / dups / nodups /
cis / trans / cis-distance bins) → the 4DN library-quality metrics in
``bulkhic_qc_criteria``.

Reference prep mirrors the ChIP/ATAC suite (FASTA download + aligner index) but
adds **chrom.sizes** (required by cooler/cooltools downstream), derived offline
from ``samtools faidx`` so it never depends on a UCSC chrom.sizes download. A
local ``reference_<genome>/<genome>.fa`` is reused if already present.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .bulkhic_qc_criteria import (
    CIS_LONG_DISTANCE_BP,
    cis_fraction_tier,
    cis_long_tier,
    cis_trans_ratio_tier,
    duplicate_tier,
    valid_pair_tier,
)

try:
    from omicsclaw.common.runlog import log_tool_output
except Exception:  # pragma: no cover
    def log_tool_output(cmd, result):  # type: ignore
        return None

logger = logging.getLogger(__name__)

_UCSC_FASTA_PATTERN = "https://hgdownload.soe.ucsc.edu/goldenPath/{ref}/bigZips/{ref}.fa.gz"


# ===========================================================================
# Reference files
# ===========================================================================

@dataclass
class GenomeFiles:
    """Resolved reference files for a Hi-C run."""
    genome:         str
    fasta:          Path | None = None
    bwa_index:      Path | None = None
    bwa_mem2_index: Path | None = None
    chrom_sizes:    Path | None = None

    def validate(self, *, require_index: bool = True) -> list[str]:
        errors: list[str] = []
        if require_index and self.bwa_index is None and self.bwa_mem2_index is None:
            errors.append(f"[{self.genome}] No aligner index (--bwa-mem2-index / --bwa-index)")
        if self.bwa_index and not Path(str(self.bwa_index) + ".amb").exists():
            errors.append(f"[{self.genome}] BWA index not found: {self.bwa_index}.amb")
        if self.bwa_mem2_index and not Path(str(self.bwa_mem2_index) + ".bwt.2bit.64").exists():
            errors.append(f"[{self.genome}] BWA-MEM2 index not found: {self.bwa_mem2_index}.bwt.2bit.64")
        if self.chrom_sizes is None:
            errors.append(f"[{self.genome}] chrom.sizes is required for Hi-C (cooler/cooltools)")
        elif not Path(self.chrom_sizes).exists():
            errors.append(f"[{self.genome}] chrom.sizes not found: {self.chrom_sizes}")
        return errors


def validate_genome_files(genome_files: GenomeFiles, *, require_index: bool = True) -> None:
    errors = genome_files.validate(require_index=require_index)
    if errors:
        raise RuntimeError("Reference file validation failed:\n" + "\n".join(f"  {e}" for e in errors))
    logger.info("Reference files validated for genome: %s", genome_files.genome)


def download_genome_fasta(genome: str, output_dir: Path, *, url: str | None = None) -> Path:
    """Download + decompress a reference FASTA (UCSC goldenPath by default)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    url = url or _UCSC_FASTA_PATTERN.format(ref=genome)
    gz_name = url.split("/")[-1]
    gz_path = output_dir / gz_name
    fa_path = output_dir / gz_name.replace(".gz", "")
    if fa_path.exists():
        logger.info("FASTA already exists: %s", fa_path)
        return fa_path
    logger.info("Downloading genome FASTA: %s", url)
    _download_url(url, gz_path)
    tmp_fa = fa_path.with_suffix(".fa.tmp")
    try:
        _run_shell(f"gunzip -c {gz_path} > {tmp_fa}", label=f"gunzip {gz_path.name}")
        tmp_fa.rename(fa_path)
        gz_path.unlink(missing_ok=True)
    except Exception:
        tmp_fa.unlink(missing_ok=True)
        raise
    return fa_path


def write_chrom_sizes(fasta: Path, output_dir: Path, genome: str) -> Path:
    """Derive chrom.sizes offline from ``samtools faidx`` (col1=name, col2=len)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sizes_path = output_dir / f"{genome}.chrom.sizes"
    if sizes_path.exists() and sizes_path.stat().st_size > 0:
        logger.info("chrom.sizes already exists: %s", sizes_path)
        return sizes_path
    fai = Path(str(fasta) + ".fai")
    if not fai.exists():
        _run(["samtools", "faidx", str(fasta)], label=f"samtools faidx [{fasta.name}]")
    rows = [ln.split("\t")[:2] for ln in fai.read_text().splitlines() if ln.strip()]
    sizes_path.write_text("".join(f"{c}\t{n}\n" for c, n in rows))
    logger.info("chrom.sizes written (%d contigs): %s", len(rows), sizes_path)
    return sizes_path


def build_bwa_mem2_index(fasta: Path, index_dir: Path) -> Path:
    _require("bwa-mem2")
    index_dir.mkdir(parents=True, exist_ok=True)
    index_prefix = index_dir / fasta.stem
    if Path(str(index_prefix) + ".bwt.2bit.64").exists():
        logger.info("BWA-MEM2 index already exists: %s.*", index_prefix)
        return index_prefix
    logger.info("Building BWA-MEM2 index: %s → %s.*", fasta.name, index_prefix)
    _run(["bwa-mem2", "index", "-p", str(index_prefix), str(fasta)],
         label=f"bwa-mem2 index [{fasta.name}]")
    return index_prefix


def build_bwa_index(fasta: Path, index_dir: Path) -> Path:
    _require("bwa")
    index_dir.mkdir(parents=True, exist_ok=True)
    index_prefix = index_dir / fasta.stem
    if Path(str(index_prefix) + ".amb").exists():
        logger.info("BWA index already exists: %s.*", index_prefix)
        return index_prefix
    fasta_target = index_prefix.parent / fasta.name
    if not fasta_target.exists():
        fasta_target.symlink_to(fasta.resolve())
    logger.info("Building BWA index: %s → %s.*", fasta.name, index_prefix)
    _run(["bwa", "index", "-p", str(index_prefix), str(fasta_target)],
         label=f"bwa index [{fasta.name}]")
    return index_prefix


def prepare_reference(
    genome: str,
    ref_dir: Path,
    *,
    aligner: str = "bwa-mem2",
    threads: int = 8,  # noqa: ARG001 — symmetry with the ChIP/ATAC API
    fasta_url: str | None = None,
) -> GenomeFiles:
    """Resolve FASTA + aligner index + chrom.sizes for Hi-C.

    A local ``ref_dir/<genome>.fa`` is reused if present (so an offline host
    with a pre-staged reference — e.g. one built by the ChIP/ATAC demos —
    skips the UCSC download). chrom.sizes is always derived locally via faidx.
    """
    ref_dir.mkdir(parents=True, exist_ok=True)
    local_fa = ref_dir / f"{genome}.fa"
    fasta = local_fa if local_fa.exists() else download_genome_fasta(genome, ref_dir, url=fasta_url)

    index_dir = ref_dir / f"{aligner}_index"
    bwa_index = bwa_mem2_index = None
    if aligner == "bwa-mem2":
        bwa_mem2_index = build_bwa_mem2_index(fasta, index_dir)
    elif aligner == "bwa":
        bwa_index = build_bwa_index(fasta, index_dir)
    else:
        raise ValueError(f"Unknown aligner '{aligner}' (use bwa-mem2 or bwa)")

    chrom_sizes = write_chrom_sizes(fasta, ref_dir, genome)
    gf = GenomeFiles(genome=genome, fasta=fasta, bwa_index=bwa_index,
                     bwa_mem2_index=bwa_mem2_index, chrom_sizes=chrom_sizes)
    logger.info("Reference ready for %s:\n  FASTA: %s\n  Index: %s\n  chrom.sizes: %s",
                genome, fasta, bwa_mem2_index or bwa_index, chrom_sizes)
    return gf


# ===========================================================================
# Per-sample mapping → .pairs
# ===========================================================================

@dataclass
class MappingResult:
    """Output of one sample's reads → .pairs run, with pairtools QC."""
    sample_name:     str
    pairs:           Path
    aligner:         str
    n_total:         int = 0
    n_mapped:        int = 0
    n_dups:          int = 0
    n_nodups:        int = 0          # unique valid pairs
    n_cis:           int = 0
    n_trans:         int = 0
    n_cis_long:      int = 0          # cis pairs > CIS_LONG_DISTANCE_BP
    dup_frac:        float = 0.0
    valid_frac:      float = 0.0
    cis_frac:        float = 0.0
    cis_trans_ratio: float = 0.0
    cis_long_frac:   float = 0.0
    stats_file:      Path | None = None


def _index_prefix(genome_files: GenomeFiles, aligner: str) -> Path:
    idx = genome_files.bwa_mem2_index if aligner == "bwa-mem2" else genome_files.bwa_index
    if idx is None:
        raise RuntimeError(f"No {aligner} index in genome_files.")
    return idx


def run_one_mapping(
    sample_name: str,
    r1: Path,
    r2: Path,
    genome_files: GenomeFiles,
    output_dir: Path,
    *,
    aligner: str = "bwa-mem2",
    threads: int = 8,
    min_mapq: int = 30,
) -> MappingResult:
    """bwa-mem2 -SP5M | pairtools parse|sort → dedup → pairix → QC."""
    _require(aligner)
    _require("pairtools")
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = output_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)

    index    = _index_prefix(genome_files, aligner)
    chrom    = genome_files.chrom_sizes
    sorted_p = output_dir / f"{sample_name}.sorted.pairs.gz"
    nodups_p = output_dir / f"{sample_name}.nodups.pairs.gz"
    stats_f  = output_dir / f"{sample_name}.dedup.stats"
    done     = output_dir / f"{sample_name}.mapping.done"

    if done.exists() and nodups_p.exists() and stats_f.exists():
        logger.info("  [%s] checkpoint: pairs + stats present — skipping alignment", sample_name)
        return _result_from_stats(sample_name, nodups_p, aligner, stats_f)

    align = aligner if aligner != "bwa-mem2" else "bwa-mem2"
    pipe = (
        f"{align} mem -SP5M -t {threads} {index} {r1} {r2} "
        f"| pairtools parse --min-mapq {min_mapq} --walks-policy 5unique "
        f"--max-inter-align-gap 30 --drop-sam --add-columns mapq "
        f"--chroms-path {chrom} --assembly {genome_files.genome} "
        f"| pairtools sort --nproc {threads} --tmpdir {tmp_dir} -o {sorted_p}"
    )
    _run_shell(pipe, label=f"bwa-mem2 -SP5M | pairtools parse|sort [{sample_name}]")

    _run_shell(
        f"pairtools dedup --output-stats {stats_f} --output {nodups_p} {sorted_p}",
        label=f"pairtools dedup [{sample_name}]",
    )

    # bgzip-index the pairs for random access (cooler cload reads it directly too).
    if shutil.which("pairix"):
        _run_shell(f"pairix -f {nodups_p}", label=f"pairix [{sample_name}]")

    sorted_p.unlink(missing_ok=True)  # intermediate; nodups is the deliverable
    done.write_text("")
    return _result_from_stats(sample_name, nodups_p, aligner, stats_f)


def run_all_mapping(
    mapping_inputs: list[tuple[str, Path, Path]],
    genome_files: GenomeFiles,
    output_dir: Path,
    *,
    aligner: str = "bwa-mem2",
    threads: int = 8,
    min_mapq: int = 30,
) -> list[MappingResult]:
    results: list[MappingResult] = []
    for name, r1, r2 in mapping_inputs:
        logger.info("Mapping %s → pairs  [%s] ...", name, aligner)
        results.append(run_one_mapping(
            name, r1, r2, genome_files, output_dir / name,
            aligner=aligner, threads=threads, min_mapq=min_mapq,
        ))
    return results


# ===========================================================================
# pairtools stats parsing → QC
# ===========================================================================

def parse_pairtools_stats(stats_file: Path) -> dict[str, int]:
    """Parse the flat ``key<TAB>value`` lines of a pairtools stats file."""
    out: dict[str, int] = {}
    for line in Path(stats_file).read_text().splitlines():
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 2:
            continue
        key, val = parts
        try:
            out[key] = int(val)
        except ValueError:
            continue
    return out


def _result_from_stats(sample_name: str, pairs: Path, aligner: str, stats_file: Path) -> MappingResult:
    s = parse_pairtools_stats(stats_file)
    total   = s.get("total", 0)
    mapped  = s.get("total_mapped", 0)
    dups    = s.get("total_dups", 0)
    nodups  = s.get("total_nodups", 0)
    cis     = s.get("cis", 0)
    trans   = s.get("trans", 0)
    # cis-long: pairtools emits cumulative bins like 'cis_20kb+'
    cis_long = s.get(f"cis_{CIS_LONG_DISTANCE_BP // 1000}kb+", 0)

    dup_frac     = dups / mapped if mapped else 0.0
    valid_frac   = nodups / total if total else 0.0
    cis_frac     = cis / (cis + trans) if (cis + trans) else 0.0
    ct_ratio     = cis / trans if trans else float(cis)
    cis_long_fr  = cis_long / cis if cis else 0.0

    return MappingResult(
        sample_name=sample_name, pairs=pairs, aligner=aligner,
        n_total=total, n_mapped=mapped, n_dups=dups, n_nodups=nodups,
        n_cis=cis, n_trans=trans, n_cis_long=cis_long,
        dup_frac=dup_frac, valid_frac=valid_frac, cis_frac=cis_frac,
        cis_trans_ratio=ct_ratio, cis_long_frac=cis_long_fr,
        stats_file=stats_file,
    )


def write_mapping_summary(results: list[MappingResult], output_dir: Path) -> Path:
    import pandas as pd
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [{
        "sample":          r.sample_name,
        "aligner":         r.aligner,
        "total_pairs":     r.n_total,
        "valid_pairs":     r.n_nodups,
        "valid_frac":      round(r.valid_frac, 4),
        "valid_tier":      valid_pair_tier(r.valid_frac),
        "dup_frac":        round(r.dup_frac, 4),
        "dup_tier":        duplicate_tier(r.dup_frac),
        "cis_frac":        round(r.cis_frac, 4),
        "cis_tier":        cis_fraction_tier(r.cis_frac),
        "cis_trans_ratio": round(r.cis_trans_ratio, 3),
        "cis_trans_tier":  cis_trans_ratio_tier(r.cis_trans_ratio),
        "cis_long_frac":   round(r.cis_long_frac, 4),
        "cis_long_tier":   cis_long_tier(r.cis_long_frac),
    } for r in results]
    path = output_dir / "mapping_summary.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    logger.info("Mapping summary written: %s", path)
    return path


# ===========================================================================
# Internal subprocess helpers
# ===========================================================================

def _require(tool: str) -> None:
    if not shutil.which(tool):
        raise RuntimeError(
            f"'{tool}' not found in PATH.\n"
            f"Install: conda install -c bioconda {tool.replace('_', '-')}"
        )


def _download_url(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("wget"):
        _run(["wget", "-q", "-O", str(dest), url], label=f"wget {dest.name}")
    elif shutil.which("curl"):
        _run(["curl", "-fsSL", "-o", str(dest), url], label=f"curl {dest.name}")
    else:
        import urllib.request
        urllib.request.urlretrieve(url, dest)  # noqa: S310


def _run(cmd: list[str], *, label: str) -> None:
    logger.info("Running: %s", label)
    result = subprocess.run(cmd, capture_output=True, text=True)
    log_tool_output(cmd, result)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {result.returncode}):\n{result.stderr[-3000:]}")


def _run_shell(cmd: str, *, label: str) -> None:
    logger.info("Running: %s", label)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    log_tool_output(cmd, result)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {result.returncode}):\n{result.stderr[-3000:]}")
