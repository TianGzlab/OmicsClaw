#!/usr/bin/env python3
"""Genomics variant-calling: summarize existing local files.\n\nThe CLI owns demo generation, reports and file output. Its function library\ncontains the computations. No external analysis tool is started."""

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

SKILL_NAME = "genomics-variant-calling"
SKILL_VERSION = "0.5.0"

# Transition / Transversion classification
# Transitions: A<->G, C<->T (purine<->purine or pyrimidine<->pyrimidine)
# Transversions: all other substitutions
TRANSITIONS = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}


# ---------------------------------------------------------------------------
# Demo variant generation
# ---------------------------------------------------------------------------

def generate_demo_variants(output_dir: Path, n_variants: int = 500) -> Path:
    """Generate a realistic demo VCF file with variants across chromosomes.

    Generates variants with realistic characteristics:
    - Ti/Tv ratio ~2.0 (matching human genome expectation)
    - SNP/indel ratio ~10:1
    - QUAL scores from realistic distribution
    - Heterozygous/homozygous ratio ~1.5:1
    """
    rng = random.Random(42)
    chroms = [f"chr{i}" for i in range(1, 23)] + ["chrX"]
    bases = "ACGT"

    vcf_path = output_dir / "demo_variants.vcf"

    with open(vcf_path, "w") as fh:
        # VCF header (v4.2)
        fh.write("##fileformat=VCFv4.2\n")
        fh.write(f"##source=OmicsClaw-{SKILL_NAME}-{SKILL_VERSION}\n")
        for c in chroms:
            fh.write(f"##contig=<ID={c},length=250000000>\n")
        fh.write('##INFO=<ID=DP,Number=1,Type=Integer,Description="Total Depth">\n')
        fh.write('##INFO=<ID=AF,Number=A,Type=Float,Description="Allele Frequency">\n')
        fh.write('##INFO=<ID=TYPE,Number=1,Type=String,Description="Variant Type">\n')
        fh.write('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n')
        fh.write('##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Read Depth">\n')
        fh.write('##FORMAT=<ID=GQ,Number=1,Type=Integer,Description="Genotype Quality">\n')
        fh.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE1\n")

        positions = sorted(rng.sample(range(1000, 249_000_000), n_variants))

        for i, pos in enumerate(positions):
            chrom = chroms[i % len(chroms)]

            # 90% SNPs, 10% indels — realistic ratio
            if rng.random() < 0.90:
                ref = rng.choice(bases)
                # Ti/Tv ~2.0: transitions are 2x as likely as transversions
                if rng.random() < 0.67:  # ~2/3 transitions for Ti/Tv=2
                    ti_map = {"A": "G", "G": "A", "C": "T", "T": "C"}
                    alt = ti_map[ref]
                else:
                    tv_options = [b for b in bases if b != ref and (ref, b) not in TRANSITIONS]
                    alt = rng.choice(tv_options)
                vtype = "SNP"
            else:
                # Indels
                if rng.random() < 0.5:
                    # Insertion
                    ref = rng.choice(bases)
                    ins_len = rng.randint(1, 10)
                    alt = ref + "".join(rng.choice(bases) for _ in range(ins_len))
                    vtype = "INS"
                else:
                    # Deletion
                    del_len = rng.randint(1, 10)
                    ref = "".join(rng.choice(bases) for _ in range(del_len + 1))
                    alt = ref[0]
                    vtype = "DEL"

            dp = rng.randint(15, 100)
            qual = rng.randint(20, 200)
            af = round(rng.uniform(0.2, 1.0), 3)
            gt = rng.choices(["0/1", "1/1"], weights=[60, 40])[0]
            gq = rng.randint(20, 99)

            info = f"DP={dp};AF={af};TYPE={vtype}"
            fmt = "GT:DP:GQ"
            sample = f"{gt}:{dp}:{gq}"
            filt = "PASS" if qual >= 30 else "LowQual"

            fh.write(f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t{qual}\t{filt}\t{info}\t{fmt}\t{sample}\n")

    logger.info(f"Generated demo VCF with {n_variants} variants: {vcf_path}")
    return vcf_path


# ---------------------------------------------------------------------------
# VCF analysis


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write variant calling report."""
    header = generate_report_header(
        title="Genomics Variant Calling Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Variants": f"{stats['n_variants']:,}"},
    )

    body_lines = [
        "## Variant Summary\n",
        f"- **Total variants**: {stats['n_variants']:,}",
        f"- **PASS variants**: {stats['n_pass']:,}",
        "",
        "### Variant Types\n",
        f"- **SNPs**: {stats['n_snps']:,}",
        f"- **Insertions**: {stats['n_insertions']:,}",
        f"- **Deletions**: {stats['n_deletions']:,}",
        f"- **MNPs**: {stats['n_mnps']:,}",
        f"- **Complex**: {stats['n_complex']:,}",
        "",
        "### Quality Metrics\n",
        f"- **Ti/Tv ratio**: {stats['ti_tv_ratio']:.2f}",
        f"- **Mean QUAL**: {stats['mean_qual']:.1f}",
        f"- **Median QUAL**: {stats['median_qual']:.1f}",
        "",
        "## Quality Assessment\n",
    ]

    # Ti/Tv ratio assessment (expected ~2.0-2.1 for WGS, ~2.8-3.3 for WES)
    if 1.8 <= stats["ti_tv_ratio"] <= 3.5:
        body_lines.append(f"✅ **Ti/Tv ratio** ({stats['ti_tv_ratio']:.2f}) within expected range\n")
    else:
        body_lines.append(f"⚠️ **Ti/Tv ratio** ({stats['ti_tv_ratio']:.2f}) outside expected range "
                          "(1.8–3.5) — possible quality concern\n")

    body_lines.append("")
    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Genomics Variant Calling")
    parser.add_argument("--input", dest="input_path", help="Input VCF or BAM file")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with synthetic demo data")
    parser.add_argument("--n-variants", type=int, default=500, help="Number of demo variants")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        vcf_path = generate_demo_variants(output_dir, n_variants=args.n_variants)
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
    result_df = api.analyze(api.read_records(vcf_path))
    stats = api.run_info(result_df, keep=False)["summary"]

    # Save tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    result_df.to_csv(tables_dir / "variants.csv", index=False)

    # Per-chromosome summary
    if "variants_per_chrom" in stats:
        chrom_df = pd.DataFrame(
            sorted(stats["variants_per_chrom"].items()),
            columns=["chrom", "n_variants"],
        )
        chrom_df.to_csv(tables_dir / "variants_per_chrom.csv", index=False)

    # Remove non-serializable items for JSON
    summary = {k: v for k, v in stats.items() if k != "variants_per_chrom"}

    write_report(output_dir, stats, input_file)
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary,
        data={"variants_per_chrom": stats.get("variants_per_chrom", {})},
    )

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Variant calling complete: {stats['n_variants']:,} variants "
          f"({stats['n_snps']:,} SNPs, Ti/Tv={stats['ti_tv_ratio']:.2f})")


if __name__ == "__main__":
    main()
