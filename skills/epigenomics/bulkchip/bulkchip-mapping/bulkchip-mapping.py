#!/usr/bin/env python3
"""
bulkchip-mapping.py — Bulk ChIP-seq mapping + ChIP QC (Step 2).

Scope
-----
  Step 2a — Alignment & BAM processing (ChIP + control samples)
    Trimmed FASTQs from Step 1
    → BWA-MEM2 (default) / BWA-MEM / Bowtie2 alignment
    → ENCODE BAM filtering (-F 1804 -f 2 -q 30 PE | -F 1796 -q 30 SE)
    → chrM removal → duplicate removal (samtools markdup -r)
    → optional ENCODE blacklist removal
    → library complexity (NRF / PBC1 / PBC2)

  Step 2b — ChIP signal-to-noise QC
    → strand cross-correlation NSC / RSC + fragment-length estimate
      (phantompeakqualtools run_spp.R)
    → deepTools fingerprint (ChIP vs input enrichment, JS distance)
    → RPGC-normalised bigWig signal tracks

  ChIP BAMs are NOT shifted (no Tn5 offset). Control (input/IgG) BAMs are
  processed identically and carried forward (with their is_control flag and
  ChIP→control pairing) for Step 3 `MACS2 -c`.

Output layout
-------------
  <output>/
  ├── README.md, report.md, result.json, mapping_summary.csv
  ├── bam/                            (dedup BAMs per sample, incl. controls)
  ├── bigwig/                         (RPGC signal tracks)
  ├── reproducibility/
  └── qc_after_mapping/
      ├── qc_after_mapping_summary.csv
      ├── cross_correlation/          (NSC/RSC per ChIP sample)
      └── fingerprint/                (deepTools plotFingerprint vs input)

References
----------
  ENCODE ChIP-seq standards : https://www.encodeproject.org/chip-seq/transcription_factor/
  nf-core/chipseq           : https://github.com/nf-core/chipseq
  bwa-mem2                  : https://github.com/bwa-mem2/bwa-mem2
  phantompeakqualtools      : https://github.com/kundajelab/phantompeakqualtools
  deepTools                 : https://github.com/deeptools/deepTools

Quick-start
-----------
  python bulkchip-mapping.py --prev-result <project>/preprocessing/result.json --wd <project>/mapping
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_SKILL_DIR    = Path(__file__).resolve().parent
_BULKCHIP_DIR = _SKILL_DIR.parent
_PROJECT_ROOT = _BULKCHIP_DIR.parent.parent.parent

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SKILL_NAME    = "bulkchip-mapping"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkchip/bulkchip-mapping/bulkchip-mapping.py"

# Relocate into the omicsclaw_bulkchip sub-env before the tool-backed _lib imports.
from skills.epigenomics.bulkchip._lib.subenv_bootstrap import ensure_bulkchip_env  # noqa: E402
from skills.epigenomics.bulkchip._lib.progress import tty_write  # noqa: E402
ensure_bulkchip_env()

from skills.epigenomics.bulkchip._lib.preprocessing import (              # noqa: E402
    Sample, SampleSheet,
)
from skills.epigenomics.bulkchip._lib.mapping import (                    # noqa: E402
    GenomeFiles, validate_genome_files, MappingResult,
    run_all_mapping, write_mapping_summary, prepare_reference,
)
from skills.epigenomics.bulkchip._lib.QC_after_mapping import (           # noqa: E402
    QcAfterMappingResult, run_all_qc_after_mapping, write_qc_after_mapping_summary,
)
from skills.epigenomics.bulkchip._lib.encode_qc_criteria import (         # noqa: E402
    ENCODE_QC_THRESHOLDS, UsableReadRule, NARROW_MODE, BROAD_MODE,
)
from omicsclaw.common.runlog import attach_run_log                        # noqa: E402


# ---------------------------------------------------------------------------
# Load Step 1 result.json
# ---------------------------------------------------------------------------

def load_mapping_result(result_json: Path) -> tuple[SampleSheet, list[Any]]:
    """Reconstruct SampleSheet + preprocess stubs from Step 1 result.json."""
    import types

    data    = json.loads(result_json.read_text())
    ss_data = data["sample_sheet"]
    genome  = ss_data["genome"]

    samples = [
        Sample(
            name       = s["name"],
            condition  = s["condition"],
            replicate  = int(s["replicate"]),
            r1         = Path(s["r1"]),
            r2         = Path(s["r2"]) if s.get("r2") else None,
            genome     = s.get("genome", genome),
            is_control = bool(s.get("is_control", False)),
            control    = s.get("control"),
            antibody   = s.get("antibody"),
            peak_mode  = s.get("peak_mode") or "narrow",
        )
        for s in ss_data["samples"]
    ]

    sheet = SampleSheet(
        samples                  = samples,
        layout                   = ss_data["layout"],
        conditions               = ss_data["conditions"],
        replicates_per_condition = ss_data.get("replicates_per_condition", {}),
        genome                   = genome,
        is_replicated            = ss_data["is_replicated"],
        control_map              = ss_data.get("control_map", {}),
    )

    PR = types.SimpleNamespace
    preprocess_results = [
        PR(
            sample_name = e["sample"],
            tool        = e.get("tool", ""),
            is_control  = bool(e.get("is_control", False)),
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
        "# ChIP-seq Mapping Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "", "---", "",
        "## Step 2a — Alignment and BAM Filtering", "",
        f"- **Samples**: {len(sheet)} "
        f"({len(sheet.chip_samples)} ChIP + {len(sheet.control_samples)} control)",
        f"- **Layout**: {sheet.layout}",
        f"- **Genome**: {sheet.genome}",
        f"- **Aligner**: {params.get('aligner', 'bwa-mem2')}",
        "",
        "### Mapping Statistics\n",
        "| Sample | Type | Align% | Frags | %mito | NRF | PBC1 | PBC2 | DS |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in mapping_results:
        ds   = f"→{r.downsample_target:,}" if r.downsampled else "—"
        kind = "input" if r.is_control else "ChIP"
        lines.append(
            f"| {r.sample_name} | {kind} | {r.align_rate*100:.1f}% | {r.n_fragments:,} "
            f"| {r.pct_mito:.1f}% | {r.nrf:.3f} | {r.pbc1:.3f} | {r.pbc2:.2f} | {ds} |"
        )

    # Step 2b: ChIP signal-to-noise QC
    qc_by_name = {q.sample_name: q for q in qc_results}
    if any(q.nsc > 0 or q.fingerprint_js > 0 for q in qc_results):
        lines += [
            "", "## Step 2b — ChIP Signal-to-Noise QC", "",
            "### Strand Cross-Correlation & Fingerprint\n",
            "| Sample | NSC | NSC tier | RSC | RSC tier | Frag len | JSD vs input |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in mapping_results:
            if r.is_control:
                continue
            q = qc_by_name.get(r.sample_name)
            if q:
                lines.append(
                    f"| {q.sample_name} | {q.nsc:.3f} | {q.nsc_tier or '—'} "
                    f"| {q.rsc:.3f} | {q.rsc_tier or '—'} | {q.est_frag_len} bp "
                    f"| {q.fingerprint_js:.3f} |"
                )

    lines += [
        "",
        "### ENCODE QC Thresholds\n",
        "| Metric | Preferred | Acceptable |",
        "|---|---|---|",
        "| NRF            | > 0.90  | > 0.80 |",
        "| PBC1           | > 0.90  | > 0.50 |",
        "| PBC2           | > 10    | > 3 |",
        "| NSC            | > 1.10  | > 1.05 |",
        "| RSC            | > 1.00  | > 0.80 |",
        "| Alignment rate | > 95%   | > 80% |",
        "| Usable (TF/narrow)  | ≥ 20 M | ≥ 10 M |",
        "| Usable (broad)      | ≥ 45 M | ≥ 20 M |",
        "",
        "**Usable read rule:**",
    ]
    for line in rule.description().splitlines():
        lines.append(f"  {line}")

    if sheet.control_map:
        lines += ["", "### ChIP → input pairing (for Step 3 `MACS2 -c`)", ""]
        for chip, ctrl in sheet.control_map.items():
            lines.append(f"- `{chip}` → `{ctrl}`")

    if any(r.downsampled for r in mapping_results):
        t = next(r.downsample_target for r in mapping_results if r.downsampled)
        lines += ["", f"**Downsampling applied** to {t:,} fragments (min usable depth)."]

    lines += [
        "",
        "## Next Steps", "",
        "- **Step 3**: `bulkchip-peak-calling` — MACS2 vs matched input "
        "(narrow / broad), naive-overlap consensus, featureCounts matrix, FRiP.",
        "", "---", "",
        "> **Disclaimer**: OmicsClaw is a research tool. Results require expert interpretation.",
    ]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    # ── result.json ──────────────────────────────────────────────────────────
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
                "is_control":        r.is_control,
                "control":           r.control,
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
                "is_control":     q.is_control,
                "nsc":            q.nsc,
                "nsc_tier":       q.nsc_tier,
                "rsc":            q.rsc,
                "rsc_tier":       q.rsc_tier,
                "est_frag_len":   q.est_frag_len,
                "fingerprint_js": q.fingerprint_js,
                "bigwig":         str(q.bigwig) if q.bigwig else None,
                "bigwig_log2_input": str(q.bigwig_log2_input) if q.bigwig_log2_input else None,
            }
            for q in qc_results
        ],
        "control_map":          sheet.control_map,
        "encode_qc_thresholds": ENCODE_QC_THRESHOLDS,
        "usable_read_rule": {
            "layout":          sheet.layout,
            "excl_flags":      rule.samtools_excl_flags,
            "req_flags":       rule.samtools_req_flags,
            "mapq_threshold":  rule.mapq_threshold,
        },
        "genome_files": {
            "genome":      genome_files.genome if genome_files else "",
            "fasta":       str(genome_files.fasta) if genome_files and genome_files.fasta else None,
            "gtf":         str(genome_files.gtf) if genome_files and genome_files.gtf else None,
            "blacklist":   str(genome_files.blacklist) if genome_files and genome_files.blacklist else None,
            "chrom_sizes": str(genome_files.chrom_sizes) if genome_files and genome_files.chrom_sizes else None,
        },
        "sample_sheet":       step1_data.get("sample_sheet"),
        "prev_result":        str(prev_result_path),
        "prev_params":        step1_data.get("params"),
        "prev_preprocessing": step1_data.get("preprocessing"),
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

def write_reproducibility(output_dir: Path, params: dict[str, Any], prev_result_path: Path) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)

    cmd = (
        f"python {SCRIPT_REL} "
        f"--prev-result {shlex.quote(str(prev_result_path))} "
        f"--ref-dir {shlex.quote(str(params.get('ref_dir', '')))} "
        f"--wd {shlex.quote(str(output_dir))}"
    )
    for key, flag in [
        ("aligner",        "--aligner"),
        ("threads",        "--threads"),
        ("bwa_mem2_index", "--bwa-mem2-index"),
        ("bwa_index",      "--bwa-index"),
        ("bowtie2_index",  "--bowtie2-index"),
        ("blacklist",      "--blacklist"),
    ]:
        v = params.get(key)
        if v is not None:
            cmd += f" {flag} {shlex.quote(str(v))}"
    if params.get("downsample", False):
        cmd += " --downsample"
    if params.get("skip_qc", False):
        cmd += " --skip-qc"

    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["pandas", "numpy", "matplotlib"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            f"{SKILL_NAME} v{SKILL_VERSION} — Bulk ChIP-seq alignment + ChIP QC.\n\n"
            "Step 2a: BWA-MEM2/BWA/Bowtie2 alignment, ENCODE BAM filtering,\n"
            "         chrM removal, dedup, NRF/PBC1/PBC2 (ChIP + controls).\n"
            "Step 2b: cross-correlation (NSC/RSC), fingerprint, RPGC bigWig.\n\n"
            "By default downloads the genome FASTA and builds the aligner index\n"
            "in --ref-dir.  Skip with --bwa-mem2-index / --bwa-index / --bowtie2-index."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", dest="prev_result", default=None,
                     help="result.json from bulkchip-preprocessing (Step 1). "
                          "Auto-detected from --wd's sibling preprocessing/result.json if omitted.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too).")
    req.add_argument("--genome", default=None,
                     help="Reference build (overrides Step 1's genome).")
    req.add_argument("--ref-dir", dest="ref_dir", default=None,
                     help="Directory for reference files (auto-built if absent).")

    ref = p.add_argument_group("reference")
    ref.add_argument("--aligner", default="bwa-mem2", choices=["bwa-mem2", "bwa", "bowtie2"],
                     help="Aligner (default: bwa-mem2, the ENCODE ChIP-seq / nf-core workhorse).")
    idx = ref.add_mutually_exclusive_group()
    idx.add_argument("--bwa-mem2-index", dest="bwa_mem2_index", default=None,
                     help="Existing BWA-MEM2 index prefix (skips download; --aligner bwa-mem2).")
    idx.add_argument("--bwa-index", dest="bwa_index", default=None,
                     help="Existing BWA index prefix (skips download; --aligner bwa).")
    idx.add_argument("--bowtie2-index", dest="bowtie2_index", default=None,
                     help="Existing Bowtie2 index prefix (skips download; --aligner bowtie2).")
    ref.add_argument("--fasta-url", default=None, dest="fasta_url",
                     help="Override FASTA download URL (auto-selected if omitted).")
    ref.add_argument("--blacklist-url", default=None, dest="blacklist_url",
                     help="Override blacklist BED download URL.")
    ref.add_argument("--blacklist", default=None, help="Existing ENCODE blacklist BED.")
    ref.add_argument("--no-blacklist", action="store_true", dest="no_blacklist",
                     help="Skip blacklist download/filtering.")

    opt = p.add_argument_group("optional")
    opt.add_argument("--threads", type=int, default=16)
    opt.add_argument("--downsample", action="store_true",
                     help="Downsample all samples to min(usable) for QC comparability.")
    opt.add_argument("--skip-qc", action="store_true", dest="skip_qc",
                     help="Skip Step 2b ChIP QC (cross-correlation + fingerprint).")
    opt.add_argument("--keep-intermediates", action="store_true", dest="keep_intermediates")
    return p


_STEPS = [
    "Load Step-1 result + resolve genome",
    "Resolve reference genome (FASTA + aligner index)",
    "Alignment + ENCODE BAM filtering + dedup + NRF/PBC  (Step 2a)",
    "ChIP QC — NSC/RSC cross-correlation + deepTools fingerprint + bigWig  (Step 2b)",
    "Write report, reproducibility, and result.json",
]


def _emit_progress(text: str) -> None:
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
        prev_result_path = Path(args.wd).parent / "preprocessing" / "result.json"
    else:
        parser.error("Provide --prev-result or --wd so the Step-1 result.json can be located.")
    if not prev_result_path.exists():
        parser.error(f"Preprocessing result not found: {prev_result_path}\n"
                     f"  Use --prev-result to specify it explicitly.")

    _print_step_plan()

    # ── Step 1: load preprocessing result ──────────────────────────────────
    _step(1, "loading Step-1 preprocessing result")
    step1_data                = json.loads(prev_result_path.read_text())
    sheet, preprocess_results = load_mapping_result(prev_result_path)
    genome = args.genome or sheet.genome
    if not genome:
        parser.error("--genome is required because preprocessing result.json has no genome.")
    sheet.genome = genome

    project_dir = prev_result_path.resolve().parent.parent
    output_dir  = Path(args.wd) if args.wd else project_dir / "mapping"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)
    ref_dir = Path(args.ref_dir) if args.ref_dir else project_dir / f"reference_{genome}"

    logger.info("Loaded Step 1: %d samples (%d ChIP + %d control)  [%s]  genome=%s",
                len(sheet), len(sheet.chip_samples), len(sheet.control_samples),
                sheet.layout, genome)

    # ── Step 2: resolve reference index ────────────────────────────────────
    bwa_mem2_index = args.bwa_mem2_index
    bwa_index      = args.bwa_index
    bowtie2_index  = args.bowtie2_index
    blacklist      = Path(args.blacklist) if args.blacklist else None
    supplied_index = bwa_mem2_index or bwa_index or bowtie2_index

    # If the user supplied a specific index, infer the matching aligner.
    if supplied_index:
        if bwa_mem2_index:  args.aligner = "bwa-mem2"
        elif bwa_index:     args.aligner = "bwa"
        elif bowtie2_index: args.aligner = "bowtie2"

    _step(2, "resolving reference genome — "
             + ("using supplied aligner index" if supplied_index
                else "downloading FASTA + building aligner index (slow)"))
    if supplied_index:
        genome_files = GenomeFiles(
            genome         = genome,
            bwa_mem2_index = Path(bwa_mem2_index) if bwa_mem2_index else None,
            bwa_index      = Path(bwa_index)      if bwa_index      else None,
            bowtie2_index  = Path(bowtie2_index)  if bowtie2_index  else None,
            blacklist      = blacklist,
        )
    else:
        logger.info("Preparing reference for genome '%s' in %s ...", genome, ref_dir)
        genome_files = prepare_reference(
            genome, ref_dir,
            aligner                = args.aligner,
            threads                = args.threads,
            fasta_url              = args.fasta_url,
            blacklist_url          = args.blacklist_url,
            download_blacklist_bed = not args.no_blacklist,
        )
        if args.aligner == "bwa-mem2":
            bwa_mem2_index = str(genome_files.bwa_mem2_index)
        elif args.aligner == "bwa":
            bwa_index = str(genome_files.bwa_index)
        else:
            bowtie2_index = str(genome_files.bowtie2_index)
        if genome_files.blacklist and blacklist is None:
            blacklist = genome_files.blacklist

    validate_genome_files(genome_files, require_index=True)

    # Peak mode drives the ENCODE depth floor when --downsample is used.
    chip_modes = {s.peak_mode for s in sheet.chip_samples}
    peak_mode  = BROAD_MODE if BROAD_MODE in chip_modes else NARROW_MODE

    params: dict[str, Any] = {
        "aligner":            args.aligner,
        "threads":            args.threads,
        "bwa_mem2_index":     bwa_mem2_index,
        "bwa_index":          bwa_index,
        "bowtie2_index":      bowtie2_index,
        "blacklist":          str(blacklist) if blacklist else None,
        "downsample":         args.downsample,
        "peak_mode":          peak_mode,
        "skip_qc":            args.skip_qc,
        "keep_intermediates": args.keep_intermediates,
        "ref_dir":            str(ref_dir),
    }

    # ── Step 3 (2a): mapping ───────────────────────────────────────────────
    bam_dir = output_dir / "bam"
    pp_by_name = {pr.sample_name: pr for pr in preprocess_results}
    mapping_inputs = [
        (s.name, pp_by_name[s.name].r1_trimmed, pp_by_name[s.name].r2_trimmed)
        for s in sheet.samples
    ]
    sample_meta = {
        s.name: {"is_control": s.is_control, "control": s.control}
        for s in sheet.samples
    }

    _step(3, f"alignment + ENCODE filtering + dedup + NRF/PBC on {len(sheet)} sample(s) "
             f"[{args.aligner}]")
    mapping_results = run_all_mapping(
        mapping_inputs, genome_files, bam_dir,
        aligner            = args.aligner,
        threads            = args.threads,
        sample_meta        = sample_meta,
        downsample         = args.downsample,
        peak_mode          = peak_mode,
        keep_intermediates = args.keep_intermediates,
    )
    write_mapping_summary(mapping_results, output_dir)

    # ── Step 4 (2b): ChIP QC ───────────────────────────────────────────────
    qc_results: list[QcAfterMappingResult] = []
    if args.skip_qc:
        _step(4, "skipping Step 2b ChIP QC (--skip-qc)")
    else:
        _step(4, "ChIP QC — NSC/RSC cross-correlation + deepTools fingerprint + bigWig")
        qc_results = run_all_qc_after_mapping(
            mapping_results, genome_files, output_dir, threads=args.threads,
        )
        write_qc_after_mapping_summary(qc_results, output_dir / "qc_after_mapping")

    # ── Step 5: outputs ────────────────────────────────────────────────────
    _step(5, "writing report, reproducibility, and result.json")
    write_report(output_dir, sheet, mapping_results, qc_results, params, step1_data,
                 genome_files=genome_files, prev_result_path=prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)

    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        "`bam/` — deduplicated BAMs per sample (ChIP + controls, full-depth).\n"
        "`bigwig/` — per-sample RPGC tracks + log2(ChIP/input) bamCompare tracks.\n"
        "`qc_after_mapping/` — NSC/RSC cross-correlation + deepTools fingerprint.\n"
        "`mapping_summary.csv` — per-sample alignment + library-complexity metrics.\n"
        f"`{SKILL_NAME}.log` — full run log: narrative + every tool's stdout/stderr.\n"
        "\nNext: Step 3 (peak calling with MACS2 vs matched input).\n"
    )

    ds_n  = sum(1 for r in mapping_results if r.downsampled)
    nsc_n = sum(1 for q in qc_results if q.nsc > 0)
    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
        f"  {len(mapping_results)} samples  [{sheet.layout}]  "
        f"({len(sheet.chip_samples)} ChIP + {len(sheet.control_samples)} control)\n"
        f"  Aligner:        {args.aligner}\n"
        f"  Downsampled:    {ds_n}/{len(mapping_results)} samples\n"
        f"  NSC/RSC:        {nsc_n}/{len(sheet.chip_samples)} ChIP samples\n"
        f"  BAMs:           {bam_dir}\n"
        f"  BigWigs:        {output_dir / 'bigwig'}\n"
        f"  QC:             {output_dir / 'qc_after_mapping'}\n"
        f"  Summary:        {output_dir / 'mapping_summary.csv'}\n"
        f"  Report:         {output_dir / 'report.md'}\n"
        f"\n  Next → bulkchip-peak-calling → bulkchip-DA\n"
        f"         → bulkchip-motif-enrichment (sequence motifs)\n"
        f"         → bulkchip-peak-annotation → bulkchip-enrichment (peaks → genes → GO/KEGG)\n"
    )


if __name__ == "__main__":
    main()
