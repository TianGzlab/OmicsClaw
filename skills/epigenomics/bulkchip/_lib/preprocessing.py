"""
preprocessing.py — Bulk ChIP-seq Step 1: data acquisition, QC, and adapter
trimming (with ChIP/input control pairing).

Public API
----------
  get_data(...)             Step 1a — load or download the sample data → SampleSheet
  run_all_preprocessing()   Step 1b — FastQC + adapter trimming → list[PreprocessResult]

Data classes
  Sample, SampleSheet, PreprocessResult

Utilities
  load_sample_sheet, detect_layout_from_fastq, sample_sheet_to_dict
  build_preprocessing_summary, write_preprocessing_summary

Sample sheet format (for --input / file mode)
---------------------------------------------
Required columns:
  sample      unique sample identifier  (e.g. SPT5_T0_rep1)
  condition   biological condition      (e.g. T0, T15, INPUT)
  replicate   integer replicate number  (e.g. 1, 2)
  R1          path to read-1 FASTQ.gz

Optional columns:
  R2          path to read-2 FASTQ.gz   (omit for single-end)
  control     name of the matched input/IgG control sample (ChIP rows only)
  antibody    target antibody / factor  (e.g. SPT5, H3K27me3); EMPTY ⇒ control
  peak_mode   narrow | broad            (default: inferred from antibody)
  genome      per-sample genome override
  adapter_r1  explicit adapter sequence for R1
  adapter_r2  explicit adapter sequence for R2

A sample with an EMPTY `antibody` is treated as an input/IgG control. Every ChIP
sample's `control` must reference an existing control sample.
"""

from __future__ import annotations

import gzip
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .encode_qc_criteria import ILLUMINA_UNIVERSAL_ADAPTER, infer_peak_mode

try:
    from omicsclaw.common.runlog import log_tool_output
except Exception:  # pragma: no cover - omicsclaw not importable in isolation
    def log_tool_output(cmd, result):  # type: ignore
        return None

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

MIN_READ_LENGTH_AFTER_TRIM = 20
BASE_QUALITY_THRESHOLD     = 20

_PEEK_READS = 1_000


# ===========================================================================
# PART 1 — Sample sheet data classes
# ===========================================================================

@dataclass
class Sample:
    """One row of the sample sheet."""
    name:       str
    condition:  str
    replicate:  int
    r1:         Path
    r2:         Path | None = None
    genome:     str         = "hg38"
    is_control: bool        = False           # True for input / IgG samples
    control:    str | None  = None            # matched control sample name (ChIP only)
    antibody:   str | None  = None            # target factor / mark
    peak_mode:  str         = "narrow"        # "narrow" | "broad"
    adapter_r1: str | None  = None
    adapter_r2: str | None  = None

    @property
    def is_paired(self) -> bool:
        return self.r2 is not None

    @property
    def layout(self) -> str:
        return "paired-end" if self.is_paired else "single-end"

    def __repr__(self) -> str:
        kind = "control" if self.is_control else f"ChIP:{self.antibody}"
        return (
            f"Sample({self.name!r}, condition={self.condition!r}, "
            f"rep={self.replicate}, {self.layout}, {kind})"
        )


@dataclass
class SampleSheet:
    """
    Parsed and validated ChIP-seq sample sheet.

    Attributes
    ----------
    samples                  : list of Sample objects in sheet order
    layout                   : "paired-end" | "single-end" | "mixed"
    conditions               : sorted list of unique condition labels
    replicates_per_condition : {condition -> [replicate numbers]}
    genome                   : genome build (or "mixed" if per-sample)
    is_replicated            : True if any condition has >= 2 replicates
    control_map              : {chip_sample_name -> control_sample_name}
    """
    samples:                  list[Sample]
    layout:                   str
    conditions:               list[str]
    replicates_per_condition: dict[str, list[int]]
    genome:                   str
    is_replicated:            bool
    control_map:              dict[str, str] = field(default_factory=dict)

    def by_condition(self, condition: str) -> list[Sample]:
        return [s for s in self.samples if s.condition == condition]

    @property
    def chip_samples(self) -> list[Sample]:
        return [s for s in self.samples if not s.is_control]

    @property
    def control_samples(self) -> list[Sample]:
        return [s for s in self.samples if s.is_control]

    def __len__(self) -> int:
        return len(self.samples)

    def __iter__(self):
        return iter(self.samples)

    def summary(self) -> str:
        lines = [
            f"  Samples    : {len(self.samples)} "
            f"({len(self.chip_samples)} ChIP + {len(self.control_samples)} control)",
            f"  Layout     : {self.layout}",
            f"  Genome     : {self.genome}",
            f"  Conditions : {', '.join(self.conditions)}",
            f"  Replicated : {self.is_replicated}",
        ]
        for cond, reps in self.replicates_per_condition.items():
            lines.append(f"    {cond}: {len(reps)} replicate(s) -> {reps}")
        if self.control_map:
            lines.append("  ChIP → control pairing:")
            for chip, ctrl in self.control_map.items():
                lines.append(f"    {chip} → {ctrl}")
        return "\n".join(lines)


# ===========================================================================
# PART 2 — Sample sheet loading
# ===========================================================================

def load_sample_sheet(
    path: str | Path,
    *,
    default_genome: str = "hg38",
    data_type: str = "auto",
) -> SampleSheet:
    """
    Parse a TSV or CSV ChIP-seq sample sheet and return a validated SampleSheet.

    Raises
    ------
    ValueError          if required columns are missing, names duplicated, or a
                        ChIP sample references a control that is absent / not a control
    FileNotFoundError   if any declared FASTQ does not exist
    """
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

    dupes = df["sample"][df["sample"].duplicated()].tolist()
    if dupes:
        raise ValueError(f"Duplicate sample names in sheet: {dupes}")

    samples: list[Sample] = []
    errors:  list[str]    = []

    for _, row in df.iterrows():
        name      = row["sample"].strip()
        condition = row["condition"].strip()

        try:
            replicate = int(row["replicate"])
        except (ValueError, TypeError):
            errors.append(f"  [{name}] replicate must be an integer, got: {row['replicate']!r}")
            replicate = 0

        r1 = Path(row["r1"].strip())
        r2 = (
            Path(row["r2"].strip())
            if "r2" in df.columns and row.get("r2", "").strip()
            else None
        )
        genome     = row.get("genome",     "").strip() or default_genome
        antibody   = row.get("antibody",   "").strip() or None
        control    = row.get("control",    "").strip() or None
        # Empty antibody ⇒ this row is an input/IgG control.
        is_control = antibody is None
        peak_mode  = (row.get("peak_mode", "").strip().lower()
                      or (infer_peak_mode(antibody) if not is_control else "narrow"))
        adapter_r1 = row.get("adapter_r1", "").strip() or None
        adapter_r2 = row.get("adapter_r2", "").strip() or None

        if data_type in ("auto", "fastq"):
            if not r1.exists():
                errors.append(f"  [{name}] R1 not found: {r1}")
            if r2 and not r2.exists():
                errors.append(f"  [{name}] R2 not found: {r2}")

        samples.append(Sample(
            name=name, condition=condition, replicate=replicate,
            r1=r1, r2=r2, genome=genome,
            is_control=is_control, control=control, antibody=antibody,
            peak_mode=peak_mode, adapter_r1=adapter_r1, adapter_r2=adapter_r2,
        ))

    # ── Validate ChIP↔control pairing ───────────────────────────────────────
    names      = {s.name for s in samples}
    control_ok = {s.name for s in samples if s.is_control}
    for s in samples:
        if s.is_control:
            continue
        if not s.control:
            logger.warning(
                "ChIP sample %s has no input/IgG `control` — MACS2 will call peaks "
                "without -c (local-lambda background). Supported, but lower-confidence; "
                "ENCODE recommends a matched input control.",
                s.name,
            )
            continue
        if s.control not in names:
            errors.append(f"  [{s.name}] control '{s.control}' is not a sample in the sheet")
        elif s.control not in control_ok:
            errors.append(
                f"  [{s.name}] control '{s.control}' is not an input/IgG control "
                f"(it has an antibody set)"
            )

    if errors:
        raise (ValueError if any("control" in e for e in errors) else FileNotFoundError)(
            "Sample sheet validation failed:\n" + "\n".join(errors)
        )

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
        "n_samples":     len(sheet.samples),
        "layout":        sheet.layout,
        "genome":        sheet.genome,
        "conditions":    sheet.conditions,
        "is_replicated": sheet.is_replicated,
        "replicates_per_condition": sheet.replicates_per_condition,
        "control_map":   sheet.control_map,
        "samples": [
            {
                "name":       s.name,
                "condition":  s.condition,
                "replicate":  s.replicate,
                "r1":         str(s.r1),
                "r2":         str(s.r2) if s.r2 else None,
                "genome":     s.genome,
                "is_control": s.is_control,
                "control":    s.control,
                "antibody":   s.antibody,
                "peak_mode":  s.peak_mode,
            }
            for s in sheet.samples
        ],
    }


# ===========================================================================
# PART 3 — Demo data
# ===========================================================================
#
# Dataset: SPT5 ChIP-seq in S. cerevisiae — the nf-core/chipseq test set.
#   Two timepoints (T0 / T15) x 2 replicates of SPT5 ChIP + 2 input controls.
#   PE reads, sacCer3 (R64-1-1). Tiny (subsampled), runs in minutes.
#
# ChIP reads reuse the nf-core ATAC-seq yeast test FASTQs (SRR18221xx); the
# input controls are the dedicated chipseq test FASTQs (SRR520480x, ss100k).
# This mirrors the composition of nf-core/test-datasets chipseq samplesheet.
#
# Download strategy (per file, tried in order):
#   1. nf-core GitHub raw (raw.githubusercontent.com) — fast global default;
#      may be blocked in mainland China.
#   2. EBI ENA FTP HTTPS (ftp.sra.ebi.ac.uk) — China-accessible fallback for
#      the ChIP accessions (full files, subsampled on first run).

_NFCORE_ATAC = "https://raw.githubusercontent.com/nf-core/test-datasets/atacseq/testdata"
_NFCORE_CHIP = "https://raw.githubusercontent.com/nf-core/test-datasets/chipseq/testdata"
_EBI_BASE    = "https://ftp.sra.ebi.ac.uk/vol1/fastq"

_DEMO_FILES: dict[str, dict[str, str]] = {
    # ── SPT5 ChIP samples (T0 / T15, 2 reps each) ──────────────────────────
    "SPT5_T0_rep1": {
        "R1_url":          f"{_NFCORE_ATAC}/SRR1822153_1.fastq.gz",
        "R2_url":          f"{_NFCORE_ATAC}/SRR1822153_2.fastq.gz",
        "R1_url_fallback": f"{_EBI_BASE}/SRR182/003/SRR1822153/SRR1822153_1.fastq.gz",
        "R2_url_fallback": f"{_EBI_BASE}/SRR182/003/SRR1822153/SRR1822153_2.fastq.gz",
        "condition": "T0", "replicate": "1",
        "control": "SPT5_INPUT_rep1", "antibody": "SPT5", "peak_mode": "narrow",
    },
    "SPT5_T0_rep2": {
        "R1_url":          f"{_NFCORE_ATAC}/SRR1822154_1.fastq.gz",
        "R2_url":          f"{_NFCORE_ATAC}/SRR1822154_2.fastq.gz",
        "R1_url_fallback": f"{_EBI_BASE}/SRR182/006/SRR1822156/SRR1822156_1.fastq.gz",
        "R2_url_fallback": f"{_EBI_BASE}/SRR182/006/SRR1822156/SRR1822156_2.fastq.gz",
        "condition": "T0", "replicate": "2",
        "control": "SPT5_INPUT_rep2", "antibody": "SPT5", "peak_mode": "narrow",
    },
    "SPT5_T15_rep1": {
        "R1_url":          f"{_NFCORE_ATAC}/SRR1822157_1.fastq.gz",
        "R2_url":          f"{_NFCORE_ATAC}/SRR1822157_2.fastq.gz",
        "R1_url_fallback": f"{_EBI_BASE}/SRR182/007/SRR1822157/SRR1822157_1.fastq.gz",
        "R2_url_fallback": f"{_EBI_BASE}/SRR182/007/SRR1822157/SRR1822157_2.fastq.gz",
        "condition": "T15", "replicate": "1",
        "control": "SPT5_INPUT_rep1", "antibody": "SPT5", "peak_mode": "narrow",
    },
    "SPT5_T15_rep2": {
        "R1_url":          f"{_NFCORE_ATAC}/SRR1822158_1.fastq.gz",
        "R2_url":          f"{_NFCORE_ATAC}/SRR1822158_2.fastq.gz",
        "R1_url_fallback": f"{_EBI_BASE}/SRR182/008/SRR1822158/SRR1822158_1.fastq.gz",
        "R2_url_fallback": f"{_EBI_BASE}/SRR182/008/SRR1822158/SRR1822158_2.fastq.gz",
        "condition": "T15", "replicate": "2",
        "control": "SPT5_INPUT_rep2", "antibody": "SPT5", "peak_mode": "narrow",
    },
    # ── Input controls (2 reps) ────────────────────────────────────────────
    "SPT5_INPUT_rep1": {
        "R1_url":          f"{_NFCORE_CHIP}/SRR5204809_Spt5-ChIP_Input1_SacCer_ChIP-Seq_ss100k_R1.fastq.gz",
        "R2_url":          f"{_NFCORE_CHIP}/SRR5204809_Spt5-ChIP_Input1_SacCer_ChIP-Seq_ss100k_R2.fastq.gz",
        "R1_url_fallback": f"{_EBI_BASE}/SRR520/009/SRR5204809/SRR5204809_1.fastq.gz",
        "R2_url_fallback": f"{_EBI_BASE}/SRR520/009/SRR5204809/SRR5204809_2.fastq.gz",
        "condition": "INPUT", "replicate": "1",
        "control": "", "antibody": "", "peak_mode": "",
    },
    "SPT5_INPUT_rep2": {
        "R1_url":          f"{_NFCORE_CHIP}/SRR5204810_Spt5-ChIP_Input2_SacCer_ChIP-Seq_ss100k_R1.fastq.gz",
        "R2_url":          f"{_NFCORE_CHIP}/SRR5204810_Spt5-ChIP_Input2_SacCer_ChIP-Seq_ss100k_R2.fastq.gz",
        "R1_url_fallback": f"{_EBI_BASE}/SRR520/000/SRR5204810/SRR5204810_1.fastq.gz",
        "R2_url_fallback": f"{_EBI_BASE}/SRR520/000/SRR5204810/SRR5204810_2.fastq.gz",
        "condition": "INPUT", "replicate": "2",
        "control": "", "antibody": "", "peak_mode": "",
    },
}


def _download_and_subsample(
    output_dir: Path,
    *,
    n_reads: int,
    subsample_dir: Path | None = None,
    no_input: bool = False,
) -> Path:
    """
    Download the SPT5 ChIP-seq demo FASTQs (nf-core GitHub primary, EBI
    fallback), write a TSV sample sheet (with the ChIP
    `control`/`antibody`/`peak_mode` columns), and return its path. When
    *n_reads* > 0 the FASTQs are subsampled to that many reads; when *n_reads*
    <= 0 (the default) the full files are used as-is.

    When *no_input* is True, the two input/IgG controls are skipped and the
    `control` column is left blank — the control-free demo (4 SPT5 ChIP
    samples) that exercises MACS2's no-`-c` peak-calling path. The sheet is
    written as ``demo_samplesheet_no_input.tsv``.
    """
    subsample_dir = subsample_dir or output_dir
    subsample_dir.mkdir(parents=True, exist_ok=True)
    import subprocess as _sp
    import urllib.request

    def _http_download(url: str, dest: Path, *, fallback_url: str | None = None) -> Path:
        import sys as _sys
        fallback_dest = dest.parent / Path(fallback_url).name if fallback_url else None
        for candidate in [dest, fallback_dest]:
            if candidate and candidate.exists() and candidate.stat().st_size > 0:
                logger.info("  Cached: %s  (%.1f MB)", candidate.name, candidate.stat().st_size / 1e6)
                return candidate
        dest.unlink(missing_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")

        def _bar(n: int, bs: int, total: int) -> None:
            downloaded = min(n * bs, total) if total > 0 else n * bs
            if total > 0:
                pct    = int(downloaded * 100 / total)
                filled = pct // 5
                bar    = "█" * filled + "░" * (20 - filled)
                line   = f"\r  [{bar}] {pct:3d}%  {downloaded/1e6:.1f}/{total/1e6:.1f} MB"
            else:
                line   = f"\r  Downloaded {downloaded/1e6:.1f} MB..."
            _sys.stderr.write(line); _sys.stderr.flush()
            if total > 0 and downloaded >= total:
                _sys.stderr.write("\n"); _sys.stderr.flush()

        _CONNECT_TIMEOUT = 30
        _STALL_TIMEOUT   = 60

        def _fetch(src_url: str) -> None:
            if shutil.which("wget"):
                _sp.run(["wget", "-q", "--show-progress", "--progress=bar:force:noscroll",
                         "--tries=2", f"--dns-timeout={_CONNECT_TIMEOUT}",
                         f"--connect-timeout={_CONNECT_TIMEOUT}", f"--read-timeout={_STALL_TIMEOUT}",
                         "-O", str(tmp), src_url], check=True)
            elif shutil.which("curl"):
                _sp.run(["curl", "-fSL", "--progress-bar",
                         "--connect-timeout", str(_CONNECT_TIMEOUT),
                         "--speed-time", str(_STALL_TIMEOUT), "--speed-limit", "1024",
                         "--retry", "2", "-o", str(tmp), src_url], check=True)
            else:
                import socket as _socket
                _prev = _socket.getdefaulttimeout()
                _socket.setdefaulttimeout(_STALL_TIMEOUT)
                try:
                    urllib.request.urlretrieve(src_url, tmp, reporthook=_bar)
                finally:
                    _socket.setdefaulttimeout(_prev)

        for attempt, src_url in enumerate([u for u in [url, fallback_url] if u], start=1):
            label       = "primary" if attempt == 1 else "fallback"
            actual_dest = dest if attempt == 1 else (dest.parent / Path(src_url).name)
            logger.info("  Downloading %s [%s] ...", actual_dest.name, label)
            try:
                tmp.unlink(missing_ok=True)
                _fetch(src_url)
                tmp.rename(actual_dest)
                if attempt > 1 and actual_dest != dest:
                    logger.warning("  SUBSTITUTION: %s unavailable; using %s as stand-in",
                                   dest.name, actual_dest.name)
                logger.info("  Saved: %s  (%.1f MB)", actual_dest.name, actual_dest.stat().st_size / 1e6)
                return actual_dest
            except Exception as exc:
                tmp.unlink(missing_ok=True)
                if fallback_url and attempt == 1:
                    logger.warning("  %s source failed (%s) — trying fallback ...", label, exc)
                else:
                    raise RuntimeError(
                        f"All download sources failed for {dest.name}.\n  Last error: {exc}"
                    ) from exc
        raise RuntimeError(f"No download sources configured for {dest.name}")

    def _downsample(src: Path, sample: str, read: str) -> tuple[Path, int]:
        import re as _re

        def _ds_count(p: Path) -> int:
            m = _re.search(r"\.ds(\d+)_R\d+\.fastq\.gz$", p.name)
            return int(m.group(1)) if m else -1

        candidates = sorted(subsample_dir.glob(f"{sample}.ds*_{read}.fastq.gz"),
                            key=_ds_count, reverse=True)
        for candidate in candidates:
            embedded = _ds_count(candidate)
            if embedded <= 0 or embedded > n_reads:
                continue
            try:
                count = _count_reads(candidate)
            except Exception:
                logger.warning("  Corrupt cache file %s — re-subsampling", candidate.name)
                candidate.unlink(missing_ok=True)
                break
            if count == embedded and count <= n_reads:
                logger.info("  Cached subsample: %s (%d reads)", candidate.name, count)
                return candidate, count
            logger.warning("  Cache mismatch %s (expected %d, got %d) — re-subsampling",
                            candidate.name, embedded, count)
            candidate.unlink(missing_ok=True)
        tmp = subsample_dir / f"{sample}._tmp_{read}.fastq.gz"
        tmp.unlink(missing_ok=True)
        count = 0
        try:
            with gzip.open(src, "rt") as fin, gzip.open(tmp, "wt") as fout:
                while count < n_reads:
                    header = fin.readline()
                    if not header:
                        break
                    fout.write(header + fin.readline() + fin.readline() + fin.readline())
                    count += 1
            dest = subsample_dir / f"{sample}.ds{count}_{read}.fastq.gz"
            tmp.rename(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        logger.info("  Subsampled: %d reads → %s", count, dest.name)
        return dest, count

    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    for sample_name, meta in _DEMO_FILES.items():
        if no_input and not meta.get("antibody"):
            logger.info("── %s ── skipped (no-input demo: control-free)", sample_name)
            continue
        logger.info("── %s ─────────────────────────────────────", sample_name)
        r1_raw = _http_download(meta["R1_url"], output_dir / Path(meta["R1_url"]).name,
                                fallback_url=meta.get("R1_url_fallback"))
        r2_raw = _http_download(meta["R2_url"], output_dir / Path(meta["R2_url"]).name,
                                fallback_url=meta.get("R2_url_fallback"))
        if n_reads <= 0:
            # No subsampling — use the full downloaded FASTQs as-is.
            logger.info("  Using full FASTQs (no subsampling) ...")
            r1_out, r2_out = r1_raw, r2_raw
            n_r1, n_r2 = _count_reads(r1_raw), _count_reads(r2_raw)
        else:
            logger.info("  Subsampling to up to %d reads ...", n_reads)
            r1_out, n_r1 = _downsample(r1_raw, sample_name, "R1")
            r2_out, n_r2 = _downsample(r2_raw, sample_name, "R2")
        if n_r1 != n_r2:
            logger.warning("%s: R1=%d reads, R2=%d reads", sample_name, n_r1, n_r2)
        rows.append({
            "sample":    sample_name,
            "condition": meta["condition"],
            "replicate": meta["replicate"],
            "R1":        str(r1_out),
            "R2":        str(r2_out),
            "control":   "" if no_input else meta["control"],
            "antibody":  meta["antibody"],
            "peak_mode": meta["peak_mode"],
        })

    sheet_name = "demo_samplesheet_no_input.tsv" if no_input else "demo_samplesheet.tsv"
    sheet_path = output_dir.parent / sheet_name
    pd.DataFrame(rows).to_csv(sheet_path, sep="\t", index=False)
    logger.info("Demo sample sheet: %s", sheet_path)
    return sheet_path


def _count_reads(path: Path) -> int:
    count = 0
    with gzip.open(path, "rt") as fh:
        for i, _ in enumerate(fh):
            if i % 4 == 0:
                count += 1
    return count


def get_data(
    samplesheet: str | Path | None,
    *,
    demo: bool = False,
    demo_n_reads: int = 0,
    demo_no_input: bool = False,
    output_dir: Path,
    subsample_dir: Path | None = None,
    default_genome: str = "hg38",
) -> SampleSheet:
    """
    Step 1a — Obtain the sample sheet.

    Demo mode : download the SPT5 ChIP-seq FASTQs (4 ChIP + 2 input) into
                output_dir.parent/fastq/, write demo_samplesheet.tsv, parse and
                return SampleSheet. By default the full FASTQs are used as-is;
                pass demo_n_reads > 0 to subsample to that many reads.
    File mode : parse the user-supplied TSV/CSV sample sheet directly.
    """
    if demo:
        fastq_dir  = output_dir.parent / "fastq"
        sheet_path = _download_and_subsample(fastq_dir, n_reads=demo_n_reads,
                                             subsample_dir=subsample_dir,
                                             no_input=demo_no_input)
        sheet      = load_sample_sheet(sheet_path, default_genome="sacCer3", data_type="fastq")
    else:
        sheet = load_sample_sheet(samplesheet, default_genome=default_genome, data_type="fastq")

    if sheet.layout == "single-end":
        for sample in sheet:
            if detect_layout_from_fastq(sample.r1) == "paired-end":
                logger.warning(
                    "Sample %s: R2 absent in sample sheet but FASTQ headers suggest "
                    "paired-end data. Add an R2 column if this is PE data.", sample.name,
                )
                break
    return sheet


# ===========================================================================
# PART 4 — Preprocessing (FastQC + adapter trimming)
# ===========================================================================

@dataclass
class PreprocessResult:
    sample_name:  str
    r1_trimmed:   Path
    r2_trimmed:   Path | None    = None
    qc_json:      Path | None    = None
    fastqc_html:  list[Path]     = field(default_factory=list)
    tool:         str            = "unknown"
    is_control:   bool           = False
    stats:        dict[str, Any] = field(default_factory=dict)

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
            "is_control":         r.is_control,
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
    sample: Sample,
    output_dir: Path,
    *,
    tool: str = "auto",
    threads: int = 4,
    adapter: str | None = None,
    min_length: int = MIN_READ_LENGTH_AFTER_TRIM,
    quality: int = BASE_QUALITY_THRESHOLD,
    run_fastqc: bool = True,
) -> PreprocessResult:
    sample_dir = output_dir / sample.name
    sample_dir.mkdir(parents=True, exist_ok=True)

    if tool == "auto":
        tool = _pick_tool()

    fqc_html: list[Path] = []
    if run_fastqc:
        fqc_html = _run_fastqc(sample, sample_dir, threads=threads)

    eff_adapter = adapter or sample.adapter_r1 or ILLUMINA_UNIVERSAL_ADAPTER

    if tool == "fastp":
        result = _run_fastp(sample, sample_dir, threads=threads,
                            adapter=eff_adapter, min_length=min_length, quality=quality)
    elif tool == "trim_galore":
        result = _run_trim_galore(sample, sample_dir, threads=threads,
                                  min_length=min_length, quality=quality)
    else:
        raise ValueError(f"Unknown tool '{tool}'. Choose 'auto', 'fastp', or 'trim_galore'.")

    result.fastqc_html = fqc_html
    result.is_control  = sample.is_control
    return result


def run_all_preprocessing(
    samples: list[Sample],
    output_dir: Path,
    *,
    tool: str = "auto",
    threads: int = 4,
    adapter: str | None = None,
    min_length: int = MIN_READ_LENGTH_AFTER_TRIM,
    quality: int = BASE_QUALITY_THRESHOLD,
    run_fastqc: bool = True,
) -> list[PreprocessResult]:
    results: list[PreprocessResult] = []
    for sample in samples:
        logger.info("Preprocessing %s  [%s%s] ...",
                    sample.name, sample.layout, ", control" if sample.is_control else "")
        result = run_preprocessing(sample, output_dir, tool=tool, threads=threads,
                                   adapter=adapter, min_length=min_length,
                                   quality=quality, run_fastqc=run_fastqc)
        results.append(result)
        n = result.stats.get("total_reads_after") or 0
        logger.info("  %s → %s reads after trimming",
                    sample.name, f"{n:,}" if n else "unknown")
    write_preprocessing_summary(results, output_dir)
    return results


# ===========================================================================
# PART 5 — Internal helpers
# ===========================================================================

def _build_sample_sheet(samples: list[Sample], *, default_genome: str) -> SampleSheet:
    layouts = {s.layout for s in samples}
    layout  = layouts.pop() if len(layouts) == 1 else "mixed"
    if layout == "mixed":
        logger.warning("Mixed SE/PE samples: %s", {s.name: s.layout for s in samples})

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

    control_map = {s.name: s.control for s in samples if not s.is_control and s.control}

    return SampleSheet(
        samples=samples, layout=layout, conditions=conditions,
        replicates_per_condition=reps_per_cond,
        genome=genome if genome != "mixed" else default_genome,
        is_replicated=is_replicated, control_map=control_map,
    )


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
        with open(json_path) as fh:
            data = json.load(fh)
        bf = data.get("summary", {}).get("before_filtering", {})
        af = data.get("summary", {}).get("after_filtering",  {})
        return {
            "total_reads_before":    bf.get("total_reads"),
            "total_reads_after":     af.get("total_reads"),
            "q30_rate_before":       bf.get("q30_rate"),
            "q30_rate_after":        af.get("q30_rate"),
            "adapter_trimmed_reads": data.get("adapter_cutting", {}).get("adapter_trimmed_reads"),
        }
    except Exception as exc:
        logger.warning("Could not parse fastp JSON (%s): %s", json_path, exc)
        return {}


def _run_trim_galore(
    sample: Sample, sample_dir: Path, *,
    threads: int, min_length: int, quality: int,
) -> PreprocessResult:
    _require("trim_galore")
    sentinel = sample_dir / f"{sample.name}.trim_galore.done"

    def _tg_out(fastq: Path, tag: str) -> Path:
        stem = fastq.name.replace(".fastq.gz", "").replace(".fq.gz", "")
        return sample_dir / f"{stem}{tag}.fq.gz"

    r1_out = _tg_out(sample.r1, "_trimmed" if not sample.is_paired else "_val_1")
    r2_out = _tg_out(sample.r2, "_val_2") if sample.is_paired else None

    sentinel_data = {
        "r1": str(sample.r1), "r2": str(sample.r2) if sample.r2 else None,
        "min_length": min_length, "quality": quality,
    }
    if sentinel.exists():
        try:
            if json.loads(sentinel.read_text()) == sentinel_data:
                r1_cached = r1_out if r1_out.exists() else _find_trimmed(sample_dir, "R1")
                r2_cached = (
                    (r2_out if (r2_out and r2_out.exists()) else _find_trimmed(sample_dir, "R2"))
                    if sample.is_paired else None
                )
                if r1_cached.exists():
                    logger.info("Trim Galore cached — skipping %s", sample.name)
                    return PreprocessResult(
                        sample_name=sample.name, r1_trimmed=r1_cached, r2_trimmed=r2_cached,
                        tool="trim_galore", stats=_parse_trim_galore_report(sample_dir),
                    )
        except Exception:
            pass

    cmd = [
        "trim_galore", "--illumina", "--fastqc",
        "--length", str(min_length), "--quality", str(quality),
        "--cores", str(threads), "--output_dir", str(sample_dir),
    ]
    if sample.is_paired:
        cmd += ["--paired", str(sample.r1), str(sample.r2)]
    else:
        cmd.append(str(sample.r1))
    _run(cmd, label=f"Trim Galore [{sample.name}]")
    sentinel.write_text(json.dumps(sentinel_data))
    return PreprocessResult(
        sample_name=sample.name,
        r1_trimmed=r1_out if r1_out.exists() else _find_trimmed(sample_dir, "R1"),
        r2_trimmed=(r2_out if (r2_out and r2_out.exists()) else _find_trimmed(sample_dir, "R2"))
                   if sample.is_paired else None,
        tool="trim_galore", stats=_parse_trim_galore_report(sample_dir),
    )


def _parse_trim_galore_report(sample_dir: Path) -> dict[str, Any]:
    reports = list(sample_dir.glob("*_trimming_report.txt"))
    if not reports:
        return {}
    stats: dict[str, Any] = {}
    try:
        with open(reports[0]) as fh:
            for line in fh:
                if "Total reads processed:" in line:
                    stats["total_reads_before"] = _parse_int(line)
                elif "Reads written (passing filters):" in line:
                    stats["total_reads_after"] = _parse_int(line)
                elif "Reads with adapters:" in line:
                    stats["adapter_trimmed_reads"] = _parse_int(line)
    except Exception as exc:
        logger.warning("Could not parse Trim Galore report: %s", exc)
    return stats


def _parse_int(line: str) -> int | None:
    import re
    m = re.search(r"[\d,]+", line.split(":")[1] if ":" in line else line)
    return int(m.group().replace(",", "")) if m else None


def _find_trimmed(sample_dir: Path, read: str) -> Path:
    tag = "val_1" if read == "R1" else "val_2"
    for pat in (f"*{tag}*.fq.gz", "*trimmed*.fastq.gz"):
        hits = list(sample_dir.glob(pat))
        if hits:
            return hits[0]
    return sample_dir / f"{read}_trimmed.fq.gz"


def _pick_tool() -> str:
    if shutil.which("fastp"):       return "fastp"
    if shutil.which("trim_galore"): return "trim_galore"
    raise RuntimeError(
        "Neither fastp nor trim_galore found in PATH.\n"
        "Install: conda install -c bioconda fastp   "
        "OR   conda install -c bioconda trim-galore"
    )


def _require(tool: str) -> None:
    if not shutil.which(tool):
        raise RuntimeError(
            f"'{tool}' not found in PATH.  "
            f"Install: conda install -c bioconda {tool.replace('_', '-')}"
        )


def _run(cmd: list[str], *, label: str) -> None:
    logger.info("Running: %s", label)
    result = subprocess.run(cmd, capture_output=True, text=True)
    log_tool_output(cmd, result)
    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed (exit {result.returncode}):\n"
            f"STDERR: {result.stderr[-2000:]}"
        )
