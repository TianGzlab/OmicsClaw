"""Seeded synthetic tables for metabolomics examples and CLI demos."""

import logging

import numpy as np

import pandas as pd

from skills.metabolomics._lib.annotation import DEMO_METABOLITES, _PROTON

logger = logging.getLogger(__name__)

def normalization(*, random_state=42):
    """Generate demo metabolomics data with realistic structure."""
    logger.info("Generating demo metabolomics data")
    rng = np.random.default_rng(random_state)
    n_features = 150
    n_samples = 12

    # Base intensities from log-normal, with varying dilution per sample
    base = rng.lognormal(10, 2, (n_features, n_samples))
    dilution_factors = rng.uniform(0.5, 2.0, n_samples)
    data = base * dilution_factors[np.newaxis, :]

    return pd.DataFrame(
        data,
        columns=[f"sample_{i + 1}" for i in range(n_samples)],
        index=[f"feature_{i + 1}" for i in range(n_features)],
    )

def quantification(*, random_state=42):
    """Generate synthetic metabolomics feature table with ~10% missing values."""
    rng = np.random.default_rng(random_state)
    n_features = 120
    n_samples = 8

    data = {
        "feature_id": [f"M{i:04d}" for i in range(n_features)],
        "mz": np.round(rng.uniform(80, 1200, n_features), 4),
        "rt": np.round(rng.uniform(0.5, 25, n_features), 3),
    }
    for s in range(n_samples):
        intensities = rng.lognormal(10, 2, n_features)
        # Inject ~10 % missing values (set to 0)
        mask = rng.random(n_features) < 0.1
        intensities[mask] = 0
        data[f"sample_{s + 1}"] = np.round(intensities, 2)

    df = pd.DataFrame(data)
    return df


def de(*, random_state=42):
    """Generate demo quantified feature table with condition labels."""
    rng = np.random.default_rng(random_state)
    n_features = 100
    n_per_group = 4

    data = {"feature_id": [f"M{i:04d}" for i in range(n_features)]}

    # Control group
    for s in range(n_per_group):
        data[f"ctrl_{s + 1}"] = np.round(rng.lognormal(10, 1.5, n_features), 2)

    # Treatment group — first 20 features are differentially abundant
    for s in range(n_per_group):
        vals = rng.lognormal(10, 1.5, n_features)
        vals[:20] *= rng.uniform(1.5, 3.0, 20)
        data[f"treat_{s + 1}"] = np.round(vals, 2)

    df = pd.DataFrame(data)
    return df


def statistics(*, random_state=42):
    """Generate demo metabolomics data."""
    logger.info("Generating demo metabolomics data")
    rng = np.random.default_rng(random_state)
    n_features = 100
    n_per_group = 6

    group1_cols = [f"control_{i + 1}" for i in range(n_per_group)]
    group2_cols = [f"treatment_{i + 1}" for i in range(n_per_group)]

    data = pd.DataFrame(
        rng.lognormal(10, 1, (n_features, n_per_group * 2)),
        columns=group1_cols + group2_cols,
        index=[f"metabolite_{i + 1}" for i in range(n_features)],
    )

    # Inject differential features
    for i in range(20):
        data.loc[f"metabolite_{i + 1}", group2_cols] *= rng.uniform(1.5, 3.0)

    return data, group1_cols, group2_cols

def annotation(*, random_state=42):
    """Generate demo peak table with realistic m/z values.

    Some values are drawn from known metabolites (shifted to [M+H]+ m/z)
    so that annotation will produce matches.
    """
    logger.info("Generating demo peak table")
    rng = np.random.default_rng(random_state)
    n_peaks = 50

    # Generate known-metabolite m/z values (as [M+H]+ adducts with small noise)
    known_mz = []
    for name, mass, _, _ in DEMO_METABOLITES[:12]:
        known_mz.append(mass + _PROTON + rng.normal(0, mass * 2e-6))

    # Fill remaining with random m/z
    random_mz = rng.uniform(100, 800, n_peaks - len(known_mz))
    all_mz = np.concatenate([known_mz, random_mz])
    rng.shuffle(all_mz)

    return pd.DataFrame({
        "mz": np.round(all_mz, 6),
        "rt": np.round(rng.uniform(0.5, 25, len(all_mz)), 3),
        "intensity": np.round(rng.lognormal(10, 2, len(all_mz)), 2),
    })

def peak_detection(*, random_state=42):
    """Generate realistic demo metabolomics data with embedded peaks.

    Creates a synthetic dataset sorted by retention time, with Gaussian
    peaks added on top of a noisy baseline to simulate a realistic
    chromatographic signal.
    """
    rng = np.random.default_rng(random_state)
    n_points = 500
    n_samples = 3

    # Retention time axis (minutes)
    rt = np.linspace(0.5, 30.0, n_points)
    # m/z values — assign realistic m/z drawn from a plausible range
    mz = rng.uniform(80, 1200, n_points)

    data: dict = {"mz": np.round(mz, 4), "rt": np.round(rt, 4)}

    # Number of true peaks to embed
    n_true_peaks = 25

    for s in range(n_samples):
        # Noisy baseline (log-normal background + white noise)
        baseline = rng.lognormal(6, 0.5, n_points) + rng.normal(0, 200, n_points)
        baseline = np.clip(baseline, 0, None)

        # Add Gaussian peaks at random RT positions
        peak_centres = rng.uniform(2, 28, n_true_peaks)
        peak_heights = rng.uniform(5e4, 5e5, n_true_peaks)
        peak_sigmas = rng.uniform(0.1, 0.5, n_true_peaks)

        signal = baseline.copy()
        for pc, ph, ps in zip(peak_centres, peak_heights, peak_sigmas):
            signal += ph * np.exp(-0.5 * ((rt - pc) / ps) ** 2)

        data[f"intensity_{s + 1}"] = np.round(signal, 2)

    df = pd.DataFrame(data)
    return df


def pathway_enrichment(*, random_state=42):
    """Generate demo metabolite list."""
    rng = np.random.default_rng(random_state)
    metabolites = [
        "glucose", "pyruvate", "lactate", "citrate", "succinate",
        "glutamate", "alanine", "tryptophan", "serotonin",
        "adenine", "uric_acid", "palmitate", "cholate",
        "uracil", "glycine", "kynurenine",
    ]
    df = pd.DataFrame({
        "metabolite": metabolites,
        "log2fc": np.round(rng.normal(0.3, 1.0, len(metabolites)), 3),
        "pvalue": np.round(rng.uniform(0.001, 0.05, len(metabolites)), 5),
    })
    return df
