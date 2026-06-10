#!/usr/bin/env python3
"""
bulkchip-motif-enrichment.py — Bulk ChIP-seq motif enrichment (Step 5a).

Runs HOMER findMotifsGenome.pl on ChIP-seq peaks to discover enriched TF
motifs via both de novo motif discovery and known motif enrichment.

For a transcription-factor ChIP the assayed factor's own motif is expected to
top the known-motif ranking (a built-in positive control); for histone-mark
ChIP HOMER instead surfaces the co-bound TFs enriched under the mark.

Scope
-----
  Step 5a — HOMER motif enrichment on a peak subset
    Peaks from Step 3 (consensus / per-condition) or Step 4 (DA up/down)
    → HOMER findMotifsGenome.pl
        known-motif enrichment + de novo discovery

Background strategy
-------------------
  • all_peaks (consensus):  default genomic background (GC-matched random
    regions).  Question: "Which motifs are enriched in ChIP peaks?"

  • da_up / da_down:  -bg consensus_peaks.bed -chopify
    Question: "Which motifs are *specifically* enriched in peaks that
    gained/lost binding vs all ChIP peaks?"

Output layout
-------------
  <output>/
  ├── README.md, report.md, result.json
  ├── motif_enrichment_summary.csv / top_motif_summary.tsv
  ├── all_peaks/                       (HOMER output: knownResults.* , homerResults.html)
  ├── da_up/, da_down/                 (HOMER output on DA subsets, if --de-result)
  ├── plots/
  └── reproducibility/

References
----------
  HOMER : http://homer.ucsd.edu/homer/motif/
          Heinz et al. 2010, Mol Cell 38(4):576-589

Quick-start
-----------
  python bulkchip-motif-enrichment.py --wd <project>/motif --peak-subset consensus
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

SKILL_NAME    = "bulkchip-motif-enrichment"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkchip/bulkchip-motif-enrichment/bulkchip-motif-enrichment.py"

from skills.epigenomics.bulkchip._lib.subenv_bootstrap import ensure_bulkchip_env  # noqa: E402
from skills.epigenomics.bulkchip._lib.progress import tty_write  # noqa: E402
ensure_bulkchip_env()

from skills.epigenomics.bulkchip._lib.motif_enrichment import (          # noqa: E402
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

def _find_genome_fasta(gf: dict, ss: dict, genome: str, result_json: Path) -> Path | None:
    """Locate a genome FASTA (optional HOMER fallback).

    Priority:
      1. genome_files.fasta in the peak-calling result.json
      2. reference_{genome}*/{genome}.fa next to the result.json or its
         project parent (the layout bulkchip-mapping writes)
    """
    # 1. Explicit path in genome_files
    if gf.get("fasta") and Path(gf["fasta"]).exists():
        return Path(gf["fasta"])

    if not genome:
        return None

    fa_names = [f"{genome}.fa", f"fasta/{genome}.fa"]

    # 2. reference_* dirs next to the result.json and one level up
    search_roots = [result_json.resolve().parent, result_json.resolve().parent.parent]
    for root in search_roots:
        if not root.is_dir():
            continue
        for ref_dir in sorted(root.glob(f"reference_{genome}*")):
            if not ref_dir.is_dir():
                continue
            for name in fa_names:
                cand = ref_dir / name
                if cand.exists():
                    return cand
            for cand in ref_dir.glob("*.fa"):
                if cand.exists():
                    return cand

    return None


def load_peak_calling_result(result_json: Path) -> dict[str, Any]:
    """Load bulkchip-peak-calling result.json → consensus peaks, genome, FASTA."""
    data = json.loads(result_json.read_text())

    consensus = data.get("consensus", {}) or {}
    consensus_bed = consensus.get("consensus_bed")
    if consensus_bed:
        consensus_bed = Path(consensus_bed)

    ss = data.get("sample_sheet", {}) or {}
    genome = ss.get("genome", "") or ""

    gf = data.get("genome_files") or {}
    genome_fasta = _find_genome_fasta(gf, ss, genome, result_json)

    # Per-condition / per-sample peaks (for --peak-subset condition).
    per_sample_peaks: dict[str, Path] = {}
    for rec in data.get("peak_calling", []) or []:
        pf = rec.get("peaks_file")
        if pf and Path(pf).exists():
            per_sample_peaks[rec.get("sample", "")] = Path(pf)

    return {
        "data":              data,
        "consensus_bed":     consensus_bed,
        "genome":            genome,
        "genome_fasta":      genome_fasta,
        "genome_files":      gf,
        "sample_sheet":      ss,
        "per_sample_peaks":  per_sample_peaks,
    }


def load_da_result(result_json: Path) -> dict[str, Any]:
    """Load bulkchip-DA result.json → up/down DA peak BED files."""
    data = json.loads(result_json.read_text())

    db = data.get("differential_binding", {}) or {}
    up_bed   = Path(db["up_bed"])   if db.get("up_bed")   and Path(db["up_bed"]).exists()   else None
    down_bed = Path(db["down_bed"]) if db.get("down_bed") and Path(db["down_bed"]).exists() else None
    contrast = db.get("contrast", "")

    return {
        "data":     data,
        "up_bed":   up_bed,
        "down_bed": down_bed,
        "contrast": contrast,
    }


# ---------------------------------------------------------------------------
# Report + result.json + reproducibility
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    enrichment_results: list[MotifEnrichmentResult],
    params: dict[str, Any],
    *,
    prev_result_path: Path | None = None,
    da_result_path: Path | None = None,
) -> None:
    lines: list[str] = [
        "# ChIP-seq Motif Enrichment Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "**Tool**: HOMER findMotifsGenome.pl",
        "", "---", "",
        "## Parameters\n",
        f"- Genome: `{params.get('genome', 'N/A')}`",
        f"- Peak subset: `{params.get('peak_subset', 'consensus')}`",
        f"- Region size: {params.get('size', 200)}",
        f"- Repeat masking: {'yes' if params.get('mask', True) else 'no'}",
        f"- De novo motif lengths: {params.get('denovo_length', '8,10,12')}",
        f"- Autonormalization: HOMER default (auto)",
        "",
    ]

    for res in enrichment_results:
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
        "What motifs are enriched in ChIP peaks vs genome? |",
        "| da_up | DA-up peaks | Consensus peaks (`-bg -chopify`) | "
        "What motifs drive *gained* binding? |",
        "| da_down | DA-down peaks | Consensus peaks (`-bg -chopify`) | "
        "What motifs drive *lost* binding? |",
        "",
        "> HOMER uses hypergeometric scoring (ZOOPS) with GC-content",
        "> normalization and lower-order oligo autonormalization.",
        "> Custom backgrounds (-bg) undergo the same normalization.",
        "> For a TF ChIP the assayed factor's motif should rank at the top;",
        "> for histone marks the enriched motifs point to co-bound TFs.",
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
                "peak_set":            res.peak_set,
                "n_peaks":             res.n_peaks,
                "homer_succeeded":     res.homer_succeeded,
                "n_known_motifs":      len(res.known_results),
                "n_denovo_motifs":     len(res.denovo_results),
                "top_known":           [h.motif_name for h in res.known_results[:5]],
                "top_denovo":          [h.consensus for h in res.denovo_results[:5]],
                "known_results_txt":   str(res.known_txt) if res.known_txt else None,
                "known_results_html":  str(res.known_html) if res.known_html else None,
                "denovo_results_html": str(res.denovo_html) if res.denovo_html else None,
                "output_dir":          str(res.output_dir),
            }
            for res in enrichment_results
        ],
        "summary_tsv":  str(output_dir / "top_motif_summary.tsv"),
        "prev_result":  str(prev_result_path) if prev_result_path else None,
        "da_result":    str(da_result_path) if da_result_path else None,
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


def write_reproducibility(
    output_dir: Path,
    params: dict[str, Any],
    prev_result_path: Path,
    da_result_path: Path | None = None,
) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)

    cmd = (
        f"python {SCRIPT_REL} "
        f"--prev-result {shlex.quote(str(prev_result_path))} "
        f"--wd {shlex.quote(str(output_dir))} "
        f"--peak-subset {shlex.quote(str(params.get('peak_subset', 'consensus')))}"
    )
    if da_result_path:
        cmd += f" --de-result {shlex.quote(str(da_result_path))}"

    for key, flag in [
        ("genome",        "--genome"),
        ("genome_fasta",  "--genome-fasta"),
        ("size",          "--size"),
        ("denovo_length", "--len"),
        ("n_motifs",      "--n-motifs"),
        ("threads",       "--threads"),
    ]:
        v = params.get(key)
        if v is not None:
            cmd += f" {flag} {shlex.quote(str(v))}"

    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["matplotlib", "numpy", "pandas"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"{SKILL_NAME} v{SKILL_VERSION} — Bulk ChIP-seq motif enrichment (HOMER).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", dest="prev_result", default=None,
                     help="result.json from bulkchip-peak-calling (Step 3) or bulkchip-DA (Step 4). "
                          "Auto-detected from --wd's sibling peak_calling/result.json if omitted.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too).")

    opt = p.add_argument_group("optional")
    opt.add_argument("--peak-subset", default="consensus", dest="peak_subset",
                     choices=["consensus", "condition", "up", "down"],
                     help="Which peak set to scan (default: consensus). "
                          "up/down require a bulkchip-DA result via --de-result.")
    opt.add_argument("--de-result", default=None, dest="de_result",
                     help="bulkchip-DA result.json (required for --peak-subset up/down).")
    opt.add_argument("--genome", default=None,
                     help="Genome name for HOMER (e.g. hg38, mm10, sacCer3). "
                          "Auto-detected from peak-calling result.json if omitted.")
    opt.add_argument("--genome-fasta", default=None, dest="genome_fasta",
                     help="Genome FASTA. If provided, passed to HOMER via -fasta "
                          "(no HOMER genome install required).")
    opt.add_argument("--size", default="200",
                     help="HOMER region size around peak center (default 200; 'given' for full peaks).")
    opt.add_argument("--len", default="8,10,12", dest="motif_len",
                     help="HOMER de novo motif lengths (default 8,10,12).")
    opt.add_argument("--n-motifs", type=int, default=25, dest="n_motifs",
                     help="Max de novo motifs to report (default: 25).")
    opt.add_argument("--no-mask", action="store_true", dest="no_mask",
                     help="Disable repeat masking (on by default).")
    opt.add_argument("--threads", type=int, default=8)
    return p


# ── Progress reporting ──────────────────────────────────────────────────
_STEPS = [
    "Check HOMER + load upstream result + resolve peak subset",
    "HOMER findMotifsGenome.pl (known + de novo)",
    "Summary table + top-motif plots",
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


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.prev_result and not args.wd:
        parser.error("Provide --prev-result or --wd so the upstream result.json can be located.")

    _print_step_plan()

    # ── Step 1: check HOMER + resolve upstream results ──────────────────────
    _step(1, "checking HOMER + loading upstream result + resolving peak subset")
    if not check_homer():
        parser.error(
            "HOMER findMotifsGenome.pl not found in PATH.\n"
            "Install with:  conda install -c bioconda homer\n"
            "Then install genome:  configureHomer.pl -install hg38"
        )

    # Resolve prev-result: explicit > inferred from --wd sibling.
    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    else:
        prev_result_path = Path(args.wd).parent / "peak_calling" / "result.json"
    if not prev_result_path.exists():
        parser.error(f"--prev-result not found: {prev_result_path}")

    # The prev-result may be a peak-calling result OR a DA result. If it is a
    # DA result, follow its `prev_result` chain back to peak-calling.
    prev_data = json.loads(prev_result_path.read_text())
    prev_skill = prev_data.get("skill", "")

    da_result_path: Path | None = None
    if prev_skill == "bulkchip-DA" or "differential_binding" in prev_data:
        da_result_path = prev_result_path
        chain_ref = prev_data.get("prev_result")
        if not (chain_ref and Path(chain_ref).exists()):
            parser.error(
                "--prev-result is a bulkchip-DA result but its peak_calling "
                "result.json could not be found in the chain (prev_result missing)."
            )
        peak_calling_result_path = Path(chain_ref)
    else:
        peak_calling_result_path = prev_result_path

    # Explicit --de-result wins for up/down subsets.
    if args.de_result:
        da_result_path = Path(args.de_result)
        if not da_result_path.exists():
            parser.error(f"--de-result not found: {da_result_path}")

    pc = load_peak_calling_result(peak_calling_result_path)
    consensus_bed = pc["consensus_bed"]
    if consensus_bed is None or not consensus_bed.exists():
        parser.error("Consensus peak BED not found in bulkchip-peak-calling result.json.")

    genome = args.genome or pc["genome"]
    if not genome:
        parser.error(
            "Genome not found. Provide --genome (e.g. hg38, mm10, sacCer3) or "
            "ensure peak-calling result.json contains sample_sheet.genome."
        )
    logger.info("Genome: %s (source: %s)", genome,
                "--genome" if args.genome else "result.json")

    # Genome FASTA: CLI flag > auto-detected > None.
    if args.genome_fasta:
        genome_fasta: Path | None = Path(args.genome_fasta)
        if not genome_fasta.exists():
            parser.error(f"--genome-fasta not found: {genome_fasta}")
    else:
        genome_fasta = pc.get("genome_fasta")
    if genome_fasta:
        logger.info("Genome FASTA: %s", genome_fasta)
    else:
        logger.info("No genome FASTA found — HOMER will use installed genome '%s'", genome)

    # Resolve peak subset → which BEDs to feed HOMER.
    da_up_bed = da_down_bed = None
    if args.peak_subset in ("up", "down"):
        if da_result_path is None:
            parser.error(
                f"--peak-subset {args.peak_subset} requires a bulkchip-DA "
                "result. Provide --de-result <DA/result.json> (or pass a DA "
                "result.json as --prev-result)."
            )
        da = load_da_result(da_result_path)
        if args.peak_subset == "up":
            da_up_bed = da["up_bed"]
            if da_up_bed is None:
                parser.error("bulkchip-DA result has no up_bed (no up DA peaks?).")
        else:
            da_down_bed = da["down_bed"]
            if da_down_bed is None:
                parser.error("bulkchip-DA result has no down_bed (no down DA peaks?).")
    elif da_result_path is not None and args.peak_subset == "consensus":
        # When chained from DA (or --de-result given) on the default subset,
        # also surface the DA up/down subsets alongside the consensus run.
        da = load_da_result(da_result_path)
        da_up_bed = da["up_bed"]
        da_down_bed = da["down_bed"]
        if da_up_bed:
            logger.info("DA-up peaks: %s", da_up_bed)
        if da_down_bed:
            logger.info("DA-down peaks: %s", da_down_bed)

    # Output dir + run log.
    project_dir = prev_result_path.resolve().parent.parent
    output_dir = Path(args.wd) if args.wd else project_dir / "motif_enrichment"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    # Resolve size (int or "given").
    try:
        size: int | str = int(args.size)
    except ValueError:
        size = args.size

    mask = not args.no_mask

    params: dict[str, Any] = {
        "genome":        genome,
        "genome_fasta":  str(genome_fasta) if genome_fasta else None,
        "peak_subset":   args.peak_subset,
        "size":          size,
        "mask":          mask,
        "denovo_length": args.motif_len,
        "n_motifs":      args.n_motifs,
        "threads":       args.threads,
    }

    logger.info("Consensus peaks: %s", consensus_bed)

    # ── Step 2: HOMER motif enrichment ──────────────────────────────────────
    _step(2, "HOMER motif enrichment (known + de novo)")
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

    # ── Step 3: summary table + plots ───────────────────────────────────────
    _step(3, "summary table + top-motif plots")
    summary_tsv = write_motif_summary(enrichment_results, output_dir)
    # Mirror the documented motif_enrichment_summary.csv alongside the TSV.
    try:
        import pandas as pd
        pd.read_csv(summary_tsv, sep="\t").to_csv(
            output_dir / "motif_enrichment_summary.csv", index=False)
    except Exception as exc:  # pragma: no cover - csv mirror is best-effort
        logger.warning("Could not write motif_enrichment_summary.csv: %s", exc)

    plots_dir = output_dir / "plots"
    for res in enrichment_results:
        if res.homer_succeeded:
            plot_top_known_motifs(res, plots_dir)
            plot_top_denovo_motifs(res, plots_dir)

    # ── Step 4: outputs ─────────────────────────────────────────────────────
    _step(4, "writing report, reproducibility, and result.json")
    write_report(output_dir, enrichment_results, params,
                 prev_result_path=peak_calling_result_path,
                 da_result_path=da_result_path)
    write_reproducibility(output_dir, params, prev_result_path, da_result_path)

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
        "- `top_motif_summary.tsv` / `motif_enrichment_summary.csv` — combined ranked table\n"
        f"- `{SKILL_NAME}.log` — full run log: narrative + every tool's stdout/stderr\n\n"
        "## HOMER HTML reports\n"
        "Open `*/knownResults.html` and `*/homerResults.html` in a browser "
        "for interactive motif logos and enrichment tables.\n\n"
        "For a TF ChIP the assayed factor's motif should top the known list; "
        "for histone marks the enriched motifs point to co-bound TFs.\n"
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
    print(f"\n  Next → bulkchip-peak-annotation → bulkchip-enrichment (peaks → genes → GO/KEGG)")


if __name__ == "__main__":
    main()
