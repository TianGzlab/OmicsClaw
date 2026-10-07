"""Parsing and calculations for sv-detection."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd


def parse_sv_vcf(vcf_path: Path) -> list[dict]:
    """Parse structural variants from a VCF file.

    Handles standard SV VCF fields including:
    - SVTYPE in INFO field
    - SVLEN for length
    - END for end position
    - INFO/SVTYPE for BND records; ALT breakends are not resolved
    """
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
            sv_id = fields[2]
            ref = fields[3]
            alt = fields[4]
            qual = float(fields[5]) if fields[5] != "." else 0
            filt = fields[6]
            info_str = fields[7]

            # Parse INFO
            info = {}
            for entry in info_str.split(";"):
                if "=" in entry:
                    k, v = entry.split("=", 1)
                    info[k] = v
                else:
                    info[entry] = "true"

            sv_type = info.get("SVTYPE", "UNKNOWN")
            end = int(info.get("END", pos))
            sv_len = abs(int(info.get("SVLEN", end - pos)))

            # Extract genotype if present
            gt = "."
            if len(fields) >= 10:
                gt_field = fields[9].split(":")[0] if fields[9] else "."
                gt = gt_field

            # Determine evidence type from INFO
            evidence = []
            if "SR" in info:
                evidence.append("split_read")
            if "PE" in info:
                evidence.append("read_pair")
            if "RD" in info:
                evidence.append("read_depth")
            if not evidence:
                evidence.append("unknown")

            # Size classification
            if sv_type in ("TRA", "BND"):
                size_class = "translocation"
            elif sv_len < 1000:
                size_class = "small"
            elif sv_len < 100_000:
                size_class = "medium"
            else:
                size_class = "large"

            records.append({
                "chrom": chrom,
                "pos": pos,
                "end": end,
                "sv_id": sv_id,
                "sv_type": sv_type,
                "sv_len": sv_len,
                "qual": qual,
                "filter": filt,
                "genotype": gt,
                "size_class": size_class,
                "evidence": ",".join(evidence),
            })

    return records

def compute_sv_stats(records: list[dict]) -> dict:
    """Compute structural variant summary statistics."""
    if not records:
        return {"n_svs": 0}

    df = pd.DataFrame(records)

    type_counts = df["sv_type"].value_counts().to_dict()
    size_counts = df["size_class"].value_counts().to_dict()

    # Size distribution for non-translocation SVs
    non_tra = df[~df["sv_type"].isin(["TRA", "BND"])]
    sv_lengths = non_tra["sv_len"].values if len(non_tra) > 0 else np.array([0])

    stats = {
        "n_svs": len(df),
        "n_pass": int((df["filter"] == "PASS").sum()),
        "n_del": int(type_counts.get("DEL", 0)),
        "n_dup": int(type_counts.get("DUP", 0)),
        "n_inv": int(type_counts.get("INV", 0)),
        "n_tra": int(type_counts.get("TRA", 0)) + int(type_counts.get("BND", 0)),
        "n_small": int(size_counts.get("small", 0)),
        "n_medium": int(size_counts.get("medium", 0)),
        "n_large": int(size_counts.get("large", 0)),
        "mean_sv_len": int(np.mean(sv_lengths)) if len(sv_lengths) > 0 else 0,
        "median_sv_len": int(np.median(sv_lengths)) if len(sv_lengths) > 0 else 0,
        "n_chromosomes_affected": int(df["chrom"].nunique()),
        "het_hom_ratio": round(
            (df["genotype"] == "0/1").sum() / max(1, (df["genotype"] == "1/1").sum()),
            2,
        ),
    }
    return stats
