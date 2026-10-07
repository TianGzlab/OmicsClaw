"""Parsing and calculations for variant-calling."""
from __future__ import annotations
from pathlib import Path
import pandas as pd

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

def parse_variants(vcf_path: Path) -> tuple[pd.DataFrame, dict]:
    """Read and classify alleles from a text VCF."""
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

    return pd.DataFrame(records)


def variant_stats(df):
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
