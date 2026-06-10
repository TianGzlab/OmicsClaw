"""
mapping.py — Bulk ATAC-seq alignment, BAM filtering, deduplication,
                     library complexity, bigWig generation, and downsampling.

Per-sample: Bowtie2/BWA → ENCODE filter → chrM removal → dedup → blacklist
            → NRF/PBC1/PBC2.  BAMs are NOT Tn5-shifted (downstream tools
            like TOBIAS and MACS2 handle the offset internally).
Cross-sample: downsample to min(n_usable) for comparability.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .encode_qc_criteria import (
    ENCODE_QC_THRESHOLDS,
    UsableReadRule,
    compute_downsample_depth,
    align_rate_tier,
    nrf_tier,
    pbc1_tier,
    pbc2_tier,
    depth_tier,
)

try:
    from omicsclaw.common.runlog import log_tool_output
except Exception:  # pragma: no cover - omicsclaw not importable in isolation
    def log_tool_output(cmd, result):  # type: ignore
        return None

logger = logging.getLogger(__name__)

_MITO_CONTIGS: frozenset[str] = frozenset({"chrM", "chrMT", "MT", "M"})

# ---------------------------------------------------------------------------
# Known reference URLs
# ---------------------------------------------------------------------------

_UCSC_FASTA_PATTERN       = "https://hgdownload.soe.ucsc.edu/goldenPath/{ref}/bigZips/{ref}.fa.gz"
_UCSC_CHROM_SIZES_PATTERN = "https://hgdownload.soe.ucsc.edu/goldenPath/{ref}/bigZips/{ref}.chrom.sizes"

# UCSC ncbiRefSeq GTF — chr-prefixed, matches UCSC FASTA chromosome names
_GTF_URLS: dict[str, str] = {
    "hg38":    "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/genes/hg38.ncbiRefSeq.gtf.gz",
    "hg19":    "https://hgdownload.soe.ucsc.edu/goldenPath/hg19/bigZips/genes/hg19.ncbiRefSeq.gtf.gz",
    "mm10":    "https://hgdownload.soe.ucsc.edu/goldenPath/mm10/bigZips/genes/mm10.ncbiRefSeq.gtf.gz",
    "mm39":    "https://hgdownload.soe.ucsc.edu/goldenPath/mm39/bigZips/genes/mm39.ncbiRefSeq.gtf.gz",
    "dm6":     "https://hgdownload.soe.ucsc.edu/goldenPath/dm6/bigZips/genes/dm6.ncbiRefSeq.gtf.gz",
    "sacCer3": "https://hgdownload.soe.ucsc.edu/goldenPath/sacCer3/bigZips/genes/sacCer3.ncbiRefSeq.gtf.gz",
    "danRer11":"https://hgdownload.soe.ucsc.edu/goldenPath/danRer11/bigZips/genes/danRer11.ncbiRefSeq.gtf.gz",
    "rn6":     "https://hgdownload.soe.ucsc.edu/goldenPath/rn6/bigZips/genes/rn6.ncbiRefSeq.gtf.gz",
    "galGal6": "https://hgdownload.soe.ucsc.edu/goldenPath/galGal6/bigZips/genes/galGal6.ncbiRefSeq.gtf.gz",
}

# ENCODE blacklist BED URLs (Boyle Lab)
_BLACKLIST_URLS: dict[str, str] = {
    "hg38": "https://github.com/Boyle-Lab/Blacklist/raw/master/lists/hg38-blacklist.v2.bed.gz",
    "hg19": "https://github.com/Boyle-Lab/Blacklist/raw/master/lists/hg19-blacklist.v2.bed.gz",
    "mm10": "https://github.com/Boyle-Lab/Blacklist/raw/master/lists/mm10-blacklist.v2.bed.gz",
    "dm6":  "https://github.com/Boyle-Lab/Blacklist/raw/master/lists/dm6-blacklist.v2.bed.gz",
}

# Effective genome sizes for deepTools bamCoverage RPGC normalisation.
# Source: https://github.com/deeptools/deepTools/blob/master/docs/content/feature/effectiveGenomeSize.rst
_EFFECTIVE_GENOME_SIZES: dict[str, int] = {
    "hg38":    2913022398,
    "hg19":    2864785220,
    "mm10":    2652783500,
    "mm39":    2654621783,     # was 2728222451; corrected to deepTools GRCm39
    "dm6":      142573017,
    "dm3":      162367812,
    "sacCer3":   12157105,
    "danRer11": 1368780147,
    "danRer10": 1369631918,
    "ce11":     100286401,
    "rn6":     2647915728,
    "galGal6":  987054996,
    "TAIR10":   119482012,
}


def _ucsc_fasta_url(genome: str) -> str:
    return _UCSC_FASTA_PATTERN.format(ref=genome)


def compute_effective_genome_size(fasta: Path) -> int:
    """
    Compute effective genome size (non-N bases) from a FASTA file.

    Fallback for genomes not in the deepTools lookup table.  Reads the FASTA
    line-by-line and counts A/C/G/T characters (case-insensitive).  For a
    typical vertebrate genome this takes a few minutes but only needs to run
    once — callers should cache the result.
    """
    n_bases = 0
    valid = frozenset(b"ACGTacgt")
    with open(fasta, "rb") as fh:
        for line in fh:
            if line.startswith(b">"):
                continue
            n_bases += sum(1 for ch in line.rstrip() if ch in valid)
    logger.info(
        "Computed effective genome size from %s: %s", fasta.name, f"{n_bases:,}"
    )
    return n_bases


def get_effective_genome_size(
    genome: str,
    fasta: Path | None = None,
) -> int | None:
    """
    Look up effective genome size; fall back to computing from FASTA.

    Returns None only if the genome is unknown *and* no FASTA is provided.
    """
    if genome in _EFFECTIVE_GENOME_SIZES:
        return _EFFECTIVE_GENOME_SIZES[genome]
    if fasta and fasta.exists():
        size = compute_effective_genome_size(fasta)
        # Cache for later calls in the same process
        _EFFECTIVE_GENOME_SIZES[genome] = size
        return size
    logger.warning(
        "Effective genome size unknown for '%s' and no FASTA available "
        "to compute it. Known genomes: %s",
        genome, sorted(_EFFECTIVE_GENOME_SIZES),
    )
    return None


# ===========================================================================
# Reference file records
# ===========================================================================

@dataclass
class GenomeFiles:
    """Paths to reference files required for alignment (Step 2 onwards)."""
    genome:        str
    fasta:         Path | None = None
    bwa_index:     Path | None = None
    bowtie2_index: Path | None = None
    chrom_sizes:   Path | None = None
    gtf:           Path | None = None
    blacklist:     Path | None = None

    def validate(self, *, require_index: bool = True) -> list[str]:
        errors: list[str] = []
        if require_index:
            if self.bwa_index is None and self.bowtie2_index is None:
                errors.append(
                    f"[{self.genome}] No aligner index provided "
                    "(--bwa-index or --bowtie2-index required)"
                )
            if self.bwa_index and not Path(str(self.bwa_index) + ".amb").exists():
                errors.append(
                    f"[{self.genome}] BWA index not found: {self.bwa_index}.amb"
                )
            if self.bowtie2_index and not Path(str(self.bowtie2_index) + ".1.bt2").exists():
                errors.append(
                    f"[{self.genome}] Bowtie2 index not found: {self.bowtie2_index}.1.bt2"
                )
        for attr, label in [
            ("gtf",        "GTF"),
            ("blacklist",  "Blacklist BED"),
            ("chrom_sizes","chrom sizes"),
        ]:
            p = getattr(self, attr)
            if p is not None and not Path(p).exists():
                errors.append(f"[{self.genome}] {label} not found: {p}")
        return errors


def validate_genome_files(
    genome_files: GenomeFiles,
    *,
    require_index: bool = True,
) -> None:
    """Validate reference files. Raises RuntimeError listing all problems."""
    errors = genome_files.validate(require_index=require_index)
    if errors:
        raise RuntimeError(
            "Reference file validation failed:\n"
            + "\n".join(f"  {e}" for e in errors)
        )
    logger.info("Reference files validated for genome: %s", genome_files.genome)


# ===========================================================================
# Reference file helpers
# ===========================================================================

def download_genome_fasta(
    genome: str,
    output_dir: Path,
    *,
    url: str | None = None,
    decompress: bool = True,
) -> Path:
    """
    Download a reference genome FASTA from UCSC goldenPath.

    URL pattern: https://hgdownload.soe.ucsc.edu/goldenPath/{genome}/bigZips/{genome}.fa.gz

    Works for any genome on UCSC (hg38, mm10, dm6, sacCer3, …).
    Pass url to override for non-UCSC genomes.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if url is None:
        url = _ucsc_fasta_url(genome)
        logger.info(
            "FASTA URL auto-constructed (UCSC goldenPath): %s\n"
            "  Pass --fasta-url to override for non-UCSC genomes.",
            url,
        )

    gz_name = url.split("/")[-1]
    gz_path = output_dir / gz_name
    fa_path = output_dir / gz_name.replace(".gz", "")

    if decompress and fa_path.exists():
        logger.info("FASTA already exists: %s", fa_path)
        return fa_path
    if not decompress and gz_path.exists():
        logger.info("FASTA already exists: %s", gz_path)
        return gz_path

    logger.info("Downloading genome FASTA: %s", url)
    _download_url(url, gz_path)

    if decompress:
        logger.info("Decompressing %s ...", gz_path)
        tmp_fa = fa_path.with_suffix(".fa.tmp")
        try:
            _run_shell(
                f"gunzip -c {gz_path} > {tmp_fa}",
                label=f"gunzip {gz_path.name}",
            )
            tmp_fa.rename(fa_path)
            gz_path.unlink(missing_ok=True)
        except Exception:
            tmp_fa.unlink(missing_ok=True)
            raise
        return fa_path

    return gz_path


def download_gtf(
    genome: str,
    output_dir: Path,
    *,
    url: str | None = None,
) -> Path:
    """
    Download a GTF annotation file for the given genome.

    Uses UCSC ncbiRefSeq GTF by default — chromosome names match UCSC FASTA
    (e.g. chrI, chr1 rather than I, 1) so no name-mapping is needed.

    For genomes not in the built-in table, pass url explicitly.
    Returns path to the (possibly gzipped) GTF.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if url is None:
        url = _GTF_URLS.get(genome)
        if url is None:
            raise ValueError(
                f"No built-in GTF URL for genome '{genome}'. "
                f"Pass --gtf or --gtf-url to provide one. "
                f"Known genomes: {sorted(_GTF_URLS)}"
            )

    gz_name  = url.split("/")[-1]
    gz_path  = output_dir / gz_name
    # Keep gzipped — downstream consumers handle .gz natively
    if gz_path.exists():
        logger.info("GTF already exists: %s", gz_path)
        return gz_path

    # Also check for a pre-decompressed copy
    plain_path = output_dir / gz_name.removesuffix(".gz")
    if plain_path.exists():
        logger.info("GTF already exists: %s", plain_path)
        return plain_path

    logger.info("Downloading GTF: %s", url)
    _download_url(url, gz_path)
    return gz_path


def get_chrom_sizes(
    genome: str,
    output_dir: Path,
    *,
    url: str | None = None,
) -> Path:
    """
    Retrieve chromosome sizes for the given genome.

    First tries ``fetchChromSizes`` (UCSC tool); if not available, downloads
    the .chrom.sizes file directly from UCSC goldenPath.

    Returns path to the chrom.sizes file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    sizes_path = output_dir / f"{genome}.chrom.sizes"

    if sizes_path.exists():
        logger.info("Chrom sizes already exist: %s", sizes_path)
        return sizes_path

    # Try fetchChromSizes (UCSC toolkit)
    if shutil.which("fetchChromSizes"):
        logger.info("Running fetchChromSizes %s ...", genome)
        try:
            result = subprocess.run(
                ["fetchChromSizes", genome],
                capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired:
            # fetchChromSizes rsync/ftp's from UCSC with no internal
            # timeout; if it stalls, fall through to the direct download.
            logger.warning("fetchChromSizes timed out — falling back to direct download")
            result = None
        if result is not None and result.returncode == 0 and result.stdout.strip():
            sizes_path.write_text(result.stdout)
            logger.info("Chrom sizes written: %s", sizes_path)
            return sizes_path

    # Download from UCSC
    dl_url = url or _UCSC_CHROM_SIZES_PATTERN.format(ref=genome)
    logger.info("Downloading chrom sizes: %s", dl_url)
    _download_url(dl_url, sizes_path)
    return sizes_path


def download_blacklist(
    genome: str,
    output_dir: Path,
    *,
    url: str | None = None,
) -> Path:
    """Download the ENCODE blacklist BED for a genome build."""
    output_dir.mkdir(parents=True, exist_ok=True)

    if url is None:
        url = _BLACKLIST_URLS.get(genome)
        if url is None:
            raise ValueError(
                f"No known blacklist URL for genome '{genome}'. "
                f"Pass --blacklist-url explicitly. Known genomes: "
                f"{sorted(_BLACKLIST_URLS)}"
            )

    gz_name  = url.split("/")[-1]
    gz_path  = output_dir / gz_name
    bed_path = output_dir / gz_name.replace(".gz", "")

    if bed_path.exists():
        logger.info("Blacklist already exists: %s", bed_path)
        return bed_path

    logger.info("Downloading blacklist: %s", url)
    _download_url(url, gz_path)
    tmp_bed = bed_path.with_suffix(".bed.tmp")
    try:
        _run_shell(f"gunzip -c {gz_path} > {tmp_bed}", label=f"gunzip {gz_path.name}")
        tmp_bed.rename(bed_path)
        gz_path.unlink(missing_ok=True)
    except Exception:
        tmp_bed.unlink(missing_ok=True)
        raise
    return bed_path


def build_bwa_index(
    fasta: Path,
    index_dir: Path | None = None,
) -> Path:
    """
    Build a BWA index from a FASTA file.

    Returns the index prefix (pass this as --genome-index).
    """
    _require("bwa")

    if index_dir is None:
        index_prefix = fasta.parent / fasta.stem
    else:
        index_dir.mkdir(parents=True, exist_ok=True)
        index_prefix = index_dir / fasta.stem

    if Path(str(index_prefix) + ".amb").exists():
        logger.info("BWA index already exists: %s.*", index_prefix)
        return index_prefix

    logger.info("Building BWA index: %s → %s.*", fasta.name, index_prefix)

    fasta_target = index_prefix.parent / fasta.name
    if not fasta_target.exists():
        fasta_target.symlink_to(fasta.resolve())

    _run(
        ["bwa", "index", "-p", str(index_prefix), str(fasta_target)],
        label=f"bwa index [{fasta.name}]",
    )
    logger.info("BWA index ready: %s", index_prefix)
    return index_prefix


def build_bowtie2_index(
    fasta: Path,
    index_dir: Path | None = None,
    *,
    threads: int = 8,
) -> Path:
    """
    Build a Bowtie2 index from a FASTA file.

    Returns the index prefix (pass this as --bowtie2-index).
    """
    _require("bowtie2-build")

    if index_dir is None:
        index_prefix = fasta.parent / fasta.stem
    else:
        index_dir.mkdir(parents=True, exist_ok=True)
        index_prefix = index_dir / fasta.stem

    if Path(str(index_prefix) + ".1.bt2").exists():
        logger.info("Bowtie2 index already exists: %s.*", index_prefix)
        return index_prefix

    logger.info("Building Bowtie2 index: %s → %s.*", fasta.name, index_prefix)
    _run(
        ["bowtie2-build", "--threads", str(threads), str(fasta), str(index_prefix)],
        label=f"bowtie2-build [{fasta.name}]",
    )
    logger.info("Bowtie2 index ready: %s", index_prefix)
    return index_prefix


def prepare_reference(
    genome: str,
    ref_dir: Path,
    *,
    aligner: str = "bowtie2",
    threads: int = 8,
    fasta_url: str | None = None,
    gtf_url: str | None = None,
    blacklist_url: str | None = None,
    download_blacklist_bed: bool = True,
) -> GenomeFiles:
    """
    One-shot helper: download FASTA + build index + download GTF + chrom_sizes
    + download blacklist.

    Layout produced under ref_dir/
    ───────────────────────────────
      {genome}.fa           ← FASTA
      bwa_index/            ← BWA index files
      bowtie2_index/        ← Bowtie2 index files
      {genome}.*.gtf.gz     ← GTF (gzipped)
      {genome}.chrom.sizes  ← chromosome sizes
      blacklist/            ← ENCODE blacklist BED (if available)

    Returns
    -------
    GenomeFiles with all fields populated.
    """
    ref_dir.mkdir(parents=True, exist_ok=True)

    # 1. FASTA
    local_fa    = ref_dir / f"{genome}.fa"
    local_fa_gz = ref_dir / f"{genome}.fa.gz"
    fasta_subdir = ref_dir / "fasta"
    subdir_fa   = fasta_subdir / f"{genome}.fa"

    if local_fa.exists():
        logger.info("FASTA already exists (user-provided): %s", local_fa)
        fasta = local_fa
    elif local_fa_gz.exists():
        logger.info("Decompressing existing %s ...", local_fa_gz.name)
        _run_shell(f"gunzip -k {local_fa_gz}", label=f"gunzip {local_fa_gz.name}")
        fasta = local_fa
    elif subdir_fa.exists():
        logger.info("FASTA already exists (in fasta/): %s", subdir_fa)
        fasta = subdir_fa
    else:
        logger.info("FASTA not found locally — downloading ...")
        fasta = download_genome_fasta(genome, ref_dir, url=fasta_url)

    # 2. Aligner index
    index_dir = ref_dir / f"{aligner}_index"
    if aligner == "bwa":
        index_path = build_bwa_index(fasta, index_dir)
        bwa_index, bowtie2_index = index_path, None
    elif aligner == "bowtie2":
        index_path = build_bowtie2_index(fasta, index_dir, threads=threads)
        bwa_index, bowtie2_index = None, index_path
    else:
        raise ValueError(f"Unknown aligner '{aligner}'")

    # 3. GTF
    # The GTF is optional — only TSS enrichment QC needs it — so ANY failure
    # here (unknown-genome ValueError *or* a download RuntimeError) must be
    # non-fatal: catch broad Exception, warn, and continue without it.
    gtf: Path | None = None
    try:
        gtf = download_gtf(genome, ref_dir, url=gtf_url)
        logger.info("GTF: %s", gtf)
    except Exception as exc:
        logger.warning(
            "GTF download skipped: %s\n"
            "  Pass --gtf to provide one manually.  "
            "TSS enrichment QC will be unavailable.",
            exc,
        )

    # 4. Chrom sizes
    chrom_sizes: Path | None = None
    try:
        chrom_sizes = get_chrom_sizes(genome, ref_dir)
        logger.info("Chrom sizes: %s", chrom_sizes)
    except Exception as exc:
        logger.warning("Chrom sizes download skipped: %s", exc)

    # 5. Blacklist (optional)
    blacklist: Path | None = None
    if download_blacklist_bed:
        try:
            blacklist = download_blacklist(genome, ref_dir / "blacklist", url=blacklist_url)
        except ValueError:
            logger.warning(
                "No blacklist URL known for '%s'. Skipping. Pass --blacklist-url to override.",
                genome,
            )

    genome_files = GenomeFiles(
        genome        = genome,
        fasta         = fasta,
        bwa_index     = bwa_index,
        bowtie2_index = bowtie2_index,
        chrom_sizes   = chrom_sizes,
        gtf           = gtf,
        blacklist     = blacklist,
    )

    logger.info(
        "Reference ready for %s:\n"
        "  FASTA:       %s\n"
        "  Index:       %s\n"
        "  GTF:         %s\n"
        "  Chrom sizes: %s\n"
        "  Blacklist:   %s",
        genome, fasta, index_path,
        gtf or "not downloaded",
        chrom_sizes or "not downloaded",
        blacklist or "not downloaded",
    )
    return genome_files


# ===========================================================================
# Data loading helpers (from Step 1)
# ===========================================================================

def load_step1_result(result_json: Path) -> dict[str, Any]:
    """Load the result.json written by bulkatac-preprocessing (Step 1)."""
    if not result_json.exists():
        raise FileNotFoundError(
            f"Step 1 result not found: {result_json}\n"
            "Run bulkatac-preprocessing first."
        )
    return json.loads(result_json.read_text())


def get_mapping_inputs(
    step1_result: dict[str, Any],
) -> list[tuple[str, Path, Path | None]]:
    """
    Extract [(sample_name, r1_trimmed, r2_trimmed)] from a Step 1 result dict.

    r2_trimmed is None for single-end libraries.
    """
    inputs: list[tuple[str, Path, Path | None]] = []
    for entry in step1_result.get("preprocessing", []):
        r1 = Path(entry["r1_trimmed"])
        r2 = Path(entry["r2_trimmed"]) if entry.get("r2_trimmed") else None
        inputs.append((entry["sample"], r1, r2))
    if not inputs:
        raise ValueError("No preprocessing entries found in Step 1 result.json")
    return inputs


# ===========================================================================
# Result dataclass
# ===========================================================================

@dataclass
class MappingResult:
    """Output of run_mapping() for one sample."""
    sample_name:      str
    bam:              Path           # final deduplicated BAM
    aligner:          str
    # Read counts at each pipeline stage
    n_total_reads:    int   = 0      # raw BAM total reads
    n_mapped_reads:   int   = 0      # mapped reads in raw BAM (before any filter)
    mito_fraction:    float = 0.0    # mito reads / total (raw BAM)
    n_uniquely_mapped:int   = 0      # fragments after ENCODE filter (MAPQ ≥ 30)
    align_rate:       float = 0.0    # n_uniquely_mapped * read_mult / n_total
    n_non_duplicate:  int   = 0      # fragments after dedup
    n_usable:         int   = 0      # fragments in final BAM (post all filters)
    dup_rate:         float = 0.0    # duplicate fraction from markdup stats
    # Library complexity
    nrf:              float = 0.0
    pbc1:             float = 0.0
    pbc2:             float = 0.0
    # Downsampling (disabled by default; enable with --downsample)
    downsampled:      bool  = False
    downsample_target:int | None = None
    bam_downsampled:  Path | None = None
    # Raw text outputs for debugging
    flagstat:         str   = ""
    markdup_stats:    str   = ""

    @property
    def n_fragments(self) -> int:
        """Alias for n_usable (usable fragment count)."""
        return self.n_usable

    @property
    def pct_mito(self) -> float:
        """Mitochondrial read percentage (0–100 scale)."""
        return self.mito_fraction * 100

    @property
    def bam_full(self) -> Path:
        """The non-downsampled final BAM (alias for bam)."""
        return self.bam

    def get_analysis_bam(self) -> Path:
        """Return the BAM used for downstream analysis (downsampled if available)."""
        if self.bam_downsampled and self.bam_downsampled.exists():
            return self.bam_downsampled
        return self.bam


# ===========================================================================
# Public API
# ===========================================================================

def run_mapping(
    sample_name: str,
    r1: str | Path,
    r2: str | Path | None,
    genome_files: GenomeFiles,
    output_dir: Path,
    *,
    aligner: str = "bowtie2",
    threads: int = 8,
    keep_intermediates: bool = False,
) -> MappingResult:
    """
    Align one sample and run the full ENCODE ATAC-seq BAM processing pipeline.

    Pipeline order
    --------------
    1. Align → raw BAM
    2. ENCODE filter (MAPQ ≥ 30, flag filter)
    3. Remove chrM/MT/M   ← before dedup to avoid counting mito duplicates
    4. samtools markdup -r (remove duplicates)
    5. Remove blacklist (if genome_files.blacklist is set)
    6. Library complexity: NRF, PBC1, PBC2
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    is_paired = r2 is not None

    index = genome_files.bwa_index if aligner == "bwa" else genome_files.bowtie2_index
    if index is None:
        raise ValueError(
            f"No {aligner} index in genome_files. "
            "Run prepare_reference() or pass the index explicitly."
        )

    # ── Checkpoint: skip only if .done marker exists ─────────────────────
    # The .done marker is written at the very end of run_mapping() AFTER
    # all steps succeed.  If the pipeline crashed mid-way, no marker is
    # written and any partial files are cleaned up and redone.
    done_marker = output_dir / f"{sample_name}.mapping.done"
    dedup_bam   = output_dir / f"{sample_name}.dedup.bam"
    pbc_file    = output_dir / f"{sample_name}.pbc.txt"
    stats_file  = output_dir / f"{sample_name}.markdup_stats.txt"

    if done_marker.exists() and dedup_bam.exists():
        logger.info("  [%s] checkpoint: mapping already complete — loading cached stats",
                     sample_name)
        # Reload from cached files
        final_bam = dedup_bam
        bl_bam = output_dir / f"{sample_name}.no_blacklist.bam"
        if bl_bam.exists():
            final_bam = bl_bam

        cached          = json.loads(done_marker.read_text())
        nrf, pbc1, pbc2 = _parse_pbc(pbc_file, sample_name)
        markdup_stats   = stats_file.read_text() if stats_file.exists() else ""
        dup_rate        = _parse_markdup_stats(markdup_stats)
        final_flagstat  = _flagstat(final_bam)

        return MappingResult(
            sample_name       = sample_name,
            bam               = final_bam,
            aligner           = aligner,
            n_total_reads     = cached.get("n_total_reads", 0),
            n_mapped_reads    = cached.get("n_mapped_reads", 0),
            mito_fraction     = cached.get("mito_fraction", 0.0),
            n_uniquely_mapped = cached.get("n_uniquely_mapped", 0),
            align_rate        = cached.get("align_rate", 0.0),
            n_non_duplicate   = cached.get("n_non_duplicate", 0),
            n_usable          = cached.get("n_usable", 0),
            dup_rate          = dup_rate,
            nrf               = nrf,
            pbc1              = pbc1,
            pbc2              = pbc2,
            flagstat          = final_flagstat,
            markdup_stats     = markdup_stats,
        )
    else:
        # Previous run may have crashed — clean up partial files
        for partial in (
            dedup_bam,
            Path(str(dedup_bam) + ".bai"),
            output_dir / f"{sample_name}.no_blacklist.bam",
            output_dir / f"{sample_name}.no_blacklist.bam.bai",
        ):
            if partial.exists() and not done_marker.exists():
                logger.warning("  [%s] removing partial file from crashed run: %s",
                               sample_name, partial.name)
                _rm(partial)

    # ── 1. Align ────────────────────────────────────────────────────────────
    raw_bam = _align(
        sample_name, Path(r1), Path(r2) if r2 else None,
        index, output_dir,
        aligner=aligner, threads=threads, is_paired=is_paired,
    )

    raw_flagstat       = _flagstat(raw_bam)
    n_total, n_mapped_raw = _parse_flagstat_reads(raw_flagstat)
    n_mito             = _count_mito_reads(raw_bam)
    mito_fraction      = n_mito / n_total if n_total > 0 else 0.0

    logger.info(
        "  [%s] raw: %d total reads  |  %.1f%% mito",
        sample_name, n_total, mito_fraction * 100,
    )

    # ── 2. ENCODE BAM filter (MAPQ ≥ 30  =  uniquely mapped) ────────────────
    filtered_bam = _filter_bam(
        sample_name, raw_bam, output_dir, threads=threads, is_paired=is_paired
    )
    filt_flagstat       = _flagstat(filtered_bam)
    _, n_mapped_filt    = _parse_flagstat_reads(filt_flagstat)
    n_uniquely_mapped   = n_mapped_filt // 2 if is_paired else n_mapped_filt
    align_rate          = (
        n_mapped_filt / n_total if n_total > 0 else 0.0
    )

    logger.info(
        "  [%s] after ENCODE filter: %d uniquely mapped fragments  |  %.1f%% align rate",
        sample_name, n_uniquely_mapped, align_rate * 100,
    )

    # ── 3. Remove chrM (before dedup) ───────────────────────────────────────
    no_mito_bam = _remove_mito(sample_name, filtered_bam, output_dir, threads=threads)

    # ── 4. samtools markdup (remove duplicates) ──────────────────────────────
    dedup_bam, markdup_stats, dup_rate = _dedup_bam(
        sample_name, no_mito_bam, output_dir, threads=threads
    )
    dedup_flagstat     = _flagstat(dedup_bam)
    _, n_mapped_dedup  = _parse_flagstat_reads(dedup_flagstat)
    n_non_duplicate    = n_mapped_dedup // 2 if is_paired else n_mapped_dedup

    logger.info(
        "  [%s] after dedup: %d non-dup fragments  |  dup rate=%.1f%%",
        sample_name, n_non_duplicate, dup_rate * 100,
    )

    # ── 5. Remove blacklist (optional) ──────────────────────────────────────
    final_bam = dedup_bam
    bl = genome_files.blacklist
    if bl and Path(bl).exists():
        final_bam = _remove_blacklist(sample_name, dedup_bam, Path(bl), output_dir)

    final_flagstat    = _flagstat(final_bam)
    _, n_mapped_final = _parse_flagstat_reads(final_flagstat)
    n_usable          = n_mapped_final // 2 if is_paired else n_mapped_final

    logger.info(
        "  [%s] usable: %d fragments  (NRF/PBC computing ...)",
        sample_name, n_usable,
    )

    # ── 6. Library complexity ────────────────────────────────────────────────
    nrf, pbc1, pbc2 = _compute_library_complexity(
        sample_name, final_bam, output_dir, is_paired=is_paired
    )

    # ── 7. Cleanup ───────────────────────────────────────────────────────────
    if not keep_intermediates:
        for tmp in (raw_bam, filtered_bam, no_mito_bam):
            if tmp != final_bam:
                _rm(tmp); _rm(Path(str(tmp) + ".bai"))
        if dedup_bam != final_bam:
            _rm(dedup_bam); _rm(Path(str(dedup_bam) + ".bai"))

    # ── Write .done marker (only after all steps succeeded) ───────────────
    # Stores stats so checkpoint reload can recover exact values even after
    # intermediate BAMs are cleaned up.
    done_marker.write_text(json.dumps({
        "sample_name":       sample_name,
        "aligner":           aligner,
        "n_total_reads":     n_total,
        "n_mapped_reads":    n_mapped_raw,
        "mito_fraction":     mito_fraction,
        "n_uniquely_mapped": n_uniquely_mapped,
        "align_rate":        align_rate,
        "n_non_duplicate":   n_non_duplicate,
        "n_usable":          n_usable,
    }))

    return MappingResult(
        sample_name       = sample_name,
        bam               = final_bam,
        aligner           = aligner,
        n_total_reads     = n_total,
        n_mapped_reads    = n_mapped_raw,
        mito_fraction     = mito_fraction,
        n_uniquely_mapped = n_uniquely_mapped,
        align_rate        = align_rate,
        n_non_duplicate   = n_non_duplicate,
        n_usable          = n_usable,
        dup_rate          = dup_rate,
        nrf               = nrf,
        pbc1              = pbc1,
        pbc2              = pbc2,
        flagstat          = final_flagstat,
        markdup_stats     = markdup_stats,
    )


def run_all_mapping(
    mapping_inputs: list[tuple[str, Path, Path | None]],
    genome_files: GenomeFiles,
    output_dir: Path,
    *,
    aligner: str = "bowtie2",
    threads: int = 8,
    downsample: bool = False,
    keep_intermediates: bool = False,
) -> list[MappingResult]:
    """
    Align all samples.  By default, full-depth deduplicated BAMs are kept
    for all downstream steps (peak calling, counting, differential analysis).
    RPGC-normalised BigWigs handle depth differences for visualisation.

    Pass ``downsample=True`` to equalise all samples to the minimum usable
    depth (useful for specific QC comparisons, but not recommended for
    peak calling or differential analysis).

    Parameters
    ----------
    mapping_inputs : list of (sample_name, r1_path, r2_path_or_None)
    genome_files   : GenomeFiles with index (and optionally blacklist)
    output_dir     : root dir for per-sample BAM files
    downsample     : equalise depths to min(n_usable) (default False)
    """
    results: list[MappingResult] = []
    is_paired = any(r2 is not None for _, _, r2 in mapping_inputs)
    output_dir.mkdir(parents=True, exist_ok=True)

    for sample_name, r1, r2 in mapping_inputs:
        logger.info(
            "Mapping %s  [%s] ...",
            sample_name, "paired-end" if r2 else "single-end",
        )
        result = run_mapping(
            sample_name, r1, r2,
            genome_files, output_dir,
            aligner=aligner, threads=threads,
            keep_intermediates=keep_intermediates,
        )
        results.append(result)
        logger.info(
            "  %s: %.1f%% aligned | %d usable frags | dup=%.1f%% | "
            "NRF=%.3f PBC1=%.3f PBC2=%.2f",
            sample_name,
            result.align_rate * 100,
            result.n_usable,
            result.dup_rate * 100,
            result.nrf, result.pbc1, result.pbc2,
        )

    # Optional cross-sample downsampling (disabled by default)
    if downsample and len(results) > 1:
        layout = "paired-end" if is_paired else "single-end"
        usable_counts = {r.sample_name: r.n_usable for r in results}
        ds_config = compute_downsample_depth(usable_counts, layout=layout)

        if ds_config.needs_downsampling:
            logger.info(
                "Downsampling all samples to %d usable fragments.", ds_config.target_depth
            )
            results = _downsample_all(results, ds_config, threads=threads)
        else:
            logger.info("No downsampling needed — all samples at equal depth.")

    return results


# ===========================================================================
# BigWig generation
# ===========================================================================

def generate_bigwig(
    sample_name: str,
    bam: Path,
    output_dir: Path,
    *,
    genome: str | None = None,
    genome_fasta: Path | None = None,
    bin_size: int = 10,
    threads: int = 8,
    downsampled: bool = False,
) -> Path | None:
    """
    Generate an RPGC-normalised bigWig using deepTools bamCoverage.

    RPGC (Reads Per Genomic Content / 1x coverage) is the ENCODE standard
    for ATAC-seq signal tracks.  It normalises by effective genome size so
    that signal is comparable across samples with different library sizes.

    Safety flags ``--ignoreDuplicates`` and ``--minMappingQuality 30`` are
    added as defensive measures — our BAMs are already deduped and
    MAPQ-filtered, but these guard against edge cases at zero cost.

    Parameters
    ----------
    bam          : BAM file to convert (index must exist)
    genome       : genome build string for effective genome size lookup
    genome_fasta : reference FASTA — used to compute effective genome size
                   on the fly when *genome* is not in the lookup table
    bin_size     : binSize for bamCoverage (default 10 bp)
    threads      : number of threads for bamCoverage
    downsampled  : if True, tag filename as .ds.rpgc.bw

    Returns
    -------
    Path to the bigWig file, or None if deeptools is not installed.
    """
    if not _check_tool("bamCoverage"):
        logger.warning(
            "bamCoverage (deeptools) not found — skipping bigWig for %s. "
            "Install with: conda install -c bioconda deeptools",
            sample_name,
        )
        return None

    eff_size = get_effective_genome_size(genome, fasta=genome_fasta) if genome else None
    if eff_size is None:
        logger.warning(
            "Effective genome size unknown for '%s' and no FASTA provided "
            "— skipping bigWig for %s.",
            genome, sample_name,
        )
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "ds.rpgc.bw" if downsampled else "rpgc.bw"
    bw_path = output_dir / f"{sample_name}.{suffix}"

    if bw_path.exists():
        logger.info("BigWig already exists: %s", bw_path)
        return bw_path

    cmd = [
        "bamCoverage",
        "-b",   str(bam),
        "-o",   str(bw_path),
        "--normalizeUsing",     "RPGC",
        "--effectiveGenomeSize", str(eff_size),
        "--binSize",             str(bin_size),
        "--extendReads",
        "--ignoreDuplicates",
        "--minMappingQuality",   "30",
        "-p",                    str(threads),
    ]

    try:
        _run(cmd, label=f"bamCoverage RPGC [{sample_name}]")
        logger.info("BigWig written: %s", bw_path)
        return bw_path
    except RuntimeError as exc:
        logger.warning("bamCoverage failed for %s: %s", sample_name, exc)
        return None


def generate_all_bigwigs(
    results: list[MappingResult],
    output_dir: Path,
    *,
    genome: str | None = None,
    genome_fasta: Path | None = None,
    bin_size: int = 10,
    threads: int = 8,
) -> dict[str, Path]:
    """
    Generate bigWig for each sample.

    Uses bam_downsampled (if available) for comparability — all samples
    should be at the same depth when bigWigs are generated.

    Returns
    -------
    {sample_name: bigwig_path}
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    bigwig_paths: dict[str, Path] = {}

    for r in results:
        bam = r.bam_downsampled if r.bam_downsampled else r.bam
        bw = generate_bigwig(
            r.sample_name, bam, output_dir,
            genome=genome, genome_fasta=genome_fasta,
            bin_size=bin_size, threads=threads,
            downsampled=r.downsampled,
        )
        if bw:
            bigwig_paths[r.sample_name] = bw

    return bigwig_paths


# ===========================================================================
# Alignment helpers
# ===========================================================================

def _align(
    sample_name: str,
    r1: Path, r2: Path | None,
    index: Path, output_dir: Path,
    *, aligner: str, threads: int, is_paired: bool,
) -> Path:
    _require("samtools")
    raw_bam = output_dir / f"{sample_name}.raw.bam"

    if raw_bam.exists():
        logger.info("Raw BAM already exists — skipping alignment: %s", raw_bam)
        _index_bam(raw_bam, threads=threads)
        return raw_bam

    if aligner == "bwa":
        _require("bwa")
        reads = f"{r1} {r2}" if is_paired else str(r1)
        align_cmd = f"bwa mem -t {threads} {index} {reads}"
    elif aligner == "bowtie2":
        _require("bowtie2")
        if is_paired:
            align_cmd = (
                f"bowtie2 -x {index} -1 {r1} -2 {r2} "
                f"--local --very-sensitive --no-mixed --no-discordant "
                f"-I 25 -X 700 -p {threads}"
            )
        else:
            align_cmd = (
                f"bowtie2 -x {index} -U {r1} "
                f"--local --very-sensitive -p {threads}"
            )
    else:
        raise ValueError(f"Unknown aligner '{aligner}'")

    cmd = f"{align_cmd} | samtools sort -@ {threads} -o {raw_bam} -"
    _run_shell(cmd, label=f"{aligner.upper()} [{sample_name}]")
    _index_bam(raw_bam, threads=threads)
    return raw_bam


def _filter_bam(
    sample_name: str, bam: Path, output_dir: Path,
    *, threads: int, is_paired: bool,
) -> Path:
    """ENCODE BAM filter: PE -F 1804 -f 2 -q 30 | SE -F 1796 -q 30"""
    _require("samtools")
    out      = output_dir / f"{sample_name}.filtered.bam"
    if out.exists():
        return out
    req_args = ["-f", "2"] if is_paired else []
    excl     = "1804" if is_paired else "1796"
    cmd = ["samtools", "view", "-F", excl, *req_args,
           "-q", "30", "-b", "-@", str(threads), "-o", str(out), str(bam)]
    _run(cmd, label=f"samtools filter [{sample_name}]")
    _index_bam(out, threads=threads)
    return out


def _dedup_bam(
    sample_name: str, bam: Path, output_dir: Path, *, threads: int = 8
) -> tuple[Path, str, float]:
    """
    Remove PCR duplicates using samtools markdup.

    Pipeline:
      1. samtools sort -n   (name-sort — required by samtools fixmate)
      2. samtools fixmate -m
      3. samtools sort      (re-sort by coordinate)
      4. samtools markdup -r (mark AND remove duplicates)
      5. samtools index
    """
    _require("samtools")

    namesorted = output_dir / f"{sample_name}.namesorted.bam"
    fixmated   = output_dir / f"{sample_name}.fixmated.bam"
    out        = output_dir / f"{sample_name}.dedup.bam"
    stats_file = output_dir / f"{sample_name}.markdup_stats.txt"

    if out.exists():
        stats_text = stats_file.read_text() if stats_file.exists() else ""
        return out, stats_text, _parse_markdup_stats(stats_text)

    _run(
        ["samtools", "sort", "-n", "-@", str(threads), "-o", str(namesorted), str(bam)],
        label=f"samtools sort -n [{sample_name}]",
    )
    _run(
        ["samtools", "fixmate", "-m", "-@", str(threads), str(namesorted), str(fixmated)],
        label=f"samtools fixmate [{sample_name}]",
    )
    _run(
        ["samtools", "sort", "-@", str(threads), "-o", str(out), str(fixmated)],
        label=f"samtools sort [{sample_name}]",
    )
    _run(
        ["samtools", "markdup", "-r",
         "-f", str(stats_file),
         "-@", str(threads), str(out), str(out) + ".tmp"],
        label=f"samtools markdup [{sample_name}]",
    )
    shutil.move(str(out) + ".tmp", str(out))
    _index_bam(out, threads=threads)

    _rm(namesorted); _rm(fixmated)
    _rm(Path(str(namesorted) + ".bai")); _rm(Path(str(fixmated) + ".bai"))

    stats_text = stats_file.read_text() if stats_file.exists() else ""
    dup_rate   = _parse_markdup_stats(stats_text)
    return out, stats_text, dup_rate


def _parse_markdup_stats(stats_text: str) -> float:
    """Parse duplicate rate from samtools markdup -f output."""
    if not stats_text.strip():
        return 0.0
    try:
        read_count = dup_count = 0
        for line in stats_text.splitlines():
            line = line.strip()
            if line.startswith("READ:"):
                read_count = int(line.split(":")[-1].strip())
            elif line.startswith("DUPLICATE TOTAL:"):
                dup_count = int(line.split(":")[-1].strip())
        return round(dup_count / read_count, 6) if read_count > 0 else 0.0
    except Exception:
        return 0.0


def _remove_mito(
    sample_name: str, bam: Path, output_dir: Path, *, threads: int
) -> Path:
    _require("samtools")
    out = output_dir / f"{sample_name}.no_mito.bam"
    if out.exists():
        return out
    result = subprocess.run(
        ["samtools", "idxstats", str(bam)], capture_output=True, text=True, check=True
    )
    keep = [
        l.split("\t")[0] for l in result.stdout.strip().split("\n")
        if l.split("\t")[0] not in _MITO_CONTIGS and l.split("\t")[0] not in ("*", "")
    ]
    if not keep:
        logger.warning("[%s] No non-mito chromosomes found — skipping chrM removal.", sample_name)
        return bam
    _run(
        ["samtools", "view", "-b", "-@", str(threads), "-o", str(out), str(bam)] + keep,
        label=f"Remove chrM [{sample_name}]",
    )
    _index_bam(out, threads=threads)
    return out


def _remove_blacklist(
    sample_name: str, bam: Path, blacklist: Path, output_dir: Path
) -> Path:
    _require("bedtools")
    out = output_dir / f"{sample_name}.no_blacklist.bam"
    if out.exists():
        return out
    _run_shell(
        f"bedtools intersect -v -abam {bam} -b {blacklist} > {out}",
        label=f"Blacklist filter [{sample_name}]",
    )
    _index_bam(out)
    return out


# ===========================================================================
# Library complexity: NRF, PBC1, PBC2
# ===========================================================================

def _compute_library_complexity(
    sample_name: str, bam: Path, output_dir: Path, *, is_paired: bool
) -> tuple[float, float, float]:
    _require("bedtools")
    pbc_file = output_dir / f"{sample_name}.pbc.txt"

    if pbc_file.exists() and pbc_file.stat().st_size > 0:
        return _parse_pbc(pbc_file, sample_name)

    if is_paired:
        namesorted = output_dir / f"{sample_name}.namesorted_pbc.bam"
        _run(
            ["samtools", "sort", "-n", "-o", str(namesorted), str(bam)],
            label=f"Name-sort [{sample_name}]",
        )
        cmd = (
            f"bedtools bamtobed -bedpe -i {namesorted} "
            f"| awk 'BEGIN{{OFS=\"\\t\"}}{{print $1,$2,$4,$6,$9,$10}}' "
            f"| grep -v 'chrM\\|chrMT\\|^MT\\t\\|^M\\t' "
            f"| sort | uniq -c "
            f"| awk 'BEGIN{{mt=0;m0=0;m1=0;m2=0}} "
            f"($1==1){{m1++}} ($1==2){{m2++}} {{m0++; mt+=$1}} "
            f"END{{printf \"%d\\t%d\\t%d\\t%d\\n\",mt,m0,m1,m2}}' > {pbc_file}"
        )
        _run_shell(cmd, label=f"PBC PE [{sample_name}]")
        _rm(namesorted); _rm(Path(str(namesorted) + ".bai"))
    else:
        cmd = (
            f"bedtools bamtobed -i {bam} "
            f"| awk 'BEGIN{{OFS=\"\\t\"}}{{print $1,$2,$3,$6}}' "
            f"| grep -v 'chrM\\|chrMT\\|^MT\\t\\|^M\\t' "
            f"| sort | uniq -c "
            f"| awk 'BEGIN{{mt=0;m0=0;m1=0;m2=0}} "
            f"($1==1){{m1++}} ($1==2){{m2++}} {{m0++; mt+=$1}} "
            f"END{{printf \"%d\\t%d\\t%d\\t%d\\n\",mt,m0,m1,m2}}' > {pbc_file}"
        )
        _run_shell(cmd, label=f"PBC SE [{sample_name}]")

    return _parse_pbc(pbc_file, sample_name)


def _parse_pbc(pbc_file: Path, sample_name: str) -> tuple[float, float, float]:
    if not pbc_file.exists() or pbc_file.stat().st_size == 0:
        logger.warning("[%s] PBC file empty — library complexity not computed.", sample_name)
        return 0.0, 0.0, 0.0
    parts = pbc_file.read_text().strip().split("\t")
    if len(parts) < 4:
        logger.warning("[%s] PBC file malformed.", sample_name)
        return 0.0, 0.0, 0.0
    try:
        mt, m0, m1, m2 = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        return 0.0, 0.0, 0.0
    nrf  = m0 / mt if mt > 0 else 0.0
    pbc1 = m1 / m0 if m0 > 0 else 0.0
    pbc2 = m1 / m2 if m2 > 0 else 0.0
    logger.info(
        "  [%s] NRF=%.3f PBC1=%.3f PBC2=%.2f (T=%d D=%d 1R=%d 2R=%d)",
        sample_name, nrf, pbc1, pbc2, mt, m0, m1, m2,
    )
    return nrf, pbc1, pbc2


# ===========================================================================
# Downsampling
# ===========================================================================

def _downsample_all(
    results: list[MappingResult],
    ds_config,    # DownsampleConfig from encode_qc_criteria
    *,
    threads: int = 8,
) -> list[MappingResult]:
    target = ds_config.target_depth
    for result in results:
        result.downsample_target = target
        if result.n_usable <= target:
            logger.info(
                "  [%s] %d usable frags ≤ target %d — symlink as .ds for uniform naming.",
                result.sample_name, result.n_usable, target,
            )
            # Symlink dedup BAM as .ds.bam for consistent naming across samples
            ds_bam = result.bam.parent / f"{result.sample_name}.ds.bam"
            ds_bai = Path(str(ds_bam) + ".bai")
            if not ds_bam.exists():
                os.symlink(result.bam.resolve(), ds_bam)
            if not ds_bai.exists():
                src_bai = Path(str(result.bam) + ".bai")
                if src_bai.exists():
                    os.symlink(src_bai.resolve(), ds_bai)
            result.bam_downsampled = ds_bam
            result.downsampled     = True
            continue

        fraction = ds_config.downsample_fraction(result.sample_name)
        ds_bam   = result.bam.parent / f"{result.sample_name}.ds.bam"
        ds_bai   = Path(str(ds_bam) + ".bai")

        # Checkpoint: skip if downsampled BAM + index already exist
        if ds_bam.exists() and ds_bai.exists():
            logger.info("  [%s] checkpoint: downsampled BAM exists — skipping",
                        result.sample_name)
            result.bam_downsampled = ds_bam
            result.downsampled     = True
            continue

        logger.info(
            "  [%s] Downsampling %d → %d frags (fraction=%.4f) ...",
            result.sample_name, result.n_usable, target, fraction,
        )
        _require("samtools")
        # Write to temp, rename on success to avoid corrupted checkpoint
        ds_tmp = result.bam.parent / f"{result.sample_name}.ds.tmp.bam"
        _run(
            ["samtools", "view", "-@", str(threads), "-b",
             "--subsample", str(fraction), "--subsample-seed", "42",
             "-o", str(ds_tmp), str(result.bam)],
            label=f"Downsample [{result.sample_name}]",
        )
        shutil.move(str(ds_tmp), str(ds_bam))
        _index_bam(ds_bam, threads=threads)
        result.bam_downsampled = ds_bam
        result.downsampled     = True

    return results


# ===========================================================================
# Summary helpers
# ===========================================================================

def build_mapping_summary(results: list[MappingResult]) -> "pd.DataFrame":  # type: ignore[name-defined]
    import pandas as pd

    rows = []
    for r in results:
        row: dict[str, Any] = {
            "sample":             r.sample_name,
            "aligner":            r.aligner,
            "n_total_reads":      r.n_total_reads,
            "n_uniquely_mapped":  r.n_uniquely_mapped,
            "align_rate":         round(r.align_rate, 4),
            "mito_fraction":      round(r.mito_fraction, 4),
            "n_non_duplicate":    r.n_non_duplicate,
            "n_usable":           r.n_usable,
            "dup_rate":           round(r.dup_rate, 4),
            "nrf":                round(r.nrf, 4),
            "pbc1":               round(r.pbc1, 4),
            "pbc2":               round(r.pbc2, 3),
            "align_tier":         align_rate_tier(r.align_rate),
            "nrf_tier":           nrf_tier(r.nrf),
            "pbc1_tier":          pbc1_tier(r.pbc1),
            "pbc2_tier":          pbc2_tier(r.pbc2),
            "downsampled":        r.downsampled,
            "downsample_target":  r.downsample_target,
            "bam":                str(r.bam),
            "bam_downsampled":    str(r.bam_downsampled) if r.bam_downsampled else "",
        }
        rows.append(row)
    return pd.DataFrame(rows)


def write_mapping_summary(results: list[MappingResult], output_dir: Path) -> Path:
    df   = build_mapping_summary(results)
    path = output_dir / "mapping_summary.csv"
    df.to_csv(path, index=False)
    logger.info("Mapping summary written: %s", path)
    return path


# ===========================================================================
# Utility helpers
# ===========================================================================

def _download_url(url: str, dest: Path) -> None:
    """Download *url* to *dest*, writing to a temp file first.

    The final file only appears after a successful download, so a
    partial/corrupt file from an interrupted run will never be treated
    as a valid checkpoint.

    Stall guards bound every transfer: a connection that opens but then
    delivers no data — common for hgdownload.soe.ucsc.edu from some
    networks — fails within ~1 min with a clear error instead of hanging
    the whole skill indefinitely. ``-q`` is dropped so the timeout reason
    reaches the captured stderr and surfaces in the raised RuntimeError.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    _CONNECT_TIMEOUT = 30   # seconds to establish the connection
    _STALL_TIMEOUT   = 60   # seconds with no progress → abort
    try:
        if shutil.which("wget"):
            _run(["wget", "-nv", "--tries=3",
                  f"--dns-timeout={_CONNECT_TIMEOUT}",
                  f"--connect-timeout={_CONNECT_TIMEOUT}",
                  f"--read-timeout={_STALL_TIMEOUT}",
                  "-O", str(tmp), url], label=f"wget {dest.name}")
        elif shutil.which("curl"):
            # --speed-time/--speed-limit abort if throughput stays under
            # 1 KB/s for _STALL_TIMEOUT s — catches a stalled connection
            # without penalising a slow-but-progressing download.
            _run(["curl", "-fsSL",
                  "--connect-timeout", str(_CONNECT_TIMEOUT),
                  "--speed-time", str(_STALL_TIMEOUT), "--speed-limit", "1024",
                  "--retry", "3",
                  "-o", str(tmp), url], label=f"curl {dest.name}")
        else:
            raise RuntimeError(
                "Neither wget nor curl found in PATH. "
                "Install: conda install -c conda-forge wget"
            )
        tmp.rename(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _require(tool: str) -> None:
    if not shutil.which(tool):
        raise RuntimeError(
            f"'{tool}' not found in PATH.\n"
            f"Install: conda install -c bioconda {tool.replace('_', '-')}"
        )


def _check_tool(tool: str) -> bool:
    """Return True if tool is available in PATH (non-fatal version of _require)."""
    return shutil.which(tool) is not None


def _run(cmd: list[str], *, label: str) -> None:
    logger.info("Running: %s", label)
    result = subprocess.run(cmd, capture_output=True, text=True)
    log_tool_output(cmd, result)
    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed (exit {result.returncode}):\n{result.stderr[-3000:]}"
        )


def _run_shell(cmd: str, *, label: str) -> None:
    logger.info("Running: %s", label)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    log_tool_output(cmd, result)
    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed (exit {result.returncode}):\n{result.stderr[-3000:]}"
        )


def _flagstat(bam: Path) -> str:
    r = subprocess.run(
        ["samtools", "flagstat", str(bam)], capture_output=True, text=True
    )
    return r.stdout if r.returncode == 0 else ""


def _parse_flagstat_reads(flagstat: str) -> tuple[int, int]:
    """Return (n_total, n_mapped) from samtools flagstat output."""
    total = mapped = 0
    for line in flagstat.splitlines():
        if "in total" in line:
            total = int(line.split()[0])
        elif "mapped (" in line and "primary mapped" not in line:
            mapped = int(line.split()[0])
    return total, mapped


def _parse_flagstat(flagstat: str) -> tuple[int, float]:
    """Legacy helper: return (n_fragments, align_rate) — PE-centric."""
    total, mapped = _parse_flagstat_reads(flagstat)
    return mapped // 2, (mapped / total if total > 0 else 0.0)


def _count_mito_reads(bam: Path) -> int:
    r = subprocess.run(
        ["samtools", "idxstats", str(bam)], capture_output=True, text=True
    )
    total = 0
    for line in r.stdout.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0] in _MITO_CONTIGS:
            try:
                total += int(parts[2])
            except ValueError:
                pass
    return total


def _index_bam(bam: Path, *, threads: int = 1) -> None:
    subprocess.run(
        ["samtools", "index", "-@", str(threads), str(bam)],
        check=True, capture_output=True,
    )


def _rm(p: Path) -> None:
    try:
        if p.exists():
            os.remove(p)
    except OSError:
        pass
