"""Parsing and calculations for vcf-operations."""
from __future__ import annotations
from pathlib import Path
import gzip
import bz2
import lzma
import numpy as np

TRANSITIONS = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}

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

    opener = {
        ".gz": gzip.open,
        ".bz2": bz2.open,
        ".xz": lzma.open,
    }.get(vcf_path.suffix.lower(), open)
    with opener(vcf_path, "rt", encoding="utf-8") as f:
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
