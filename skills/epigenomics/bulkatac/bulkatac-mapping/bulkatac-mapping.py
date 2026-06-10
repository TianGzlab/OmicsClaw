#!/usr/bin/env python3
"""
bulkatac-mapping.py — Bulk ATAC-seq mapping + post-alignment QC (Step 2).

Scope
-----
  Step 2a — Alignment & BAM processing
    Trimmed FASTQs from Step 1
    → Bowtie2 alignment (ENCODE default; BWA MEM optional)
    → ENCODE BAM filtering  (-F 1804 -f 2 -q 30 PE | -F 1796 -q 30 SE)
    → Mitochondrial read removal
    → Duplicate removal (samtools markdup -r)
    → ENCODE blacklist removal (optional)
    → Library complexity (NRF / PBC1 / PBC2)
    → Cross-sample downsampling to common usable depth

  Step 2b — Post-alignment QC
    → BigWig signal tracks (deepTools bamCoverage, RPGC normalisation)
    → TSS enrichment score + profile (deepTools computeMatrix)
    → Fragment-length distribution (samtools)
    → Per-sample + cross-sample comparison figures (PNG dpi=300 + PDF)

  BAMs are NOT Tn5-shifted (+4/-5).  Downstream tools handle the offset
  internally: TOBIAS ATACorrect applies the shift and corrects Tn5 sequence
  bias; MACS2 has --shift/--extsize.  Pre-shifting would double-correct.

Pipeline
--------
  1. Bowtie2 (default) / BWA MEM  →  raw BAM  (sort + index)
  2. ENCODE BAM filter  →  filtered BAM (MAPQ ≥ 30)
  3. Remove chrM/MT/M   →  no_mito BAM
  4. samtools markdup -r →  dedup BAM
  5. (Optional) Remove ENCODE blacklist regions
  6. Compute NRF, PBC1, PBC2
  7. Downsample all samples to min(n_usable)
  8. BigWig (RPGC, binSize 10, --ignoreDuplicates, --minMappingQuality 30)
  9. TSS enrichment (deepTools computeMatrix reference-point)
  10. Fragment-length distribution

Bowtie2 parameters (ENCODE / CebolaLab)
----------------------------------------
  PE: --very-sensitive --no-mixed --no-discordant -I 25 -X 700
  SE: --very-sensitive

ENCODE BAM filter flags
-----------------------
  PE: samtools view -F 1804 -f 2 -q 30
  SE: samtools view -F 1796 -q 30

Output layout
-------------
  <output>/
  ├── README.md
  ├── report.md
  ├── result.json
  ├── mapping_summary.csv
  ├── reproducibility/
  ├── reference_{genome}/             (if --prepare-ref)
  ├── bam/                            (all sample BAMs, flat)
  ├── bigwig/                         (RPGC signal tracks)
  └── qc_after_mapping/
      ├── qc_after_mapping_summary.csv
      ├── tss_enrichment/             (per-sample + all + vs_encode)
      └── fragment_length/            (per-sample + all)

References
----------
  ENCODE ATAC-seq pipeline : https://www.encodeproject.org/atac-seq/
  Bowtie2                  : https://github.com/BenLangmead/bowtie2
  CebolaLab ATAC-seq       : https://github.com/CebolaLab/ATAC-seq
  deepTools                : https://github.com/deeptools/deepTools
  deepTools genome sizes   : https://github.com/deeptools/deepTools/blob/master/docs/content/feature/effectiveGenomeSize.rst
  TOBIAS (footprinting)    : https://github.com/loosolab/TOBIAS
  TOBIAS paper             : https://doi.org/10.1038/s41467-020-18035-1
  samtools                 : https://github.com/samtools/samtools
  bedtools                 : https://github.com/arq5x/bedtools2

Quick-start
-----------
  # Auto-download and build reference
  python bulkatac-mapping.py \\
      --prev-result output/preprocess/result.json \\
      --ref-dir /path/to/refs \\
      --wd output

  # Use an existing index (skips download)
  python bulkatac-mapping.py \\
      --prev-result output/preprocess/result.json \\
      --ref-dir /path/to/refs \\
      --bowtie2-index /path/to/bowtie2/hg38 \\
      --wd output
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_SKILL_DIR    = Path(__file__).resolve().parent
_BULKATAC_DIR = _SKILL_DIR.parent                            # .../bulkatac/
_PROJECT_ROOT = _BULKATAC_DIR.parent.parent.parent           # OmicsClaw/

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SKILL_NAME    = "bulkatac-mapping"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkatac/bulkatac-mapping/bulkatac-mapping.py"

# ---------------------------------------------------------------------------
# _lib imports
# ---------------------------------------------------------------------------
# Relocate into the omicsclaw_bulkatac sub-env before the tool-backed _lib imports.
from skills.epigenomics.bulkatac._lib.subenv_bootstrap import ensure_bulkatac_env  # noqa: E402
from skills.epigenomics.bulkatac._lib.progress import tty_write  # noqa: E402
ensure_bulkatac_env()

from skills.epigenomics.bulkatac._lib.preprocessing import (           # noqa: E402
    Sample, SampleSheet,
)
from skills.epigenomics.bulkatac._lib.mapping import (                 # noqa: E402
    GenomeFiles, validate_genome_files,
    MappingResult,
    run_all_mapping,
    build_mapping_summary,
    write_mapping_summary,
    prepare_reference,
)
from skills.epigenomics.bulkatac._lib.QC_after_mapping import (          # noqa: E402
    QcAfterMappingResult,
    run_all_qc_after_mapping,
    write_qc_after_mapping_summary,
)
from skills.epigenomics.bulkatac._lib.encode_qc_criteria import (      # noqa: E402
    ENCODE_QC_THRESHOLDS,
    UsableReadRule,
)
from omicsclaw.common.runlog import attach_run_log                    # noqa: E402



# ---------------------------------------------------------------------------
# Load Step 1 result.json
# ---------------------------------------------------------------------------

def load_mapping_result(result_json: Path) -> tuple[SampleSheet, list[Any]]:
    """
    Reconstruct SampleSheet + PreprocessResult stubs from Step 1 result.json.
    """
    import types

    data    = json.loads(result_json.read_text())
    ss_data = data["sample_sheet"]
    genome  = ss_data["genome"]

    samples = [
        Sample(
            name      = s["name"],
            condition = s["condition"],
            replicate = int(s["replicate"]),
            r1        = Path(s["r1"]),
            r2        = Path(s["r2"]) if s.get("r2") else None,
            genome    = s.get("genome", genome),
        )
        for s in ss_data["samples"]
    ]

    reps_per_cond: dict[str, list[int]] = {
        cond: [s.replicate for s in samples if s.condition == cond]
        for cond in ss_data["conditions"]
    }

    sheet = SampleSheet(
        samples                  = samples,
        layout                   = ss_data["layout"],
        conditions               = ss_data["conditions"],
        replicates_per_condition = reps_per_cond,
        genome                   = genome,
        is_replicated            = ss_data["is_replicated"],
    )

    PR = types.SimpleNamespace
    preprocess_results = [
        PR(
            sample_name = e["sample"],
            tool        = e["tool"],
            r1_trimmed  = Path(e["r1_trimmed"]),
            r2_trimmed  = Path(e["r2_trimmed"]) if e.get("r2_trimmed") else None,
            stats       = e.get("stats", {}),
        )
        for e in data.get("preprocessing", [])
    ]

    return sheet, preprocess_results


# ---------------------------------------------------------------------------
# Report + result.json
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    sheet: SampleSheet,
    mapping_results: list[MappingResult],
    qc_results: list[QcAfterMappingResult],
    params: dict[str, Any],
    step1_data: dict[str, Any],
    genome_files: GenomeFiles | None = None,
    prev_result_path: Path | None = None,
) -> None:
    rule = UsableReadRule(layout=sheet.layout)

    lines: list[str] = [
        "# ATAC-seq Mapping Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "", "---", "",
        "## Step 2a — Alignment and BAM Filtering", "",
        f"- **Samples**: {len(sheet)}",
        f"- **Layout**: {sheet.layout}",
        f"- **Genome**: {sheet.genome}",
        f"- **Aligner**: {params.get('aligner', 'bowtie2')}",
        "",
        "### Mapping Statistics\n",
        "| Sample | Align% | Frags | %mito | NRF | PBC1 | PBC2 | DS |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in mapping_results:
        ds = f"→{r.downsample_target:,}" if r.downsampled else "—"
        lines.append(
            f"| {r.sample_name} | {r.align_rate*100:.1f}% | {r.n_fragments:,} "
            f"| {r.pct_mito:.1f}% | {r.nrf:.3f} | {r.pbc1:.3f} | {r.pbc2:.2f} | {ds} |"
        )

    # Step 2b: QC after mapping
    qc_by_name = {q.sample_name: q for q in qc_results}
    has_tss = any(q.tss_score > 0 for q in qc_results)
    if has_tss:
        lines += [
            "", "## Step 2b — Post-alignment QC", "",
            "### TSS Enrichment & Fragment Length\n",
            "| Sample | TSS score | Tier | Frag mode | NFR% | Mono% |",
            "|---|---|---|---|---|---|",
        ]
        for r in mapping_results:
            q = qc_by_name.get(r.sample_name)
            if q:
                lines.append(
                    f"| {q.sample_name} | {q.tss_score:.2f} | {q.tss_tier} "
                    f"| {q.frag_mode} bp | {q.nfr_fraction*100:.1f}% "
                    f"| {q.mono_fraction*100:.1f}% |"
                )

    lines += [
        "",
        "### ENCODE QC Thresholds\n",
        "| Metric | Preferred | Acceptable |",
        "|---|---|---|",
        "| NRF            | > 0.90  | > 0.80 |",
        "| PBC1           | > 0.90  | > 0.50  (< 0.50 = severe bottleneck) |",
        "| PBC2           | > 3.0   | > 1.0 |",
        "| Frags PE       | ≥ 25 M  | ≥ 10 M |",
        "| Alignment rate | > 95%   | > 80% |",
        "| %mito          | < 5%    | < 20% |",
        "| TSS enrichment | > 7.0   | > 5.0 (cell line) / > 3.0 (tissue) |",
        "",
        "**Usable read rule:**",
    ]
    for line in rule.description().splitlines():
        lines.append(f"  {line}")

    if any(r.downsampled for r in mapping_results):
        t = next(r.downsample_target for r in mapping_results if r.downsampled)
        lines += ["", f"**Downsampling applied** to {t:,} fragments (min usable depth)."]

    lines += [
        "",
        "## Next Steps", "",
        "- **Step 3a**: Peak calling (MACS2) → consensus peak set",
        "- **Step 3b**: FRiP, IDR, peak annotation",
        "", "---", "",
        "> **Disclaimer**: OmicsClaw is a research tool. Results require expert interpretation.",
    ]

    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    # ── result.json ────────────────────────────────────────────────────────
    result: dict[str, Any] = {
        "skill":           SKILL_NAME,
        "version":         SKILL_VERSION,
        "log":             str(output_dir / f"{SKILL_NAME}.log"),
        "steps_completed": step1_data.get("steps_completed", []) + ["mapping", "qc_after_mapping"],
        "steps_pending":   [s for s in step1_data.get("steps_pending", [])
                            if s not in ("mapping", "qc_after_mapping")],
        "params":          params,
        "mapping": [
            {
                "sample":            r.sample_name,
                "bam":               str(r.bam),
                "bam_full":          str(r.bam_full),
                "aligner":           r.aligner,
                "n_total_reads":     r.n_total_reads,
                "n_mapped_reads":    r.n_mapped_reads,
                "n_fragments":       r.n_fragments,
                "align_rate":        r.align_rate,
                "pct_mito":          r.pct_mito,
                "dup_rate":          r.dup_rate,
                "nrf":               r.nrf,
                "pbc1":              r.pbc1,
                "pbc2":              r.pbc2,
                "downsampled":       r.downsampled,
                "downsample_target": r.downsample_target,
            }
            for r in mapping_results
        ],
        "qc_after_mapping": [
            {
                "sample":         q.sample_name,
                "tss_score":      q.tss_score,
                "tss_tier":       q.tss_tier,
                "frag_mode_bp":   q.frag_mode,
                "nfr_fraction":   q.nfr_fraction,
                "mono_fraction":  q.mono_fraction,
                "bigwig":         str(q.bigwig) if q.bigwig else None,
            }
            for q in qc_results
        ],
        "encode_qc_thresholds": ENCODE_QC_THRESHOLDS,
        "usable_read_rule": {
            "layout":          sheet.layout,
            "excl_flags":      rule.samtools_excl_flags,
            "req_flags":       rule.samtools_req_flags,
            "mapq_threshold":  rule.mapq_threshold,
            "exclude_contigs": sorted(rule.exclude_contigs),
        },
        "genome_files": {
            "genome":      genome_files.genome if genome_files else "",
            "fasta":       str(genome_files.fasta) if genome_files and genome_files.fasta else None,
            "gtf":         str(genome_files.gtf) if genome_files and genome_files.gtf else None,
            "blacklist":   str(genome_files.blacklist) if genome_files and genome_files.blacklist else None,
            "chrom_sizes": str(genome_files.chrom_sizes) if genome_files and genome_files.chrom_sizes else None,
        },
        "sample_sheet":        step1_data.get("sample_sheet"),
        "prev_result":         str(prev_result_path),
        "prev_params":         step1_data.get("params"),
        "prev_preprocessing":  step1_data.get("preprocessing"),
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

def write_reproducibility(
    output_dir: Path,
    params: dict[str, Any],
    prev_result_path: Path,
) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)

    cmd = (
        f"python {SCRIPT_REL} "
        f"--prev-result {shlex.quote(str(prev_result_path))} "
        f"--ref-dir {shlex.quote(str(params.get('ref_dir', '')))} "
        f"--wd {shlex.quote(str(output_dir))}"
    )
    for key, flag in [
        ("aligner",       "--aligner"),
        ("threads",       "--threads"),
        ("bwa_index",  "--bwa-index"),
        ("bowtie2_index", "--bowtie2-index"),
        ("blacklist",     "--blacklist"),
    ]:
        v = params.get(key)
        if v is not None:
            cmd += f" {flag} {shlex.quote(str(v))}"
    if params.get("downsample", False):
        cmd += " --downsample"

    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    # Pinned package versions → reproducibility/requirements.txt, via the
    # shared OmicsClaw helper so bulk-ATAC uses the same filename and format
    # as every other domain's skills.
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["pandas", "numpy", "matplotlib"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            f"{SKILL_NAME} v{SKILL_VERSION} — Bulk ATAC-seq alignment + QC.\n\n"
            "Step 2a: Bowtie2/BWA alignment, ENCODE BAM filtering, dedup,\n"
            "         chrM removal, NRF/PBC1/PBC2, cross-sample downsampling.\n"
            "Step 2b: BigWig (RPGC), TSS enrichment, fragment-length QC.\n\n"
            "By default, downloads genome FASTA and builds aligner index\n"
            "in --ref-dir.  Skip download with --bowtie2-index or --bwa-index."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── Required arguments ────────────────────────────────────────────────────
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", required=False, dest="prev_result", default=None,
                     help="result.json from bulkatac-preprocess (Step 1); "
                          "accepts --input too for OmicsClaw runner compatibility. "
                          "If omitted, auto-detected from --wd's sibling "
                          "preprocessing/result.json.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too for "
                          "OmicsClaw runner compatibility). Default: sibling "
                          "of prev-result's parent dir (e.g. .../mapping/).")
    req.add_argument("--genome", default=None,
                     help="Reference genome build (e.g. hg38, mm10, sacCer3). "
                          "Overrides the genome from preprocessing result.json. "
                          "Required if preprocessing was run without --genome.")
    req.add_argument("--ref-dir", default=None, dest="ref_dir",
                     help="Directory for reference files (FASTA, index, blacklist). "
                          "Downloaded and built automatically if not already present. "
                          "Default: {prev-result parent}/../reference_{genome}/.")

    # ── Reference arguments ───────────────────────────────────────────────────
    ref = p.add_argument_group("reference")
    ref.add_argument("--aligner", default="bowtie2", choices=["bwa", "bowtie2"],
                     help="Aligner (default: bowtie2, ENCODE standard).")
    idx = ref.add_mutually_exclusive_group()
    idx.add_argument("--bwa-index", default=None, dest="bwa_index",
                     help="Existing BWA index prefix (skips download; --aligner bwa).")
    idx.add_argument("--bowtie2-index", default=None, dest="bowtie2_index",
                     help="Existing Bowtie2 index prefix (skips download; --aligner bowtie2).")
    ref.add_argument("--fasta-url", default=None, dest="fasta_url",
                     help="Override FASTA download URL (auto-selected from built-in table if omitted).")
    ref.add_argument("--blacklist-url", default=None, dest="blacklist_url",
                     help="Override blacklist BED download URL.")
    ref.add_argument("--no-blacklist", action="store_true", dest="no_blacklist",
                     help="Skip blacklist download/filtering even if genome is known.")
    ref.add_argument("--blacklist", default=None,
                     help="Path to an existing ENCODE blacklist BED file.")

    # ── Optional arguments ────────────────────────────────────────────────────
    opt = p.add_argument_group("optional")
    opt.add_argument("--cell-type", default=None, dest="cell_type",
                     choices=["cell_line", "tissue"],
                     help="Cell type for ENCODE TSS enrichment tier (human/mouse only). "
                          "Omit to compute TSS score without tier assignment.")
    opt.add_argument("--threads", type=int, default=16)
    opt.add_argument("--downsample", action="store_true", dest="downsample",
                     help="Downsample all samples to min(n_usable) depth. "
                          "Disabled by default: ENCODE does not downsample, "
                          "relying on RPGC for visualization and DESeq2/edgeR "
                          "size factors for DA (encodeproject.org/atac-seq). "
                          "However, Reske et al. 2020 (PMID:32321567) showed "
                          "that library complexity differences can confound DA "
                          "results and recommend subsampling to equivalent "
                          "complexity before normalization.")
    opt.add_argument("--keep-intermediates", action="store_true", dest="keep_intermediates",
                     help="Keep raw/filtered/dedup BAMs for debugging.")
    return p


# ── Progress reporting ──────────────────────────────────────────────────
# Written to the controlling terminal (/dev/tty) when one exists, so step
# progress shows live even though the OmicsClaw runner buffers the piped
# stdout; falls back to stdout when there is no terminal. See _emit_progress.
_STEPS = [
    "Load Step-1 result + resolve genome",
    "Resolve reference genome (download FASTA + build aligner index)",
    "Alignment + ENCODE BAM filtering + dedup + NRF/PBC  (Step 2a)",
    "Post-alignment QC — BigWig, TSS enrichment, fragment length  (Step 2b)",
    "Write report, reproducibility, and result.json",
]


def _emit_progress(text: str) -> None:
    """Show progress live on the controlling terminal, bypassing the
    OmicsClaw runner's stdout capture; fall back to stdout when there is
    no terminal (CI / redirected output)."""
    if not tty_write(text):
        print(text, flush=True)


def _print_step_plan() -> None:
    n = len(_STEPS)
    lines = [f"\n[{SKILL_NAME}] pipeline — {n} step(s):"]
    lines += [f"  [{i}/{n}] {desc}" for i, desc in enumerate(_STEPS, 1)]
    lines.append("")
    _emit_progress("\n".join(lines))


def _step(n: int, msg: str) -> None:
    _emit_progress(f"[{SKILL_NAME}] ==> step {n}/{len(_STEPS)}: {msg}")
    logger.info("==> step %d/%d: %s", n, len(_STEPS), msg)


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    # Auto-detect prev-result if not provided
    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    elif args.wd:
        # --wd is this skill's own dir; preprocessing is a sibling under --wd's parent
        prev_result_path = Path(args.wd).parent / "preprocessing" / "result.json"
    else:
        parser.error("Provide --prev-result or --wd so the preprocessing "
                     "result.json can be located.")
    if not prev_result_path.exists():
        parser.error(f"Preprocessing result not found: {prev_result_path}\n"
                     f"  Use --prev-result to specify it explicitly.")

    _print_step_plan()

    # ── Load Step 1 ───────────────────────────────────────────────────────────
    _step(1, "loading Step-1 preprocessing result")
    step1_data               = json.loads(prev_result_path.read_text())
    sheet, preprocess_results = load_mapping_result(prev_result_path)
    # --genome CLI overrides the value from preprocessing result.json
    genome = args.genome or sheet.genome
    if not genome:
        parser.error(
            "--genome is required because preprocessing result.json has no genome.\n"
            "  Example: --genome hg38"
        )
    sheet.genome = genome

    # ── Derive defaults from prev-result location ─────────────────────────────
    project_dir = prev_result_path.resolve().parent.parent  # the shared project dir

    output_dir = Path(args.wd) if args.wd else project_dir / "mapping"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    ref_dir = Path(args.ref_dir) if args.ref_dir else project_dir / f"reference_{genome}"

    logger.info("Loaded Step 1: %d samples  [%s]  genome=%s",
                len(sheet), sheet.layout, genome)

    # ── Resolve genome index ──────────────────────────────────────────────────
    bwa_index  = args.bwa_index
    bowtie2_index = args.bowtie2_index
    blacklist     = Path(args.blacklist) if args.blacklist else None

    _step(2, "resolving reference genome — "
             + ("using supplied aligner index"
                if (bwa_index or bowtie2_index)
                else "downloading FASTA + building aligner index (slow)"))
    if bwa_index or bowtie2_index:
        # User provided an existing index — skip download
        genome_files = GenomeFiles(
            genome        = genome,
            bwa_index     = Path(bwa_index)  if bwa_index  else None,
            bowtie2_index = Path(bowtie2_index) if bowtie2_index else None,
            blacklist     = blacklist,
        )
    else:
        # Download and build reference automatically
        logger.info("Preparing reference for genome '%s' in %s ...", genome, ref_dir)

        genome_files = prepare_reference(
            genome, ref_dir,
            aligner               = args.aligner,
            threads               = args.threads,
            fasta_url             = args.fasta_url,
            blacklist_url         = args.blacklist_url,
            download_blacklist_bed= not args.no_blacklist,
        )

        if args.aligner == "bwa":
            bwa_index = str(genome_files.bwa_index)
        else:
            bowtie2_index = str(genome_files.bowtie2_index)

        if genome_files.blacklist and blacklist is None:
            blacklist = genome_files.blacklist

    validate_genome_files(genome_files, require_index=True)

    params: dict[str, Any] = {
        "aligner":            args.aligner,
        "threads":            args.threads,
        "bwa_index":       bwa_index,
        "bowtie2_index":      bowtie2_index,
        "blacklist":          str(blacklist) if blacklist else None,
        "downsample":         args.downsample,
        "keep_intermediates": args.keep_intermediates,
        "ref_dir":            str(ref_dir),
        "cell_type":          args.cell_type,
    }

    # ── Step 2a: mapping (all outputs directly under output_dir) ────────────
    bam_dir = output_dir / "bam"

    _step(3, f"alignment + ENCODE filtering + dedup + NRF/PBC on {len(sheet)} sample(s)")
    mapping_results = run_all_mapping(
        list(zip(
            [s.name for s in sheet.samples],
            [pr.r1_trimmed for pr in preprocess_results],
            [pr.r2_trimmed for pr in preprocess_results],
        )),
        genome_files,
        bam_dir,
        aligner            = args.aligner,
        threads            = args.threads,
        downsample         = args.downsample,
        keep_intermediates = args.keep_intermediates,
    )

    write_mapping_summary(mapping_results, output_dir)

    # ── Step 2b: QC after mapping ─────────────────────────────────────────────
    _step(4, "post-alignment QC — BigWig, TSS enrichment, fragment length")
    qc_results = run_all_qc_after_mapping(
        mapping_results,
        genome_files,
        output_dir,
        threads     = args.threads,
        tissue_type = args.cell_type,   # None when not specified
    )

    write_qc_after_mapping_summary(
        qc_results,
        output_dir / "qc_after_mapping",
    )

    # ── Outputs ───────────────────────────────────────────────────────────────
    _step(5, "writing report, reproducibility, and result.json")
    write_report(output_dir, sheet, mapping_results, qc_results, params, step1_data,
                 genome_files=genome_files, prev_result_path=prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)

    # README
    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        "`bam/` — deduplicated BAMs per sample (full-depth).\n"
        "`bigwig/` — RPGC-normalised signal tracks.\n"
        "`qc_after_mapping/` — TSS enrichment and fragment-length QC figures.\n"
        "`mapping_summary.csv` — per-sample alignment and library complexity metrics.\n"
        f"`{SKILL_NAME}.log` — full run log: narrative + every tool's stdout/stderr.\n"
        "\nNext: Step 3a (peak calling with MACS2).\n"
    )

    ds_n   = sum(1 for r in mapping_results if r.downsampled)
    tss_ok = sum(1 for q in qc_results if q.tss_score > 0)
    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
        f"  {len(mapping_results)} samples  [{sheet.layout}]\n"
        f"  Aligner:        {args.aligner}\n"
        f"  Downsampled:    {ds_n}/{len(mapping_results)} samples\n"
        f"  TSS enrichment: {tss_ok}/{len(qc_results)} computed\n"
        f"  BAMs:           {bam_dir}\n"
        f"  BigWigs:        {output_dir / 'bigwig'}\n"
        f"  QC figures:     {output_dir / 'qc_after_mapping'}\n"
        f"  Summary:        {output_dir / 'mapping_summary.csv'}\n"
        f"  Report:         {output_dir / 'report.md'}\n"
        f"\n  Next → bulkatac-peak-calling → bulkatac-DA\n"
        f"         → bulkatac-motif-enrichment (sequence motifs)  |  "
        f"bulkatac-footprinting (TF occupancy)\n"
    )


if __name__ == "__main__":
    main()