#!/usr/bin/env python3
"""
bulkchip-peak-annotation.py — Bulk ChIP-seq peak→gene genomic annotation
(Step 5b, annotation half).

Implemented (HOMER annotatePeaks.pl / GTF bedtools-closest backed). See
`_lib/peak_annotation.py`.

Scope
-----
  Annotate a ChIP-seq peak set with genomic features + nearest genes:
    Peaks from Step 3 (consensus / per-condition) or Step 4 (DA up/down)
    → genomic annotation (HOMER annotatePeaks.pl, or GTF bedtools-closest):
        feature distribution (promoter-TSS / exon / intron / intergenic / ...)
        + nearest gene per peak
    → feature-distribution pie + TSS-distance histogram
    → target-gene set (peaks within a TSS window)

  GO/KEGG functional enrichment is a SEPARATE skill
  (bulkchip-annotation-enrichment / its enrichment successor) that consumes
  this skill's result.json target_genes.

Output layout
-------------
  <output>/
  ├── README.md, report.md, result.json
  ├── annotation/                  (annotated_peaks.tsv, feature pie, TSS dist)
  └── reproducibility/

References
----------
  HOMER annotatePeaks.pl : http://homer.ucsd.edu/homer/ngs/annotation.html
  ChIPseeker (concept)   : https://doi.org/10.1093/bioinformatics/btv145

Quick-start
-----------
  python bulkchip-peak-annotation.py --wd <project>/annotation --peak-subset consensus
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

SKILL_NAME    = "bulkchip-peak-annotation"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkchip/bulkchip-peak-annotation/bulkchip-peak-annotation.py"

from skills.epigenomics.bulkchip._lib.subenv_bootstrap import ensure_bulkchip_env  # noqa: E402
from skills.epigenomics.bulkchip._lib.progress import tty_write  # noqa: E402
ensure_bulkchip_env()

from skills.epigenomics.bulkchip._lib.peak_annotation import annotate_peaks  # noqa: E402
from omicsclaw.common.runlog import attach_run_log  # noqa: E402

_STEPS = [
    "Load upstream result + resolve peak subset + genome/GTF",
    "Genomic annotation (HOMER annotatePeaks.pl / GTF bedtools-closest)",
    "Feature pie + TSS-distance plot + target-gene set",
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
# Upstream result loading + peak / genome / GTF resolution
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _count_data_rows(tsv: Path) -> int:
    """Count data rows (excluding the header) in an annotated_peaks.tsv."""
    try:
        with open(tsv) as fh:
            return max(0, sum(1 for _ in fh) - 1)
    except OSError:
        return 0


def _is_da_result(data: dict[str, Any]) -> bool:
    """A bulkchip-DA result — by skill name or the presence of its payload."""
    return data.get("skill") == "bulkchip-DA" or "differential_binding" in data


def _find_da_result(
    prev_result_path: Path, prev_data: dict[str, Any], de_result_arg: str | None,
) -> Path | None:
    """
    Locate a bulkchip-DA result.json so we can also annotate the up/down peaks,
    WITHOUT raising. Priority: --de-result > the upstream result itself (if it is
    a DA result) > the sibling ``<project>/DA/result.json``. Returns None when no
    DA result is reachable (→ consensus-only annotation).
    """
    if de_result_arg:
        p = Path(de_result_arg)
        return p if p.exists() else None
    if _is_da_result(prev_data):
        return prev_result_path
    sib = prev_result_path.resolve().parent.parent / "DA" / "result.json"
    if sib.exists():
        try:
            if _is_da_result(_load_json(sib)):
                return sib
        except Exception:
            return None
    return None


def _probe_reference_gtf(
    containers: tuple[dict[str, Any], ...], search_root: Path | None = None,
) -> Path | None:
    """
    Find a GTF/GFF sitting in a reference directory. ChIP mapping does not
    download a GTF, so a user who drops one into ``reference_<genome>/`` expects
    it to be picked up automatically — this covers that case.

    Looks (in order) next to the genome FASTA recorded in ``genome_files.fasta``,
    then in any ``reference_*`` directory under ``search_root`` (the project dir)
    — the latter works even when the upstream chain didn't carry genome_files.
    Returns the first match (uncompressed preferred).
    """
    ref_dirs: list[Path] = []
    for container in containers:
        gf = (container or {}).get("genome_files", {}) or {}
        fa = gf.get("fasta")
        if fa:
            d = Path(fa).parent
            if d not in ref_dirs:
                ref_dirs.append(d)
    if search_root:
        for ref in sorted(Path(search_root).glob("reference_*")):
            if ref.is_dir() and ref not in ref_dirs:
                ref_dirs.append(ref)
    for d in ref_dirs:
        if not d.exists():
            continue
        for pat in ("*.gtf", "*.gff3", "*.gff", "*.gtf.gz", "*.gff3.gz", "*.gff.gz"):
            hits = sorted(d.glob(pat))
            if hits:
                return hits[0]
    return None


def _resolve_genome_and_gtf(
    pc_data: dict[str, Any], cli_gtf: str | None, search_root: Path | None = None,
) -> tuple[str | None, Path | None]:
    """
    Resolve (genome_name, gtf_path) for annotation.

    GTF priority: --gtf > genome_files.gtf (top-level or under sample_sheet) >
    a GTF/GFF auto-detected in the reference directory (next to the FASTA, or in
    a ``reference_*`` dir under the project). Genome name: sample_sheet.genome
    (used as the HOMER genome when no GTF).
    """
    ss = pc_data.get("sample_sheet", {}) or {}
    genome = ss.get("genome") or None

    gtf: Path | None = None
    if cli_gtf:
        gtf = Path(cli_gtf)
    else:
        for container in (pc_data, ss):
            gf = (container or {}).get("genome_files", {}) or {}
            cand = gf.get("gtf")
            if cand and Path(cand).exists():
                gtf = Path(cand)
                break
        if gtf is None:
            probed = _probe_reference_gtf((pc_data, ss), search_root)
            if probed is not None:
                logger.info("Auto-detected GTF in reference dir: %s", probed)
                gtf = probed
    return genome, gtf


def resolve_peak_set(
    prev_result_path: Path,
    peak_subset: str,
    de_result_arg: str | None,
    cli_gtf: str | None,
) -> dict[str, Any]:
    """
    Resolve the peak BED to annotate plus the genome/GTF for annotation.

    Returns dict with: peaks_bed, genome, gtf, pc_result_path (peak-calling
    result.json used for genome/GTF), pc_data.
    """
    prev_data = _load_json(prev_result_path)
    # Project dir (…/<skill>/result.json → …/<skill> → project) — used to glob
    # reference_* dirs for a GTF even when the chain didn't carry genome_files.
    search_root = prev_result_path.resolve().parent.parent

    # ----- up/down subsets come from a bulkchip-DA result -----
    if peak_subset in ("up", "down"):
        if de_result_arg:
            da_path = Path(de_result_arg)
            da_data = _load_json(da_path)
        elif _is_da_result(prev_data):
            da_path = prev_result_path
            da_data = prev_data
        else:
            raise SystemExit(
                f"--peak-subset {peak_subset} requires a bulkchip-DA result "
                "(pass it via --de-result, or chain from a DA result.json)."
            )

        db = da_data.get("differential_binding", {}) or {}
        bed_key = "up_bed" if peak_subset == "up" else "down_bed"
        bed_val = db.get(bed_key)
        if not bed_val:
            raise SystemExit(f"DA result has no {bed_key} for --peak-subset {peak_subset}.")
        peaks_bed = Path(bed_val)

        # Follow DA's prev_result back to peak-calling for genome/GTF.
        pc_path = Path(da_data.get("prev_result", "")) if da_data.get("prev_result") else None
        pc_data = _load_json(pc_path) if (pc_path and pc_path.exists()) else da_data
        pc_used = pc_path if (pc_path and pc_path.exists()) else da_path

        genome, gtf = _resolve_genome_and_gtf(pc_data, cli_gtf, search_root)
        return {"peaks_bed": peaks_bed, "genome": genome, "gtf": gtf,
                "pc_result_path": pc_used, "pc_data": pc_data}

    # ----- consensus / condition subsets come from peak-calling -----
    if _is_da_result(prev_data):
        # Chained from DA but asking for consensus/condition — walk back.
        pc_path = Path(prev_data.get("prev_result", "")) if prev_data.get("prev_result") else None
        pc_data = _load_json(pc_path) if (pc_path and pc_path.exists()) else prev_data
        pc_used = pc_path if (pc_path and pc_path.exists()) else prev_result_path
    else:
        pc_data = prev_data
        pc_used = prev_result_path

    if peak_subset == "consensus":
        consensus = pc_data.get("consensus", {}) or {}
        bed_val = consensus.get("consensus_bed")
        if not bed_val:
            raise SystemExit("Peak-calling result has no consensus.consensus_bed.")
        peaks_bed = Path(bed_val)
    else:  # condition — first per-sample/condition peaks_file
        pcs = pc_data.get("peak_calling", []) or []
        bed_val = next((p.get("peaks_file") for p in pcs if p.get("peaks_file")), None)
        if not bed_val:
            raise SystemExit("Peak-calling result has no peak_calling[].peaks_file.")
        peaks_bed = Path(bed_val)

    genome, gtf = _resolve_genome_and_gtf(pc_data, cli_gtf, search_root)
    return {"peaks_bed": peaks_bed, "genome": genome, "gtf": gtf,
            "pc_result_path": pc_used, "pc_data": pc_data}


# ---------------------------------------------------------------------------
# Report + result.json + reproducibility
# ---------------------------------------------------------------------------

def _annotation_block(ann, params: dict[str, Any], ann_dir: Path) -> dict[str, Any]:
    """One subset's annotation payload for result.json."""
    return {
        "peak_subset":    params.get("peak_subset"),
        "dir":            str(ann_dir),
        "annotated_tsv":  str(ann.annotated_tsv),
        "feature_counts": ann.feature_counts or {},
        "n_target_genes": len(ann.target_genes),
        "target_genes":   ann.target_genes,
        "pie_png":        str(ann.pie_png) if ann.pie_png else None,
        "tss_dist_png":   str(ann.tss_dist_png) if ann.tss_dist_png else None,
        "genome":         params.get("genome"),
        "tss_window":     params.get("tss_window"),
    }


def _report_section(ann, params: dict[str, Any]) -> list[str]:
    """Markdown section for one annotated subset."""
    feature_counts = ann.feature_counts or {}
    total = sum(feature_counts.values())
    lines = [
        f"## Peak→gene annotation — `{params.get('peak_subset')}` subset", "",
        f"- **Genome**: {params.get('genome') or '—'}  |  "
        f"**GTF**: {params.get('gtf') or '(HOMER genome / none)'}",
        f"- **TSS window for target genes**: {params.get('tss_window')} bp",
        f"- **Annotated peaks**: {total:,}",
        "",
        "### Feature distribution\n",
        "| Feature | Peaks | Fraction |",
        "|---|---|---|",
    ]
    for cat, count in sorted(feature_counts.items(), key=lambda x: -x[1]):
        frac = count / max(total, 1)
        lines.append(f"| {cat} | {count:,} | {frac:.1%} |")
    if not feature_counts:
        lines.append("| (no feature annotation — no HOMER genome / GTF) | — | — |")
    lines += [
        "",
        f"**Target genes** (nearest-gene TSS ≤ {params.get('tss_window')} bp): "
        f"{len(ann.target_genes):,}",
        "",
    ]
    if ann.target_genes:
        preview = ", ".join(ann.target_genes[:25])
        lines.append(f"Top target genes: {preview}"
                     + (" …" if len(ann.target_genes) > 25 else ""))
    lines += [
        "",
        f"- Feature pie: `{ann.pie_png.name if ann.pie_png else 'n/a'}`",
        f"- TSS-distance histogram: `{ann.tss_dist_png.name if ann.tss_dist_png else 'n/a'}`",
        "", "---", "",
    ]
    return lines


def write_report(
    output_dir: Path,
    subset_results: list[dict[str, Any]],
    prev_result_path: Path,
) -> None:
    """Write a multi-section report + result.json over all annotated subsets.

    ``subset_results[0]`` is the primary subset (consensus when present); it is
    surfaced at the top-level ``annotation`` block so downstream
    bulkchip-enrichment keeps reading ``annotation.target_genes`` unchanged.
    Every subset also appears in the ``annotations`` list.
    """
    primary = subset_results[0]
    subsets_csv = ", ".join(r["params"]["peak_subset"] for r in subset_results)
    lines: list[str] = [
        "# ChIP-seq Peak Annotation Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        f"**Annotated subsets**: {subsets_csv}",
        "", "---", "",
    ]
    for r in subset_results:
        lines += _report_section(r["ann"], r["params"])
    lines += [
        "## Next Steps", "",
        "- **GO/KEGG enrichment** — run `bulkchip-enrichment` on the "
        "`annotation.target_genes` set (consensus subset) in this `result.json`.",
        "- **bulkchip-motif-enrichment** — HOMER motif enrichment on the same peaks.",
        "", "---", "",
        "> **Disclaimer**: OmicsClaw is a research and educational tool for "
        "multi-omics analysis. It is not a medical device and does not provide "
        "clinical diagnoses. Consult a domain expert before making decisions "
        "based on these results.",
    ]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    blocks = [_annotation_block(r["ann"], r["params"], r["dir"]) for r in subset_results]
    result: dict[str, Any] = {
        "skill":   SKILL_NAME,
        "version": SKILL_VERSION,
        "log":     str(output_dir / f"{SKILL_NAME}.log"),
        "params":  primary["params"],
        "annotation":  blocks[0],   # primary (consensus) — back-compat for enrichment
        "annotations": blocks,      # every annotated subset
        "prev_result": str(prev_result_path),
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


def write_reproducibility(
    output_dir: Path, params: dict[str, Any], prev_result_path: Path,
) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)
    cmd = (
        f"python {SCRIPT_REL} "
        f"--prev-result {shlex.quote(str(prev_result_path))} "
        f"--wd {shlex.quote(str(output_dir))} "
        f"--peak-subset {params.get('peak_subset')} "
        f"--tss-window {params.get('tss_window')} "
        f"--threads {params.get('threads')}"
    )
    if params.get("genome"):
        cmd += f" --genome {shlex.quote(str(params['genome']))}"
    if params.get("gtf"):
        cmd += f" --gtf {shlex.quote(str(params['gtf']))}"
    if params.get("de_result"):
        cmd += f" --de-result {shlex.quote(str(params['de_result']))}"
    if params.get("consensus_only"):
        cmd += " --consensus-only"
    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["pandas", "numpy", "matplotlib"])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            f"{SKILL_NAME} v{SKILL_VERSION} — Bulk ChIP-seq peak→gene genomic "
            "annotation (HOMER annotatePeaks.pl / GTF bedtools-closest)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", dest="prev_result", default=None,
                     help="result.json from bulkchip-peak-calling (Step 3) or "
                          "bulkchip-DA (Step 4). Auto-detected from --wd's sibling "
                          "peak_calling/result.json if omitted.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too).")

    opt = p.add_argument_group("optional")
    opt.add_argument("--peak-subset", default="consensus", dest="peak_subset",
                     choices=["consensus", "condition", "up", "down"],
                     help="Primary peak set to annotate (default consensus). With "
                          "the default, the DA up/down subsets are ALSO annotated "
                          "automatically when a bulkchip-DA result is reachable "
                          "(see --consensus-only). Pass up/down/condition to "
                          "annotate only that one subset.")
    opt.add_argument("--consensus-only", action="store_true", dest="consensus_only",
                     help="Annotate only the consensus peaks; do NOT auto-annotate "
                          "the DA up/down subsets even if a DA result is reachable.")
    opt.add_argument("--de-result", default=None, dest="de_result",
                     help="bulkchip-DA result.json (for the up/down subsets). "
                          "Auto-detected from the upstream chain or the sibling "
                          "DA/result.json when omitted.")
    opt.add_argument("--gtf", default=None,
                     help="Gene annotation GTF (overrides the one auto-detected "
                          "from upstream genome_files).")
    opt.add_argument("--tss-window", type=int, default=3000, dest="tss_window",
                     help="Distance (bp) from a TSS for a peak's nearest gene to "
                          "count as a target gene (default 3000).")
    opt.add_argument("--genome", default=None,
                     help="Genome name (e.g. hg38) used as the HOMER genome when "
                          "no GTF is available. Defaults to the upstream genome.")
    opt.add_argument("--threads", type=int, default=8)
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    elif args.wd:
        prev_result_path = Path(args.wd).parent / "peak_calling" / "result.json"
    else:
        parser.error("Provide --prev-result or --wd so the upstream result.json can be located.")
    if not prev_result_path.exists():
        parser.error(f"Upstream result.json not found: {prev_result_path}")

    project_dir = prev_result_path.resolve().parent.parent
    output_dir  = Path(args.wd) if args.wd else project_dir / "annotation"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    _print_step_plan()

    # ── Step 1: load upstream + decide which subsets to annotate ────────────
    prev_data = _load_json(prev_result_path)
    da_path = _find_da_result(prev_result_path, prev_data, args.de_result)

    if args.peak_subset in ("up", "down", "condition"):
        subsets = [args.peak_subset]                 # explicit single-subset request
    else:                                            # consensus (default or explicit)
        subsets = ["consensus"]
        if da_path and not args.consensus_only:
            subsets += ["up", "down"]                # auto-add DA peaks

    _step(1, f"loading upstream result + resolving subsets to annotate: "
             f"{', '.join(subsets)}"
             + (f"  (DA: {da_path})" if da_path and len(subsets) > 1 else ""))

    multi = len(subsets) > 1
    subset_results: list[dict[str, Any]] = []

    _step(2, "genomic annotation per subset (HOMER annotatePeaks.pl / GTF bedtools-closest)")
    for sub in subsets:
        de_arg = str(da_path) if sub in ("up", "down") else args.de_result
        try:
            resolved = resolve_peak_set(prev_result_path, sub, de_arg, args.gtf)
        except SystemExit as exc:
            logger.warning("Skipping subset '%s': %s", sub, exc)
            continue
        peaks_bed = resolved["peaks_bed"]
        genome    = args.genome or resolved["genome"]
        gtf       = resolved["gtf"]
        if not peaks_bed.exists():
            logger.warning("Skipping subset '%s': resolved peak BED missing: %s", sub, peaks_bed)
            continue

        ann_dir = output_dir / ("annotation" if (sub == "consensus" or not multi)
                                else f"annotation_{sub}")
        logger.info("Annotating '%s' peaks: %s  (genome=%s, gtf=%s)",
                    sub, peaks_bed, genome or "none", gtf or "none")
        ann = annotate_peaks(
            peaks_bed, ann_dir,
            genome=genome, gtf=gtf,
            tss_window=args.tss_window, threads=args.threads,
        )
        params: dict[str, Any] = {
            "peak_subset":    sub,
            "tss_window":     args.tss_window,
            "genome":         genome,
            "gtf":            str(gtf) if gtf else None,
            "de_result":      str(da_path) if (da_path and multi) else args.de_result,
            "consensus_only": args.consensus_only,
            "threads":        args.threads,
        }
        subset_results.append({"subset": sub, "ann": ann, "params": params, "dir": ann_dir})

    if not subset_results:
        parser.error("No peak subset could be resolved/annotated — check the upstream result.json.")

    _step(3, "feature pies + TSS-distance plots + target-gene sets")

    # ── Step 4: outputs ─────────────────────────────────────────────────────
    _step(4, "writing report, reproducibility, and result.json")
    write_report(output_dir, subset_results, prev_result_path)
    write_reproducibility(output_dir, subset_results[0]["params"], prev_result_path)

    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        "`annotation/annotated_peaks.tsv` — consensus-peak feature category + nearest gene + TSS distance.\n"
        "`annotation_up/`, `annotation_down/` — same, for the DA gained/lost peaks (when a DA result is present).\n"
        "`annotation*/peak_annotation_pie.{png,pdf}` — feature-distribution donut per subset.\n"
        "`annotation*/peak_tss_distance.{png,pdf}` — distance-to-TSS histogram per subset.\n"
        "`result.json` — `annotation.target_genes` (consensus) feeds GO/KEGG enrichment; "
        "`annotations[]` carries every subset.\n"
        f"`{SKILL_NAME}.log` — full run log: narrative + every tool's stdout/stderr.\n"
        "\nNext: run bulkchip-enrichment on `annotation.target_genes`.\n"
    )

    lines = [
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:",
        f"  Subsets annotated: {', '.join(r['subset'] for r in subset_results)}",
    ]
    for r in subset_results:
        ann = r["ann"]
        nf = sum(ann.feature_counts.values())
        if ann.feature_counts:
            lines.append(
                f"  [{r['subset']}] {nf:,} peaks in {len(ann.feature_counts)} categories "
                f"→ {len(ann.target_genes):,} target genes"
            )
            for cat, n in sorted(ann.feature_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]:
                pct = f"{100 * n / nf:.1f}%" if nf else "0%"
                lines.append(f"      {cat}: {n:,} ({pct})")
        else:
            n_rows = _count_data_rows(ann.annotated_tsv)
            lines.append(
                f"  [{r['subset']}] {n_rows:,} peaks — NO feature/gene annotation: "
                "no GTF or installed HOMER genome found → 0 target genes"
            )
            lines.append("      provide a GTF (--gtf) or drop one in the reference dir, then re-run")
    lines += [
        f"  Report:  {output_dir / 'report.md'}",
        "",
        "  Next → bulkchip-enrichment — GO/KEGG over-representation on the target genes",
        "",
    ]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
