#!/usr/bin/env python3
"""Create demo datasets for proteomics and metabolomics."""

import pandas as pd
import numpy as np
import os

os.makedirs("../examples", exist_ok=True)

print("Creating demo datasets...")

# Proteomics
np.random.seed(42)
proteins = [f"P{i:05d}" for i in range(1, 101)]
samples = [f"Sample_{i}" for i in range(1, 7)]
intensities = np.random.lognormal(mean=10, sigma=2, size=(100, 6))
proteomics_df = pd.DataFrame(intensities, index=proteins, columns=samples)
proteomics_df.index.name = "Protein"
proteomics_df.to_csv("examples/demo_proteomics.csv")
print(f"✓ Proteomics: examples/demo_proteomics.csv (100 proteins × 6 samples)")

# Metabolomics
metabolites = [f"M{i:04d}" for i in range(1, 201)]
samples_metab = [f"Sample_{i}" for i in range(1, 9)]
peak_intensities = np.random.lognormal(mean=8, sigma=1.5, size=(200, 8))
metabolomics_df = pd.DataFrame(peak_intensities, index=metabolites, columns=samples_metab)
metabolomics_df.index.name = "Metabolite"
metabolomics_df.to_csv("examples/demo_metabolomics.csv")
print(f"✓ Metabolomics: examples/demo_metabolomics.csv (200 metabolites × 8 samples)")

print("\nAll demo datasets ready!")
