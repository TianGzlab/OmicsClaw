#!/usr/bin/env python3
"""Regenerate hardcoded skill counts inside ``skills/orchestrator/SKILL.md``.

The orchestrator SKILL.md contains three passages whose numbers must stay in
sync with the real registry:

* ``<!-- ORCH-INTRO-START -->`` ... ``<!-- ORCH-INTRO-END -->`` — the
  "Without it" bullet with the total skill count.
* ``<!-- ORCH-DOMAINS-START -->`` ... ``<!-- ORCH-DOMAINS-END -->`` — the
  supported-domains list.
* ``<!-- ORCH-FOOTER-START -->`` ... ``<!-- ORCH-FOOTER-END -->`` — the
  closing "All N skills across M domains" line.

Usage::

    python scripts/generate_orchestrator_counts.py            # preview
    python scripts/generate_orchestrator_counts.py --apply    # rewrite file
    python scripts/generate_orchestrator_counts.py --check    # exit 1 on drift
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.core.registry import OmicsRegistry  # noqa: E402

SKILL_MD = _ROOT / "skills" / "orchestrator" / "SKILL.md"

MARKERS = {
    "intro": ("<!-- ORCH-INTRO-START -->", "<!-- ORCH-INTRO-END -->"),
    "domains": ("<!-- ORCH-DOMAINS-START -->", "<!-- ORCH-DOMAINS-END -->"),
    "footer": ("<!-- ORCH-FOOTER-START -->", "<!-- ORCH-FOOTER-END -->"),
}

# Display order + human label + typical file extensions for the domain list.
DOMAIN_DISPLAY = [
    ("spatial", "Spatial Transcriptomics", "`.h5ad`, `.h5`, `.zarr`, `.loom`"),
    ("singlecell", "Single-Cell Omics", "`.h5ad`, `.h5`, `.loom`, `.mtx`"),
    ("genomics", "Genomics", "`.vcf`, `.bam`, `.cram`, `.fasta`, `.fastq`, `.bed`"),
    ("proteomics", "Proteomics", "`.mzml`, `.mzxml`, `.csv`"),
    ("metabolomics", "Metabolomics", "`.mzml`, `.cdf`, `.csv`"),
    ("bulkrna", "Bulk RNA-seq", "`.csv`, `.tsv`, `.fastq`"),
    ("orchestrator", "Orchestrator", "`*` (all types)"),
    ("literature", "Literature", "`PDF`, `DOI`, `PubMed`, `URL`, text"),
]


def _count_skills_per_domain() -> dict[str, int]:
    reg = OmicsRegistry()
    reg.load_all()
    counts: dict[str, int] = {}
    for alias, info in reg.skills.items():
        if info.get("alias") != alias:  # skip legacy alias duplicates
            continue
        domain = info.get("domain") or "unknown"
        counts[domain] = counts.get(domain, 0) + 1
    return counts


def render_blocks() -> dict[str, str]:
    counts = _count_skills_per_domain()
    total = sum(counts.get(d, 0) for d, _, _ in DOMAIN_DISPLAY)
    n_domains = sum(1 for d, _, _ in DOMAIN_DISPLAY if counts.get(d, 0) > 0)

    # Intro block
    intro = (
        f"- **Without it**: Users must know exact skill names and CLI flags "
        f"across {total} skills in {n_domains} domains"
    )

    # Domains block
    lines = [f"OmicsClaw currently supports **{total} skills across {n_domains} domains**:", ""]
    idx = 1
    for key, label, exts in DOMAIN_DISPLAY:
        n = counts.get(key, 0)
        if n == 0:
            continue
        lines.append(f"{idx}. **{label}** ({n} skills) - {exts}")
        idx += 1
    domains_block = "\n".join(lines)

    # Footer block
    footer = (
        f"- All {total} skills across {n_domains} domains are accessible through "
        f"this single interface"
    )

    return {"intro": intro, "domains": domains_block, "footer": footer}


def _replace_between(text: str, start: str, end: str, new_body: str) -> str:
    """Replace content between two markers; markers themselves are kept."""
    s = text.find(start)
    e = text.find(end)
    if s == -1 or e == -1 or e < s:
        raise RuntimeError(f"Markers not found: {start} .. {end}")
    return text[: s + len(start)] + "\n" + new_body + "\n" + text[e:]


def rewrite(current: str, blocks: dict[str, str]) -> str:
    out = current
    for key, body in blocks.items():
        start, end = MARKERS[key]
        out = _replace_between(out, start, end, body)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate orchestrator SKILL.md skill counts")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Rewrite the file in place")
    group.add_argument("--check", action="store_true", help="Exit 1 if file is out of date")
    args = parser.parse_args()

    if not SKILL_MD.exists():
        print(f"ERROR: {SKILL_MD} not found", file=sys.stderr)
        return 1

    current = SKILL_MD.read_text(encoding="utf-8")
    blocks = render_blocks()
    expected = rewrite(current, blocks)

    if args.check:
        if current != expected:
            print(
                "ERROR: skills/orchestrator/SKILL.md is out of date.\n"
                "       Run: python scripts/generate_orchestrator_counts.py --apply",
                file=sys.stderr,
            )
            return 1
        print("skills/orchestrator/SKILL.md is up to date.")
        return 0

    if args.apply:
        if current == expected:
            print("skills/orchestrator/SKILL.md already up to date.")
            return 0
        SKILL_MD.write_text(expected, encoding="utf-8")
        print(f"Updated {SKILL_MD}")
        return 0

    # Preview mode
    for key in ("intro", "domains", "footer"):
        start, end = MARKERS[key]
        print(f"--- {key} ({start} .. {end}) ---")
        print(blocks[key])
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
