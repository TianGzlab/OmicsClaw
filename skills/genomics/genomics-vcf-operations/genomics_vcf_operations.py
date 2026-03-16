#!/usr/bin/env python3
"""Genomics VCF Operations — VCF statistics, filtering, and manipulation.

Provides operations that mirror bcftools functionality:
- stats: variant counts, Ti/Tv, per-chromosome breakdown
- filter: quality / depth / region filtering
- merge: combine multiple VCF files

Handles multi-allelic sites, proper SNP/indel/MNP/complex classification
per VCF 4.2 spec.

Usage:
    python genomics_vcf_operations.py --input <file.vcf> --output <dir>
    python genomics_vcf_operations.py --demo --output <dir>
    python genomics_vcf_operations.py --input <file.vcf> --output <dir> \
        --min-qual 30 --min-dp 10
"""

from __future__ import annotations

import argparse
import logging
import sys
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

SKILL_NAME = "genomics-vcf-operations"
SKILL_VERSION = "0.2.0"

# Transition pairs (purine<->purine or pyrimidine<->pyrimidine)
TRANSITIONS = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}


# ---------------------------------------------------------------------------
# VCF Parsing
# ---------------------------------------------------------------------------

def classify_variant(ref: str, alt: str) -> str:
    """Classify variant type per VCF spec conventions.

    - SNP: single-nucleotide polymorphism (len(ref)==len(alt)==1)
    - MNP: multi-nucleotide polymorphism (len(ref)==len(alt)>1)
    - INS: insertion (ref is prefix of alt, len(ref)<len(alt))
    - DEL: deletion (alt is prefix of ref, len(ref)>len(alt))
    - COMPLEX: anything else (e.g., simultaneous sub + indel)
    """
    if len(ref) == 1 and len(alt) == 1:
        return "SNP"
    elif len(ref) == len(alt):
        return "MNP"
    elif len(ref) < len(alt) and alt.startswith(ref):
        return "INS"
    elif len(ref) > len(alt) and ref.startswith(alt):
        return "DEL"
    else:
        return "COMPLEX"


def _parse_info_field(info_str: str) -> dict[str, str]:
    """Parse a VCF INFO field into a key-value dictionary."""
    result = {}
    if info_str == "." or not info_str:
        return result
    for entry in info_str.split(";"):
        if "=" in entry:
            k, v = entry.split("=", 1)
            result[k] = v
        else:
            result[entry] = "true"  # flag fields
    return result


def parse_vcf(vcf_path: Path, min_qual: float = 0.0, min_dp: int = 0) -> tuple[list[dict], list[str]]:
    """Parse a VCF file, returning records and header lines.

    Handles multi-allelic sites by processing each ALT allele independently.
    Applies optional QUAL and DP filters.
    """
    header_lines = []
    records = []

    with open(vcf_path, "r") as f:
        for line in f:
            if line.startswith("##"):
                header_lines.append(line.rstrip())
                continue
            if line.startswith("#CHROM"):
                header_lines.append(line.rstrip())
                continue

            fields = line.strip().split("\t")
            if len(fields) < 8:
                continue

            chrom = fields[0]
            pos = int(fields[1])
            var_id = fields[2]
            ref = fields[3]
            alts = fields[4]
            qual_str = fields[5]
            filt = fields[6]
            info_str = fields[7]

            qual = float(qual_str) if qual_str != "." else 0

            # Quality filter
            if qual < min_qual:
                continue

            # Depth filter from INFO
            info = _parse_info_field(info_str)
            dp = int(info.get("DP", "0"))
            if dp < min_dp:
                continue

            # Handle multi-allelic sites
            for alt in alts.split(","):
                alt = alt.strip()
                vtype = classify_variant(ref, alt)
                records.append({
                    "chrom": chrom,
                    "pos": pos,
                    "id": var_id,
                    "ref": ref,
                    "alt": alt,
                    "qual": qual,
                    "filter": filt,
                    "dp": dp,
                    "type": vtype,
                })

    return records, header_lines


def compute_vcf_stats(records: list[dict]) -> dict:
    """Compute comprehensive VCF statistics from parsed records."""
    if not records:
        return {"n_variants": 0, "n_snps": 0, "n_indels": 0}

    n_total = len(records)
    type_counts = {}
    for r in records:
        vtype = r["type"]
        type_counts[vtype] = type_counts.get(vtype, 0) + 1

    n_snps = type_counts.get("SNP", 0)
    n_ins = type_counts.get("INS", 0)
    n_del = type_counts.get("DEL", 0)
    n_mnp = type_counts.get("MNP", 0)
    n_complex = type_counts.get("COMPLEX", 0)

    # Ti/Tv ratio for SNPs
    n_ti = 0
    n_tv = 0
    for r in records:
        if r["type"] == "SNP":
            if (r["ref"].upper(), r["alt"].upper()) in TRANSITIONS:
                n_ti += 1
            else:
                n_tv += 1
    ti_tv = round(n_ti / n_tv, 2) if n_tv > 0 else float("inf")

    # Per-chromosome counts
    chrom_counts: dict[str, int] = {}
    for r in records:
        c = r["chrom"]
        chrom_counts[c] = chrom_counts.get(c, 0) + 1

    # PASS / filtered breakdown
    n_pass = sum(1 for r in records if r["filter"] == "PASS")

    # Quality distribution
    quals = [r["qual"] for r in records if r["qual"] > 0]
    depths = [r["dp"] for r in records if r["dp"] > 0]

    return {
        "n_variants": n_total,
        "n_pass": n_pass,
        "n_filtered": n_total - n_pass,
        "n_snps": n_snps,
        "n_insertions": n_ins,
        "n_deletions": n_del,
        "n_mnps": n_mnp,
        "n_complex": n_complex,
        "n_indels": n_ins + n_del,
        "snp_to_indel_ratio": round(n_snps / (n_ins + n_del), 2) if (n_ins + n_del) > 0 else float("inf"),
        "ti_tv_ratio": ti_tv,
        "n_transitions": n_ti,
        "n_transversions": n_tv,
        "mean_qual": round(float(np.mean(quals)), 1) if quals else 0,
        "median_qual": round(float(np.median(quals)), 1) if quals else 0,
        "mean_dp": round(float(np.mean(depths)), 1) if depths else 0,
        "n_chromosomes": len(chrom_counts),
        "variants_per_chrom": chrom_counts,
    }


# ---------------------------------------------------------------------------
# Demo VCF Generation
# ---------------------------------------------------------------------------

def generate_demo_vcf(output_path: Path) -> None:
    """Generate a realistic demo VCF file with diverse variant types."""
    vcf_content = """##fileformat=VCFv4.2
##source=OmicsClaw-vcf-operations-demo
##contig=<ID=chr1,length=248956422>
##contig=<ID=chr2,length=242193529>
##contig=<ID=chr3,length=198295559>
##INFO=<ID=DP,Number=1,Type=Integer,Description="Total Depth">
##INFO=<ID=AF,Number=A,Type=Float,Description="Allele Frequency">
##FILTER=<ID=LowQual,Description="Low quality">
##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">
##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Read Depth">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE1
chr1\t10045\t.\tA\tG\t45\tPASS\tDP=52;AF=0.45\tGT:DP\t0/1:52
chr1\t20132\t.\tC\tT\t60\tPASS\tDP=65;AF=0.51\tGT:DP\t0/1:65
chr1\t30250\t.\tG\tA\t35\tPASS\tDP=40;AF=0.48\tGT:DP\t0/1:40
chr1\t40100\t.\tT\tC\t55\tPASS\tDP=58;AF=0.53\tGT:DP\t1/1:58
chr1\t50400\t.\tA\tT\t40\tPASS\tDP=45;AF=0.42\tGT:DP\t0/1:45
chr1\t60800\t.\tG\tC\t38\tPASS\tDP=42;AF=0.38\tGT:DP\t0/1:42
chr1\t70200\t.\tAT\tA\t25\tPASS\tDP=30;AF=0.35\tGT:DP\t0/1:30
chr1\t80500\t.\tC\tCGA\t28\tPASS\tDP=35;AF=0.40\tGT:DP\t0/1:35
chr1\t90100\t.\tATG\tA\t32\tPASS\tDP=38;AF=0.43\tGT:DP\t0/1:38
chr2\t15000\t.\tA\tG,T\t50\tPASS\tDP=55;AF=0.30,0.20\tGT:DP\t1/2:55
chr2\t25000\t.\tTA\tGC\t42\tPASS\tDP=48;AF=0.45\tGT:DP\t0/1:48
chr3\t35000\t.\tG\tA\t15\tLowQual\tDP=8;AF=0.25\tGT:DP\t0/1:8
chr3\t45000\t.\tC\tT\t52\tPASS\tDP=60;AF=0.50\tGT:DP\t1/1:60
"""
    with open(output_path, "w") as f:
        f.write(vcf_content)
    logger.info(f"Generated demo VCF: {output_path}")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write VCF operations report."""
    header = generate_report_header(
        title="VCF Operations Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Variants": f"{stats['n_variants']:,}"},
    )

    body_lines = [
        "## Variant Summary\n",
        f"- **Total variants**: {stats['n_variants']:,}",
        f"- **PASS**: {stats['n_pass']:,}",
        f"- **Filtered**: {stats['n_filtered']:,}",
        "",
        "### Variant Type Breakdown\n",
        f"- **SNPs**: {stats['n_snps']:,}",
        f"- **Insertions**: {stats['n_insertions']:,}",
        f"- **Deletions**: {stats['n_deletions']:,}",
        f"- **MNPs**: {stats['n_mnps']:,}",
        f"- **Complex**: {stats['n_complex']:,}",
        "",
        "### Quality Metrics\n",
        f"- **Ti/Tv ratio**: {stats['ti_tv_ratio']}",
        f"- **SNP/Indel ratio**: {stats['snp_to_indel_ratio']}",
        f"- **Mean QUAL**: {stats['mean_qual']}",
        f"- **Mean DP**: {stats['mean_dp']}",
        "",
    ]

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="VCF Operations")
    parser.add_argument("--input", dest="input_path", help="Input VCF file")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with demo data")
    parser.add_argument("--min-qual", type=float, default=0.0, help="Minimum QUAL filter")
    parser.add_argument("--min-dp", type=int, default=0, help="Minimum depth filter")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get VCF file
    if args.demo:
        vcf_path = output_dir / "demo.vcf"
        generate_demo_vcf(vcf_path)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        vcf_path = Path(args.input_path)
        if not vcf_path.exists():
            raise FileNotFoundError(f"Input file not found: {vcf_path}")
        input_file = args.input_path

    # Parse and analyse
    records, header_lines = parse_vcf(vcf_path, min_qual=args.min_qual, min_dp=args.min_dp)
    stats = compute_vcf_stats(records)
    logger.info(f"VCF stats: {stats['n_variants']} variants, Ti/Tv={stats['ti_tv_ratio']}")

    # Save tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    if records:
        pd.DataFrame(records).to_csv(tables_dir / "variants.csv", index=False)

    # Write filtered VCF
    if args.min_qual > 0 or args.min_dp > 0:
        filtered_vcf = output_dir / "filtered.vcf"
        with open(filtered_vcf, "w") as fh:
            for hl in header_lines:
                fh.write(hl + "\n")
            for r in records:
                fh.write(f"{r['chrom']}\t{r['pos']}\t{r['id']}\t{r['ref']}\t{r['alt']}\t"
                         f"{r['qual']}\t{r['filter']}\tDP={r['dp']}\tGT\t.\n")
        logger.info(f"Wrote filtered VCF: {filtered_vcf}")

    # Report
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
    print(f"VCF analysis complete: {stats['n_variants']} variants "
          f"({stats['n_snps']} SNPs, {stats['n_indels']} indels, "
          f"Ti/Tv={stats['ti_tv_ratio']})")


if __name__ == "__main__":
    main()
