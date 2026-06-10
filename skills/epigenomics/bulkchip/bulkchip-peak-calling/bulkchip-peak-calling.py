#!/usr/bin/env python3
"""
bulkchip-peak-calling.py — Bulk ChIP-seq peak calling (Step 3).

Implemented (MACS2-backed). See `_lib/peak_calling.py`.

Scope
-----
  Step 3 — Peak calling against input control
    Dedup ChIP + control BAMs from Step 2
    → MACS2 callpeak  -t <chip>  -c <control>
        narrow mode (TF / sharp histone)  →  narrowPeak
        broad  mode (broad histone)        →  --broad broadPeak
    → ENCODE naive-overlap consensus across conditions (vs pooled control)
    → featureCounts matrix (peaks × samples) for bulkchip-DA
    → FRiP per sample
    → optional IDR reproducibility (point-source, true replicates)

  Annotation + functional enrichment are a SEPARATE skill
  (bulkchip-annotation-enrichment); this skill stops at the consensus count
  matrix + FRiP.

Output layout
-------------
  <output>/
  ├── README.md, report.md, result.json, peak_calling_summary.csv
  ├── peaks/<sample>/                  (MACS2 narrowPeak / broadPeak vs control)
  ├── consensus/                       (consensus_peaks.bed/.saf, peak_counts.txt)
  ├── qc/                              (FRiP, optional IDR)
  └── reproducibility/

References
----------
  ENCODE ChIP-seq standards : https://www.encodeproject.org/chip-seq/transcription_factor/
  MACS2                     : https://github.com/macs3-project/MACS
  nf-core/chipseq           : https://github.com/nf-core/chipseq

Quick-start
-----------
  python bulkchip-peak-calling.py --wd <project>/peak_calling --peak-mode auto
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
import types
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_SKILL_DIR    = Path(__file__).resolve().parent
_BULKCHIP_DIR = _SKILL_DIR.parent
_PROJECT_ROOT = _BULKCHIP_DIR.parent.parent.parent

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SKILL_NAME    = "bulkchip-peak-calling"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkchip/bulkchip-peak-calling/bulkchip-peak-calling.py"

from skills.epigenomics.bulkchip._lib.subenv_bootstrap import ensure_bulkchip_env  # noqa: E402
from skills.epigenomics.bulkchip._lib.progress import tty_write  # noqa: E402
ensure_bulkchip_env()

from skills.epigenomics.bulkchip._lib.peak_calling import (             # noqa: E402
    PeakCallingResult, ConsensusPeakResult, IdrResult,
    get_macs2_genome_size, run_all_peak_calling, build_consensus_peaks,
    build_count_matrix, compute_frip, run_all_idr, write_peak_calling_summary,
)
from skills.epigenomics.bulkchip._lib.encode_qc_criteria import (       # noqa: E402
    infer_peak_mode, ENCODE_QC_THRESHOLDS,
)
from omicsclaw.common.runlog import attach_run_log                      # noqa: E402

_STEPS = [
    "Load Step-2 result + resolve ChIP/control pairs",
    "MACS2 callpeak per sample vs control (narrow / --broad)",
    "ENCODE naive-overlap consensus + featureCounts matrix",
    "FRiP per sample (+ optional IDR)",
    "Write report, reproducibility, and result.json",
]


def _emit_progress(text: str) -> None:
    if not tty_write(text):
        print(text, flush=True)


def _print_step_plan() -> None:
    n = len(_STEPS)
    lines = [f"\n[{SKILL_NAME}] pipeline — {n} step(s):"]
    lines += [f"  [{i}/{n}] {d}" for i, d in enumerate(_STEPS, 1)]
    lines.append("")
    _emit_progress("\n".join(lines))


def _step(n: int, msg: str) -> None:
    _emit_progress(f"[{SKILL_NAME}] ==> step {n}/{len(_STEPS)}: {msg}")
    logger.info("==> step %d/%d: %s", n, len(_STEPS), msg)


# ---------------------------------------------------------------------------
# Load Step-2 (mapping) result.json
# ---------------------------------------------------------------------------

def load_step2_result(result_json: Path) -> dict[str, Any]:
    """Reconstruct mapping samples + ChIP/control pairing + reference from Step 2."""
    data = json.loads(result_json.read_text())
    ss   = data.get("sample_sheet", {}) or {}
    genome = ss.get("genome", "") or ""

    # Per-sample mapping records (SimpleNamespace with the attrs _lib expects).
    mapping_results = []
    for m in data.get("mapping", []):
        mapping_results.append(types.SimpleNamespace(
            sample_name=m["sample"],
            bam=Path(m["bam"]),
            is_control=bool(m.get("is_control", False)),
            control=m.get("control"),
            n_usable=int(m.get("n_fragments", 0)),
        ))

    # ChIP→control pairing + per-sample condition / peak_mode / antibody.
    control_map = data.get("control_map", {}) or {}
    samples = ss.get("samples", [])
    sample_conditions = {s["name"]: s.get("condition", "") for s in samples}
    sheet_peak_mode   = {s["name"]: (s.get("peak_mode") or "") for s in samples}
    antibody          = {s["name"]: s.get("antibody") for s in samples}
    is_paired = ss.get("layout", "paired-end") == "paired-end"

    # Reference FASTA (for MACS2 effective genome size fallback).
    fasta = None
    gf = data.get("genome_files", {}) or {}
    if gf.get("fasta") and Path(gf["fasta"]).exists():
        fasta = Path(gf["fasta"])
    else:
        for ref in sorted(result_json.resolve().parent.parent.glob("reference_*")):
            for cand in [ref / f"{genome}.fa", *ref.glob("*.fa")]:
                if cand.exists():
                    fasta = cand
                    break
            if fasta:
                break

    return {
        "data": data, "genome": genome, "fasta": fasta,
        "mapping_results": mapping_results, "control_map": control_map,
        "sample_conditions": sample_conditions, "sheet_peak_mode": sheet_peak_mode,
        "antibody": antibody, "is_paired": is_paired,
    }


def _resolve_peak_modes(
    chip_names: list[str], cli_mode: str,
    sheet_peak_mode: dict[str, str], antibody: dict[str, str | None],
) -> dict[str, str]:
    """Per-ChIP-sample peak mode: forced globally, or auto (sheet value / antibody)."""
    modes: dict[str, str] = {}
    for name in chip_names:
        if cli_mode in ("narrow", "broad"):
            modes[name] = cli_mode
        else:  # auto
            modes[name] = sheet_peak_mode.get(name) or infer_peak_mode(antibody.get(name))
    return modes


# ---------------------------------------------------------------------------
# Report + result.json + reproducibility
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    peak_results: list[PeakCallingResult],
    consensus: ConsensusPeakResult,
    idr_results: list[IdrResult],
    params: dict[str, Any],
    step2_data: dict[str, Any],
    prev_result_path: Path,
) -> None:
    lines: list[str] = [
        "# ChIP-seq Peak Calling Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "", "---", "",
        "## Step 3 — MACS2 peak calling vs matched input", "",
        f"- **Aligner genome size (MACS2 -g)**: {params.get('genome_size')}",
        f"- **q-value**: {params.get('qvalue')}  |  **broad-cutoff**: {params.get('broad_cutoff')}",
        f"- **Consensus overlap fraction**: {params.get('overlap_fraction')}",
        "",
        "### Per-sample peaks + FRiP\n",
        "| ChIP sample | Control | Mode | Peaks | FRiP | Tier |",
        "|---|---|---|---|---|---|",
    ]
    for r in peak_results:
        frip = f"{r.frip:.3f}" if r.frip else "—"
        lines.append(
            f"| {r.sample_name} | {r.control_name or '—'} | {r.peak_mode} "
            f"| {r.n_peaks:,} | {frip} | {r.frip_tier or '—'} |"
        )
    lines += [
        "",
        f"**Consensus peaks (ENCODE naive overlap)**: {consensus.n_peaks:,} "
        f"→ `{consensus.consensus_bed.name}`",
        f"**Count matrix**: `{consensus.count_matrix.name if consensus.count_matrix else 'n/a'}` "
        "(peaks × ChIP samples) — input for `bulkchip-DA`.",
        "",
        "### ENCODE FRiP guidance\n",
        f"- preferred ≥ {ENCODE_QC_THRESHOLDS['frip']['preferred']}, "
        f"acceptable ≥ {ENCODE_QC_THRESHOLDS['frip']['acceptable']} "
        "(target-dependent — sharp TF marks run lower than broad histone marks).",
    ]
    if idr_results:
        lines += ["", "### IDR (true-replicate reproducibility)\n",
                  "| Condition | IDR peaks | Note |", "|---|---|---|"]
        for ir in idr_results:
            lines.append(f"| {ir.condition} | {ir.n_idr_peaks:,} | {ir.note} |")
    lines += [
        "",
        "## Next Steps", "",
        "- **Step 4**: `bulkchip-DA` — pyDESeq2 differential binding on the "
        "consensus count matrix (e.g. T15 vs T0).",
        "- **bulkchip-annotation-enrichment** / **bulkchip-motif-enrichment** — "
        "peak→gene annotation, GO/KEGG, and motif enrichment.",
        "", "---", "",
        "> **Disclaimer**: OmicsClaw is a research tool. Results require expert interpretation.",
    ]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    result: dict[str, Any] = {
        "skill":           SKILL_NAME,
        "version":         SKILL_VERSION,
        "log":             str(output_dir / f"{SKILL_NAME}.log"),
        "steps_completed": step2_data.get("steps_completed", []) + ["peak_calling"],
        "steps_pending":   [s for s in step2_data.get("steps_pending", [])
                            if s not in ("peak_calling",)],
        "params":          params,
        "peak_calling": [
            {
                "sample":      r.sample_name,
                "control":     r.control_name,
                "peak_mode":   r.peak_mode,
                "peaks_file":  str(r.peaks_file),
                "summits_bed": str(r.summits_bed) if r.summits_bed else None,
                "n_peaks":     r.n_peaks,
                "frip":        r.frip,
                "frip_tier":   r.frip_tier,
            }
            for r in peak_results
        ],
        "consensus": {
            "consensus_bed": str(consensus.consensus_bed),
            "consensus_saf": str(consensus.consensus_saf),
            "count_matrix":  str(consensus.count_matrix) if consensus.count_matrix else None,
            "n_peaks":       consensus.n_peaks,
            "per_sample_peaks": consensus.per_sample_peaks,
        },
        "idr": [
            {"condition": ir.condition, "n_idr_peaks": ir.n_idr_peaks,
             "idr_file": str(ir.idr_file) if ir.idr_file else None, "note": ir.note}
            for ir in idr_results
        ],
        "control_map":  step2_data.get("control_map", {}),
        # NB: step2_data is the *processed* dict from load_step2_result; the raw
        # Step-2 result.json (with sample_sheet + genome_files) is under ["data"].
        "sample_sheet": step2_data["data"].get("sample_sheet"),
        # Propagate the reference files (FASTA/GTF/genome) from Step 2 so the
        # downstream motif-enrichment / peak-annotation skills can resolve them
        # via the chain (e.g. HOMER -fasta mode without a genome install).
        "genome_files": step2_data["data"].get("genome_files"),
        "prev_result":  str(prev_result_path),
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


def write_reproducibility(output_dir: Path, params: dict[str, Any], prev_result_path: Path) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)
    cmd = (
        f"python {SCRIPT_REL} "
        f"--prev-result {shlex.quote(str(prev_result_path))} "
        f"--wd {shlex.quote(str(output_dir))} "
        f"--peak-mode {params.get('peak_mode', 'auto')} "
        f"--qvalue {params.get('qvalue')} --broad-cutoff {params.get('broad_cutoff')} "
        f"--overlap-fraction {params.get('overlap_fraction')} --threads {params.get('threads')}"
    )
    if params.get("idr"):
        cmd += " --idr"
    if params.get("skip_qc"):
        cmd += " --skip-qc"
    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["pandas", "numpy"])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"{SKILL_NAME} v{SKILL_VERSION} — Bulk ChIP-seq peak calling vs input control.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", dest="prev_result", default=None,
                     help="result.json from bulkchip-mapping (Step 2). "
                          "Auto-detected from --wd's sibling mapping/result.json if omitted.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too).")

    opt = p.add_argument_group("optional")
    opt.add_argument("--peak-mode", default="auto", choices=["auto", "narrow", "broad"],
                     dest="peak_mode",
                     help="narrow (TF/sharp) | broad (broad histone) | auto "
                          "(infer per-sample from antibody label).")
    opt.add_argument("--qvalue", type=float, default=0.05,
                     help="MACS2 q-value threshold (narrow; default 0.05).")
    opt.add_argument("--broad-cutoff", type=float, default=0.1, dest="broad_cutoff",
                     help="MACS2 --broad-cutoff (broad mode; default 0.1).")
    opt.add_argument("--overlap-fraction", type=float, default=0.5, dest="overlap_fraction",
                     help="Reciprocal-overlap fraction for naive-overlap consensus (default 0.5).")
    opt.add_argument("--idr", action="store_true",
                     help="Run IDR reproducibility (point-source; needs >= 2 replicates/condition).")
    opt.add_argument("--skip-qc", action="store_true", dest="skip_qc",
                     help="Skip FRiP / IDR QC (the count matrix is still produced).")
    opt.add_argument("--threads", type=int, default=16)
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    elif args.wd:
        prev_result_path = Path(args.wd).parent / "mapping" / "result.json"
    else:
        parser.error("Provide --prev-result or --wd so the Step-2 result.json can be located.")
    if not prev_result_path.exists():
        parser.error(f"Step-2 mapping result not found: {prev_result_path}")

    project_dir = prev_result_path.resolve().parent.parent
    output_dir  = Path(args.wd) if args.wd else project_dir / "peak_calling"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    _print_step_plan()

    # ── Step 1: load Step-2 result + resolve ChIP/control pairs ─────────────
    _step(1, "loading Step-2 mapping result + resolving ChIP/control pairs")
    s2 = load_step2_result(prev_result_path)
    mapping_results   = s2["mapping_results"]
    control_map       = s2["control_map"]
    sample_conditions = s2["sample_conditions"]
    is_paired         = s2["is_paired"]
    genome            = s2["genome"]
    genome_size       = get_macs2_genome_size(genome, fasta=s2["fasta"])

    chip = [m for m in mapping_results if not m.is_control]
    ctrl = [m for m in mapping_results if m.is_control]
    if not chip:
        parser.error("No ChIP samples found in Step-2 result (all flagged as control?).")
    chip_names   = [m.sample_name for m in chip]
    peak_modes   = _resolve_peak_modes(chip_names, args.peak_mode,
                                       s2["sheet_peak_mode"], s2["antibody"])
    logger.info("Loaded Step 2: %d ChIP + %d control  genome=%s (-g %s)",
                len(chip), len(ctrl), genome, genome_size)

    params: dict[str, Any] = {
        "peak_mode":        args.peak_mode,
        "qvalue":           args.qvalue,
        "broad_cutoff":     args.broad_cutoff,
        "overlap_fraction": args.overlap_fraction,
        "threads":          args.threads,
        "genome_size":      genome_size,
        "idr":              args.idr,
        "skip_qc":          args.skip_qc,
    }

    # ── Step 2: per-sample MACS2 vs control ─────────────────────────────────
    _step(2, f"MACS2 callpeak vs matched input on {len(chip)} ChIP sample(s)")
    peak_results = run_all_peak_calling(
        mapping_results, output_dir / "peaks",
        control_map=control_map, peak_modes=peak_modes,
        genome_size=genome_size, is_paired=is_paired,
        qvalue=args.qvalue, broad_cutoff=args.broad_cutoff,
    )

    # ── Step 3: consensus + count matrix ────────────────────────────────────
    _step(3, "ENCODE naive-overlap consensus (vs pooled control) + featureCounts matrix")
    chip_bam_paths    = {m.sample_name: m.bam for m in chip}
    control_bam_paths = {m.sample_name: m.bam for m in ctrl}
    consensus = build_consensus_peaks(
        peak_results, sample_conditions, chip_bam_paths, control_bam_paths, control_map,
        output_dir / "consensus",
        genome_size=genome_size, is_paired=is_paired,
        qvalue=args.qvalue, broad_cutoff=args.broad_cutoff,
        threads=args.threads, overlap_fraction=args.overlap_fraction,
    )
    consensus.count_matrix = build_count_matrix(
        [m.bam for m in chip], chip_names, consensus.consensus_saf,
        output_dir / "consensus", is_paired=is_paired, threads=args.threads,
    )

    # ── Step 4: FRiP per ChIP sample (+ optional IDR) ───────────────────────
    idr_results: list[IdrResult] = []
    if args.skip_qc:
        _step(4, "skipping FRiP / IDR QC (--skip-qc)")
    else:
        _step(4, "FRiP per ChIP sample (vs consensus)" + ("  + IDR" if args.idr else ""))
        n_usable = {m.sample_name: m.n_usable for m in chip}
        for r in peak_results:
            if consensus.n_peaks > 0:
                r.frip, r.frip_tier = compute_frip(
                    r.sample_name, chip_bam_paths[r.sample_name], consensus.consensus_bed,
                    n_usable=n_usable.get(r.sample_name, 0), is_paired=is_paired,
                )
        if args.idr:
            idr_results = run_all_idr(peak_results, sample_conditions, output_dir / "qc" / "idr")

    write_peak_calling_summary(peak_results, consensus, output_dir)

    # ── Step 5: outputs ─────────────────────────────────────────────────────
    _step(5, "writing report, reproducibility, and result.json")
    write_report(output_dir, peak_results, consensus, idr_results,
                 params, s2["data"], prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)

    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        "`peaks/<sample>/` — per-ChIP-sample MACS2 narrowPeak/broadPeak (vs input).\n"
        "`consensus/` — consensus_peaks.bed/.saf + peak_counts.txt (peaks × ChIP samples).\n"
        "`qc/idr/` — optional IDR reproducibility (with --idr).\n"
        "`peak_calling_summary.csv` — per-sample peaks + FRiP.\n"
        f"`{SKILL_NAME}.log` — full run log: narrative + every tool's stdout/stderr.\n"
        "\nNext: Step 4 (bulkchip-DA — differential binding on the count matrix).\n"
    )

    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
        f"  {len(chip)} ChIP + {len(ctrl)} control\n"
        f"  Consensus peaks: {consensus.n_peaks:,}\n"
        f"  Count matrix:    {consensus.count_matrix}\n"
        f"  Summary:         {output_dir / 'peak_calling_summary.csv'}\n"
        f"  Report:          {output_dir / 'report.md'}\n"
        f"\n  Next → bulkchip-DA (differential binding)\n"
        f"         → bulkchip-motif-enrichment (sequence motifs)\n"
        f"         → bulkchip-peak-annotation → bulkchip-enrichment (peaks → genes → GO/KEGG)\n"
    )


if __name__ == "__main__":
    main()
