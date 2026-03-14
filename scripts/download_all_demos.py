#!/usr/bin/env python3
"""Download demo datasets for all omics domains."""

import os
import urllib.request
import gzip
import shutil

os.makedirs("../examples", exist_ok=True)

print("=" * 60)
print("Downloading demo datasets for OmicsClaw")
print("=" * 60)

# 1. Genomics - Small VCF from 1000 Genomes
print("\n[1/3] Genomics: Downloading VCF demo...")
vcf_url = "https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/working/20220422_3202_phased_SNV_INDEL_SV/1kGP_high_coverage_Illumina.chr22.filtered.SNV_INDEL_SV_phased_panel.vcf.gz"
vcf_path = "../examples/demo_variants.vcf.gz"

try:
    print(f"  Downloading from 1000 Genomes (chr22, ~100MB)...")
    urllib.request.urlretrieve(vcf_url, vcf_path)
    print(f"  ✓ Saved to: {vcf_path}")
except Exception as e:
    print(f"  ✗ Failed: {e}")
    print("  Creating minimal synthetic VCF instead...")

    # Create minimal synthetic VCF
    vcf_content = """##fileformat=VCFv4.2
##contig=<ID=chr1,length=248956422>
##INFO=<ID=DP,Number=1,Type=Integer,Description="Total Depth">
##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">
##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Read Depth">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSample1\tSample2
chr1\t10000\trs001\tA\tG\t30\tPASS\tDP=50\tGT:DP\t0/1:25\t1/1:25
chr1\t20000\trs002\tC\tT\t40\tPASS\tDP=60\tGT:DP\t0/0:30\t0/1:30
chr1\t30000\trs003\tG\tA\t35\tPASS\tDP=55\tGT:DP\t1/1:28\t0/1:27
"""
    with gzip.open(vcf_path, 'wt') as f:
        f.write(vcf_content)
    print(f"  ✓ Created synthetic VCF: {vcf_path}")

print("\n[2/3] Proteomics: Creating demo dataset...")
# Create synthetic proteomics data (peptide intensities)
import pandas as pd
import numpy as np

np.random.seed(42)
proteins = [f"P{i:05d}" for i in range(1, 101)]
samples = [f"Sample_{i}" for i in range(1, 7)]

intensities = np.random.lognormal(mean=10, sigma=2, size=(100, 6))
proteomics_df = pd.DataFrame(intensities, index=proteins, columns=samples)
proteomics_df.index.name = "Protein"

proteomics_path = "../examples/demo_proteomics.csv"
proteomics_df.to_csv(proteomics_path)
print(f"  ✓ Created synthetic proteomics data: {proteomics_path}")
print(f"    {len(proteins)} proteins × {len(samples)} samples")

print("\n[3/3] Metabolomics: Creating demo dataset...")
# Create synthetic metabolomics data (peak table)
metabolites = [f"M{i:04d}" for i in range(1, 201)]
samples_metab = [f"Sample_{i}" for i in range(1, 9)]

peak_intensities = np.random.lognormal(mean=8, sigma=1.5, size=(200, 8))
metabolomics_df = pd.DataFrame(peak_intensities, index=metabolites, columns=samples_metab)
metabolomics_df.index.name = "Metabolite"

metabolomics_path = "../examples/demo_metabolomics.csv"
metabolomics_df.to_csv(metabolomics_path)
print(f"  ✓ Created synthetic metabolomics data: {metabolomics_path}")
print(f"    {len(metabolites)} metabolites × {len(samples_metab)} samples")

print("\n" + "=" * 60)
print("Summary of demo datasets:")
print("=" * 60)
print(f"✓ Single-cell:     examples/pbmc3k.h5ad (2700 cells)")
print(f"✓ Genomics:        {vcf_path}")
print(f"✓ Proteomics:      {proteomics_path} (100 proteins)")
print(f"✓ Metabolomics:    {metabolomics_path} (200 metabolites)")
print(f"✓ Spatial:         examples/demo_visium.h5ad (existing)")
print("=" * 60)
