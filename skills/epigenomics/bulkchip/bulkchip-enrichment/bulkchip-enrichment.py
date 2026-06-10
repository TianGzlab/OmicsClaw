#!/usr/bin/env python3
"""
bulkchip-enrichment.py — Bulk ChIP-seq GO/KEGG functional over-representation.

Implemented (gseapy-backed). See `_lib/enrichment.py`.

Scope
-----
  Functional enrichment on the ChIP target-gene set
    Target genes from `bulkchip-peak-annotation` result.json
    → gseapy.enrichr GO / KEGG over-representation (ORA)
    → one results CSV + dotplot PNG per gene-set library
    → enrichment_summary.csv

  Peak→gene annotation is a SEPARATE skill (bulkchip-peak-annotation); this
  skill ONLY consumes the produced gene list — it does not annotate peaks.

  Degrades gracefully: a missing gseapy, an Enrichr network failure, or an
  empty gene list yields empty (header-only) results rather than a crash.

Output layout
-------------
  <output>/
  ├── README.md, report.md, result.json
  ├── enrichment/                      (per-library GO/KEGG CSVs + dotplots)
  ├── enrichment_summary.csv
  └── reproducibility/

References
----------
  gseapy / Enrichr : https://github.com/zqfang/GSEApy

Quick-start
-----------
  python bulkchip-enrichment.py --wd <project>/enrichment \
      --gene-sets GO_Biological_Process,KEGG
      # organism is auto-derived from the upstream genome (e.g. sacCer3 → yeast);
      # pass --organism only to override for an unmapped genome.
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

SKILL_NAME    = "bulkchip-enrichment"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkchip/bulkchip-enrichment/bulkchip-enrichment.py"

from skills.epigenomics.bulkchip._lib.subenv_bootstrap import ensure_bulkchip_env  # noqa: E402
from skills.epigenomics.bulkchip._lib.progress import tty_write  # noqa: E402
ensure_bulkchip_env()

from skills.epigenomics.bulkchip._lib.enrichment import (  # noqa: E402
    run_functional_enrichment, write_enrichment_summary,
)
from omicsclaw.common.runlog import attach_run_log  # noqa: E402

_STEPS = [
    "Load bulkchip-peak-annotation result + extract target-gene set",
    "GO / KEGG over-representation (gseapy.enrichr) per library",
    "Write report, reproducibility, and result.json",
]

# Genome build → Enrichr organism. Enrichr supports a fixed organism set
# (human, mouse, yeast, fly, worm, fish); the genome build is mapped to it so
# the user specifies a genome (consistent with the rest of the suite) rather
# than a second organism vocabulary.
_GENOME_TO_ORGANISM: dict[str, str] = {
    "hg38": "human", "hg19": "human",
    "mm10": "mouse", "mm39": "mouse",
    "sacCer3": "yeast", "sacCer2": "yeast",
    "dm6": "fly", "dm3": "fly",
    "ce11": "worm", "ce10": "worm",
    "danRer11": "fish", "danRer10": "fish",
}


def _genome_to_organism(genome: str | None) -> str | None:
    """Map a genome build to its Enrichr organism (None if unmapped)."""
    if not genome:
        return None
    g = genome.strip()
    if g in _GENOME_TO_ORGANISM:
        return _GENOME_TO_ORGANISM[g]
    gl = g.lower()
    for prefix, org in (("hg", "human"), ("grch", "human"), ("mm", "mouse"),
                        ("grcm", "mouse"), ("saccer", "yeast"), ("dm", "fly"),
                        ("ce", "worm"), ("danrer", "fish"), ("grcz", "fish")):
        if gl.startswith(prefix):
            return org
    return None


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
# Load bulkchip-peak-annotation result.json → target-gene set
# ---------------------------------------------------------------------------

def _genes_from_annotated_tsv(tsv_path: Path) -> list[str]:
    """Fallback: parse the nearest-gene column from an annotated TSV.

    Looks for a column named like 'gene', 'nearest_gene', 'gene_name', or
    'symbol' (case-insensitive); returns its de-duplicated non-empty values.
    """
    import csv
    if not tsv_path.exists():
        return []
    with tsv_path.open(newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration:
            return []
        lower = [h.strip().lower() for h in header]
        gene_col = None
        for cand in ("nearest_gene", "gene_name", "gene", "symbol", "gene_symbol", "genename"):
            if cand in lower:
                gene_col = lower.index(cand)
                break
        if gene_col is None:
            return []
        seen: set[str] = set()
        genes: list[str] = []
        for row in reader:
            if gene_col < len(row):
                val = row[gene_col].strip()
                if val and val not in seen and val.upper() not in ("NA", "NAN", "."):
                    seen.add(val)
                    genes.append(val)
        return genes


def load_annotation_result(result_json: Path) -> dict[str, Any]:
    """Extract the target-gene set from a bulkchip-peak-annotation result.json.

    Prefers ``annotation.target_genes``; falls back to the nearest-gene column
    of ``annotation.annotated_tsv``. Hard-fails only if neither is available.
    """
    data = json.loads(result_json.read_text())
    ann = data.get("annotation", {}) or {}

    target_genes = [str(g) for g in (ann.get("target_genes") or []) if str(g)]
    source = "target_genes"

    if not target_genes:
        annotated_tsv = ann.get("annotated_tsv")
        if annotated_tsv and Path(annotated_tsv).exists():
            target_genes = _genes_from_annotated_tsv(Path(annotated_tsv))
            source = "annotated_tsv"
        if not target_genes:
            raise SystemExit(
                f"[{SKILL_NAME}] No target genes available: "
                f"'annotation.target_genes' is empty and "
                f"'annotation.annotated_tsv' "
                f"({annotated_tsv or 'missing'}) could not be parsed. "
                "Re-run bulkchip-peak-annotation first."
            )

    return {
        "data": data,
        "target_genes": target_genes,
        "gene_source": source,
        "genome": ann.get("genome", ""),
        "peak_subset": ann.get("peak_subset", ""),
        "n_target_genes": ann.get("n_target_genes", len(target_genes)),
    }


# ---------------------------------------------------------------------------
# Report + result.json + reproducibility
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    results: list,
    summary_csv: Path,
    params: dict[str, Any],
    ann_meta: dict[str, Any],
    prev_result_path: Path,
) -> None:
    lines: list[str] = [
        "# ChIP-seq Functional Enrichment Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "", "---", "",
        "## GO / KEGG over-representation on ChIP target genes", "",
        f"- **Target genes**: {len(ann_meta['target_genes'])} "
        f"(source: `{ann_meta['gene_source']}`, peak subset: "
        f"`{ann_meta.get('peak_subset') or 'n/a'}`)",
        f"- **Organism**: {params.get('organism')}  |  "
        f"**Gene-set libraries**: {', '.join(params.get('gene_sets', []))}",
        f"- **Adjusted-p cutoff**: {params.get('padj')}"
        + (f"  |  **Offline GMT**: `{params.get('gmt')}`" if params.get("gmt") else ""),
        "",
        "### Significant terms per library\n",
        "| Gene-set library | Significant terms | Results CSV | Dotplot |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.gene_set} | {r.n_terms:,} | `{Path(r.results_csv).name}` "
            f"| {'`' + Path(r.dotplot_png).name + '`' if r.dotplot_png else '—'} |"
        )

    total = sum(r.n_terms for r in results)
    if total == 0:
        lines += [
            "",
            "> **No significant terms.** This can mean a small/intergenic target-gene "
            "set, an organism/library mismatch, or that `gseapy`/Enrichr was "
            "unavailable (offline). Check the run log; supply an offline `--gmt` "
            "library for air-gapped environments.",
        ]

    lines += [
        "",
        f"**Summary table**: `{summary_csv.name}`",
        "",
        "## Next Steps", "",
        "- **bulkchip-motif-enrichment** — HOMER motif enrichment (sequence-level "
        "complement to the gene/pathway view).",
        "", "---", "",
        "> **Disclaimer**: OmicsClaw is a research and educational tool for "
        "multi-omics analysis. It is not a medical device and does not provide "
        "clinical diagnoses. Consult a domain expert before making decisions "
        "based on these results.",
    ]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    result: dict[str, Any] = {
        "skill":   SKILL_NAME,
        "version": SKILL_VERSION,
        "log":     str(output_dir / f"{SKILL_NAME}.log"),
        "params":  params,
        "enrichment": {
            "n_target_genes": len(ann_meta["target_genes"]),
            "gene_source":    ann_meta["gene_source"],
            "peak_subset":    ann_meta.get("peak_subset"),
            "organism":       params.get("organism"),
            "summary_csv":    str(summary_csv),
            "libraries": [
                {
                    "gene_set":    r.gene_set,
                    "results_csv": str(r.results_csv),
                    "dotplot_png": str(r.dotplot_png) if r.dotplot_png else None,
                    "n_terms":     r.n_terms,
                }
                for r in results
            ],
        },
        "prev_result": str(prev_result_path),
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


def write_reproducibility(output_dir: Path, params: dict[str, Any], prev_result_path: Path) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)
    cmd = (
        f"python {SCRIPT_REL} "
        f"--prev-result {shlex.quote(str(prev_result_path))} "
        f"--wd {shlex.quote(str(output_dir))} "
        f"--gene-sets {shlex.quote(','.join(params.get('gene_sets', [])))} "
        f"--organism {shlex.quote(str(params.get('organism')))} "  # resolved from --genome / upstream
        f"--padj {params.get('padj')} --threads {params.get('threads')}"
    )
    if params.get("gmt"):
        cmd += f" --gmt {shlex.quote(str(params['gmt']))}"
    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["pandas", "numpy", "gseapy", "matplotlib"])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            f"{SKILL_NAME} v{SKILL_VERSION} — Bulk ChIP-seq GO/KEGG functional "
            "over-representation on the target-gene set from bulkchip-peak-annotation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", dest="prev_result", default=None,
                     help="result.json from bulkchip-peak-annotation. "
                          "Auto-detected from --wd's sibling annotation/result.json if omitted.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too).")

    opt = p.add_argument_group("optional")
    opt.add_argument("--gene-sets", default="GO_Biological_Process,KEGG", dest="gene_sets",
                     help="Comma-separated gseapy/Enrichr gene-set libraries "
                          "(default GO_Biological_Process,KEGG).")
    opt.add_argument("--genome", default=None,
                     help="Genome build (e.g. sacCer3, hg38). Defaults to the upstream "
                          "genome; mapped to the Enrichr organism automatically.")
    opt.add_argument("--organism", default=None,
                     help="Override the Enrichr organism (human/mouse/yeast/fly/worm/fish). "
                          "Normally derived from the genome — only needed for builds "
                          "outside the genome→organism map.")
    opt.add_argument("--gmt", default=None,
                     help="Optional offline .gmt gene-set library (used for every library; "
                          "for air-gapped environments).")
    opt.add_argument("--padj", type=float, default=0.05,
                     help="Adjusted p-value cutoff for significant terms / dotplot (default 0.05).")
    opt.add_argument("--threads", type=int, default=4)
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    elif args.wd:
        prev_result_path = Path(args.wd).parent / "annotation" / "result.json"
    else:
        parser.error("Provide --prev-result or --wd so the bulkchip-peak-annotation "
                     "result.json can be located.")
    if not prev_result_path.exists():
        parser.error(f"bulkchip-peak-annotation result not found: {prev_result_path}")

    project_dir = prev_result_path.resolve().parent.parent
    output_dir  = Path(args.wd) if args.wd else project_dir / "enrichment"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    _print_step_plan()

    # ── Step 1: load annotation result + extract target-gene set ────────────
    _step(1, "loading bulkchip-peak-annotation result + extracting target genes")
    ann = load_annotation_result(prev_result_path)
    gene_sets = [s.strip() for s in args.gene_sets.split(",") if s.strip()]

    # Resolve organism: explicit --organism wins; else derive from the genome
    # (--genome override, else the upstream genome); else fall back to human.
    genome = args.genome or ann.get("genome") or ""
    organism = args.organism or _genome_to_organism(genome)
    if not organism:
        organism = "human"
        logger.warning("Could not derive Enrichr organism from genome %r — "
                        "defaulting to 'human'. Pass --organism to override.",
                        genome or "(unknown)")
    logger.info("Loaded %d target genes (source=%s); libraries=%s; genome=%s organism=%s",
                len(ann["target_genes"]), ann["gene_source"], gene_sets,
                genome or "(unknown)", organism)

    params: dict[str, Any] = {
        "gene_sets": gene_sets,
        "genome":    genome,
        "organism":  organism,
        "gmt":       args.gmt,
        "padj":      args.padj,
        "threads":   args.threads,
    }

    # ── Step 2: GO / KEGG over-representation ───────────────────────────────
    _step(2, f"GO/KEGG over-representation on {len(ann['target_genes'])} genes "
             f"across {len(gene_sets)} library/libraries")
    results = run_functional_enrichment(
        ann["target_genes"], output_dir / "enrichment",
        gene_sets=gene_sets, organism=organism,
        gmt=args.gmt, padj_cutoff=args.padj,
    )
    summary_csv = write_enrichment_summary(results, output_dir)

    # ── Step 3: outputs ─────────────────────────────────────────────────────
    _step(3, "writing report, reproducibility, and result.json")
    write_report(output_dir, results, summary_csv, params, ann, prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)

    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        "`enrichment/` — per-library GO/KEGG results CSV (term, overlap, adjusted "
        "p-value, genes) + dotplot PNG.\n"
        "`enrichment_summary.csv` — one row per gene-set library (significant-term counts).\n"
        f"`{SKILL_NAME}.log` — full run log: narrative + every tool's stdout/stderr.\n"
        "\nUpstream: bulkchip-peak-annotation (target-gene set).\n"
        "Next: bulkchip-motif-enrichment (sequence-level motif complement).\n"
    )

    total = sum(r.n_terms for r in results)
    lines = [
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:",
        f"  Target genes: {len(ann['target_genes'])} (source: {ann['gene_source']})",
    ]
    for r in results:
        status = "OK" if r.n_terms else "no significant terms"
        lines.append(f"  [{r.gene_set}] {status} — {r.n_terms} significant term(s) (padj ≤ {args.padj})")
        if r.top_term:
            padj = f"padj={r.top_padj:.2g}" if r.top_padj is not None else "padj=NA"
            lines.append(f"    Top: {r.top_term} ({padj})")
    lines += [
        f"  Significant terms (total): {total}",
        f"  Summary:  {summary_csv}",
        f"  Report:   {output_dir / 'report.md'}",
        "",
        "  Pipeline complete — this is the final downstream step of the bulkchip suite.",
        "  (Sibling analysis: bulkchip-motif-enrichment for sequence-level TF motifs.)",
        "",
    ]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
