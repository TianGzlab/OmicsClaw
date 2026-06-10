#!/usr/bin/env python3
"""
bulkhic-mapping.py — Bulk Hi-C Step 2: reads → ``.pairs`` (4DN / pairtools).

Per sample: ``bwa-mem2 mem -SP5M`` (both mates mapped independently — no
mate-rescue) → ``pairtools parse | sort`` → ``pairtools dedup`` →
pairix-indexed ``<sample>.nodups.pairs.gz`` + pairtools QC (valid-pair /
duplicate / cis-fraction / cis-trans / cis-long).

Builds the reference (FASTA + bwa-mem2 index + chrom.sizes) in --ref-dir if not
supplied; a local ``reference_<genome>/<genome>.fa`` is reused.

Quick-start
-----------
  python bulkhic-mapping.py --prev-result <project>/preprocessing/result.json --wd <project>/mapping
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
_BULKHIC_DIR  = _SKILL_DIR.parent
_PROJECT_ROOT = _BULKHIC_DIR.parent.parent.parent

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SKILL_NAME    = "bulkhic-mapping"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkhic/bulkhic-mapping/bulkhic-mapping.py"

from skills.epigenomics.bulkhic._lib.subenv_bootstrap import ensure_bulkhic_env  # noqa: E402
from skills.epigenomics.bulkhic._lib.progress import tty_write  # noqa: E402
ensure_bulkhic_env()

from skills.epigenomics.bulkhic._lib.mapping import (  # noqa: E402
    GenomeFiles, validate_genome_files, prepare_reference,
    run_all_mapping, write_mapping_summary, MappingResult,
)
from skills.epigenomics.bulkhic._lib.bulkhic_qc_criteria import (  # noqa: E402
    HIC_QC_THRESHOLDS, thresholds_markdown,
    valid_pair_tier, duplicate_tier, cis_fraction_tier, cis_trans_ratio_tier, cis_long_tier,
)
from omicsclaw.common.runlog import attach_run_log  # noqa: E402

_STEPS = [
    "Load Step-1 result + resolve genome",
    "Resolve reference (FASTA + aligner index + chrom.sizes)",
    "bwa-mem2 -SP5M + pairtools parse/sort/dedup → .pairs + QC",
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


def load_step1(result_json: Path) -> tuple[dict, str, list[tuple[str, Path, Path]]]:
    """Return (raw step1 dict, genome, [(sample, r1_trimmed, r2_trimmed)])."""
    data = json.loads(result_json.read_text())
    ss = data.get("sample_sheet", {}) or {}
    genome = ss.get("genome", "") or ""
    inputs: list[tuple[str, Path, Path]] = []
    for e in data.get("preprocessing", []):
        r1 = Path(e["r1_trimmed"])
        r2 = Path(e["r2_trimmed"]) if e.get("r2_trimmed") else None
        if r2 is None:
            raise SystemExit(f"Hi-C requires paired reads; sample {e['sample']} has no R2.")
        inputs.append((e["sample"], r1, r2))
    return data, genome, inputs


def write_report(output_dir, results: list[MappingResult], params, step1_data,
                 genome_files: GenomeFiles, prev_result_path: Path) -> None:
    lines = [
        "# Hi-C Mapping Report (reads → pairs)\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "", "---", "",
        "## Alignment + pairs",
        f"- **Samples**: {len(results)}   **Aligner**: {params.get('aligner')}   "
        f"**Genome**: {genome_files.genome}",
        "",
        "### Library QC (pairtools)\n",
        "| Sample | Valid pairs | Valid% | Dup% | Cis% | Cis/trans | Cis-long% |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.sample_name} | {r.n_nodups:,} | {r.valid_frac*100:.1f}% ({valid_pair_tier(r.valid_frac)}) "
            f"| {r.dup_frac*100:.1f}% ({duplicate_tier(r.dup_frac)}) "
            f"| {r.cis_frac*100:.1f}% ({cis_fraction_tier(r.cis_frac)}) "
            f"| {r.cis_trans_ratio:.2f} ({cis_trans_ratio_tier(r.cis_trans_ratio)}) "
            f"| {r.cis_long_frac*100:.1f}% ({cis_long_tier(r.cis_long_frac)}) |"
        )
    lines += ["", "### QC thresholds (4DN / pairtools)\n", *thresholds_markdown(), ""]
    lines += [
        "## Next Steps", "",
        "- **Step 3**: `bulkhic-matrix` — cooler cload + balance + zoomify → `.mcool` + P(s) QC.",
        "", "---", "",
        "> **Disclaimer**: OmicsClaw is a research tool. Results require expert interpretation.",
    ]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    result: dict[str, Any] = {
        "skill":           SKILL_NAME,
        "version":         SKILL_VERSION,
        "log":             str(output_dir / f"{SKILL_NAME}.log"),
        "steps_completed": step1_data.get("steps_completed", []) + ["mapping"],
        "steps_pending":   [s for s in step1_data.get("steps_pending", []) if s != "mapping"],
        "params":          params,
        "mapping": [
            {
                "sample":          r.sample_name,
                "pairs":           str(r.pairs),
                "aligner":         r.aligner,
                "n_total":         r.n_total,
                "n_valid_pairs":   r.n_nodups,
                "valid_frac":      r.valid_frac,
                "dup_frac":        r.dup_frac,
                "cis_frac":        r.cis_frac,
                "cis_trans_ratio": r.cis_trans_ratio,
                "cis_long_frac":   r.cis_long_frac,
                "stats_file":      str(r.stats_file) if r.stats_file else None,
            }
            for r in results
        ],
        "hic_qc_thresholds": HIC_QC_THRESHOLDS,
        "genome_files": {
            "genome":         genome_files.genome,
            "fasta":          str(genome_files.fasta) if genome_files.fasta else None,
            "chrom_sizes":    str(genome_files.chrom_sizes) if genome_files.chrom_sizes else None,
            "bwa_mem2_index": str(genome_files.bwa_mem2_index) if genome_files.bwa_mem2_index else None,
            "bwa_index":      str(genome_files.bwa_index) if genome_files.bwa_index else None,
        },
        "sample_sheet": step1_data.get("sample_sheet"),
        "prev_result":  str(prev_result_path),
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


def write_reproducibility(output_dir: Path, params: dict[str, Any], prev_result_path: Path) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)
    cmd = (f"python {SCRIPT_REL} --prev-result {shlex.quote(str(prev_result_path))} "
           f"--wd {shlex.quote(str(output_dir))} --aligner {params.get('aligner')} "
           f"--threads {params.get('threads')}")
    if params.get("ref_dir"):
        cmd += f" --ref-dir {shlex.quote(str(params['ref_dir']))}"
    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["pandas", "numpy"])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"{SKILL_NAME} v{SKILL_VERSION} — Bulk Hi-C reads → .pairs (bwa-mem2 + pairtools).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", dest="prev_result", default=None,
                     help="result.json from bulkhic-preprocessing (Step 1). "
                          "Auto-detected from --wd's sibling preprocessing/result.json if omitted.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too).")
    req.add_argument("--genome", default=None, help="Reference build (overrides Step 1's genome).")
    req.add_argument("--ref-dir", dest="ref_dir", default=None,
                     help="Directory for reference files (auto-built if absent).")
    ref = p.add_argument_group("reference")
    ref.add_argument("--aligner", default="bwa-mem2", choices=["bwa-mem2", "bwa"],
                     help="Aligner (default bwa-mem2; both run with -SP5M).")
    idx = ref.add_mutually_exclusive_group()
    idx.add_argument("--bwa-mem2-index", dest="bwa_mem2_index", default=None)
    idx.add_argument("--bwa-index", dest="bwa_index", default=None)
    ref.add_argument("--fasta-url", default=None, dest="fasta_url")
    opt = p.add_argument_group("optional")
    opt.add_argument("--threads", type=int, default=16)
    opt.add_argument("--min-mapq", type=int, default=30, dest="min_mapq",
                     help="Minimum MAPQ for pairtools parse (default 30).")
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    elif args.wd:
        prev_result_path = Path(args.wd).parent / "preprocessing" / "result.json"
    else:
        parser.error("Provide --prev-result or --wd so the Step-1 result.json can be located.")
    if not prev_result_path.exists():
        parser.error(f"Preprocessing result not found: {prev_result_path}")

    _print_step_plan()

    _step(1, "loading Step-1 preprocessing result")
    step1_data, genome, mapping_inputs = load_step1(prev_result_path)
    genome = args.genome or genome
    if not genome:
        parser.error("--genome is required (Step-1 result has no genome).")

    project_dir = prev_result_path.resolve().parent.parent
    output_dir = Path(args.wd) if args.wd else project_dir / "mapping"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)
    ref_dir = Path(args.ref_dir) if args.ref_dir else project_dir / f"reference_{genome}"

    supplied = args.bwa_mem2_index or args.bwa_index
    if args.bwa_mem2_index:
        args.aligner = "bwa-mem2"
    elif args.bwa_index:
        args.aligner = "bwa"

    _step(2, "resolving reference — "
             + ("using supplied index (+ chrom.sizes)" if supplied
                else "FASTA + aligner index + chrom.sizes (slow on first run)"))
    if supplied:
        from skills.epigenomics.bulkhic._lib.mapping import write_chrom_sizes
        fasta = ref_dir / f"{genome}.fa"
        chrom_sizes = write_chrom_sizes(fasta, ref_dir, genome) if fasta.exists() else None
        genome_files = GenomeFiles(
            genome=genome, fasta=fasta if fasta.exists() else None,
            bwa_mem2_index=Path(args.bwa_mem2_index) if args.bwa_mem2_index else None,
            bwa_index=Path(args.bwa_index) if args.bwa_index else None,
            chrom_sizes=chrom_sizes,
        )
    else:
        genome_files = prepare_reference(genome, ref_dir, aligner=args.aligner,
                                         threads=args.threads, fasta_url=args.fasta_url)
    validate_genome_files(genome_files, require_index=True)

    params: dict[str, Any] = {
        "aligner": args.aligner, "threads": args.threads,
        "min_mapq": args.min_mapq, "ref_dir": str(ref_dir),
    }

    _step(3, f"bwa-mem2 -SP5M + pairtools on {len(mapping_inputs)} sample(s) [{args.aligner}]")
    results = run_all_mapping(mapping_inputs, genome_files, output_dir / "pairs",
                              aligner=args.aligner, threads=args.threads, min_mapq=args.min_mapq)
    write_mapping_summary(results, output_dir)

    _step(4, "writing report, reproducibility, and result.json")
    write_report(output_dir, results, params, step1_data, genome_files, prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)
    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        "`pairs/<sample>/<sample>.nodups.pairs.gz` — deduplicated, pairix-indexed pairs.\n"
        "`mapping_summary.csv` — per-sample pairtools library-QC metrics.\n"
        f"`{SKILL_NAME}.log` — full run log.\n"
        "\nNext: bulkhic-matrix (Step 3 — pairs → balanced .mcool).\n"
    )

    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
        f"  {len(results)} sample(s)   Aligner: {args.aligner}   Genome: {genome}\n"
        + "".join(f"  [{r.sample_name}] {r.n_nodups:,} valid pairs "
                  f"(valid {r.valid_frac*100:.0f}%, dup {r.dup_frac*100:.0f}%, "
                  f"cis {r.cis_frac*100:.0f}%, cis/trans {r.cis_trans_ratio:.1f})\n"
                  for r in results)
        + f"  Pairs:   {output_dir / 'pairs'}\n"
        f"  Report:  {output_dir / 'report.md'}\n"
        f"\n  Next → bulkhic-matrix\n"
        f"         → bulkhic-compartments | bulkhic-insulation | bulkhic-loops → bulkhic-pileup\n"
    )


if __name__ == "__main__":
    main()
