#!/usr/bin/env python3
"""bulkrna-read-alignment — RNA-seq read alignment/quantification statistics.

Parses STAR/HISAT2/Salmon mapping summaries. Gene-body coverage is only
simulated in the demo; input logs do not supply coverage or strandedness.

Usage:
    python bulkrna_read_alignment.py --input Log.final.out --output results/
    python bulkrna_read_alignment.py --demo --output /tmp/alignment_demo
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))
from skills._sdk.report import (
    generate_report_header,
    generate_report_footer,
)
from skills._sdk.result import write_result_json

logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-read-alignment"
SKILL_VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def write_report(output_dir: Path, stats: dict, quality: dict, params: dict):
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    header = generate_report_header(
        title="Bulk RNA-seq Alignment Report",
        skill_name=SKILL_NAME,
    )

    emoji = {"EXCELLENT": "🟢", "GOOD": "🟢", "WARNING": "🟡", "FAIL": "🔴"}
    if 'mapped' in stats:
        mapping_lines = [f"- Mapped: {stats['mapped']:,} ({stats['mapped_rate']:.1f}%)",
                         '- Unique versus multi-mapping is not available from Salmon meta_info.']
    else:
        mapping_lines = [f"- Uniquely mapped: {stats['uniquely_mapped']:,} ({stats['unique_rate']:.1f}%)",
                         f"- Multi-mapped: {stats['multi_mapped']:,} ({stats['multi_rate']:.1f}%)"]
    body_lines = [
        f"## Quality Assessment: {emoji.get(quality['overall'], '')} {quality['overall']}\n",
        "## Alignment Statistics\n",
        f"- **Aligner**: {stats['aligner']}",
        f"- **Total reads**: {stats['total_reads']:,}",
        *mapping_lines,
        f"- **Unmapped**: {stats['unmapped']:,} ({stats['unmapped_rate']:.1f}%)",
        "",
        "### Quality Checks\n",
        "| Check | Status |",
        "|-------|--------|",
    ]
    for check, status in quality["checks"].items():
        body_lines.append(f"| {check} | {status} |")
    if stats['aligner'] == 'HISAT2':
        body_lines.append('\nHISAT2 counts concordant pairs. The residual labeled unmapped also includes discordant and unpaired mappings.')

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(
        "\n".join([header, "\n".join(body_lines), footer]), encoding="utf-8")

    result_metrics = {k: v for k, v in stats.items()
                      if not isinstance(v, (np.ndarray,))}
    result_metrics["quality"] = quality
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, result_metrics, params)

    pd.DataFrame([stats]).to_csv(tables_dir / "alignment_stats.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    (repro_dir / "commands.sh").write_text(
        f"#!/usr/bin/env bash\npython bulkrna_read_alignment.py "
        f"--input {params.get('input', '<INPUT>')} "
        f"--output {params.get('output', '<OUTPUT>')}\n", encoding="utf-8")


def main():
    from skills._sdk.notebook import load_skill
    library = load_skill(SKILL_NAME)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=f"{SKILL_NAME} v{SKILL_VERSION}")
    ap.add_argument("--input", type=str, help="Alignment log file")
    ap.add_argument("--output", type=str, required=True)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--method", type=str, default="star",
                    choices=["star", "hisat2", "salmon"],
                    help="Log format; select explicitly (default: star)")
    args = ap.parse_args()

    output_dir = Path(args.output)
    params = {"output": str(output_dir), "method": args.method}

    if args.demo:
        result = library.summarize(library.demo_data())
        params["input"] = "demo"
    else:
        if not args.input:
            ap.error("--input required (or use --demo)")
        input_path = Path(args.input)
        params["input"] = str(input_path)

        result = library.summarize(library.read_log(input_path), method=args.method)

    diagnostics = library.run_info(result, keep=False)
    quality = diagnostics['quality']
    stats = result.iloc[0].to_dict()
    fig_dir = output_dir / 'figures'
    fig_dir.mkdir(parents=True, exist_ok=True)
    library.mapping_figure(result).savefig(fig_dir / 'mapping_summary.png', dpi=150)
    library.composition_figure(result).savefig(fig_dir / 'alignment_composition.png', dpi=150)
    if args.demo:
        library.coverage_figure(library.demo_coverage()).savefig(fig_dir / 'gene_body_coverage.png', dpi=150)
    params['diagnostics'] = diagnostics
    write_report(output_dir, stats, quality, params)
    logger.info("✓ Alignment QC complete → %s (overall: %s)", output_dir, quality["overall"])


if __name__ == "__main__":
    main()
