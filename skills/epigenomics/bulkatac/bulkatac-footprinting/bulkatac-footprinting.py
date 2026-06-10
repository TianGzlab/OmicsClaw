#!/usr/bin/env python3
"""
bulkatac-footprinting.py — TF footprint analysis using TOBIAS (Step 5b).

Corrects Tn5 insertion bias, computes per-base footprint scores, scans
for motif occurrences, and classifies each TFBS as bound or unbound.
With two conditions, estimates differential TF binding.

Normalization
-------------
  ATACorrect:  10M / reads_in_peaks  (equalizes signal depth within peaks)
  BINDetect:   quantile normalization (non-linear, sigmoid-fitted)

Statistical test (no replicates needed)
---------------------------------------
  BINDetect uses a spatial test — compares TF binding site log2FC
  to random genomic background log2FC.  Each TFBS is an independent
  observation; a TF with 1000 sites provides ample statistical power.

Usage
-----
  python bulkatac-footprinting.py \\
      --prev-result output/peak_calling/result.json \\
      --wd output \\
      --genome-fasta ref/sacCer3.fa \\
      --motifs JASPAR2024_yeast.jaspar \\
      --treat T15 --control T0

  # Auto-download JASPAR motifs for the genome
  python bulkatac-footprinting.py \\
      --prev-result output/peak_calling/result.json \\
      --wd output

Output layout
-------------
  <output>/
  ├── report.md, result.json, reproducibility/
  ├── merged_bams/          — one BAM per condition
  ├── merged_peaks.bed
  ├── atacorrect/{cond}/    — corrected/uncorrected/bias bigwigs, QC pdf
  ├── footprints/{cond}/    — footprint score bigwigs
  ├── bindetect/            — per-TF bound/unbound BEDs, summary tables
  ├── plots/aggregate/      — aggregate footprint profiles for top TFs
  ├── plots/tf_differential_volcano.{pdf,png}
  └── top_tf_ranking.tsv

References
----------
  TOBIAS  : Bentsen et al. 2020, Nat Commun 11:4267
  GitHub  : https://github.com/loosolab/TOBIAS
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import shutil
import subprocess
import sys
import urllib.request
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

SKILL_NAME    = "bulkatac-footprinting"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkatac/bulkatac-footprinting/bulkatac-footprinting.py"

# ---------------------------------------------------------------------------
# _lib imports
# ---------------------------------------------------------------------------
# Relocate into the omicsclaw_bulkatac sub-env before the tool-backed _lib imports.
from skills.epigenomics.bulkatac._lib.subenv_bootstrap import ensure_bulkatac_env  # noqa: E402
from skills.epigenomics.bulkatac._lib.progress import tty_write  # noqa: E402
ensure_bulkatac_env()

from skills.epigenomics.bulkatac._lib.footprinting import (          # noqa: E402
    FootprintingResult,
    check_tobias,
    check_prerequisites,
    run_footprinting,
)
from omicsclaw.common.runlog import attach_run_log                   # noqa: E402

# ---------------------------------------------------------------------------
# JASPAR motif database auto-download
# ---------------------------------------------------------------------------

# JASPAR 2024 core motif URLs by organism group
_JASPAR_URLS: dict[str, tuple[str, str]] = {
    "vertebrates": (
        "https://jaspar.elixir.no/download/data/2024/CORE/JASPAR2024_CORE_vertebrates_non-redundant_pfms_jaspar.txt",
        "JASPAR2024_CORE_vertebrates.jaspar",
    ),
    "plants": (
        "https://jaspar.elixir.no/download/data/2024/CORE/JASPAR2024_CORE_plants_non-redundant_pfms_jaspar.txt",
        "JASPAR2024_CORE_plants.jaspar",
    ),
    "insects": (
        "https://jaspar.elixir.no/download/data/2024/CORE/JASPAR2024_CORE_insects_non-redundant_pfms_jaspar.txt",
        "JASPAR2024_CORE_insects.jaspar",
    ),
    "fungi": (
        "https://jaspar.elixir.no/download/data/2024/CORE/JASPAR2024_CORE_fungi_non-redundant_pfms_jaspar.txt",
        "JASPAR2024_CORE_fungi.jaspar",
    ),
    "nematodes": (
        "https://jaspar.elixir.no/download/data/2024/CORE/JASPAR2024_CORE_nematodes_non-redundant_pfms_jaspar.txt",
        "JASPAR2024_CORE_nematodes.jaspar",
    ),
}

# Genome name → JASPAR organism group
_GENOME_TO_JASPAR: dict[str, str] = {
    "hg38": "vertebrates", "hg19": "vertebrates",
    "mm10": "vertebrates", "mm39": "vertebrates",
    "rn6": "vertebrates", "rn7": "vertebrates",
    "danRer11": "vertebrates", "danRer10": "vertebrates",
    "galGal6": "vertebrates",
    "dm6": "insects", "dm3": "insects",
    "ce11": "nematodes", "ce10": "nematodes",
    "sacCer3": "fungi", "sacCer2": "fungi",
    "TAIR10": "plants",
}

_GENOME_PREFIX_TO_JASPAR: dict[str, str] = {
    "hg": "vertebrates", "mm": "vertebrates", "rn": "vertebrates",
    "danrer": "vertebrates", "galgal": "vertebrates",
    "dm": "insects",
    "ce": "nematodes", "caeel": "nematodes",
    "saccer": "fungi",
    "tair": "plants", "oryza": "plants",
}


def _detect_jaspar_group(genome: str) -> str:
    """Map genome name to JASPAR organism group."""
    if genome in _GENOME_TO_JASPAR:
        return _GENOME_TO_JASPAR[genome]
    g = genome.lower()
    for prefix, group in _GENOME_PREFIX_TO_JASPAR.items():
        if g.startswith(prefix):
            return group
    return "vertebrates"  # safe default


def download_jaspar_motifs(genome: str, output_dir: Path) -> Path:
    """Download JASPAR core motifs for the genome's organism group.

    Returns path to the downloaded .jaspar file.
    """
    group = _detect_jaspar_group(genome)
    if group not in _JASPAR_URLS:
        group = "vertebrates"

    url, filename = _JASPAR_URLS[group]
    output_dir.mkdir(parents=True, exist_ok=True)
    local_path = output_dir / filename

    if local_path.exists() and local_path.stat().st_size > 0:
        logger.info("JASPAR motifs already downloaded: %s", local_path)
        return local_path

    logger.info("Downloading JASPAR 2024 %s motifs ...", group)
    logger.info("  URL: %s", url)

    try:
        urllib.request.urlretrieve(url, str(local_path))
        logger.info("  Downloaded: %s (%.1f KB)",
                    local_path, local_path.stat().st_size / 1024)
        return local_path
    except Exception as e:
        raise RuntimeError(
            f"Failed to download JASPAR motifs from {url}: {e}\n"
            f"  Provide --motifs /path/to/motifs.jaspar manually."
        ) from e


# ---------------------------------------------------------------------------
# Load upstream results
# ---------------------------------------------------------------------------

def _find_genome_fasta(
    gf: dict, data: dict, genome: str, result_json: Path,
) -> Path | None:
    """Search for genome FASTA with multiple fallback strategies."""
    if gf.get("fasta") and Path(gf["fasta"]).exists():
        return Path(gf["fasta"])
    if not genome:
        return None

    fa_names = [f"{genome}.fa", f"fasta/{genome}.fa"]

    # ref_dir from params
    params = data.get("params") or {}
    ref_dir = params.get("ref_dir")
    if ref_dir:
        for name in fa_names:
            candidate = Path(ref_dir) / name
            if candidate.exists():
                return candidate

    # reference_* dirs next to result.json and siblings
    for search_root in [result_json.parent, result_json.parent.parent]:
        if not search_root.exists():
            continue
        for subdir in [search_root] + list(search_root.iterdir()):
            if not subdir.is_dir():
                continue
            for ref_dir_candidate in sorted(subdir.glob(f"reference_{genome}*")):
                if ref_dir_candidate.is_dir():
                    for name in fa_names:
                        candidate = ref_dir_candidate / name
                        if candidate.exists():
                            return candidate
    return None


def load_step3_result(result_json: Path) -> dict[str, Any]:
    """Load Step 3 result.json → BAM paths, consensus peaks, genome info."""
    data = json.loads(result_json.read_text())

    # Consensus peaks
    consensus = data.get("consensus", {})
    consensus_bed = consensus.get("consensus_bed")
    if consensus_bed:
        consensus_bed = Path(consensus_bed)

    # Sample info
    ss = data.get("sample_sheet", {})
    genome = ss.get("genome", "")
    samples = ss.get("samples", [])
    sample_conditions = {s["name"]: s.get("condition", "") for s in samples}

    # Genome files
    gf = data.get("genome_files") or {}
    genome_fasta = _find_genome_fasta(gf, data, genome, result_json)
    blacklist = Path(gf["blacklist"]) if gf.get("blacklist") and Path(gf["blacklist"]).exists() else None

    # BAM paths from Step 2 mapping data (carried through Step 3)
    sample_bams: dict[str, Path] = {}
    for m in data.get("mapping", []):
        bam = Path(m["bam"])
        if bam.exists():
            sample_bams[m["sample"]] = bam

    # If mapping data not in Step 3, walk the prev_result chain to find BAMs
    if not sample_bams:
        prev_result = data.get("prev_result") or data.get("step2_result")
        if prev_result and Path(prev_result).exists():
            prev_data = json.loads(Path(prev_result).read_text())
            for m in prev_data.get("mapping", []):
                bam = Path(m["bam"])
                if bam.exists():
                    sample_bams[m["sample"]] = bam

    return {
        "data":              data,
        "consensus_bed":     consensus_bed,
        "genome":            genome,
        "genome_fasta":      genome_fasta,
        "blacklist":         blacklist,
        "sample_bams":       sample_bams,
        "sample_conditions": sample_conditions,
        "sample_sheet":      ss,
    }


# ---------------------------------------------------------------------------
# Report + result.json
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    fp_result: FootprintingResult,
    params: dict[str, Any],
    *,
    prev_result_path: Path | None = None,
) -> None:
    conds = fp_result.conditions
    bd = fp_result.bindetect

    lines = [
        "# TF Footprint Analysis Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        f"**Tool**: TOBIAS (Bentsen et al. 2020, Nat Commun 11:4267)",
        "", "---", "",
        "## Parameters\n",
        f"- Genome FASTA: `{params.get('genome_fasta', 'N/A')}`",
        f"- Motif database: `{params.get('motifs_file', 'N/A')}`",
        f"- Conditions: {conds}",
        f"- Threads: {params.get('threads', 16)}",
        "",
    ]

    # ATACorrect summary
    lines += ["## Step 2: Tn5 Bias Correction (ATACorrect)\n"]
    for ac in fp_result.atacorrect:
        lines.append(f"- **{ac.condition}**: `{ac.corrected_bw}`")
    lines.append("")

    # Footprint summary
    lines += ["## Step 3: Footprint Scoring (ScoreBigwig)\n"]
    for fp in fp_result.footprints:
        lines.append(f"- **{fp.condition}**: `{fp.footprint_bw}`")
    lines.append("")

    # BINDetect summary
    if bd:
        lines += [
            "## Step 4: Motif Scanning + Binding Prediction (BINDetect)\n",
            f"- Motifs tested: {bd.n_motifs_tested}",
            f"- Differential analysis: {'yes' if bd.is_differential else 'no'}",
        ]
        if bd.is_differential:
            lines.append(f"- TFs with |change| > 0.1: {bd.n_differential}")
        lines += [
            f"- Results: `bindetect/bindetect_results.txt`",
            f"- Figures: `bindetect/bindetect_figures.pdf`",
            "",
        ]

    # Aggregate plots
    if fp_result.aggregate_plots:
        lines += [
            "## Step 5: Aggregate Footprint Profiles\n",
            f"- {len(fp_result.aggregate_plots)} plots in `plots/aggregate/`",
            "",
        ]

    lines += [
        "", "---", "",
        "## Normalization\n",
        "| Step | Method |",
        "|---|---|",
        "| ATACorrect | 10M / reads_in_peaks (equalizes signal depth at peaks) |",
        "| BINDetect | Quantile normalization (sigmoid-fitted, non-linear) |",
        "",
        "## Statistical test\n",
        "BINDetect compares TF binding site log2FC to random genomic background",
        "log2FC using a one-sample t-test against 100 null resamples.",
        "Each TFBS is an independent observation — no biological replicates needed.",
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
        "footprinting": {
            "conditions":    fp_result.conditions,
            "n_conditions":  fp_result.n_conditions,
            "merged_peaks":  str(fp_result.merged_peaks_bed),
            "atacorrect": [
                {"condition": ac.condition, "corrected_bw": str(ac.corrected_bw)}
                for ac in fp_result.atacorrect
            ],
            "footprints": [
                {"condition": fp.condition, "footprint_bw": str(fp.footprint_bw)}
                for fp in fp_result.footprints
            ],
            "bindetect": {
                "results_txt":     str(bd.results_txt) if bd and bd.results_txt else None,
                "figures_pdf":     str(bd.figures_pdf) if bd and bd.figures_pdf else None,
                "n_motifs_tested": bd.n_motifs_tested if bd else 0,
                "n_differential":  bd.n_differential if bd else 0,
                "is_differential": bd.is_differential if bd else False,
            } if bd else None,
            "top_tf_ranking": str(output_dir / "top_tf_ranking.tsv"),
            "aggregate_plots": [str(p) for p in fp_result.aggregate_plots],
        },
        "prev_result": str(prev_result_path) if prev_result_path else None,
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
        ("genome_fasta", "--genome-fasta"),
        ("motifs_file",  "--motifs"),
        ("treat",        "--treat"),
        ("control",      "--control"),
        ("threads",      "--threads"),
    ]:
        v = params.get(key)
        if v is not None:
            cmd += f" {flag} {shlex.quote(str(v))}"

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
            f"{SKILL_NAME} v{SKILL_VERSION}\n\n"
            "TF footprint analysis using TOBIAS.\n"
            "ATACorrect → ScoreBigwig → BINDetect → PlotAggregate\n\n"
            "Requires: genome FASTA + motif database (auto-downloaded\n"
            "from JASPAR 2024 if --motifs is not provided)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    req = p.add_argument_group("required (at least one)")
    req.add_argument("--prev-result", "--input", required=False, dest="prev_result",
                     default=None,
                     help="result.json from bulkatac-peak-calling (Step 3); accepts "
                          "--input too for OmicsClaw runner compatibility. "
                          "If omitted, auto-detected as <wd>/peak_calling/result.json. "
                          "BAM paths are resolved from the mapping data "
                          "carried in result.json.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too for "
                          "OmicsClaw runner compatibility). Default: sibling "
                          "of prev-result's parent dir (e.g. .../footprinting/).")

    ref = p.add_argument_group("reference")
    ref.add_argument("--genome-fasta", default=None, dest="genome_fasta",
                     help="Genome FASTA with .fai index. Auto-detected from "
                          "Step 2/3 reference directory if omitted.")
    ref.add_argument("--motifs", default=None, dest="motifs_file",
                     help="Motif database in JASPAR/PFM/MEME format. "
                          "Auto-downloaded from JASPAR 2024 if omitted.")
    ref.add_argument("--blacklist", default=None,
                     help="ENCODE blacklist BED (recommended). Auto-detected "
                          "from Step 2 if available.")

    contrast = p.add_argument_group("contrast")
    contrast.add_argument("--treat", default=None,
                          help="Treatment condition name (controls BINDetect ordering).")
    contrast.add_argument("--control", default=None,
                          help="Control condition name.")

    opt = p.add_argument_group("optional")
    opt.add_argument("--threads", type=int, default=16,
                     help="Number of threads (default: 16).")

    return p


# ── Progress reporting ──────────────────────────────────────────────────
# Written to the controlling terminal (/dev/tty) when one exists, so step
# progress shows live even though the OmicsClaw runner buffers the piped
# stdout; falls back to stdout when there is no terminal. See _emit_progress.
_STEPS = [
    "Check prerequisites + load Step-3 peak-calling result",
    "Resolve genome FASTA + motif database (JASPAR)",
    "TOBIAS footprinting — ATACorrect, ScoreBigwig, BINDetect, aggregate plots",
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

    # ── Check prerequisites ──────────────────────────────────────────────
    _step(1, "checking prerequisites + loading Step-3 peak-calling result")
    missing = check_prerequisites()
    if missing:
        parser.error(
            f"Missing required tools: {', '.join(missing)}\n"
            "Install with: pip install tobias && conda install -c bioconda samtools bedtools"
        )
    check_tobias()  # logs version

    # ── Resolve prev-result: explicit > inferred from --wd ────────────────
    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    elif args.wd:
        prev_result_path = Path(args.wd).parent / "peak_calling" / "result.json"
    else:
        parser.error("Either --prev-result or --wd must be provided.")

    if not prev_result_path.exists():
        parser.error(f"--prev-result not found: {prev_result_path}")

    step3 = load_step3_result(prev_result_path)
    consensus_bed     = step3["consensus_bed"]
    genome            = step3["genome"]
    sample_bams       = step3["sample_bams"]
    sample_conditions = step3["sample_conditions"]

    if consensus_bed is None or not consensus_bed.exists():
        parser.error("Consensus peak BED not found in --prev-result.")

    if not sample_bams:
        parser.error(
            "No BAM files found. Ensure the peak_calling result.json "
            "contains mapping data with BAM paths (re-run peak_calling "
            "to regenerate result.json with mapping chain)."
        )

    # ── Genome FASTA ─────────────────────────────────────────────────────
    _step(2, "resolving genome FASTA + motif database (JASPAR)")
    if args.genome_fasta:
        genome_fasta = Path(args.genome_fasta)
        if not genome_fasta.exists():
            parser.error(f"--genome-fasta not found: {genome_fasta}")
    else:
        genome_fasta = step3.get("genome_fasta")

    if not genome_fasta or not genome_fasta.exists():
        parser.error(
            "Genome FASTA not found. Provide --genome-fasta /path/to/genome.fa\n"
            "TOBIAS requires the genome FASTA for bias correction and motif scanning."
        )

    # Check .fai index
    fai = genome_fasta.with_suffix(".fa.fai")
    if not fai.exists():
        fai = Path(str(genome_fasta) + ".fai")
    if not fai.exists():
        logger.info("Creating FASTA index with samtools faidx ...")
        subprocess.run(["samtools", "faidx", str(genome_fasta)], check=True)

    # ── Motif database ───────────────────────────────────────────────────
    project_dir = prev_result_path.resolve().parent.parent
    output_dir = Path(args.wd) if args.wd else project_dir / "footprinting"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    if args.motifs_file:
        motifs_file = Path(args.motifs_file)
        if not motifs_file.exists():
            parser.error(f"--motifs not found: {motifs_file}")
    else:
        motifs_file = download_jaspar_motifs(genome, output_dir / "motifs")

    # ── Blacklist ────────────────────────────────────────────────────────
    blacklist = None
    if args.blacklist:
        blacklist = Path(args.blacklist)
        if not blacklist.exists():
            parser.error(f"--blacklist not found: {blacklist}")
    elif step3.get("blacklist"):
        blacklist = step3["blacklist"]

    # ── Log summary ──────────────────────────────────────────────────────
    logger.info("Consensus peaks: %s", consensus_bed)
    logger.info("Genome FASTA: %s", genome_fasta)
    logger.info("Motif database: %s", motifs_file)
    logger.info("Blacklist: %s", blacklist or "(none)")
    logger.info("Samples: %d BAMs → %d conditions",
                len(sample_bams), len(set(sample_conditions.values())))
    for sample, bam in sorted(sample_bams.items()):
        logger.info("  %s [%s]: %s",
                    sample, sample_conditions.get(sample, "?"), bam)

    params: dict[str, Any] = {
        "genome":       genome,
        "genome_fasta": str(genome_fasta),
        "motifs_file":  str(motifs_file),
        "treat":        args.treat,
        "control":      args.control,
        "threads":      args.threads,
        "blacklist":    str(blacklist) if blacklist else None,
    }

    # ── Run footprinting pipeline ────────────────────────────────────────
    _step(3, "TOBIAS footprinting — ATACorrect, ScoreBigwig, BINDetect, aggregate plots")
    fp_result = run_footprinting(
        sample_bams=sample_bams,
        sample_conditions=sample_conditions,
        consensus_bed=consensus_bed,
        genome_fasta=genome_fasta,
        motifs_file=motifs_file,
        output_dir=output_dir,
        blacklist=blacklist,
        treat=args.treat,
        control=args.control,
        cores=args.threads,
    )

    # ── Outputs ──────────────────────────────────────────────────────────
    _step(4, "writing report, reproducibility, and result.json")
    write_report(output_dir, fp_result, params,
                 prev_result_path=prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)

    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n\n"
        "## Directories\n"
        "- `merged_bams/` — one BAM per condition (replicates merged)\n"
        "- `atacorrect/` — Tn5 bias-corrected bigwigs + QC plots\n"
        "- `footprints/` — footprint score bigwigs\n"
        "- `bindetect/` — per-TF bound/unbound BEDs, summary tables, volcano\n"
        "- `plots/aggregate/` — aggregate footprint profiles for top TFs\n"
        "- `top_tf_ranking.tsv` — ranked TF table\n"
        f"- `{SKILL_NAME}.log` — full run log: narrative + every tool's stdout/stderr\n\n"
        "## Key files\n"
        "- `bindetect/bindetect_results.txt` — one row per TF with scores, "
        "bound counts, differential change, p-values\n"
        "- `bindetect/bindetect_figures.pdf` — TOBIAS built-in score "
        "distributions and volcano plots\n"
        "- `plots/tf_differential_volcano.pdf` — custom volcano plot\n"
    )

    # ── Console summary ──────────────────────────────────────────────────
    bd = fp_result.bindetect
    print(f"\n{SKILL_NAME} v{SKILL_VERSION} complete:")
    print(f"  Conditions:  {fp_result.conditions}")
    print(f"  Peaks:       {fp_result.merged_peaks_bed}")
    if bd:
        print(f"  Motifs:      {bd.n_motifs_tested} tested")
        if bd.is_differential:
            print(f"  Differential: {bd.n_differential} TFs with |change| > 0.1")
        print(f"  BINDetect:   {bd.results_txt}")
    print(f"  Plots:       {output_dir / 'plots'}")
    print(f"  Report:      {output_dir / 'report.md'}")
    print(f"\n  Sibling downstream → bulkatac-motif-enrichment (sequence-level TF motifs)")


if __name__ == "__main__":
    main()
