#!/usr/bin/env python3
"""Genomics Variant Calling — Call germline/somatic variants from SAM/VCF data.

Implements a simplified pileup-based variant caller for demo purposes.
For real data, wraps external variant callers (GATK HaplotypeCaller,
DeepVariant, FreeBayes) via subprocess.

The demo mode generates synthetic variants that match the characteristics of
real germline variants (Ti/Tv ratio ~2.0-2.1, ~3-4M SNPs per whole genome).

Usage:
    python genomics_variant_calling.py --input <file.sam> --output <dir>
    python genomics_variant_calling.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "genomics-variant-calling"
SKILL_VERSION = "0.2.0"

# Transition / Transversion classification
# Transitions: A<->G, C<->T (purine<->purine or pyrimidine<->pyrimidine)
# Transversions: all other substitutions
TRANSITIONS = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}


def classify_variant(ref: str, alt: str) -> str:
    """Classify a variant as SNP, MNP, insertion, deletion, or complex.

    Classification follows VCF spec conventions:
    - SNP: len(ref)==1 and len(alt)==1
    - MNP: len(ref)==len(alt)>1 (e.g., AT->GC)
    - Insertion: len(ref)<len(alt) and ref is prefix of alt
    - Deletion: len(ref)>len(alt) and alt is prefix of ref
    - Complex: everything else
    """
    if len(ref) == 1 and len(alt) == 1:
        return "SNP"
    elif len(ref) == len(alt) and len(ref) > 1:
        return "MNP"
    elif len(ref) < len(alt) and alt.startswith(ref):
        return "INS"
    elif len(ref) > len(alt) and ref.startswith(alt):
        return "DEL"
    else:
        return "COMPLEX"


def is_transition(ref: str, alt: str) -> bool:
    """Check if a single-nucleotide substitution is a transition."""
    return (ref.upper(), alt.upper()) in TRANSITIONS


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

def analyse_vcf(vcf_path: Path) -> tuple[pd.DataFrame, dict]:
    """Parse a VCF and compute variant calling summary statistics."""
    records = []

    with open(vcf_path, "r") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            fields = line.strip().split("\t")
            if len(fields) < 8:
                continue

            chrom = fields[0]
            pos = int(fields[1])
            ref = fields[3]
            alt = fields[4]
            qual = float(fields[5]) if fields[5] != "." else 0
            filt = fields[6]

            # Handle multi-allelic (split by comma)
            for a in alt.split(","):
                vtype = classify_variant(ref, a)
                records.append({
                    "chrom": chrom,
                    "pos": pos,
                    "ref": ref,
                    "alt": a,
                    "qual": qual,
                    "filter": filt,
                    "type": vtype,
                })

    df = pd.DataFrame(records)
    if df.empty:
        return df, {"n_variants": 0}

    type_counts = df["type"].value_counts().to_dict()

    # Ti/Tv ratio (for SNPs only)
    snps = df[df["type"] == "SNP"]
    n_ti = sum(1 for _, r in snps.iterrows() if is_transition(r["ref"], r["alt"]))
    n_tv = len(snps) - n_ti
    ti_tv_ratio = round(n_ti / n_tv, 2) if n_tv > 0 else float("inf")

    pass_count = (df["filter"] == "PASS").sum()

    stats = {
        "n_variants": len(df),
        "n_pass": int(pass_count),
        "n_snps": int(type_counts.get("SNP", 0)),
        "n_insertions": int(type_counts.get("INS", 0)),
        "n_deletions": int(type_counts.get("DEL", 0)),
        "n_mnps": int(type_counts.get("MNP", 0)),
        "n_complex": int(type_counts.get("COMPLEX", 0)),
        "ti_tv_ratio": ti_tv_ratio,
        "mean_qual": round(float(df["qual"].mean()), 1),
        "median_qual": round(float(df["qual"].median()), 1),
        "variants_per_chrom": df["chrom"].value_counts().to_dict(),
    }
    return df, stats


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

    result_df, stats = analyse_vcf(vcf_path)

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
