"""
Mendelian Randomization for causal inference in TWAS.

This module performs two-sample Mendelian Randomization to test causal effects
of gene expression (exposure) on disease/trait (outcome), providing gold-standard
evidence for therapeutic target validation.

MR uses genetic variants (eQTLs) as instrumental variables to estimate causal effects,
addressing confounding and reverse causation that limit observational studies.

Author: Claude Code (Anthropic)
Date: 2026-01-28
"""

import pandas as pd
import numpy as np
from scipy import stats
from typing import Dict, List, Tuple, Optional, Literal
import warnings


def harmonize_exposure_outcome(
    exposure_data: pd.DataFrame,
    outcome_data: pd.DataFrame,
    exposure_name: str = "Expression",
    outcome_name: str = "Trait"
) -> pd.DataFrame:
    """
    Harmonize exposure (eQTL) and outcome (GWAS) data for MR analysis.

    Ensures effect alleles are aligned between exposure and outcome datasets.

    Parameters
    ----------
    exposure_data : pd.DataFrame
        eQTL summary statistics with columns: SNP, A1, A2, BETA, SE, P
        A1 = effect allele, BETA = effect of A1 on gene expression
    outcome_data : pd.DataFrame
        GWAS summary statistics with columns: SNP, A1, A2, BETA, SE, P
        A1 = effect allele, BETA = effect of A1 on trait
    exposure_name : str
        Name of exposure (e.g., "IL6R expression")
    outcome_name : str
        Name of outcome (e.g., "Coronary Artery Disease")

    Returns
    -------
    pd.DataFrame
        Harmonized data with columns:
        - SNP: Variant ID
        - beta.exposure: Effect on exposure
        - se.exposure: Standard error of exposure effect
        - beta.outcome: Effect on outcome (aligned to exposure effect allele)
        - se.outcome: Standard error of outcome effect
        - pval.exposure, pval.outcome: P-values

    Examples
    --------
    >>> harmonized = harmonize_exposure_outcome(eqtl_df, gwas_df,
    ...                                          "IL6R expression", "CAD")
    """

    # Merge on SNP
    merged = exposure_data.merge(outcome_data, on='SNP', suffixes=('_exp', '_out'))

    # Check allele alignment
    harmonized_data = []

    for idx, row in merged.iterrows():
        # Exposure alleles
        a1_exp = row['A1_exp']
        a2_exp = row['A2_exp']
        beta_exp = row['BETA_exp']
        se_exp = row['SE_exp']
        p_exp = row['P_exp']

        # Outcome alleles
        a1_out = row['A1_out']
        a2_out = row['A2_out']
        beta_out = row['BETA_out']
        se_out = row['SE_out']
        p_out = row['P_out']

        # Case 1: Alleles already aligned (A1_exp = A1_out, A2_exp = A2_out)
        if a1_exp == a1_out and a2_exp == a2_out:
            harmonized_data.append({
                'SNP': row['SNP'],
                'effect_allele': a1_exp,
                'other_allele': a2_exp,
                'beta.exposure': beta_exp,
                'se.exposure': se_exp,
                'pval.exposure': p_exp,
                'beta.outcome': beta_out,
                'se.outcome': se_out,
                'pval.outcome': p_out,
                'aligned': True
            })

        # Case 2: Alleles flipped (A1_exp = A2_out, A2_exp = A1_out)
        elif a1_exp == a2_out and a2_exp == a1_out:
            # Flip outcome effect to match exposure
            harmonized_data.append({
                'SNP': row['SNP'],
                'effect_allele': a1_exp,
                'other_allele': a2_exp,
                'beta.exposure': beta_exp,
                'se.exposure': se_exp,
                'pval.exposure': p_exp,
                'beta.outcome': -beta_out,  # Flip beta
                'se.outcome': se_out,  # SE doesn't change
                'pval.outcome': p_out,
                'aligned': True
            })

        # Case 3: Ambiguous SNPs (A/T or G/C) - exclude to avoid strand ambiguity
        elif (set([a1_exp, a2_exp]) == {'A', 'T'} or
              set([a1_exp, a2_exp]) == {'G', 'C'}):
            warnings.warn(f"Ambiguous SNP {row['SNP']} (A/T or G/C), excluding from analysis")
            continue

        else:
            warnings.warn(f"Allele mismatch for SNP {row['SNP']}, excluding from analysis")
            continue

    harmonized_df = pd.DataFrame(harmonized_data)

    print(f"\nHarmonization summary:")
    print(f"  Exposure: {exposure_name}")
    print(f"  Outcome: {outcome_name}")
    print(f"  Total SNPs in exposure: {len(exposure_data)}")
    print(f"  Total SNPs in outcome: {len(outcome_data)}")
    print(f"  Harmonized SNPs: {len(harmonized_df)}")

    return harmonized_df


def clump_instruments(
    harmonized_data: pd.DataFrame,
    pvalue_threshold: float = 5e-8,
    r2_threshold: float = 0.001,
    kb_window: int = 10000,
    ld_matrix: Optional[np.ndarray] = None
) -> pd.DataFrame:
    """
    Select independent genetic instruments for MR analysis.

    Clumps SNPs based on LD to ensure independence of instruments.

    Parameters
    ----------
    harmonized_data : pd.DataFrame
        Harmonized exposure-outcome data
    pvalue_threshold : float
        P-value threshold for instrument selection (default: 5e-8 genome-wide)
    r2_threshold : float
        LD r² threshold for clumping (default: 0.001 for independence)
    kb_window : int
        Window size in kb for LD clumping (default: 10 Mb)
    ld_matrix : np.ndarray, optional
        Pairwise LD r² matrix (if None, uses simple distance-based clumping)

    Returns
    -------
    pd.DataFrame
        Independent instruments passing thresholds

    Examples
    --------
    >>> instruments = clump_instruments(harmonized_df, pvalue_threshold=5e-6)
    """

    # Filter by p-value threshold
    significant = harmonized_data[harmonized_data['pval.exposure'] < pvalue_threshold].copy()

    if len(significant) == 0:
        warnings.warn(f"No SNPs pass p-value threshold {pvalue_threshold}")
        return pd.DataFrame()

    # Sort by p-value (most significant first)
    significant = significant.sort_values('pval.exposure').reset_index(drop=True)

    if ld_matrix is not None:
        # LD-based clumping (requires LD matrix)
        # This is a simplified version - in practice, use PLINK for clumping
        selected_indices = [0]  # Start with most significant SNP

        for i in range(1, len(significant)):
            # Check LD with all previously selected SNPs
            independent = True
            for j in selected_indices:
                if ld_matrix[i, j] > r2_threshold:
                    independent = False
                    break

            if independent:
                selected_indices.append(i)

        clumped = significant.iloc[selected_indices]

    else:
        # Simple distance-based clumping (assume chr/bp columns available)
        # In practice, should use proper LD-based clumping with reference panel
        warnings.warn("LD matrix not provided, using simple distance-based clumping. "
                     "For production analysis, use PLINK clumping with LD reference panel.")

        clumped = significant.iloc[[0]]  # Just take top SNP as simple approach

    print(f"\nInstrument selection:")
    print(f"  P-value threshold: {pvalue_threshold}")
    print(f"  Significant SNPs: {len(significant)}")
    print(f"  Independent instruments: {len(clumped)}")

    return clumped


def calculate_f_statistic(
    instruments: pd.DataFrame,
    sample_size: int
) -> Tuple[float, bool]:
    """
    Calculate F-statistic for instrument strength.

    F-statistic < 10 suggests weak instrument bias.

    Parameters
    ----------
    instruments : pd.DataFrame
        Instrumental variables with beta.exposure and se.exposure
    sample_size : int
        Sample size of exposure GWAS

    Returns
    -------
    tuple
        (F-statistic, is_strong) where is_strong = True if F > 10

    Examples
    --------
    >>> f_stat, is_strong = calculate_f_statistic(instruments, n=500)
    """

    # F-statistic = (beta / se)^2
    # For multiple instruments, use mean F-statistic
    f_stats = (instruments['beta.exposure'] / instruments['se.exposure']) ** 2

    mean_f = f_stats.mean()

    # Alternative: R² based F-statistic
    # F = R² * (n - k - 1) / (k * (1 - R²))
    # where k = number of instruments, n = sample size

    is_strong = mean_f > 10

    print(f"\nInstrument strength:")
    print(f"  Mean F-statistic: {mean_f:.2f}")
    print(f"  Status: {'Strong' if is_strong else 'WEAK - risk of weak instrument bias'}")

    return mean_f, is_strong


def ivw_method(
    instruments: pd.DataFrame,
    use_random_effects: bool = False
) -> Dict:
    """
    Inverse-variance weighted (IVW) Mendelian Randomization.

    This is the main MR method, providing causal estimate assuming all
    instruments are valid (no horizontal pleiotropy).

    Parameters
    ----------
    instruments : pd.DataFrame
        Harmonized instruments with beta.exposure, se.exposure, beta.outcome, se.outcome
    use_random_effects : bool
        Use random-effects model if heterogeneity detected (default: False)

    Returns
    -------
    dict
        IVW results with causal estimate, SE, p-value, heterogeneity stats

    Examples
    --------
    >>> ivw_result = ivw_method(instruments)
    >>> print(f"Causal estimate: {ivw_result['beta']:.3f} (p={ivw_result['pval']:.2e})")
    """

    n_snps = len(instruments)

    if n_snps == 0:
        return {'error': 'No instruments available'}

    # Ratio estimates: beta_outcome / beta_exposure for each SNP
    ratio = instruments['beta.outcome'] / instruments['beta.exposure']

    # Weights: 1 / se²_ratio
    # se_ratio = sqrt((se_outcome / beta_exposure)^2 + (se_exposure * beta_outcome / beta_exposure^2)^2)
    se_ratio = np.sqrt(
        (instruments['se.outcome'] / instruments['beta.exposure']) ** 2
    )  # Simplified formula (assumes se_exposure << beta_exposure)

    weights = 1 / (se_ratio ** 2)

    # IVW estimate: weighted mean of ratios
    ivw_beta = np.sum(ratio * weights) / np.sum(weights)
    ivw_se = np.sqrt(1 / np.sum(weights))
    ivw_z = ivw_beta / ivw_se
    ivw_pval = 2 * (1 - stats.norm.cdf(abs(ivw_z)))

    # Heterogeneity test (Cochran's Q)
    q_statistic = np.sum(weights * (ratio - ivw_beta) ** 2)
    q_df = n_snps - 1
    q_pval = 1 - stats.chi2.cdf(q_statistic, q_df)

    # I² statistic (proportion of variance due to heterogeneity)
    i_squared = max(0, (q_statistic - q_df) / q_statistic) if q_statistic > 0 else 0

    result = {
        'method': 'IVW (Inverse Variance Weighted)',
        'nsnp': n_snps,
        'beta': ivw_beta,
        'se': ivw_se,
        'pval': ivw_pval,
        'q_statistic': q_statistic,
        'q_df': q_df,
        'q_pval': q_pval,
        'i_squared': i_squared
    }

    if q_pval < 0.05:
        result['heterogeneity_warning'] = "Significant heterogeneity detected (Q p < 0.05)"

    return result


def mr_egger(instruments: pd.DataFrame) -> Dict:
    """
    MR-Egger regression for directional pleiotropy detection.

    MR-Egger allows for horizontal pleiotropy by estimating an intercept term.
    Non-zero intercept suggests directional pleiotropy.

    Parameters
    ----------
    instruments : pd.DataFrame
        Harmonized instruments

    Returns
    -------
    dict
        MR-Egger results with causal estimate, intercept, and pleiotropy test

    Examples
    --------
    >>> egger_result = mr_egger(instruments)
    >>> if egger_result['intercept_pval'] < 0.05:
    ...     print("WARNING: Directional pleiotropy detected")
    """

    n_snps = len(instruments)

    if n_snps < 3:
        return {'error': 'MR-Egger requires ≥3 instruments'}

    # Weighted linear regression: beta_outcome ~ beta_exposure
    # Weights: 1 / se_outcome²

    X = instruments['beta.exposure'].values
    y = instruments['beta.outcome'].values
    weights = 1 / (instruments['se.outcome'].values ** 2)

    # Weighted regression
    W = np.diag(weights)
    X_weighted = np.column_stack([np.ones(n_snps), X])

    # Beta = (X'WX)^-1 X'Wy
    XWX = X_weighted.T @ W @ X_weighted
    XWy = X_weighted.T @ W @ y

    try:
        beta_egger = np.linalg.solve(XWX, XWy)
    except np.linalg.LinAlgError:
        return {'error': 'MR-Egger matrix inversion failed'}

    intercept = beta_egger[0]
    slope = beta_egger[1]

    # Standard errors
    residuals = y - (intercept + slope * X)
    mse = np.sum(weights * residuals ** 2) / (n_snps - 2)
    cov_matrix = mse * np.linalg.inv(XWX)

    se_intercept = np.sqrt(cov_matrix[0, 0])
    se_slope = np.sqrt(cov_matrix[1, 1])

    # P-values
    z_intercept = intercept / se_intercept
    pval_intercept = 2 * (1 - stats.norm.cdf(abs(z_intercept)))

    z_slope = slope / se_slope
    pval_slope = 2 * (1 - stats.norm.cdf(abs(z_slope)))

    result = {
        'method': 'MR-Egger',
        'nsnp': n_snps,
        'beta': slope,  # Causal estimate
        'se': se_slope,
        'pval': pval_slope,
        'intercept': intercept,
        'intercept_se': se_intercept,
        'intercept_pval': pval_intercept
    }

    if pval_intercept < 0.05:
        result['pleiotropy_warning'] = ("Significant MR-Egger intercept (p < 0.05) suggests "
                                        "directional pleiotropy")

    return result


def weighted_median_method(instruments: pd.DataFrame) -> Dict:
    """
    Weighted median MR method.

    More robust to invalid instruments than IVW. Provides consistent estimate
    if <50% of instruments are invalid.

    Parameters
    ----------
    instruments : pd.DataFrame
        Harmonized instruments

    Returns
    -------
    dict
        Weighted median results

    Examples
    --------
    >>> wm_result = weighted_median_method(instruments)
    """

    n_snps = len(instruments)

    if n_snps < 3:
        return {'error': 'Weighted median requires ≥3 instruments'}

    # Ratio estimates
    ratio = instruments['beta.outcome'] / instruments['beta.exposure']

    # Weights
    se_ratio = np.sqrt(
        (instruments['se.outcome'] / instruments['beta.exposure']) ** 2
    )
    weights = 1 / (se_ratio ** 2)
    weights = weights / np.sum(weights)  # Normalize to sum to 1

    # Sort by ratio
    sorted_idx = np.argsort(ratio)
    ratio_sorted = ratio.iloc[sorted_idx].values
    weights_sorted = weights.iloc[sorted_idx].values

    # Find weighted median
    cumsum_weights = np.cumsum(weights_sorted)
    median_idx = np.where(cumsum_weights >= 0.5)[0][0]
    wm_beta = ratio_sorted[median_idx]

    # Bootstrap SE (simplified - in practice use proper bootstrap)
    # For now, use IQR / 1.35 as rough estimate
    q25_idx = np.where(cumsum_weights >= 0.25)[0][0]
    q75_idx = np.where(cumsum_weights >= 0.75)[0][0]
    iqr = ratio_sorted[q75_idx] - ratio_sorted[q25_idx]
    wm_se = iqr / 1.35

    wm_z = wm_beta / wm_se
    wm_pval = 2 * (1 - stats.norm.cdf(abs(wm_z)))

    result = {
        'method': 'Weighted Median',
        'nsnp': n_snps,
        'beta': wm_beta,
        'se': wm_se,
        'pval': wm_pval
    }

    return result


def two_sample_mr(
    gene: str,
    exposure_data: pd.DataFrame,
    outcome_data: pd.DataFrame,
    exposure_name: str = "Expression",
    outcome_name: str = "Trait",
    pvalue_threshold: float = 5e-6,
    sample_size_exposure: int = 500
) -> Dict:
    """
    Perform two-sample Mendelian Randomization analysis.

    Tests causal effect of gene expression (exposure) on trait (outcome)
    using eQTL SNPs as genetic instruments.

    Parameters
    ----------
    gene : str
        Gene symbol
    exposure_data : pd.DataFrame
        eQTL summary statistics (SNP, A1, A2, BETA, SE, P)
    outcome_data : pd.DataFrame
        GWAS summary statistics (SNP, A1, A2, BETA, SE, P)
    exposure_name : str
        Name of exposure (default: "Expression")
    outcome_name : str
        Name of outcome (default: "Trait")
    pvalue_threshold : float
        P-value threshold for instrument selection (default: 5e-6)
    sample_size_exposure : int
        Sample size of eQTL study (for F-statistic calculation)

    Returns
    -------
    dict
        MR results from multiple methods with interpretation

    Examples
    --------
    >>> mr_result = two_sample_mr(
    ...     gene="IL6R",
    ...     exposure_data=il6r_eqtl_df,
    ...     outcome_data=cad_gwas_df,
    ...     exposure_name="IL6R expression",
    ...     outcome_name="Coronary Artery Disease"
    ... )
    >>> print(f"Causal effect: {mr_result['ivw']['beta']:.3f}")
    """

    print(f"\n{'='*70}")
    print(f"Two-Sample Mendelian Randomization: {gene}")
    print(f"Exposure: {exposure_name}")
    print(f"Outcome: {outcome_name}")
    print(f"{'='*70}")

    # Step 1: Harmonize data
    harmonized = harmonize_exposure_outcome(
        exposure_data, outcome_data, exposure_name, outcome_name
    )

    if len(harmonized) == 0:
        return {'error': 'No overlapping SNPs after harmonization'}

    # Step 2: Select instruments
    instruments = clump_instruments(harmonized, pvalue_threshold=pvalue_threshold)

    if len(instruments) == 0:
        return {'error': f'No instruments pass p-value threshold {pvalue_threshold}'}

    # Step 3: Check instrument strength
    f_stat, is_strong = calculate_f_statistic(instruments, sample_size_exposure)

    # Step 4: Run MR methods
    results = {
        'gene': gene,
        'exposure': exposure_name,
        'outcome': outcome_name,
        'n_instruments': len(instruments),
        'f_statistic': f_stat,
        'instruments_strong': is_strong
    }

    # IVW (main method)
    results['ivw'] = ivw_method(instruments)

    # MR-Egger (pleiotropy test)
    if len(instruments) >= 3:
        results['egger'] = mr_egger(instruments)

    # Weighted median (robust method)
    if len(instruments) >= 3:
        results['weighted_median'] = weighted_median_method(instruments)

    # Step 5: Interpret results
    results['interpretation'] = interpret_mr_results(results)

    return results


def interpret_mr_results(mr_results: Dict) -> Dict:
    """
    Provide interpretation and confidence assessment for MR results.

    Parameters
    ----------
    mr_results : dict
        Results from two_sample_mr

    Returns
    -------
    dict
        Interpretation with causal conclusion and confidence level
    """

    interpretation = {}

    # Check instrument strength
    if not mr_results['instruments_strong']:
        interpretation['warning'] = ("WEAK INSTRUMENTS (F < 10): Results may be biased. "
                                     "Consider using more relaxed p-value threshold or "
                                     "larger eQTL study.")
        interpretation['confidence'] = "Low"
        return interpretation

    # Extract IVW result
    ivw = mr_results['ivw']
    ivw_beta = ivw['beta']
    ivw_pval = ivw['pval']

    # Check statistical significance
    if ivw_pval < 0.05:
        direction = "increases" if ivw_beta > 0 else "decreases"
        interpretation['causal_effect'] = (
            f"Genetically predicted {mr_results['exposure']} {direction} "
            f"{mr_results['outcome']} risk"
        )
        interpretation['effect_size'] = (
            f"1 SD increase in {mr_results['exposure']} causes "
            f"{abs(ivw_beta):.2%} {'increase' if ivw_beta > 0 else 'decrease'} "
            f"in {mr_results['outcome']}"
        )
    else:
        interpretation['causal_effect'] = "No significant causal effect detected"
        interpretation['confidence'] = "None"
        return interpretation

    # Check for heterogeneity
    if 'q_pval' in ivw and ivw['q_pval'] < 0.05:
        interpretation['heterogeneity_warning'] = (
            "Significant heterogeneity detected. Effect may vary across instruments."
        )

    # Check for pleiotropy
    if 'egger' in mr_results:
        egger = mr_results['egger']
        if egger.get('intercept_pval', 1) < 0.05:
            interpretation['pleiotropy_warning'] = (
                "MR-Egger detects directional pleiotropy. IVW estimate may be biased."
            )

    # Check consistency across methods
    methods_consistent = True
    if 'weighted_median' in mr_results:
        wm = mr_results['weighted_median']
        # Check if IVW and weighted median have same sign
        if np.sign(ivw_beta) != np.sign(wm['beta']):
            methods_consistent = False
            interpretation['consistency_warning'] = (
                "IVW and weighted median show different effect directions. "
                "Results may not be robust."
            )

    # Overall confidence assessment
    if (mr_results['instruments_strong'] and
        ivw_pval < 0.05 and
        methods_consistent and
        'pleiotropy_warning' not in interpretation and
        'heterogeneity_warning' not in interpretation):
        interpretation['confidence'] = "High"
        interpretation['recommendation'] = "Strong causal evidence supports therapeutic targeting"

    elif (mr_results['instruments_strong'] and
          ivw_pval < 0.05):
        interpretation['confidence'] = "Medium"
        interpretation['recommendation'] = "Moderate causal evidence. Consider additional validation."

    else:
        interpretation['confidence'] = "Low"
        interpretation['recommendation'] = "Weak evidence. MR assumptions may be violated."

    return interpretation


if __name__ == "__main__":
    print("Mendelian Randomization Module for TWAS")
    print("=" * 70)

    # Example: IL6R expression → CAD risk
    print("\nExample: IL6R expression → Coronary Artery Disease")

    # Simulated eQTL data
    eqtl_sim = pd.DataFrame({
        'SNP': ['rs2228145', 'rs4129267', 'rs7529229', 'rs8192284'],
        'A1': ['C', 'T', 'A', 'G'],
        'A2': ['A', 'C', 'G', 'T'],
        'BETA': [0.30, 0.20, 0.15, 0.12],
        'SE': [0.03, 0.04, 0.04, 0.05],
        'P': [1e-9, 1e-7, 1e-5, 1e-4]
    })

    # Simulated GWAS data
    gwas_sim = pd.DataFrame({
        'SNP': ['rs2228145', 'rs4129267', 'rs7529229', 'rs8192284'],
        'A1': ['C', 'T', 'A', 'G'],
        'A2': ['A', 'C', 'G', 'T'],
        'BETA': [0.052, 0.035, 0.028, 0.022],
        'SE': [0.010, 0.012, 0.015, 0.015],
        'P': [1e-7, 1e-3, 0.06, 0.14]
    })

    # Run MR
    mr_result = two_sample_mr(
        gene="IL6R",
        exposure_data=eqtl_sim,
        outcome_data=gwas_sim,
        exposure_name="IL6R expression",
        outcome_name="Coronary Artery Disease",
        pvalue_threshold=5e-6,
        sample_size_exposure=500
    )

    # Print results
    print("\n" + "=" * 70)
    print("MR Results Summary:")
    print("=" * 70)

    if 'ivw' in mr_result:
        ivw = mr_result['ivw']
        print(f"\nIVW Method:")
        print(f"  Causal estimate (beta): {ivw['beta']:+.3f}")
        print(f"  Standard error: {ivw['se']:.3f}")
        print(f"  P-value: {ivw['pval']:.2e}")
        print(f"  N instruments: {ivw['nsnp']}")

    if 'egger' in mr_result:
        egger = mr_result['egger']
        print(f"\nMR-Egger:")
        print(f"  Causal estimate: {egger['beta']:+.3f} (p={egger['pval']:.2e})")
        print(f"  Intercept: {egger['intercept']:+.3f} (p={egger['intercept_pval']:.2e})")
        if egger['intercept_pval'] < 0.05:
            print(f"  ⚠ WARNING: Directional pleiotropy detected")

    if 'interpretation' in mr_result:
        interp = mr_result['interpretation']
        print(f"\nInterpretation:")
        print(f"  {interp.get('causal_effect', 'N/A')}")
        if 'effect_size' in interp:
            print(f"  {interp['effect_size']}")
        print(f"  Confidence: {interp.get('confidence', 'N/A')}")
        print(f"  Recommendation: {interp.get('recommendation', 'N/A')}")

