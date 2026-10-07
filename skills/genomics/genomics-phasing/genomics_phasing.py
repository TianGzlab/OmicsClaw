#!/usr/bin/env python3
"""Genomics phasing: summarize existing local files.\n\nThe CLI owns demo generation, reports and file output. Its function library\ncontains the computations. No external analysis tool is started."""

from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

import pandas as pd

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.report import (
    generate_report_footer,
    generate_report_header,
)
from skills._sdk.result import write_result_json

logger = logging.getLogger(__name__)

SKILL_NAME = "genomics-phasing"
SKILL_VERSION = "0.5.0"


# ---------------------------------------------------------------------------
# Phase Block Analysis


# ---------------------------------------------------------------------------
# Demo Data
# ---------------------------------------------------------------------------

def generate_demo_phased_vcf(output_dir: Path, n_variants: int = 2000) -> Path:
    """Generate a realistic phased VCF for demo purposes.

    Simulates WhatsHap-style output with:
    - Phased and unphased heterozygous variants
    - Phase blocks of varying sizes (reflecting long-read phasing)
    - PS (Phase Set) field indicating phase block membership
    """
    rng = random.Random(42)
    bases = "ACGT"
    chroms = [f"chr{i}" for i in range(1, 23)]

    vcf_path = output_dir / "demo_phased.vcf"

    with open(vcf_path, "w") as fh:
        # Header
        fh.write("##fileformat=VCFv4.2\n")
        fh.write(f"##source=OmicsClaw-{SKILL_NAME}-{SKILL_VERSION}\n")
        for c in chroms:
            fh.write(f"##contig=<ID={c},length=250000000>\n")
        fh.write('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n')
        fh.write('##FORMAT=<ID=PS,Number=1,Type=Integer,Description="Phase Set">\n')
        fh.write('##FORMAT=<ID=GQ,Number=1,Type=Integer,Description="Genotype Quality">\n')
        fh.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE1\n")

        # Generate variants per chromosome
        variants_per_chrom = n_variants // len(chroms)

        for chrom in chroms:
            positions = sorted(rng.sample(range(10000, 249_000_000), variants_per_chrom))

            # Create phase blocks (varying sizes, some gaps)
            current_ps = positions[0]
            block_remaining = rng.randint(10, 200)  # variants in current block

            for pos in positions:
                ref = rng.choice(bases)
                alt = rng.choice([b for b in bases if b != ref])
                qual = rng.randint(20, 99)
                gq = rng.randint(20, 99)

                # ~85% of het variants are phased (typical for long-read phasing)
                is_phased = rng.random() < 0.85

                if block_remaining <= 0:
                    # Start new phase block
                    current_ps = pos
                    block_remaining = rng.randint(10, 200)

                if is_phased:
                    gt = rng.choice(["0|1", "1|0"])
                    sample = f"{gt}:{current_ps}:{gq}"
                else:
                    gt = "0/1"
                    sample = f"{gt}:.:{gq}"

                fh.write(f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t{qual}\tPASS\t.\tGT:PS:GQ\t{sample}\n")
                block_remaining -= 1

    logger.info(f"Generated demo phased VCF with {n_variants} variants: {vcf_path}")
    return vcf_path


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write phasing report."""
    header = generate_report_header(
        title="Haplotype Phasing Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Variants": f"{stats['n_total_variants']:,}"},
    )

    body_lines = [
        "## Phasing Summary\n",
        f"- **Total variants**: {stats['n_total_variants']:,}",
        f"- **Heterozygous variants**: {stats['n_het_variants']:,}",
        f"- **Phased heterozygous**: {stats['n_phased_het']:,} ({stats['phased_fraction']:.1%})",
        f"- **Phase blocks**: {stats['n_phase_blocks']:,}",
        "",
        "## Phase Block Statistics\n",
        f"- **Phase block N50 (bp)**: {stats['phase_block_n50_bp']:,}",
        f"- **Phase block N50 (variants)**: {stats['phase_block_n50_variants']:,}",
        f"- **Longest block (bp)**: {stats['longest_block_bp']:,}",
        f"- **Longest block (variants)**: {stats['longest_block_variants']:,}",
        f"- **Mean block length**: {stats['mean_block_length_bp']:,} bp",
        f"- **Median block length**: {stats['median_block_length_bp']:,} bp",
        "",
        "## Quality Assessment\n",
    ]

    if stats["phased_fraction"] >= 0.80:
        body_lines.append(f"✅ **Phasing completeness**: PASS ({stats['phased_fraction']:.1%} phased)\n")
    elif stats["phased_fraction"] >= 0.50:
        body_lines.append(f"⚠️ **Phasing completeness**: WARN ({stats['phased_fraction']:.1%} phased)\n")
    else:
        body_lines.append(f"❌ **Phasing completeness**: FAIL ({stats['phased_fraction']:.1%} phased)\n")

    body_lines.append("")
    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Genomics Haplotype Phasing")
    parser.add_argument("--input", dest="input_path", help="Input phased VCF file")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with synthetic demo data")
    parser.add_argument("--n-variants", type=int, default=2000, help="Number of demo variants")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        vcf_path = generate_demo_phased_vcf(output_dir, n_variants=args.n_variants)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        vcf_path = Path(args.input_path)
        if not vcf_path.exists():
            raise FileNotFoundError(f"Input file not found: {vcf_path}")
        input_file = args.input_path

    from skills._sdk.notebook import load_skill
    api = load_skill(SKILL_NAME)
    result = api.analyze(api.read_records(vcf_path))
    stats = api.run_info(result, keep=False)["summary"]
    variants = result.to_dict("records")
    phase_blocks = {}
    for variant in variants:
        if variant["is_phased"] and variant["is_het"]:
            phase_blocks.setdefault(f'{variant["chrom"]}:{variant["phase_set"]}', []).append(variant)

    # Save tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    # This table is an unconditional Semantic artifact.  Preserve its schema
    # even when a valid input contains no variant records.
    pd.DataFrame(
        variants,
        columns=[
            "chrom",
            "pos",
            "ref",
            "alt",
            "gt",
            "is_phased",
            "is_het",
            "phase_set",
        ],
    ).to_csv(tables_dir / "phased_variants.csv", index=False)

    # Phase block summary
    block_records = []
    for block_key, block_vars in phase_blocks.items():
        if len(block_vars) < 2:
            continue
        positions = sorted(v["pos"] for v in block_vars)
        chrom = block_vars[0]["chrom"]
        block_records.append({
            "chrom": chrom,
            "start": positions[0],
            "end": positions[-1],
            "length_bp": positions[-1] - positions[0],
            "n_variants": len(block_vars),
            "phase_set": block_vars[0]["phase_set"],
        })
    if block_records:
        pd.DataFrame(block_records).to_csv(tables_dir / "phase_blocks.csv", index=False)

    write_report(output_dir, stats, input_file)
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=stats,
        data={},
    )

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Phasing complete: {stats['n_phased_het']:,}/{stats['n_het_variants']:,} "
          f"het variants phased ({stats['phased_fraction']:.1%}), "
          f"N50={stats['phase_block_n50_bp']:,} bp")


if __name__ == "__main__":
    main()
