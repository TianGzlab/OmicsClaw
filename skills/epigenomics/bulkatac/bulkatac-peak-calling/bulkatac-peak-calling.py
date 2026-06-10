#!/usr/bin/env python3
"""
bulkatac-peak-calling.py — Bulk ATAC-seq peak calling + post-peak QC (Step 3).

Scope
-----
  Step 3a — Peak calling
    Full-depth dedup BAMs from Step 2
    → MACS2 callpeak (PE: BAMPE --nomodel; SE: --shift -37 --extsize 73)
    → Per-sample narrowPeak + summits
    → Consensus peak set (bedtools merge of all samples)
    → SAF format for featureCounts
    → Peak count matrix (featureCounts)

  Step 3b — Peak annotation
    → Distance to nearest TSS (bedtools closest)
    → Genomic feature classification (promoter/proximal/distal/intergenic)
    → Annotation pie chart + TSS distance histogram

  Step 3c — Post-peak QC & visualization
    → FRiP (Fraction of Reads in Peaks) per sample
    → TSS heatmap (deepTools plotHeatmap, all samples)
    → Peak-centered heatmap (per-sample + all-samples)
    → PCA on peak count matrix (DESeq2 VST)
    → Sample correlation heatmap
    → ENCODE IDR reproducibility analysis

Pipeline
--------
  1. MACS2 callpeak per sample     →  peaks/{sample}/qvalue{q}/narrowPeak
  2. ENCODE naive overlap consensus:
     a. Per condition: pool BAMs → MACS2 → intersect pooled ∩ rep1 ∩ rep2 (≥50%)
     b. Union across conditions  →  consensus/qvalue{q}/consensus_peaks.bed
  3. BED → SAF (1-based start)     →  consensus_peaks.saf
  4. featureCounts                  →  peak_counts.txt
  5. bedtools closest               →  annotation/qvalue{q}/
  6. FRiP per sample                →  frip/qvalue{q}/
  7. TSS + peak heatmaps            →  heatmap/qvalue{q}/
  8. PCA + correlation              →  pca/qvalue{q}/ + sample_correlation/qvalue{q}/
  9. ENCODE IDR (opt-in: --idr)     →  IDR/qvalue{q}/

Output layout
-------------
  <output>/
  ├── report.md, result.json, peak_calling_summary.csv
  ├── peaks/{sample}/qvalue{q}/       (per-sample narrowPeak + summits)
  ├── consensus/qvalue{q}/            (ENCODE naive overlap consensus)
  │   ├── {condition}/                 (pooled peaks, per-rep intersections)
  │   ├── consensus_peaks.bed          (union of reproducible peaks)
  │   ├── consensus_peaks.saf
  │   └── peak_counts.txt
  ├── annotation/qvalue{q}/           (annotated peaks, pie chart, TSS dist)
  └── qc_after_peak_calling/
      ├── frip/qvalue{q}/
      ├── pca/qvalue{q}/
      ├── sample_correlation/qvalue{q}/
      └── IDR/qvalue{q}/              (opt-in: --idr)

References
----------
  ENCODE ATAC-seq pipeline : https://www.encodeproject.org/atac-seq/
  MACS2                    : https://github.com/macs3-project/MACS
  CebolaLab ATAC-seq       : https://github.com/CebolaLab/ATAC-seq
  deepTools                : https://github.com/deeptools/deepTools
  featureCounts (Subread)  : https://subread.sourceforge.net/

Quick-start
-----------
  python bulkatac-peak-calling.py \\
      --prev-result output/step2/result.json \\
      --wd output
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import shutil
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

SKILL_NAME    = "bulkatac-peak-calling"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkatac/bulkatac-peak-calling/bulkatac-peak-calling.py"

# ---------------------------------------------------------------------------
# _lib imports
# ---------------------------------------------------------------------------
# Relocate into the omicsclaw_bulkatac sub-env before the tool-backed _lib imports.
from skills.epigenomics.bulkatac._lib.subenv_bootstrap import ensure_bulkatac_env  # noqa: E402
from skills.epigenomics.bulkatac._lib.progress import tty_write  # noqa: E402
ensure_bulkatac_env()

from skills.epigenomics.bulkatac._lib.mapping import (                  # noqa: E402
    MappingResult, GenomeFiles,
)
from skills.epigenomics.bulkatac._lib.peak_calling import (             # noqa: E402
    PeakCallingResult, ConsensusPeakResult,
    run_all_peak_calling,
    build_consensus_peaks,
    build_count_matrix,
    get_macs2_genome_size,
    peak_count_tier,
    write_peak_calling_summary,
)
from skills.epigenomics.bulkatac._lib.peak_annotation import (          # noqa: E402
    annotate_peaks,
    annotate_per_condition_peaks,
    plot_annotation_pie,
    plot_annotation_comparison,
    plot_annotation_grouped_bar,
    plot_tss_distance_histogram,
    plot_tss_distance_comparison,
)
from skills.epigenomics.bulkatac._lib.QC_after_peak_calling import (          # noqa: E402
    compute_frip,
    plot_frip_bar,
    plot_tss_heatmap,
    plot_peak_heatmap,
    plot_pca,
    plot_sample_correlation,
    run_all_idr,
    plot_idr_summary,
    write_qc_after_peak_calling_summary,
)
from omicsclaw.common.runlog import attach_run_log  # noqa: E402


# ---------------------------------------------------------------------------
# Load Step 2 result.json
# ---------------------------------------------------------------------------

def load_step2_result(result_json: Path) -> dict[str, Any]:
    """Load Step 2 result.json and reconstruct MappingResults + GenomeFiles."""
    data = json.loads(result_json.read_text())

    # Reconstruct MappingResults
    mapping_results = []
    for m in data.get("mapping", []):
        mr = MappingResult(
            sample_name=m["sample"],
            bam=Path(m["bam"]),
            aligner=m.get("aligner", "bowtie2"),
            n_usable=m.get("n_fragments", 0),
        )
        mapping_results.append(mr)

    # Reconstruct GenomeFiles
    ss = data.get("sample_sheet", {})
    genome = ss.get("genome", "")

    # Find GTF and other genome files from step1/step2 data
    params = data.get("params", {})
    ref_dir = params.get("ref_dir")

    gf = GenomeFiles(genome=genome)

    # Try to load genome files from result.json (written by Step 2)
    gf_data = data.get("genome_files") or {}

    # FASTA
    if gf_data.get("fasta") and Path(gf_data["fasta"]).exists():
        gf.fasta = Path(gf_data["fasta"])
    elif ref_dir:
        # Fallback: search ref_dir for {genome}.fa
        for fa_candidate in [
            Path(ref_dir) / f"{genome}.fa",
            Path(ref_dir) / "fasta" / f"{genome}.fa",
        ]:
            if fa_candidate.exists():
                gf.fasta = fa_candidate
                break

    # GTF
    if gf_data.get("gtf") and Path(gf_data["gtf"]).exists():
        gf.gtf = Path(gf_data["gtf"])
    elif ref_dir:
        # Fallback: search ref_dir for GTF files
        ref_path = Path(ref_dir)
        for gtf_candidate in ref_path.glob("*.gtf*"):
            gf.gtf = gtf_candidate
            break

    # Second fallback: search reference_* dirs next to result.json
    if not gf.gtf:
        result_parent = result_json.parent
        for ref_candidate in sorted(result_parent.glob("reference_*")):
            if ref_candidate.is_dir():
                for gtf_candidate in ref_candidate.glob("*.gtf*"):
                    gf.gtf = gtf_candidate
                    break
            if gf.gtf:
                break

    if gf_data.get("blacklist") and Path(gf_data["blacklist"]).exists():
        gf.blacklist = Path(gf_data["blacklist"])
    if gf_data.get("chrom_sizes") and Path(gf_data["chrom_sizes"]).exists():
        gf.chrom_sizes = Path(gf_data["chrom_sizes"])

    # Get BigWig paths from qc_after_mapping
    bigwig_paths = {}
    for q in data.get("qc_after_mapping", []):
        bw = q.get("bigwig")
        if bw and Path(bw).exists():
            bigwig_paths[q["sample"]] = Path(bw)

    # Get conditions and sample info
    conditions = ss.get("conditions", [])
    samples = ss.get("samples", [])
    sample_conditions = {s["name"]: s.get("condition", "") for s in samples}
    is_paired = ss.get("layout", "paired-end") == "paired-end"

    return {
        "data": data,
        "mapping_results": mapping_results,
        "genome_files": gf,
        "genome": genome,
        "bigwig_paths": bigwig_paths,
        "conditions": conditions,
        "sample_conditions": sample_conditions,
        "is_paired": is_paired,
    }


# ---------------------------------------------------------------------------
# Report + result.json
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    peak_results: list[PeakCallingResult],
    consensus: ConsensusPeakResult,
    qc_results: list,
    annotation_result,
    params: dict[str, Any],
    step2_data: dict[str, Any],
    counts_file: Path | None = None,
    genome_files_obj: GenomeFiles | None = None,
    prev_result_path: Path | None = None,
    condition_annotations: dict | None = None,
) -> None:
    lines: list[str] = [
        "# ATAC-seq Peak Calling Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "", "---", "",
        "## Step 3a — Peak Calling", "",
        "### Per-sample peaks\n",
        "| Sample | Peaks | ENCODE tier |",
        "|---|---|---|",
    ]
    for r in peak_results:
        lines.append(f"| {r.sample_name} | {r.n_peaks:,} | {r.peak_count_tier} |")

    lines += [
        "",
        f"**Consensus peaks**: {consensus.n_peaks:,}  "
        f"[{peak_count_tier(consensus.n_peaks)}]",
        "",
        "### ENCODE Peak Count Thresholds\n",
        "| Metric | Preferred | Acceptable |",
        "|---|---|---|",
        "| Replicated peaks | ≥ 150,000 | ≥ 100,000 |",
        "| IDR peaks        | ≥ 70,000  | ≥ 50,000  |",
        "| FRiP             | > 0.3     | > 0.2     |",
        "",
    ]

    if annotation_result:
        lines += [
            "## Step 3b — Peak Annotation", "",
            "| Category | Count | Fraction |",
            "|---|---|---|",
        ]
        total = max(sum(annotation_result.category_counts.values()), 1)
        for cat, count in annotation_result.category_counts.items():
            lines.append(f"| {cat} | {count:,} | {count/total*100:.1f}% |")
        lines.append("")

    if qc_results:
        lines += [
            "## Step 3c — Post-peak QC", "",
            "### FRiP\n",
            "| Sample | FRiP | Tier |",
            "|---|---|---|",
        ]
        for q in qc_results:
            lines.append(f"| {q.sample_name} | {q.frip:.3f} | {q.frip_tier} |")

    lines += [
        "", "---", "",
        "> **Disclaimer**: OmicsClaw is a research tool. "
        "Results require expert interpretation.",
    ]

    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    # result.json
    result: dict[str, Any] = {
        "skill":           SKILL_NAME,
        "version":         SKILL_VERSION,
        "log":             str(output_dir / f"{SKILL_NAME}.log"),
        "steps_completed": step2_data.get("steps_completed", []) + [
            "peak_calling", "peak_annotation", "qc_after_peak_calling",
        ],
        "params":          params,
        "peak_calling": [
            {
                "sample":          r.sample_name,
                "n_peaks":         r.n_peaks,
                "peak_count_tier": r.peak_count_tier,
                "narrowpeak":      str(r.peaks_narrowpeak),
            }
            for r in peak_results
        ],
        "consensus": {
            "n_peaks":       consensus.n_peaks,
            "consensus_bed": str(consensus.consensus_bed),
            "consensus_saf": str(consensus.consensus_saf),
            "count_matrix":  str(counts_file) if counts_file else None,
        },
        "genome_files": {
            "genome":      genome_files_obj.genome if genome_files_obj else "",
            "fasta":       str(genome_files_obj.fasta) if genome_files_obj and genome_files_obj.fasta else None,
            "gtf":         str(genome_files_obj.gtf) if genome_files_obj and genome_files_obj.gtf else None,
            "blacklist":   str(genome_files_obj.blacklist) if genome_files_obj and genome_files_obj.blacklist else None,
            "chrom_sizes": str(genome_files_obj.chrom_sizes) if genome_files_obj and genome_files_obj.chrom_sizes else None,
        } if genome_files_obj else step2_data.get("genome_files"),
        "sample_sheet":  step2_data.get("sample_sheet"),
        "mapping":       step2_data.get("mapping", []),
        "prev_result":   str(prev_result_path),
    }
    (output_dir / "result.json").write_text(
        json.dumps(result, indent=2, default=str)
    )


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
        f"--wd {shlex.quote(str(output_dir))}"
    )
    for key, flag in [
        ("qvalue",           "--qvalue"),
        ("shift",            "--shift"),
        ("extsize",          "--extsize"),
        ("threads",          "--threads"),
        ("overlap_fraction", "--overlap-fraction"),
    ]:
        v = params.get(key)
        if v is not None:
            cmd += f" {flag} {shlex.quote(str(v))}"
    if params.get("idr"):
        cmd += " --idr"

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
            f"{SKILL_NAME} v{SKILL_VERSION} — Bulk ATAC-seq peak calling + QC.\n\n"
            "Step 3a: MACS2 peak calling, consensus peaks, count matrix.\n"
            "Step 3b: Peak annotation (distance to TSS, feature categories).\n"
            "Step 3c: FRiP, TSS heatmap, peak heatmap, PCA, correlation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    req = p.add_argument_group("required (at least one)")
    req.add_argument("--prev-result", "--input", required=False, dest="prev_result",
                     default=None,
                     help="result.json from bulkatac-mapping (Step 2); accepts "
                          "--input too for OmicsClaw runner compatibility. "
                          "If omitted, auto-detected as <wd>/mapping/result.json.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too for "
                          "OmicsClaw runner compatibility). Default: sibling "
                          "of prev-result's parent dir (e.g. .../peak_calling/).")

    peak = p.add_argument_group("peak calling")
    peak.add_argument("--qvalue", type=float, default=0.05,
                      help="MACS2 q-value threshold (default: 0.05).")
    peak.add_argument("--shift", type=int, default=-37,
                      help="MACS2 --shift (default: -37, half-nucleosome centering).")
    peak.add_argument("--extsize", type=int, default=73,
                      help="MACS2 --extsize (default: 73, half-nucleosome window).")
    peak.add_argument("--overlap-fraction", type=float, default=0.50,
                      dest="overlap_fraction",
                      help="Reciprocal overlap fraction for ENCODE naive overlap "
                           "(default: 0.50 = ENCODE standard). Pooled peaks must "
                           "overlap each replicate's peaks by at least this fraction.")

    opt = p.add_argument_group("optional")
    opt.add_argument("--gtf", default=None,
                     help="GTF file for peak annotation and TSS heatmap. "
                          "Auto-detected from Step 2 result.json if available.")
    opt.add_argument("--threads", type=int, default=16)
    opt.add_argument("--skip-annotation", action="store_true", dest="skip_annotation",
                     help="Skip peak annotation step.")
    opt.add_argument("--skip-qc", action="store_true", dest="skip_qc",
                     help="Skip post-peak QC (heatmaps, PCA, FRiP).")
    opt.add_argument("--idr", action="store_true", dest="idr",
                     help="Run ENCODE IDR reproducibility analysis. "
                          "Disabled by default (expensive: requires BAM merging, "
                          "pseudo-replicate splitting, and multiple MACS2 calls "
                          "per condition). Requires >= 2 replicates per condition.")

    return p


# ── Progress reporting ──────────────────────────────────────────────────
# Written to the controlling terminal (/dev/tty) when one exists, so step
# progress shows live even though the OmicsClaw runner buffers the piped
# stdout; falls back to stdout when there is no terminal. See _emit_progress.
_STEPS = [
    "Load Step-2 mapping result",
    "Per-sample peak calling (MACS2)  (Step 3a)",
    "Consensus peaks + featureCounts count matrix  (Step 3a)",
    "Peak annotation  (Step 3b)",
    "Post-peak QC — FRiP, heatmaps, PCA, IDR  (Step 3c)",
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

    # ── Resolve prev-result: explicit > inferred from --wd ────────────────
    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    elif args.wd:
        prev_result_path = Path(args.wd).parent / "mapping" / "result.json"
    else:
        parser.error("Either --prev-result or --wd must be provided.")

    if not prev_result_path.exists():
        parser.error(f"--prev-result not found: {prev_result_path}")

    project_dir = prev_result_path.resolve().parent.parent
    output_dir = Path(args.wd) if args.wd else project_dir / "peak_calling"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    _print_step_plan()

    # ── Load Step 2 ──────────────────────────────────────────────────────────
    _step(1, "loading Step-2 mapping result")
    step2 = load_step2_result(prev_result_path)
    step2_data        = step2["data"]
    mapping_results   = step2["mapping_results"]
    genome_files      = step2["genome_files"]
    genome            = step2["genome"]
    bigwig_paths      = step2["bigwig_paths"]
    sample_conditions = step2["sample_conditions"]
    is_paired         = step2["is_paired"]

    # CLI --gtf overrides auto-detected GTF
    if args.gtf:
        genome_files.gtf = Path(args.gtf)

    logger.info("Loaded Step 2: %d samples  genome=%s  gtf=%s",
                len(mapping_results), genome,
                genome_files.gtf if genome_files.gtf else "not found")

    genome_fasta = genome_files.fasta if genome_files else None
    genome_size = get_macs2_genome_size(genome, fasta=genome_fasta)

    params: dict[str, Any] = {
        "qvalue":            args.qvalue,
        "shift":             args.shift,
        "extsize":           args.extsize,
        "overlap_fraction":  args.overlap_fraction,
        "threads":           args.threads,
        "genome_size":       genome_size,
        "skip_annotation":   args.skip_annotation,
        "skip_qc":           args.skip_qc,
        "idr":               args.idr,
    }

    # ── q-value tag for directory naming ─────────────────────────────────────
    qval_tag = f"qvalue{args.qvalue}"

    # ── Step 3a: Peak calling ────────────────────────────────────────────────
    peaks_dir = output_dir / "peaks"

    _step(2, f"per-sample MACS2 peak calling ({len(mapping_results)} sample(s))")
    peak_results = run_all_peak_calling(
        mapping_results, peaks_dir,
        genome_size=genome_size, is_paired=is_paired,
        qvalue=args.qvalue, shift=args.shift, extsize=args.extsize,
    )

    # Consensus peaks (ENCODE naive overlap) + count matrix
    _step(3, "consensus peaks (ENCODE naive overlap) + featureCounts count matrix")
    consensus_dir = output_dir / "consensus" / qval_tag
    bam_dict     = {mr.sample_name: mr.bam for mr in mapping_results}
    consensus = build_consensus_peaks(
        peak_results, sample_conditions, bam_dict, consensus_dir,
        genome_size=genome_size, is_paired=is_paired,
        qvalue=args.qvalue, shift=args.shift, extsize=args.extsize,
        threads=args.threads, overlap_fraction=args.overlap_fraction,
    )

    # Count matrix
    bam_paths    = [mr.bam for mr in mapping_results]
    sample_names = [mr.sample_name for mr in mapping_results]

    counts_file = build_count_matrix(
        bam_paths, sample_names, consensus.consensus_saf,
        consensus_dir, is_paired=is_paired, threads=args.threads,
    )

    write_peak_calling_summary(peak_results, consensus, output_dir)

    # ── Step 3b: Peak annotation (per condition) ───────────────────────────
    #   Merge replicates within each condition, annotate, and produce
    #   per-condition pie charts + TSS distance histograms + comparison plots.
    #   HOMER needs only genome name (e.g. sacCer3); bedtools fallback needs GTF.
    _step(4, "peak annotation (per condition)")
    annotation_result = None
    condition_annotations: dict = {}
    homer_genome = genome_files.genome or None
    can_annotate = genome_files.gtf or (homer_genome and shutil.which("annotatePeaks.pl"))
    if not args.skip_annotation and can_annotate:
        annotation_dir = output_dir / "annotation" / qval_tag

        # Per-condition annotation (merge replicates → annotate → pie + TSS)
        condition_annotations = annotate_per_condition_peaks(
            peak_results, sample_conditions, genome_files.gtf,
            annotation_dir / "per_condition",
            genome=homer_genome,
        )

        if condition_annotations:
            # Cross-condition comparison plots (side-by-side panels)
            plot_annotation_comparison(condition_annotations, annotation_dir)
            plot_annotation_grouped_bar(condition_annotations, annotation_dir)
            plot_tss_distance_comparison(condition_annotations, annotation_dir)

            # Use first condition result as representative for report
            annotation_result = next(iter(condition_annotations.values()))
        else:
            # Fallback: single-condition or no condition info — annotate consensus
            logger.info("No multi-condition data; annotating consensus peaks.")
            annotation_result = annotate_peaks(
                consensus.consensus_bed, genome_files.gtf, annotation_dir,
                genome=homer_genome,
            )
            plot_annotation_pie(annotation_result, annotation_dir)
            plot_tss_distance_histogram(
                annotation_result.annotated_tsv, annotation_dir,
            )
    elif not args.skip_annotation:
        logger.warning(
            "Skipping peak annotation: no GTF found and HOMER not available. "
            "Provide --gtf or install HOMER (conda install -c bioconda homer)."
        )

    # ── Step 3c: Post-peak QC ────────────────────────────────────────────────
    _step(5, "post-peak QC — FRiP, heatmaps, PCA, IDR")
    qc_results = []
    if not args.skip_qc:
        qc_dir       = output_dir / "qc_after_peak_calling"
        frip_dir     = qc_dir / "frip" / qval_tag
        pca_dir      = qc_dir / "pca" / qval_tag
        corr_dir     = qc_dir / "sample_correlation" / qval_tag
        idr_dir      = qc_dir / "IDR" / qval_tag
        heatmap_dir  = output_dir / "heatmap" / qval_tag

        # FRiP
        for mr in mapping_results:
            qc = compute_frip(
                mr.sample_name, mr.bam, consensus.consensus_bed,
                n_usable=mr.n_usable, is_paired=is_paired,
            )
            qc_results.append(qc)

        plot_frip_bar(qc_results, frip_dir)
        write_qc_after_peak_calling_summary(qc_results, qc_dir)

        # Heatmaps (need BigWigs from Step 2) → output_dir/heatmap/
        bw_list  = [bigwig_paths[n] for n in sample_names if n in bigwig_paths]
        bw_names = [n for n in sample_names if n in bigwig_paths]

        if bw_list:
            # TSS heatmap — all samples
            if genome_files.gtf and genome_files.gtf.exists():
                plot_tss_heatmap(
                    bw_list, bw_names, genome_files.gtf, heatmap_dir,
                    threads=args.threads,
                )

            # Peak-centered heatmap — all samples
            plot_peak_heatmap(
                bw_list, bw_names, consensus.consensus_bed, heatmap_dir,
                threads=args.threads,
            )

        # PCA + correlation (need count matrix + >= 2 conditions)
        conditions_list = [sample_conditions.get(n, "") for n in sample_names]
        if len(set(conditions_list)) >= 2:
            plot_pca(counts_file, sample_names, conditions_list, pca_dir)
            plot_sample_correlation(counts_file, sample_names, corr_dir,
                                    conditions=conditions_list)

        # IDR (need >= 2 replicates per condition, opt-in via --idr)
        if args.idr:
            bam_dict  = {mr.sample_name: mr.bam for mr in mapping_results}
            peak_dict = {r.sample_name: r.peaks_narrowpeak for r in peak_results}
            idr_results = run_all_idr(
                sample_names, sample_conditions, bam_dict, peak_dict,
                genome_size, idr_dir,
                is_paired=is_paired, threads=args.threads,
            )
            if idr_results:
                plot_idr_summary(idr_results, idr_dir)
        else:
            logger.info("IDR skipped (use --idr to enable).")

    # ── Outputs ──────────────────────────────────────────────────────────────
    _step(6, "writing report, reproducibility, and result.json")
    write_report(output_dir, peak_results, consensus, qc_results,
                 annotation_result, params, step2_data,
                 counts_file=counts_file, genome_files_obj=genome_files,
                 prev_result_path=prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)

    # README
    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        "`peaks/` — per-sample narrowPeak and summit files.\n"
        "`consensus/` — consensus peak BED, SAF, and count matrix.\n"
        "`annotation/` — peak annotation (feature categories, TSS distance).\n"
        "`qc_after_peak_calling/frip/` — FRiP bar chart.\n"
        "`qc_after_peak_calling/peak_heatmap/` — TSS + peak-centered heatmaps.\n"
        "`qc_after_peak_calling/pca/` — PCA on peak accessibility.\n"
        "`qc_after_peak_calling/sample_correlation/` — Pairwise sample correlation.\n"
        "`qc_after_peak_calling/IDR/` — ENCODE IDR reproducibility analysis.\n"
        f"{SKILL_NAME}.log — full run log: narrative + every tool's stdout/stderr.\n"
        "\nNext: Step 4 (differential accessibility / motif analysis).\n"
    )

    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
        f"  {len(peak_results)} samples\n"
        f"  Consensus peaks: {consensus.n_peaks:,}\n"
        f"  Count matrix:    {counts_file}\n"
        f"  Peaks:           {peaks_dir}\n"
        f"  Annotation:      {output_dir / 'annotation'}\n"
        f"  QC figures:      {output_dir / 'qc_after_peak_calling'}\n"
        f"  Report:          {output_dir / 'report.md'}\n"
        f"\n  Next → bulkatac-DA (differential accessibility)\n"
        f"         → bulkatac-motif-enrichment (sequence motifs)  |  "
        f"bulkatac-footprinting (TF occupancy)\n"
    )


if __name__ == "__main__":
    main()
