#!/usr/bin/env python3
"""Genomics VCF Operations - Basic VCF file statistics and filtering.

Usage:
    python vcf_operations.py --input <file.vcf> --output <dir>
    python vcf_operations.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "vcf-operations"
SKILL_VERSION = "0.1.0"


def parse_vcf_basic(vcf_path):
    """Parse VCF file and return basic statistics."""
    n_variants = 0
    n_snps = 0
    n_indels = 0

    with open(vcf_path, 'r') as f:
        for line in f:
            if line.startswith('#'):
                continue
            n_variants += 1
            fields = line.strip().split('\t')
            if len(fields) >= 5:
                ref = fields[3]
                alt = fields[4]
                if len(ref) == 1 and len(alt) == 1:
                    n_snps += 1
                else:
                    n_indels += 1

    return {
        'n_variants': n_variants,
        'n_snps': n_snps,
        'n_indels': n_indels,
    }


def generate_demo_vcf(output_path):
    """Generate a minimal demo VCF file."""
    vcf_content = """##fileformat=VCFv4.2
##contig=<ID=chr1,length=248956422>
##INFO=<ID=DP,Number=1,Type=Integer,Description="Total Depth">
##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE1
chr1\t100\t.\tA\tG\t30\tPASS\tDP=50\tGT\t0/1
chr1\t200\t.\tC\tT\t40\tPASS\tDP=60\tGT\t1/1
chr1\t300\t.\tG\tA\t35\tPASS\tDP=55\tGT\t0/1
chr1\t400\t.\tAT\tA\t25\tPASS\tDP=45\tGT\t0/1
chr1\t500\t.\tC\tCG\t28\tPASS\tDP=48\tGT\t0/1
"""
    with open(output_path, 'w') as f:
        f.write(vcf_content)
    logger.info(f"Generated demo VCF: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="VCF Operations")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get VCF file
    if args.demo:
        vcf_path = output_dir / "demo.vcf"
        generate_demo_vcf(vcf_path)
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        vcf_path = Path(args.input_path)

    # Parse VCF
    stats = parse_vcf_basic(vcf_path)
    logger.info(f"VCF stats: {stats}")

    # Report
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"VCF analysis complete: {stats['n_variants']} variants ({stats['n_snps']} SNPs, {stats['n_indels']} indels)")


if __name__ == "__main__":
    main()
