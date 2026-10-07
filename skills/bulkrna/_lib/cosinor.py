"""Fixed-period 24-hour cosinor calculation."""
import math
import re
import numpy as np
import pandas as pd

def calculate(df):
    # Drop duplicate columns if any
    dup_cols = sorted(set(df.columns[df.columns.duplicated()]))
    if dup_cols:
        df = df.loc[:, ~df.columns.duplicated()]

    if "gene" not in df.columns:
        raise ValueError("Input CSV missing 'gene' column")

    df["gene"] = df["gene"].astype(str)
    df = df.drop_duplicates(subset=["gene"]).set_index("gene")

    # Identify and deterministically sort time columns
    pat = re.compile(r"^T(\d{2})_R(\d+)$")
    sample_cols = [c for c in df.columns if pat.match(str(c))]
    sample_cols.sort(key=lambda c: (int(pat.match(str(c)).group(1)), int(pat.match(str(c)).group(2))))

    # Drop sample columns with >20% missing values
    removed_cols = []
    kept_cols = []
    for c in sample_cols:
        if df[c].isna().mean() > 0.20:
            removed_cols.append(c)
        else:
            kept_cols.append(c)
    sample_cols = kept_cols
    times = np.array([int(pat.match(str(c)).group(1)) for c in sample_cols], dtype=float)

    results = []

    for gene, row in df.iterrows():
        y = pd.to_numeric(row[sample_cols], errors="coerce").to_numpy(dtype=float)
        mask = ~np.isnan(y)
        y = y[mask]
        t = times[mask]

        rec = {
            "gene": gene,
            "mesor": np.nan,
            "beta_cos": np.nan,
            "beta_sin": np.nan,
            "amplitude": np.nan,
            "peak_phase_hours": np.nan,
            "r_squared": np.nan,
            "amplitude_ratio": np.nan,
            "rhythmic": False,
        }

        if len(y) < 3:
            results.append(rec)
            continue

        # Fixed-period single-component cosinor design matrix
        X = np.column_stack([
            np.ones_like(t),
            np.cos(2.0 * np.pi * t / 24.0),
            np.sin(2.0 * np.pi * t / 24.0),
        ])

        # Deterministic OLS via normal equations
        try:
            beta = np.linalg.solve(X.T @ X, X.T @ y)
        except np.linalg.LinAlgError:
            results.append(rec)
            continue

        mesor, beta_cos, beta_sin = float(beta[0]), float(beta[1]), float(beta[2])
        pred = X @ beta

        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

        amplitude = math.sqrt(beta_cos**2 + beta_sin**2)

        if mesor > 0:
            amplitude_ratio = amplitude / mesor
        else:
            amplitude_ratio = np.nan

        phase_raw = math.atan2(beta_sin, beta_cos) * 12.0 / math.pi
        peak_phase_hours = phase_raw % 24.0
        if abs(peak_phase_hours - 24.0) < 1e-9:
            peak_phase_hours = 0.0

        rhythmic = bool(r_squared >= 0.80 and amplitude_ratio >= 0.20)

        results.append({
            "gene": gene,
            "mesor": mesor,
            "beta_cos": beta_cos,
            "beta_sin": beta_sin,
            "amplitude": amplitude,
            "peak_phase_hours": peak_phase_hours,
            "r_squared": r_squared,
            "amplitude_ratio": amplitude_ratio,
            "rhythmic": rhythmic,
        })

    rhythmic_genes = sorted([r["gene"] for r in results if r["rhythmic"]])
    semantic_summary = {
        "gene_count": len(results),
        "rhythmic_gene_count": len(rhythmic_genes),
        "rhythmic_genes": rhythmic_genes,
        "validation": {
            "duplicate_columns_dropped": dup_cols,
            "sample_columns_dropped_gt_20pct_missing": removed_cols,
            "sample_columns_used": sample_cols,
        },
    }
    return pd.DataFrame(results), semantic_summary
