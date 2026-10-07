#!/usr/bin/env python3
"""Genomics vcf-operations: summarize existing local files.\n\nThe CLI owns demo generation, reports and file output. Its function library\ncontains the computations. No external analysis tool is started."""

from __future__ import annotations

import argparse
import logging
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

SKILL_NAME = "genomics-vcf-operations"
SKILL_VERSION = "0.5.0"

# Transition pairs (purine<->purine or pyrimidine<->pyrimidine)
TRANSITIONS = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}


# ---------------------------------------------------------------------------
# VCF Parsing


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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
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
    from skills._sdk.notebook import load_skill
    api = load_skill(SKILL_NAME)
    result = api.analyze(api.read_records(vcf_path), min_qual=args.min_qual, min_dp=args.min_dp)
    stats = api.run_info(result, keep=False)["summary"]
    records = result.to_dict("records")
    header_lines = result.attrs["vcf_headers"]
    logger.info(f"VCF stats: {stats['n_variants']} variants, Ti/Tv={stats['ti_tv_ratio']}")

    # Save tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    if records:
        pd.DataFrame(records).to_csv(tables_dir / "variants.csv", index=False)

    # ``filtered.vcf`` is a declared output artifact, so materialise it even
    # when both thresholds are zero (in that case it is the normalized pass-
    # through representation). Keep the row width consistent with #CHROM.
    filtered_vcf = output_dir / "filtered.vcf"
    chrom_header = next(
        (line for line in header_lines if line.startswith("#CHROM")),
        "",
    )
    has_samples = len(chrom_header.split("\t")) > 8
    with open(filtered_vcf, "w", encoding="utf-8") as fh:
        for hl in header_lines:
            fh.write(hl + "\n")
        for r in records:
            row = (
                f"{r['chrom']}\t{r['pos']}\t{r['id']}\t{r['ref']}\t{r['alt']}\t"
                f"{r['qual']}\t{r['filter']}\tDP={r['dp']}"
            )
            if has_samples:
                row += "\tGT\t."
            fh.write(row + "\n")
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
