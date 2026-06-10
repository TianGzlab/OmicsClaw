"""
preprocessing.py — Bulk Hi-C Step 1: sample-sheet loading, FastQC, adapter trim.

Mirrors the bulk-ChIP/ATAC preprocessing engine, minus the ChIP-only concepts:
Hi-C has **no input/IgG control and no antibody / peak-mode** — every sample is
a Hi-C library, grouped only by biological ``condition`` + ``replicate``. The
sample sheet is therefore ``sample, condition, replicate, r1, r2`` (+ optional
``genome``, ``adapter_r1``, ``adapter_r2``).

Hi-C reads are paired-end; trimming is light (adapter + min-length) — the two
ends are mapped *separately* downstream (``bwa mem -SP5M``), so we do not do PE
overlap correction here, just adapter/quality trim so junk ends don't waste
alignment.

Sample sheet format (for --input / file mode)
---------------------------------------------
  sample      unique sample identifier  (e.g. HFFc6_rep1)
  condition   biological condition      (e.g. asynchronous, G1S_arrest, WT, KO)
  replicate   integer replicate number
  r1, r2      paired FASTQ paths (Hi-C is paired-end)
  genome      optional per-row build (else --genome / default)
  adapter_r1, adapter_r2  optional explicit adapters
"""

from __future__ import annotations

import gzip
import json
import logging
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from omicsclaw.common.runlog import log_tool_output
except Exception:  # pragma: no cover - omicsclaw not importable in isolation
    def log_tool_output(cmd, result):  # type: ignore
        return None

logger = logging.getLogger(__name__)

# Illumina universal adapter (same default as the ChIP/ATAC suites).
ILLUMINA_UNIVERSAL_ADAPTER = "AGATCGGAAGAGC"
MIN_READ_LENGTH_AFTER_TRIM = 20
BASE_QUALITY_THRESHOLD     = 20
_PEEK_READS = 1_000


# ===========================================================================
# PART 1 — Sample-sheet data classes
# ===========================================================================

@dataclass
class Sample:
    """One row of the Hi-C sample sheet."""
    name:       str
    condition:  str
    replicate:  int
    r1:         Path
    r2:         Path | None = None
    genome:     str         = "hg38"
    adapter_r1: str | None  = None
    adapter_r2: str | None  = None

    @property
    def is_paired(self) -> bool:
        return self.r2 is not None

    @property
    def layout(self) -> str:
        return "paired-end" if self.is_paired else "single-end"

    def __repr__(self) -> str:
        return (
            f"Sample({self.name!r}, condition={self.condition!r}, "
            f"rep={self.replicate}, {self.layout})"
        )


@dataclass
class SampleSheet:
    """Parsed and validated Hi-C sample sheet."""
    samples:                  list[Sample]
    layout:                   str
    conditions:               list[str]
    replicates_per_condition: dict[str, list[int]]
    genome:                   str
    is_replicated:            bool

    def by_condition(self, condition: str) -> list[Sample]:
        return [s for s in self.samples if s.condition == condition]

    def __len__(self) -> int:
        return len(self.samples)

    def __iter__(self):
        return iter(self.samples)

    def summary(self) -> str:
        lines = [
            f"  Samples    : {len(self.samples)} Hi-C librar(y/ies)",
            f"  Layout     : {self.layout}",
            f"  Genome     : {self.genome}",
            f"  Conditions : {', '.join(self.conditions)}",
            f"  Replicated : {self.is_replicated}",
        ]
        for cond, reps in self.replicates_per_condition.items():
            lines.append(f"    {cond}: {len(reps)} replicate(s) -> {reps}")
        return "\n".join(lines)


# ===========================================================================
# PART 2 — Sample-sheet loading
# ===========================================================================

def load_sample_sheet(
    path: str | Path, *, default_genome: str = "hg38", data_type: str = "fastq",
) -> SampleSheet:
    """Load a TSV/CSV Hi-C sample sheet → validated SampleSheet."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Sample sheet not found: {path}")

    sep = "\t" if path.suffix in (".tsv", ".txt") else ","
    df  = pd.read_csv(path, sep=sep, dtype=str).fillna("").copy()
    df.columns = df.columns.str.strip().str.lower()

    required = {"sample", "condition", "replicate", "r1"}
    missing  = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Sample sheet missing required columns: {sorted(missing)}\n"
            f"Found: {list(df.columns)}"
        )

    names = [r.strip() for r in df["sample"]]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ValueError(f"Duplicate sample names in sheet: {sorted(dupes)}")

    samples: list[Sample] = []
    errors: list[str] = []
    for _, row in df.iterrows():
        name      = row["sample"].strip()
        condition = row["condition"].strip()
        replicate = int(row["replicate"]) if str(row["replicate"]).strip() else 1
        r1        = Path(row["r1"].strip())
        r2        = (Path(row["r2"].strip())
                     if "r2" in df.columns and row.get("r2", "").strip() else None)
        genome    = row.get("genome", "").strip() or default_genome

        if data_type in ("auto", "fastq"):
            if not r1.exists():
                errors.append(f"  [{name}] R1 not found: {r1}")
            if r2 and not r2.exists():
                errors.append(f"  [{name}] R2 not found: {r2}")

        samples.append(Sample(
            name=name, condition=condition, replicate=replicate,
            r1=r1, r2=r2, genome=genome,
            adapter_r1=row.get("adapter_r1", "").strip() or None,
            adapter_r2=row.get("adapter_r2", "").strip() or None,
        ))

    if errors:
        raise FileNotFoundError("Sample sheet validation failed:\n" + "\n".join(errors))

    sheet = _build_sample_sheet(samples, default_genome=default_genome)
    logger.info("Sample sheet loaded:\n%s", sheet.summary())
    return sheet


def detect_layout_from_fastq(r1: Path, *, peek_reads: int = _PEEK_READS) -> str:
    """Flag a paired run when a sibling R2-style FASTQ exists on disk."""
    r1_str = str(r1)
    for r1_tag, r2_tag in (
        ("_R1_", "_R2_"), ("_R1.", "_R2."), (".R1.", ".R2."),
        ("_1.fastq", "_2.fastq"), ("_1.fq", "_2.fq"),
    ):
        if r1_tag in r1_str:
            r2 = Path(r1_str.replace(r1_tag, r2_tag, 1))
            if r2 != r1 and r2.exists():
                return "paired-end"
    return "single-end"


def sample_sheet_to_dict(sheet: SampleSheet) -> dict[str, Any]:
    """Serialise a SampleSheet to a plain dict for result.json."""
    return {
        "n_samples":                len(sheet.samples),
        "layout":                   sheet.layout,
        "genome":                   sheet.genome,
        "conditions":               sheet.conditions,
        "replicates_per_condition": sheet.replicates_per_condition,
        "is_replicated":            sheet.is_replicated,
        "samples": [
            {
                "name":      s.name,
                "condition": s.condition,
                "replicate": s.replicate,
                "r1":        str(s.r1),
                "r2":        str(s.r2) if s.r2 else None,
                "genome":    s.genome,
            }
            for s in sheet.samples
        ],
    }


# ===========================================================================
# PART 3 — Demo data (small Hi-C test set)
# ===========================================================================
#
# Drosophila S2R+ in-situ Hi-C — Wang, Sun, Yang & Corces, Nat Commun 2018,
# "Sub-kb Hi-C in D. melanogaster reveals conserved characteristics of TADs
# between insect and mammalian cells" (GEO GSE101317, SRA SRP111713, dm6).
# A high-impact 2-condition × 2-replicate design — asynchronous vs G1/S-arrested
# S2R+ cells — so bulkhic-matrix exercises per-condition replicate pooling, and
# downstream skills get a real metazoan map (>4000 TADs) that actually produces
# compartments / boundaries / loops, unlike the old tiny yeast set.
#
# These are DEEP libraries (each FASTQ is 13–36 GB), so the demo NEVER downloads
# whole files — it streams the first --demo-n-reads read pairs over HTTP (see
# _http_download_prefix). dm6 (~143 Mb) keeps reference build + mapping fast; the
# the generic UCSC reference machinery resolves dm6 like any other build.
# Data-source provenance (recorded in the demo sample sheet + each sample row).
_DEMO_SOURCE = (
    "Wang Q, Sun Q, Czajkowsky DM, Shao Z. Sub-kb Hi-C in D. melanogaster reveals "
    "conserved characteristics of TADs between insect and mammalian cells. "
    "Nat Commun 9:188 (2018). doi:10.1038/s41467-017-02526-9 | "
    "GEO GSE101317 | SRA SRP111713 | BioProject PRJNA393992 | "
    "Drosophila S2R+ in-situ Hi-C, genome dm6"
)
_ENA_FASTQ = "https://ftp.sra.ebi.ac.uk/vol1/fastq"

_DEMO_FILES: dict[str, dict[str, str]] = {
    "async_rep1": {
        "R1_url":    f"{_ENA_FASTQ}/SRR582/002/SRR5820092/SRR5820092_1.fastq.gz",
        "R2_url":    f"{_ENA_FASTQ}/SRR582/002/SRR5820092/SRR5820092_2.fastq.gz",
        "condition": "asynchronous", "replicate": "1",
        "source":    "GSE101317 GSM2701046 SRR5820092 (S2R+ asynchronous, rep1)",
    },
    "async_rep2": {
        "R1_url":    f"{_ENA_FASTQ}/SRR582/004/SRR5820094/SRR5820094_1.fastq.gz",
        "R2_url":    f"{_ENA_FASTQ}/SRR582/004/SRR5820094/SRR5820094_2.fastq.gz",
        "condition": "asynchronous", "replicate": "2",
        "source":    "GSE101317 GSM2701047 SRR5820094 (S2R+ asynchronous, rep2)",
    },
    "G1S_rep1": {
        "R1_url":    f"{_ENA_FASTQ}/SRR582/000/SRR5820090/SRR5820090_1.fastq.gz",
        "R2_url":    f"{_ENA_FASTQ}/SRR582/000/SRR5820090/SRR5820090_2.fastq.gz",
        "condition": "G1S_arrest", "replicate": "1",
        "source":    "GSE101317 GSM2701044 SRR5820090 (S2R+ G1/S-arrest, rep1)",
    },
    "G1S_rep2": {
        "R1_url":    f"{_ENA_FASTQ}/SRR582/001/SRR5820091/SRR5820091_1.fastq.gz",
        "R2_url":    f"{_ENA_FASTQ}/SRR582/001/SRR5820091/SRR5820091_2.fastq.gz",
        "condition": "G1S_arrest", "replicate": "2",
        "source":    "GSE101317 GSM2701045 SRR5820091 (S2R+ G1/S-arrest, rep2)",
    },
}
_DEMO_GENOME = "dm6"


def _download_and_subsample(
    output_dir: Path, *, n_reads: int, subsample_dir: Path | None = None,
) -> Path:
    """Download the demo Hi-C FASTQs, write a TSV sample sheet, return its path.

    When *n_reads* > 0 the FASTQs are subsampled to that many reads; when
    *n_reads* <= 0 (default) the full files are used as-is.
    """
    subsample_dir = subsample_dir or output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    subsample_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Demo data source: %s", _DEMO_SOURCE)

    rows: list[dict[str, Any]] = []
    for sample_name, meta in _DEMO_FILES.items():
        logger.info("── %s ─────────────────────────────────────", sample_name)
        if n_reads > 0:
            # Demo default: the source FASTQs are 13–36 GB each, so stream only the
            # first n_reads read pairs over HTTP straight into the subsampled file.
            r1_out = _http_download_prefix(meta["R1_url"], subsample_dir / f"{sample_name}_R1.sub.fastq.gz", n_reads)
            r2_out = _http_download_prefix(meta["R2_url"], subsample_dir / f"{sample_name}_R2.sub.fastq.gz", n_reads)
        else:
            # Power-user path: pull the full files (huge for this dataset).
            r1_out = _http_download(meta["R1_url"], output_dir / Path(meta["R1_url"]).name,
                                    fallback_url=meta.get("R1_url_fallback"))
            r2_out = _http_download(meta["R2_url"], output_dir / Path(meta["R2_url"]).name,
                                    fallback_url=meta.get("R2_url_fallback"))
        rows.append({
            "sample":    sample_name,
            "condition": meta["condition"],
            "replicate": meta["replicate"],
            "R1":        str(r1_out),
            "R2":        str(r2_out),
            "genome":    _DEMO_GENOME,
            "source":    meta.get("source", _DEMO_SOURCE),
        })

    sheet_path = output_dir.parent / "demo_samplesheet.tsv"
    pd.DataFrame(rows).to_csv(sheet_path, sep="\t", index=False)
    logger.info("Demo sample sheet: %s", sheet_path)
    return sheet_path


def _http_download(url: str, dest: Path, *, fallback_url: str | None = None) -> Path:
    """Download *url* to *dest* (cached); try *fallback_url* on failure."""
    import urllib.request

    fallback_dest = dest.parent / Path(fallback_url).name if fallback_url else None
    for candidate in [dest, fallback_dest]:
        if candidate and candidate.exists() and candidate.stat().st_size > 0:
            logger.info("  Cached: %s  (%.1f MB)", candidate.name, candidate.stat().st_size / 1e6)
            return candidate

    for src_url, out in [(url, dest)] + ([(fallback_url, fallback_dest)] if fallback_url else []):
        tmp = out.with_suffix(out.suffix + ".tmp")
        try:
            logger.info("  Downloading %s ...", src_url)
            if shutil.which("wget"):
                subprocess.run(["wget", "-q", "-O", str(tmp), src_url], check=True, timeout=900)
            else:
                urllib.request.urlretrieve(src_url, tmp)  # noqa: S310
            if tmp.exists() and tmp.stat().st_size > 0:
                tmp.rename(out)
                logger.info("  Downloaded: %s  (%.1f MB)", out.name, out.stat().st_size / 1e6)
                return out
        except Exception as exc:  # noqa: BLE001 — try fallback
            logger.warning("  Download failed (%s): %s", src_url, exc)
            tmp.unlink(missing_ok=True)
    raise RuntimeError(f"Could not download demo FASTQ: {url}")


def _http_download_prefix(url: str, dest: Path, n_reads: int) -> Path:
    """Stream the first *n_reads* read pairs of a remote gzipped FASTQ to *dest*.

    Pulls only the prefix over HTTP (``curl url | zcat | head -n 4*n_reads | gzip``)
    so we never download the multi-GB source files. ``head`` closing the pipe makes
    curl/zcat exit early with SIGPIPE — that is expected, so success is judged by a
    non-empty gzip output, NOT the pipeline return code (and we avoid ``pipefail``).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        logger.info("  Cached: %s  (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
        return dest
    n_lines = n_reads * 4
    fetch = (f"curl -sL {shlex.quote(url)}" if shutil.which("curl")
             else f"wget -qO- {shlex.quote(url)}")
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    logger.info("  Streaming first %s read pairs: %s ...", f"{n_reads:,}", url)
    # `|| true` on head/gzip is unnecessary; we just don't fail on upstream SIGPIPE.
    subprocess.run(f"{fetch} | zcat | head -n {n_lines} | gzip -c > {shlex.quote(str(tmp))}",
                   shell=True, capture_output=True, text=True)
    if not (tmp.exists() and tmp.stat().st_size > 0):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Could not stream demo FASTQ prefix: {url}")
    tmp.rename(dest)
    logger.info("  Subsampled: %s  (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
    return dest


def _subsample(src: Path, out_dir: Path, sample: str, mate: str, n_reads: int) -> Path:
    """Subsample a FASTQ to *n_reads* with seqtk (head fallback)."""
    out = out_dir / f"{sample}_{mate}.sub.fastq.gz"
    if out.exists() and out.stat().st_size > 0:
        return out
    if shutil.which("seqtk"):
        _run_shell(f"seqtk sample -s100 {src} {n_reads} | gzip -c > {out}",
                   label=f"seqtk sample [{sample} {mate}]")
    else:
        _run_shell(f"zcat {src} | head -n {n_reads * 4} | gzip -c > {out}",
                   label=f"head subsample [{sample} {mate}]")
    return out


def get_data(
    samplesheet: str | Path | None,
    *,
    demo: bool = False,
    demo_n_reads: int = 0,
    output_dir: Path,
    subsample_dir: Path | None = None,
    default_genome: str = "hg38",
) -> SampleSheet:
    """Step 1a — obtain the sample sheet (demo download or user TSV)."""
    if demo:
        fastq_dir  = output_dir.parent / "fastq"
        sheet_path = _download_and_subsample(fastq_dir, n_reads=demo_n_reads,
                                             subsample_dir=subsample_dir)
        return load_sample_sheet(sheet_path, default_genome=_DEMO_GENOME, data_type="fastq")
    return load_sample_sheet(samplesheet, default_genome=default_genome, data_type="fastq")


# ===========================================================================
# PART 4 — Preprocessing (FastQC + adapter trimming)
# ===========================================================================

@dataclass
class PreprocessResult:
    sample_name: str
    r1_trimmed:  Path
    r2_trimmed:  Path | None    = None
    qc_json:     Path | None    = None
    fastqc_html: list[Path]     = field(default_factory=list)
    tool:        str            = "unknown"
    stats:       dict[str, Any] = field(default_factory=dict)

    @property
    def is_paired(self) -> bool:
        return self.r2_trimmed is not None


def build_preprocessing_summary(results: list[PreprocessResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        s        = r.stats
        before   = s.get("total_reads_before") or s.get("total_reads")
        after    = s.get("total_reads_after")  or s.get("reads_passing")
        removed  = (before - after)       if (before and after)      else None
        pct_kept = (after / before * 100) if (before and before > 0) else None
        rows.append({
            "sample":             r.sample_name,
            "tool":               r.tool,
            "total_reads_before": before,
            "total_reads_after":  after,
            "reads_removed":      removed,
            "pct_reads_kept":     round(pct_kept, 2) if pct_kept is not None else None,
            "q30_rate_before":    s.get("q30_rate_before"),
            "q30_rate_after":     s.get("q30_rate_after"),
        })
    return pd.DataFrame(rows)


def write_preprocessing_summary(results: list[PreprocessResult], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "trimmed_summary.csv"
    build_preprocessing_summary(results).to_csv(path, index=False)
    logger.info("Trimming summary written: %s", path)
    return path


def run_preprocessing(
    sample: Sample, output_dir: Path, *,
    do_trim: bool = False,
    tool: str = "auto", threads: int = 4, adapter: str | None = None,
    min_length: int = MIN_READ_LENGTH_AFTER_TRIM, quality: int = BASE_QUALITY_THRESHOLD,
    run_fastqc: bool = True,
) -> PreprocessResult:
    sample_dir = output_dir / sample.name
    sample_dir.mkdir(parents=True, exist_ok=True)

    fqc_html: list[Path] = []
    if run_fastqc:
        fqc_html = _run_fastqc(sample, sample_dir, threads=threads)

    if not do_trim:
        # Hi-C standard (4DN/distiller/Juicer): map RAW reads. bwa-mem2 -SP5M
        # soft-clips adapter/junction tails and pairtools parse rescues chimeric
        # ligation-junction reads, so pre-alignment trimming is unnecessary.
        # FastQC still runs (QC only). We symlink the raw FASTQs into the sample
        # dir so the preprocessing output is self-contained and downstream paths
        # live under this skill's output (consistent with the --trim layout).
        def _link(src, mate):
            if src is None:
                return None
            link = sample_dir / f"{sample.name}_{mate}.fastq.gz"
            try:
                if link.is_symlink() or link.exists():
                    link.unlink()
                link.symlink_to(Path(src).resolve())
                return link
            except OSError:
                return Path(src)  # fall back to the raw path if symlink fails
        result = PreprocessResult(
            sample_name=sample.name,
            r1_trimmed=_link(sample.r1, "R1"), r2_trimmed=_link(sample.r2, "R2"),
            tool="none (raw)", stats={})
        result.fastqc_html = fqc_html
        return result

    if tool == "auto":
        tool = _pick_tool()
    eff_adapter = adapter or sample.adapter_r1 or ILLUMINA_UNIVERSAL_ADAPTER
    result = _run_fastp(sample, sample_dir, threads=threads,
                        adapter=eff_adapter, min_length=min_length, quality=quality)
    result.fastqc_html = fqc_html
    return result


def run_all_preprocessing(
    samples: list[Sample], output_dir: Path, *,
    do_trim: bool = False,
    tool: str = "auto", threads: int = 4, adapter: str | None = None,
    min_length: int = MIN_READ_LENGTH_AFTER_TRIM, quality: int = BASE_QUALITY_THRESHOLD,
    run_fastqc: bool = True,
) -> list[PreprocessResult]:
    results: list[PreprocessResult] = []
    for sample in samples:
        logger.info("Preprocessing %s  [%s]%s ...", sample.name, sample.layout,
                    "" if do_trim else " (no trim — raw)")
        result = run_preprocessing(sample, output_dir, do_trim=do_trim, tool=tool,
                                   threads=threads, adapter=adapter, min_length=min_length,
                                   quality=quality, run_fastqc=run_fastqc)
        results.append(result)
        if do_trim:
            n = result.stats.get("total_reads_after") or 0
            logger.info("  %s → %s reads after trimming", sample.name, f"{n:,}" if n else "unknown")
        else:
            logger.info("  %s → mapping raw reads (no trimming)", sample.name)
    write_preprocessing_summary(results, output_dir)
    return results


# ===========================================================================
# PART 5 — Internal helpers
# ===========================================================================

def _build_sample_sheet(samples: list[Sample], *, default_genome: str) -> SampleSheet:
    layouts = {s.layout for s in samples}
    layout  = layouts.pop() if len(layouts) == 1 else "mixed"
    if layout != "paired-end":
        logger.warning("Hi-C expects paired-end reads; got layout=%s", layout)

    conditions = sorted({s.condition for s in samples})
    reps_per_cond: dict[str, list[int]] = {
        cond: sorted({s.replicate for s in samples if s.condition == cond})
        for cond in conditions
    }
    is_replicated = any(len(r) >= 2 for r in reps_per_cond.values())

    genomes = {s.genome for s in samples}
    genome  = genomes.pop() if len(genomes) == 1 else "mixed"
    if genome == "mixed":
        logger.warning("Multiple genome builds: %s", {s.name: s.genome for s in samples})

    return SampleSheet(
        samples=samples, layout=layout, conditions=conditions,
        replicates_per_condition=reps_per_cond,
        genome=genome if genome != "mixed" else default_genome,
        is_replicated=is_replicated,
    )


def _pick_tool() -> str:
    if shutil.which("fastp"):
        return "fastp"
    raise RuntimeError("fastp not found in PATH. Install: conda install -c bioconda fastp")


def _run_fastqc(sample: Sample, sample_dir: Path, *, threads: int) -> list[Path]:
    if not shutil.which("fastqc"):
        logger.info("fastqc not found — skipping for %s", sample.name)
        return []
    fqc_dir  = sample_dir / "fastqc_raw"
    sentinel = fqc_dir / ".done"
    sentinel_data = {"r1": str(sample.r1), "r2": str(sample.r2) if sample.r2 else None}
    if sentinel.exists():
        try:
            if json.loads(sentinel.read_text()) == sentinel_data:
                logger.info("FastQC cached — skipping for %s", sample.name)
                return list(fqc_dir.glob("*.html"))
        except Exception:
            pass
    fqc_dir.mkdir(parents=True, exist_ok=True)
    files = [str(sample.r1)] + ([str(sample.r2)] if sample.r2 else [])
    _run(["fastqc", "--outdir", str(fqc_dir), "--threads", str(threads)] + files,
         label=f"FastQC [{sample.name}]")
    sentinel.write_text(json.dumps(sentinel_data))
    return list(fqc_dir.glob("*.html"))


def _run_fastp(
    sample: Sample, sample_dir: Path, *,
    threads: int, adapter: str, min_length: int, quality: int,
) -> PreprocessResult:
    _require("fastp")
    r1_out   = sample_dir / f"{sample.name}_R1_trimmed.fastq.gz"
    r2_out   = sample_dir / f"{sample.name}_R2_trimmed.fastq.gz" if sample.is_paired else None
    json_out = sample_dir / f"{sample.name}_fastp.json"
    html_out = sample_dir / f"{sample.name}_fastp.html"
    sentinel = sample_dir / f"{sample.name}.fastp.done"

    sentinel_data = {
        "r1": str(sample.r1), "r2": str(sample.r2) if sample.r2 else None,
        "adapter": adapter, "min_length": min_length, "quality": quality,
    }
    if sentinel.exists():
        try:
            if json.loads(sentinel.read_text()) == sentinel_data and r1_out.exists():
                logger.info("fastp cached — skipping %s", sample.name)
                return PreprocessResult(
                    sample_name=sample.name, r1_trimmed=r1_out, r2_trimmed=r2_out,
                    qc_json=json_out if json_out.exists() else None, tool="fastp",
                    stats=_parse_fastp_json(json_out) if json_out.exists() else {},
                )
        except Exception:
            pass

    cmd = [
        "fastp", "--in1", str(sample.r1), "--out1", str(r1_out),
        "--json", str(json_out), "--html", str(html_out),
        "--adapter_sequence", adapter,
        "--length_required", str(min_length),
        "--qualified_quality_phred", str(quality),
        "--thread", str(threads),
    ]
    if sample.is_paired:
        cmd += ["--in2", str(sample.r2), "--out2", str(r2_out),
                "--adapter_sequence_r2", sample.adapter_r2 or adapter, "--detect_adapter_for_pe"]
    _run(cmd, label=f"fastp [{sample.name}]")
    sentinel.write_text(json.dumps(sentinel_data))
    return PreprocessResult(
        sample_name=sample.name, r1_trimmed=r1_out, r2_trimmed=r2_out,
        qc_json=json_out if json_out.exists() else None, tool="fastp",
        stats=_parse_fastp_json(json_out) if json_out.exists() else {},
    )


def _parse_fastp_json(json_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(json_path.read_text())
    except Exception:
        return {}
    before = data.get("summary", {}).get("before_filtering", {})
    after  = data.get("summary", {}).get("after_filtering", {})
    return {
        "total_reads_before": before.get("total_reads"),
        "total_reads_after":  after.get("total_reads"),
        "q30_rate_before":    before.get("q30_rate"),
        "q30_rate_after":     after.get("q30_rate"),
    }


def _count_reads(path: Path) -> int:
    count = 0
    with gzip.open(path, "rt") as fh:
        for i, _ in enumerate(fh):
            if i % 4 == 0:
                count += 1
    return count


def _require(tool: str) -> None:
    if not shutil.which(tool):
        raise RuntimeError(
            f"'{tool}' not found in PATH.\n"
            f"Install: conda install -c bioconda {tool.replace('_', '-')}"
        )


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
