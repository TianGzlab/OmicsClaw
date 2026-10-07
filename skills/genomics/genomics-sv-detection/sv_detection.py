#!/usr/bin/env python3
"""Genomics sv-detection: summarize existing local files.\n\nThe CLI owns demo generation, reports and file output. Its function library\ncontains the computations. No external analysis tool is started."""

from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

import numpy as np
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

SKILL_NAME = "genomics-sv-detection"
SKILL_VERSION = "0.5.0"

# SV types
SV_TYPES = ["DEL", "DUP", "INV", "TRA"]

# Size classes per 1000 Genomes classification
SIZE_CLASSES = {
    "small": (50, 1000),        # 50bp - 1kb
    "medium": (1000, 100_000),  # 1kb - 100kb
    "large": (100_000, 10_000_000),  # 100kb - 10Mb
}

# Evidence types
EVIDENCE_TYPES = ["split_read", "read_pair", "read_depth", "assembly"]


# ---------------------------------------------------------------------------
# SV VCF Parsing


# ---------------------------------------------------------------------------
# Demo Data Generation
# ---------------------------------------------------------------------------

def generate_demo_svs(output_dir: Path, n_svs: int = 100) -> Path:
    """Generate realistic structural variant demo data as VCF.

    Distribution of SV types follows observed genome-wide proportions:
    - ~50% DEL (deletions are the most common SV type)
    - ~20% DUP
    - ~15% INV
    - ~15% TRA/BND

    Size distribution: most SVs are small (50-1000 bp) with exponential
    decay for larger events (matching observed SV size distributions).
    """
    rng = random.Random(42)
    chroms = [f"chr{i}" for i in range(1, 23)] + ["chrX"]

    vcf_path = output_dir / "demo_structural_variants.vcf"

    with open(vcf_path, "w") as fh:
        # VCF header
        fh.write("##fileformat=VCFv4.2\n")
        fh.write(f"##source=OmicsClaw-{SKILL_NAME}-{SKILL_VERSION}\n")
        for c in chroms:
            fh.write(f"##contig=<ID={c},length=250000000>\n")
        fh.write('##INFO=<ID=SVTYPE,Number=1,Type=String,Description="Type of structural variant">\n')
        fh.write('##INFO=<ID=SVLEN,Number=1,Type=Integer,Description="Difference in length between REF and ALT alleles">\n')
        fh.write('##INFO=<ID=END,Number=1,Type=Integer,Description="End position of the variant">\n')
        fh.write('##INFO=<ID=SR,Number=1,Type=Integer,Description="Split read support">\n')
        fh.write('##INFO=<ID=PE,Number=1,Type=Integer,Description="Paired-end support">\n')
        fh.write('##INFO=<ID=CT,Number=1,Type=String,Description="Connection type for BND">\n')
        fh.write('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n')
        fh.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE1\n")

        type_weights = {"DEL": 50, "DUP": 20, "INV": 15, "TRA": 15}
        types = list(type_weights.keys())
        weights = list(type_weights.values())

        for i in range(n_svs):
            sv_type = rng.choices(types, weights=weights)[0]
            chrom = rng.choice(chroms)
            pos = rng.randint(10000, 249_000_000)

            # Log-normal SV length distribution (most small, some very large)
            sv_len = int(np.exp(rng.gauss(7, 2)))  # median ~1kb, range 50bp-10Mb
            sv_len = max(50, min(sv_len, 10_000_000))

            end = pos + sv_len
            qual = rng.randint(20, 500)
            sr = rng.randint(0, 20)
            pe = rng.randint(0, 30)
            gt = rng.choice(["0/1", "1/1"])
            filt = "PASS" if qual >= 50 else "LowQual"

            if sv_type == "TRA":
                # Translocation: different chromosome
                chrom2 = rng.choice([c for c in chroms if c != chrom])
                pos2 = rng.randint(10000, 249_000_000)
                alt = f"N[{chrom2}:{pos2}["
                info = f"SVTYPE=BND;CT=3to5;SR={sr};PE={pe}"
            elif sv_type == "DEL":
                alt = "<DEL>"
                info = f"SVTYPE=DEL;END={end};SVLEN=-{sv_len};SR={sr};PE={pe}"
            elif sv_type == "DUP":
                alt = "<DUP>"
                info = f"SVTYPE=DUP;END={end};SVLEN={sv_len};SR={sr};PE={pe}"
            elif sv_type == "INV":
                alt = "<INV>"
                info = f"SVTYPE=INV;END={end};SVLEN={sv_len};SR={sr};PE={pe}"
            else:
                continue

            fh.write(f"{chrom}\t{pos}\tSV_{i}\tN\t{alt}\t{qual}\t{filt}\t{info}\tGT\t{gt}\n")

    logger.info(f"Generated demo SV VCF with {n_svs} variants: {vcf_path}")
    return vcf_path


# ---------------------------------------------------------------------------
# Analysis & Statistics


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write SV detection report."""
    header = generate_report_header(
        title="Structural Variant Detection Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"SVs detected": f"{stats['n_svs']:,}"},
    )

    body_lines = [
        "## SV Summary\n",
        f"- **Total SVs**: {stats['n_svs']:,}",
        f"- **PASS SVs**: {stats['n_pass']:,}",
        f"- **Chromosomes affected**: {stats['n_chromosomes_affected']}",
        "",
        "### SV Type Distribution\n",
        f"- 🔴 **Deletions (DEL)**: {stats['n_del']:,}",
        f"- 🟢 **Duplications (DUP)**: {stats['n_dup']:,}",
        f"- 🔵 **Inversions (INV)**: {stats['n_inv']:,}",
        f"- 🟡 **Translocations (TRA/BND)**: {stats['n_tra']:,}",
        "",
        "### Size Distribution\n",
        f"- **Small (50bp–1kb)**: {stats['n_small']:,}",
        f"- **Medium (1kb–100kb)**: {stats['n_medium']:,}",
        f"- **Large (100kb–10Mb)**: {stats['n_large']:,}",
        f"- **Mean length**: {stats['mean_sv_len']:,} bp",
        f"- **Median length**: {stats['median_sv_len']:,} bp",
        "",
        f"- **Het/Hom ratio**: {stats['het_hom_ratio']:.2f}",
        "",
    ]

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Genomics SV Detection")
    parser.add_argument("--input", dest="input_path", help="Input SV VCF file")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with synthetic demo data")
    parser.add_argument("--n-svs", type=int, default=100, help="Number of demo SVs")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        vcf_path = generate_demo_svs(output_dir, n_svs=args.n_svs)
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
    records = result.to_dict("records")

    # Save tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    if records:
        pd.DataFrame(records).to_csv(tables_dir / "structural_variants.csv", index=False)

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
    print(f"SV detection complete: {stats['n_svs']} SVs "
          f"(DEL={stats['n_del']}, DUP={stats['n_dup']}, "
          f"INV={stats['n_inv']}, TRA={stats['n_tra']})")


if __name__ == "__main__":
    main()
