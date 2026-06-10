#!/usr/bin/env python3
"""
bulkatac-motif-enrichment.py — TF motif enrichment analysis (Step 5a).

Runs HOMER findMotifsGenome.pl on ATAC-seq peaks to discover enriched
TF motifs via both de novo motif discovery and known motif enrichment.

Background strategy
-------------------
  • all_peaks (consensus):  default genomic background (GC-matched random
    regions).  Question: "Which motifs are enriched in open chromatin?"

  • da_up / da_down:  -bg consensus_peaks.bed -chopify
    Question: "Which motifs are *specifically* enriched in peaks that
    gained/lost accessibility vs all open chromatin?"
    Without -bg, DA subsets would just rediscover generic open-chromatin
    motifs (AP-1, CTCF) instead of condition-specific TFs.

Usage
-----
  # On consensus peaks only (genomic background)
  python bulkatac-motif-enrichment.py \\
      --prev-result output/peak_calling/result.json \\
      --wd output \\
      --genome hg38

  # With DA peaks (consensus peaks as background for DA subsets)
  python bulkatac-motif-enrichment.py \\
      --prev-result output/DA/result.json \\
      --wd output \\
      --genome hg38

  # Use genome FASTA instead of HOMER genome install
  python bulkatac-motif-enrichment.py \\
      --prev-result output/peak_calling/result.json \\
      --wd output \\
      --genome hg38 --genome-fasta /path/to/hg38.fa

Output layout
-------------
  <output>/
  ├── report.md, result.json, reproducibility/
  ├── all_peaks/           — HOMER output on full consensus peaks
  │   ├── knownResults.txt, knownResults.html
  │   ├── homerResults.html, homerMotifs.all.motifs
  │   ├── knownResults/    — known motif logos
  │   └── homerResults/    — de novo motif logos
  ├── da_up/               — HOMER output on DA-up peaks (if Step 4)
  ├── da_down/             — HOMER output on DA-down peaks (if Step 4)
  ├── plots/
  │   ├── top_known_motifs_{set}.{pdf,png}
  │   └── top_denovo_motifs_{set}.{pdf,png}
  └── top_motif_summary.tsv

References
----------
  HOMER    : Heinz et al. 2010, Mol Cell 38(4):576-589
             http://homer.ucsd.edu/homer/ngs/peakMotifs.html
  homer2   : http://homer.ucsd.edu/homer/homer2.html
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

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_SKILL_DIR    = Path(__file__).resolve().parent
_BULKATAC_DIR = _SKILL_DIR.parent                            # .../bulkatac/
_PROJECT_ROOT = _BULKATAC_DIR.parent.parent.parent           # OmicsClaw/

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SKILL_NAME    = "bulkatac-motif-enrichment"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkatac/bulkatac-motif-enrichment/bulkatac-motif-enrichment.py"

# ---------------------------------------------------------------------------
# _lib imports
# ---------------------------------------------------------------------------
# Relocate into the omicsclaw_bulkatac sub-env before the tool-backed _lib imports.
from skills.epigenomics.bulkatac._lib.subenv_bootstrap import ensure_bulkatac_env  # noqa: E402
from skills.epigenomics.bulkatac._lib.progress import tty_write  # noqa: E402
ensure_bulkatac_env()

from skills.epigenomics.bulkatac._lib.motif_enrichment import (          # noqa: E402
    MotifEnrichmentResult,
    check_homer,
    run_motif_enrichment_multi,
    write_motif_summary,
    plot_top_known_motifs,
    plot_top_denovo_motifs,
)
from omicsclaw.common.runlog import attach_run_log                       # noqa: E402


# ---------------------------------------------------------------------------
# Load upstream results
# ---------------------------------------------------------------------------

def _find_genome_fasta(
    gf: dict, data: dict, genome: str, result_json: Path,
) -> Path | None:
    """Search for genome FASTA with multiple fallback strategies.

    Priority:
      1. genome_files.fasta in result.json
      2. ref_dir/{genome}.fa (from Step 2 params)
      3. reference_{genome}/{genome}.fa next to Step 2 result
      4. reference_{genome}/{genome}.fa next to Step 3 result
      5. ../mapping/reference_{genome}/{genome}.fa (sibling dir)
    """
    # 1. Explicit path in genome_files
    if gf.get("fasta") and Path(gf["fasta"]).exists():
        return Path(gf["fasta"])

    if not genome:
        return None

    fa_names = [f"{genome}.fa", f"fasta/{genome}.fa"]

    # 2. ref_dir from params
    params = data.get("params") or {}
    ref_dir = params.get("ref_dir")
    if ref_dir:
        for name in fa_names:
            candidate = Path(ref_dir) / name
            if candidate.exists():
                return candidate

    # 3. reference_* dirs next to Step 2 result
    step2_result = data.get("prev_result") or data.get("step2_result") or ""
    if step2_result:
        step2_parent = Path(step2_result).parent
        for ref_dir_candidate in sorted(step2_parent.glob(f"reference_{genome}*")):
            if ref_dir_candidate.is_dir():
                for name in fa_names:
                    candidate = ref_dir_candidate / name
                    if candidate.exists():
                        return candidate

    # 4. reference_* dirs next to this result.json (Step 3)
    step3_parent = result_json.parent
    for ref_dir_candidate in sorted(step3_parent.glob(f"reference_{genome}*")):
        if ref_dir_candidate.is_dir():
            for name in fa_names:
                candidate = ref_dir_candidate / name
                if candidate.exists():
                    return candidate

    # 5. Sibling directories: ../mapping/reference_{genome}/
    #    Common layout: output/{project}/mapping/ and output/{project}/peak_calling/
    project_dir = step3_parent.parent
    if project_dir.exists():
        for subdir in ("mapping", "step2", "alignment"):
            mapping_dir = project_dir / subdir
            if not mapping_dir.is_dir():
                continue
            for ref_dir_candidate in sorted(mapping_dir.glob(f"reference_{genome}*")):
                if ref_dir_candidate.is_dir():
                    for name in fa_names:
                        candidate = ref_dir_candidate / name
                        if candidate.exists():
                            return candidate

    return None


def load_step3_result(result_json: Path) -> dict[str, Any]:
    """Load Step 3 result.json → consensus peaks, genome info, sample sheet."""
    data = json.loads(result_json.read_text())

    consensus = data.get("consensus", {})
    consensus_bed = consensus.get("consensus_bed")
    if consensus_bed:
        consensus_bed = Path(consensus_bed)

    # Genome info
    ss = data.get("sample_sheet", {})
    genome = ss.get("genome", "")

    gf = data.get("genome_files") or {}
    blacklist = Path(gf["blacklist"]) if gf.get("blacklist") and Path(gf["blacklist"]).exists() else None

    # Genome FASTA — auto-detect with multiple fallback strategies.
    # Needed by HOMER (-fasta) and TOBIAS (Step 5b).
    genome_fasta = _find_genome_fasta(gf, data, genome, result_json)

    return {
        "data":          data,
        "consensus_bed": consensus_bed,
        "genome":        genome,
        "genome_fasta":  genome_fasta,
        "genome_files":  gf,
        "blacklist":     blacklist,
        "sample_sheet":  ss,
    }


def load_step4_result(result_json: Path) -> dict[str, Any]:
    """Load Step 4 result.json → DA peak BED files for up/down subsets."""
    data = json.loads(result_json.read_text())

    da = data.get("da", {})
    up_bed   = Path(da["up_bed"])   if da.get("up_bed")   and Path(da["up_bed"]).exists()   else None
    down_bed = Path(da["down_bed"]) if da.get("down_bed") and Path(da["down_bed"]).exists() else None
    contrast = da.get("contrast", "")

    return {
        "data":     data,
        "up_bed":   up_bed,
        "down_bed": down_bed,
        "contrast": contrast,
    }


# ---------------------------------------------------------------------------
# Report + result.json
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    enrichment_results: list[MotifEnrichmentResult],
    params: dict[str, Any],
    *,
    step3_result_path: Path | None = None,
    da_result_path: Path | None = None,
) -> None:
    lines: list[str] = [
        "# Motif Enrichment Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        f"**Tool**: HOMER findMotifsGenome.pl",
        "", "---", "",
        "## Parameters\n",
        f"- Genome: `{params.get('genome', 'N/A')}`",
        f"- Region size: {params.get('size', 200)}",
        f"- Repeat masking: {'yes' if params.get('mask', True) else 'no'}",
        f"- De novo motif lengths: {params.get('denovo_length', '8,10,12')}",
        f"- Autonormalization: HOMER default (auto)",
        "",
    ]

    for res in enrichment_results:
        bg_note = ""
        if res.peak_set in ("da_up", "da_down"):
            bg_note = " (background: consensus peaks, `-bg -chopify`)"
        else:
            bg_note = " (background: GC-matched genomic regions)"

        lines += [
            f"## Peak set: `{res.peak_set}`{bg_note}", "",
            f"- Peaks analysed: {res.n_peaks:,}",
            f"- HOMER succeeded: {'yes' if res.homer_succeeded else 'no'}",
        ]

        if res.known_results:
            lines += [
                f"- Known motifs tested: {len(res.known_results)}",
                "", "### Top 10 known motifs\n",
                "| Rank | Motif | Consensus | log10(p) | % Target | % Background | Enrichment |",
                "|---|---|---|---|---|---|---|",
            ]
            for i, h in enumerate(res.known_results[:10]):
                short_name = h.motif_name.split("/")[0] if "/" in h.motif_name else h.motif_name
                enrichment = h.pct_target / max(h.pct_background, 0.01)
                lines.append(
                    f"| {i+1} | {short_name} | {h.consensus} | "
                    f"{h.log_p_value:.0f} | {h.pct_target:.1f}% | "
                    f"{h.pct_background:.1f}% | {enrichment:.1f}x |"
                )
            lines.append("")

        if res.denovo_results:
            lines += [
                f"- De novo motifs discovered: {len(res.denovo_results)}",
                "", "### Top 5 de novo motifs\n",
                "| Rank | Consensus | log10(p) | Best known match |",
                "|---|---|---|---|",
            ]
            for i, h in enumerate(res.denovo_results[:5]):
                match = h.best_match.split("/")[0] if h.best_match else "—"
                lines.append(
                    f"| {i+1} | `{h.consensus}` | {h.log_p_value:.0f} | {match} |"
                )
            lines.append("")

    lines += [
        "", "---", "",
        "## Background strategy", "",
        "| Peak set | Foreground | Background | Biological question |",
        "|---|---|---|---|",
        "| all_peaks | Consensus peaks | Genomic (GC-matched) | "
        "What motifs are enriched in open chromatin vs genome? |",
        "| da_up | DA-up peaks | Consensus peaks (`-bg -chopify`) | "
        "What motifs drive *gained* accessibility? |",
        "| da_down | DA-down peaks | Consensus peaks (`-bg -chopify`) | "
        "What motifs drive *lost* accessibility? |",
        "",
        "> HOMER uses hypergeometric scoring (ZOOPS) with GC-content",
        "> normalization and lower-order oligo autonormalization (-nlen).",
        "> Custom backgrounds (-bg) undergo the same normalization.",
        "",
        "---", "",
        "> **Disclaimer**: OmicsClaw is a research and educational tool. "
        "Results require expert interpretation.",
    ]

    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    # result.json
    result: dict[str, Any] = {
        "skill":   SKILL_NAME,
        "version": SKILL_VERSION,
        "log":     str(output_dir / f"{SKILL_NAME}.log"),
        "params":  params,
        "motif_enrichment": [
            {
                "peak_set":           res.peak_set,
                "n_peaks":            res.n_peaks,
                "homer_succeeded":    res.homer_succeeded,
                "n_known_motifs":     len(res.known_results),
                "n_denovo_motifs":    len(res.denovo_results),
                "top_known":          [h.motif_name for h in res.known_results[:5]],
                "top_denovo":         [h.consensus for h in res.denovo_results[:5]],
                "known_results_txt":  str(res.known_txt) if res.known_txt else None,
                "known_results_html": str(res.known_html) if res.known_html else None,
                "denovo_results_html": str(res.denovo_html) if res.denovo_html else None,
                "output_dir":         str(res.output_dir),
            }
            for res in enrichment_results
        ],
        "summary_tsv":  str(output_dir / "top_motif_summary.tsv"),
        "prev_result":  str(step3_result_path) if step3_result_path else None,
        "da_result":    str(da_result_path) if da_result_path else None,
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


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
        ("genome",        "--genome"),
        ("genome_fasta",  "--genome-fasta"),
        ("size",          "--size"),
        ("denovo_length", "--denovo-length"),
        ("n_motifs",      "--n-motifs"),
        ("threads",       "--threads"),
    ]:
        v = params.get(key)
        if v is not None:
            cmd += f" {flag} {shlex.quote(str(v))}"

    if params.get("mask"):
        cmd += " --mask"
    if params.get("no_mask"):
        cmd += " --no-mask"

    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    # Pinned package versions → reproducibility/requirements.txt, via the
    # shared OmicsClaw helper so bulk-ATAC uses the same filename and format
    # as every other domain's skills.
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["matplotlib", "numpy", "pandas"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            f"{SKILL_NAME} v{SKILL_VERSION}\n\n"
            "TF motif enrichment analysis using HOMER findMotifsGenome.pl.\n"
            "Performs de novo motif discovery and known motif enrichment\n"
            "on ATAC-seq peaks.\n\n"
            "Background strategy:\n"
            "  all_peaks  → genomic background (GC-matched random regions)\n"
            "  da_up/down → consensus peaks as background (-bg -chopify)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    req = p.add_argument_group("required (at least one)")
    req.add_argument("--prev-result", "--input", required=False, dest="prev_result",
                     default=None,
                     help="result.json from bulkatac-DA (Step 4); accepts "
                          "--input too for OmicsClaw runner compatibility. "
                          "If omitted, auto-detected as <wd>/DA/result.json. "
                          "The peak_calling result is resolved automatically "
                          "via the chain.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too for "
                          "OmicsClaw runner compatibility). Default: sibling "
                          "of prev-result's parent dir (e.g. .../motif_enrichment/).")

    ref = p.add_argument_group("reference")
    ref.add_argument("--genome", default=None,
                     help="Genome name for HOMER (e.g. hg38, mm10, sacCer3). "
                          "Auto-detected from Step 3 result.json if omitted. "
                          "Requires HOMER genome install unless --genome-fasta "
                          "is provided.")
    ref.add_argument("--genome-fasta", default=None, dest="genome_fasta",
                     help="Genome FASTA file. If provided, passed to HOMER via "
                          "-fasta flag (no HOMER genome install required).")

    homer = p.add_argument_group("HOMER parameters")
    homer.add_argument("--size", type=str, default="200",
                       help="Region size for motif finding (default: 200 = ±100 bp "
                            "from peak center). Use 'given' for exact peak coords.")
    homer.add_argument("--mask", action="store_true", default=True,
                       help="Mask repeats (default: on, recommended for mammalian).")
    homer.add_argument("--no-mask", action="store_true", dest="no_mask",
                       help="Disable repeat masking.")
    homer.add_argument("--denovo-length", default="8,10,12", dest="denovo_length",
                       help="Comma-separated motif lengths for de novo discovery "
                            "(default: 8,10,12).")
    homer.add_argument("--n-motifs", type=int, default=25, dest="n_motifs",
                       help="Max de novo motifs to report (default: 25).")

    opt = p.add_argument_group("optional")
    opt.add_argument("--threads", type=int, default=16,
                     help="Number of threads (default: 16).")

    return p


# ── Progress reporting ──────────────────────────────────────────────────
# Written to the controlling terminal (/dev/tty) when one exists, so step
# progress shows live even though the OmicsClaw runner buffers the piped
# stdout; falls back to stdout when there is no terminal. See _emit_progress.
_STEPS = [
    "Check HOMER + load Step-3 (peak_calling) and Step-4 (DA) results",
    "HOMER motif enrichment — all peaks, DA-up, DA-down",
    "Summary table + top-motif plots",
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

    _print_step_plan()

    # ── Check HOMER ──────────────────────────────────────────────────────
    _step(1, "checking HOMER + loading Step-3/Step-4 results")
    if not check_homer():
        parser.error(
            "HOMER findMotifsGenome.pl not found in PATH.\n"
            "Install with:  conda install -c bioconda homer\n"
            "Then install genome:  configureHomer.pl -install hg38"
        )

    # ── Resolve prev-result: explicit > inferred from --wd ────────────────
    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    elif args.wd:
        prev_result_path = Path(args.wd).parent / "DA" / "result.json"
    else:
        parser.error("Either --prev-result or --wd must be provided.")

    if not prev_result_path.exists():
        parser.error(f"--prev-result not found: {prev_result_path}")

    # --prev-result must be a DA result; follow chain to find peak_calling
    prev_data = json.loads(prev_result_path.read_text())
    prev_skill = prev_data.get("skill", "")

    if prev_skill != "bulkatac-DA" and "da" not in prev_data:
        parser.error(
            "--prev-result must be a bulkatac-DA result.json, "
            f"but got skill='{prev_skill}'. Run bulkatac-DA first."
        )

    da_result_path = prev_result_path
    chain_ref = prev_data.get("prev_result") or prev_data.get("step3_result")
    if chain_ref and Path(chain_ref).exists():
        step3_result_path = Path(chain_ref)
    else:
        parser.error(
            "--prev-result is a DA result but cannot find peak_calling "
            "result.json in the chain (prev_result key missing or file deleted)."
        )

    step3 = load_step3_result(step3_result_path)
    consensus_bed = step3["consensus_bed"]

    if consensus_bed is None or not consensus_bed.exists():
        parser.error("Consensus peak BED not found in peak_calling result.json.")

    genome = args.genome or step3["genome"]
    if not genome:
        parser.error(
            "Genome not found. Provide --genome (e.g. hg38, mm10) or "
            "ensure peak_calling result.json contains sample_sheet.genome."
        )
    logger.info("Genome: %s (source: %s)", genome,
                "--genome" if args.genome else "result.json")

    # Genome FASTA: CLI flag > auto-detected > None
    if args.genome_fasta:
        genome_fasta = Path(args.genome_fasta)
        if not genome_fasta.exists():
            parser.error(f"--genome-fasta not found: {genome_fasta}")
    else:
        genome_fasta = step3.get("genome_fasta")

    if genome_fasta:
        logger.info("Genome FASTA: %s", genome_fasta)
    else:
        logger.info("No genome FASTA found — HOMER will use installed genome '%s'", genome)

    # DA results (from --prev-result chain)
    da_up_bed = da_down_bed = None
    if da_result_path:
        step4 = load_step4_result(da_result_path)
        da_up_bed   = step4["up_bed"]
        da_down_bed = step4["down_bed"]
        if da_up_bed:
            logger.info("DA-up peaks: %s", da_up_bed)
        if da_down_bed:
            logger.info("DA-down peaks: %s", da_down_bed)

    project_dir = prev_result_path.resolve().parent.parent
    output_dir = Path(args.wd) if args.wd else project_dir / "motif_enrichment"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    # Resolve size (int or "given")
    try:
        size: int | str = int(args.size)
    except ValueError:
        size = args.size  # "given"

    mask = args.mask and not args.no_mask

    params: dict[str, Any] = {
        "genome":        genome,
        "genome_fasta":  str(genome_fasta) if genome_fasta else None,
        "size":          size,
        "mask":          mask,
        "denovo_length": args.denovo_length,
        "n_motifs":      args.n_motifs,
        "threads":       args.threads,
    }

    logger.info("Consensus peaks: %s", consensus_bed)
    logger.info("Genome: %s  FASTA: %s", genome,
                genome_fasta or "(HOMER genome install)")

    # ── Run motif enrichment ─────────────────────────────────────────────
    _step(2, "HOMER motif enrichment — all peaks, DA-up, DA-down")
    enrichment_results = run_motif_enrichment_multi(
        consensus_bed=consensus_bed,
        genome=genome,
        output_dir=output_dir,
        genome_fasta=genome_fasta,
        da_up_bed=da_up_bed,
        da_down_bed=da_down_bed,
        size=size,
        mask=mask,
        n_processors=args.threads,
    )

    # ── Summary table ────────────────────────────────────────────────────
    _step(3, "summary table + top-motif plots")
    write_motif_summary(enrichment_results, output_dir)

    # ── Plots ────────────────────────────────────────────────────────────
    plots_dir = output_dir / "plots"
    for res in enrichment_results:
        if res.homer_succeeded:
            plot_top_known_motifs(res, plots_dir)
            plot_top_denovo_motifs(res, plots_dir)

    # ── Outputs ──────────────────────────────────────────────────────────
    _step(4, "writing report, reproducibility, and result.json")
    write_report(output_dir, enrichment_results, params,
                 step3_result_path=step3_result_path,
                 da_result_path=da_result_path)
    write_reproducibility(output_dir, params, prev_result_path)

    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n\n"
        "## Directories\n"
        "- `all_peaks/` — HOMER motif enrichment on full consensus peaks "
        "(genomic background)\n"
        "- `da_up/` — enrichment on DA-up peaks "
        "(consensus peaks as background, `-bg -chopify`)\n"
        "- `da_down/` — enrichment on DA-down peaks "
        "(consensus peaks as background, `-bg -chopify`)\n"
        "- `plots/` — top motif bar charts\n"
        "- `top_motif_summary.tsv` — combined ranked table\n"
        f"- `{SKILL_NAME}.log` — full run log: narrative + every tool's stdout/stderr\n\n"
        "## HOMER HTML reports\n"
        "Open `*/knownResults.html` and `*/homerResults.html` in a browser "
        "for interactive motif logos and enrichment tables.\n\n"
        "Next: Step 5b (TOBIAS footprinting) for TF occupancy analysis.\n"
    )

    # ── Console summary ──────────────────────────────────────────────────
    print(f"\n{SKILL_NAME} v{SKILL_VERSION} complete:")
    for res in enrichment_results:
        status = "OK" if res.homer_succeeded else "FAILED"
        n_known = len(res.known_results)
        n_denovo = len(res.denovo_results)
        print(f"  [{res.peak_set}] {status} — "
              f"{res.n_peaks:,} peaks, "
              f"{n_known} known motifs, {n_denovo} de novo motifs")
        if res.known_results:
            top = res.known_results[0]
            short = top.motif_name.split("/")[0] if "/" in top.motif_name else top.motif_name
            print(f"    Top known: {short} (log10p={top.log_p_value:.0f})")
        if res.denovo_results:
            top_dn = res.denovo_results[0]
            print(f"    Top de novo: {top_dn.consensus} "
                  f"(log10p={top_dn.log_p_value:.0f})")

    print(f"\n  Summary:  {output_dir / 'top_motif_summary.tsv'}")
    print(f"  Report:   {output_dir / 'report.md'}")
    print(f"  Plots:    {output_dir / 'plots'}")
    print(f"\n  Sibling downstream → bulkatac-footprinting (TOBIAS TF occupancy at motif sites)")


if __name__ == "__main__":
    main()
