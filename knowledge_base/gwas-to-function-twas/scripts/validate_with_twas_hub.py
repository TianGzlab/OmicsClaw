"""
Validate TWAS Results Against Published Studies from TWAS Hub

This module compares user-computed TWAS results against published TWAS studies
from TWAS Hub (http://twas-hub.org/) to validate findings and identify novel discoveries.

TWAS Hub contains pre-computed TWAS results from published studies across multiple
traits and tissues. This validation is optional but provides context for:
- Replication of known gene-trait associations
- Novel discoveries not previously reported
- Tissue-specific validation
- Literature context for findings

Functions:
    list_available_traits: List traits available in TWAS Hub
    download_twas_hub_data: Download published TWAS results for a trait
    compare_to_published_twas: Compare user results to TWAS Hub
    plot_replication_comparison: Visualize overlap with published results
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import requests
from pathlib import Path
import gzip
import warnings


def list_available_traits(
    twas_hub_api: str = "http://twas-hub.org/api/traits"
) -> pd.DataFrame:
    """
    List all traits available in TWAS Hub.

    Parameters
    ----------
    twas_hub_api : str
        TWAS Hub API endpoint for trait listing

    Returns
    -------
    pd.DataFrame
        DataFrame with columns: trait_id, trait_name, pmid, study_name, n_genes

    Examples
    --------
    >>> traits = list_available_traits()
    >>> print(traits[traits['trait_name'].str.contains('coronary')])
    """
    try:
        response = requests.get(twas_hub_api, timeout=10)
        response.raise_for_status()
        traits_data = response.json()

        traits_df = pd.DataFrame(traits_data)
        return traits_df

    except requests.exceptions.RequestException as e:
        warnings.warn(
            f"Could not connect to TWAS Hub API: {e}\n"
            "Please check internet connection or visit http://twas-hub.org manually"
        )
        return pd.DataFrame()


def download_twas_hub_data(
    trait: str,
    tissue: Optional[str] = None,
    output_dir: str = "data/twas_hub/",
    force_redownload: bool = False
) -> pd.DataFrame:
    """
    Download published TWAS results from TWAS Hub for a specific trait.

    Parameters
    ----------
    trait : str
        Trait identifier (e.g., 'coronary_artery_disease', 'type_2_diabetes')
        Use list_available_traits() to see available options
    tissue : str, optional
        Specific tissue to download (e.g., 'Artery_Coronary')
        If None, downloads all tissues
    output_dir : str
        Directory to save downloaded data
    force_redownload : bool
        If True, redownload even if file exists

    Returns
    -------
    pd.DataFrame
        Published TWAS results with columns: gene, tissue, twas_z, twas_p, pmid

    Examples
    --------
    >>> published_results = download_twas_hub_data(
    ...     trait='coronary_artery_disease',
    ...     tissue='Artery_Coronary'
    ... )
    """
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Construct filename
    tissue_suffix = f"_{tissue}" if tissue else "_all_tissues"
    cache_file = output_path / f"{trait}{tissue_suffix}_twashub.csv.gz"

    # Check if already downloaded
    if cache_file.exists() and not force_redownload:
        print(f"Loading cached TWAS Hub data from {cache_file}")
        return pd.read_csv(cache_file, compression='gzip')

    # Download from TWAS Hub
    print(f"Downloading TWAS Hub data for {trait}...")

    # TWAS Hub API endpoint (example - adjust based on actual API)
    api_url = f"http://twas-hub.org/api/results/{trait}"
    if tissue:
        api_url += f"?tissue={tissue}"

    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()

        # Parse results
        results_data = response.json()
        published_df = pd.DataFrame(results_data)

        # Standardize column names
        column_mapping = {
            'gene_id': 'gene',
            'gene_name': 'gene',
            'z_score': 'twas_z',
            'pvalue': 'twas_p',
            'p_value': 'twas_p'
        }
        published_df = published_df.rename(columns=column_mapping)

        # Save to cache
        published_df.to_csv(cache_file, index=False, compression='gzip')
        print(f"Cached TWAS Hub data to {cache_file}")

        return published_df

    except requests.exceptions.RequestException as e:
        warnings.warn(
            f"Could not download from TWAS Hub: {e}\n"
            "Continuing without validation data. "
            "Visit http://twas-hub.org to manually download results."
        )
        return pd.DataFrame()


def compare_to_published_twas(
    your_twas_results: pd.DataFrame,
    trait: str,
    tissue: str,
    twas_hub_download_dir: str = "data/twas_hub/",
    significance_threshold: float = 0.05,
    bonferroni_correction: bool = True,
    overlap_threshold: float = 0.5
) -> Dict:
    """
    Compare user TWAS results to published results from TWAS Hub.

    Provides validation by checking:
    - Replication rate (proportion of published genes found in your results)
    - Novel discoveries (genes significant in your results but not published)
    - Effect size concordance (sign agreement between studies)
    - Tissue specificity validation

    Parameters
    ----------
    your_twas_results : pd.DataFrame
        Your TWAS results with columns: gene, TWAS.Z or effect, TWAS.P or pvalue
    trait : str
        Trait identifier matching TWAS Hub (e.g., 'coronary_artery_disease')
    tissue : str
        Tissue name (e.g., 'Artery_Coronary')
    twas_hub_download_dir : str
        Directory for TWAS Hub cached data
    significance_threshold : float
        P-value threshold for significance (default: 0.05)
    bonferroni_correction : bool
        If True, apply Bonferroni correction to threshold
    overlap_threshold : float
        Minimum proportion of published genes to replicate (0.5 = 50%)

    Returns
    -------
    dict
        Validation results with keys:
        - replication_rate: proportion of published genes replicated
        - novel_genes: list of genes significant in your data but not published
        - replicated_genes: list of genes significant in both studies
        - effect_concordance: proportion with same direction of effect
        - validation_summary: text interpretation

    Examples
    --------
    >>> validation = compare_to_published_twas(
    ...     your_twas_results=fusion_results,
    ...     trait='coronary_artery_disease',
    ...     tissue='Artery_Coronary'
    ... )
    >>> print(f"Replication rate: {validation['replication_rate']:.1%}")
    >>> print(f"Novel discoveries: {len(validation['novel_genes'])} genes")
    """
    # Download published results
    published_results = download_twas_hub_data(
        trait=trait,
        tissue=tissue,
        output_dir=twas_hub_download_dir
    )

    if published_results.empty:
        return {
            'replication_rate': None,
            'novel_genes': [],
            'replicated_genes': [],
            'effect_concordance': None,
            'validation_summary': "No published TWAS data available for comparison"
        }

    # Standardize column names in user results
    user_results = your_twas_results.copy()
    if 'TWAS.Z' in user_results.columns:
        user_results['twas_z'] = user_results['TWAS.Z']
        user_results['twas_p'] = user_results['TWAS.P']
    elif 'effect' in user_results.columns:
        # S-PrediXcan format
        user_results['twas_z'] = user_results['effect'] / user_results['effect_se']
        user_results['twas_p'] = user_results['pvalue']

    # Standardize gene names (uppercase, remove version numbers)
    user_results['gene_clean'] = user_results['gene'].str.upper().str.split('.').str[0]
    published_results['gene_clean'] = published_results['gene'].str.upper().str.split('.').str[0]

    # Apply significance threshold
    if bonferroni_correction:
        user_threshold = significance_threshold / len(user_results)
        published_threshold = significance_threshold / len(published_results)
    else:
        user_threshold = significance_threshold
        published_threshold = significance_threshold

    # Identify significant genes
    user_sig = user_results[user_results['twas_p'] < user_threshold]['gene_clean'].tolist()
    published_sig = published_results[published_results['twas_p'] < published_threshold]['gene_clean'].tolist()

    # Calculate overlap
    replicated_genes = list(set(user_sig) & set(published_sig))
    novel_genes = list(set(user_sig) - set(published_sig))
    missed_genes = list(set(published_sig) - set(user_sig))

    # Replication rate
    if len(published_sig) > 0:
        replication_rate = len(replicated_genes) / len(published_sig)
    else:
        replication_rate = 0.0

    # Effect size concordance (same direction)
    if len(replicated_genes) > 0:
        merged = user_results[user_results['gene_clean'].isin(replicated_genes)].merge(
            published_results[published_results['gene_clean'].isin(replicated_genes)],
            on='gene_clean',
            suffixes=('_user', '_published')
        )

        concordant = (np.sign(merged['twas_z_user']) == np.sign(merged['twas_z_published'])).sum()
        effect_concordance = concordant / len(merged)
    else:
        effect_concordance = None

    # Validation summary
    summary_lines = []

    summary_lines.append(f"TWAS Hub Validation for {trait} ({tissue})")
    summary_lines.append(f"{'='*60}")
    summary_lines.append(f"Published significant genes: {len(published_sig)}")
    summary_lines.append(f"Your significant genes: {len(user_sig)}")
    summary_lines.append(f"Replicated genes: {len(replicated_genes)} ({replication_rate:.1%})")
    summary_lines.append(f"Novel discoveries: {len(novel_genes)}")
    summary_lines.append(f"Missed genes: {len(missed_genes)}")

    if effect_concordance is not None:
        summary_lines.append(f"Effect direction concordance: {effect_concordance:.1%}")

    # Interpretation
    summary_lines.append("")
    if replication_rate >= overlap_threshold:
        summary_lines.append(f"✓ GOOD: Replication rate ({replication_rate:.1%}) meets threshold ({overlap_threshold:.1%})")
    elif replication_rate >= 0.3:
        summary_lines.append(f"⚠ MODERATE: Replication rate ({replication_rate:.1%}) below threshold but acceptable")
    else:
        summary_lines.append(f"✗ POOR: Low replication rate ({replication_rate:.1%}). Check for:")
        summary_lines.append("  - Different ancestry populations")
        summary_lines.append("  - Different phenotype definitions")
        summary_lines.append("  - Statistical power differences")

    if effect_concordance is not None and effect_concordance < 0.8:
        summary_lines.append(f"⚠ WARNING: Effect directions disagree for {(1-effect_concordance):.1%} of replicated genes")

    validation_summary = '\n'.join(summary_lines)

    return {
        'replication_rate': replication_rate,
        'novel_genes': novel_genes,
        'replicated_genes': replicated_genes,
        'missed_genes': missed_genes,
        'effect_concordance': effect_concordance,
        'n_published': len(published_sig),
        'n_user': len(user_sig),
        'validation_summary': validation_summary,
        'merged_data': merged if len(replicated_genes) > 0 else None
    }


def plot_replication_comparison(
    validation_results: Dict,
    your_twas_results: pd.DataFrame,
    output_file: str = "figures/twas_hub_validation.svg"
) -> None:
    """
    Create visualization comparing user TWAS results to published results.

    Generates two plots:
    1. Venn diagram showing overlap between significant genes
    2. Effect size comparison scatter plot for replicated genes

    Parameters
    ----------
    validation_results : dict
        Output from compare_to_published_twas()
    your_twas_results : pd.DataFrame
        User TWAS results
    output_file : str
        Path to save plot (SVG format recommended)

    Examples
    --------
    >>> plot_replication_comparison(
    ...     validation_results=validation,
    ...     your_twas_results=fusion_results,
    ...     output_file="figures/cad_validation.svg"
    ... )
    """
    from plotnine import (
        ggplot, aes, geom_point, geom_abline, geom_text,
        labs, theme_minimal, scale_color_manual
    )
    from plotnine_prism import theme_prism
    import matplotlib.pyplot as plt
    from matplotlib_venn import venn2

    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Plot 1: Venn diagram
    venn2(
        subsets=(
            validation_results['n_user'] - len(validation_results['replicated_genes']),
            validation_results['n_published'] - len(validation_results['replicated_genes']),
            len(validation_results['replicated_genes'])
        ),
        set_labels=('Your Study', 'Published (TWAS Hub)'),
        ax=ax1
    )
    ax1.set_title('Significant Gene Overlap')

    # Plot 2: Effect size comparison (if replicated genes exist)
    if validation_results['merged_data'] is not None and len(validation_results['merged_data']) > 0:
        merged = validation_results['merged_data']

        # Create plotnine scatter plot
        p = (
            ggplot(merged, aes(x='twas_z_published', y='twas_z_user'))
            + geom_point(aes(color='abs(twas_z_user) > 3.0'), size=2, alpha=0.6)
            + geom_abline(intercept=0, slope=1, linetype='dashed', color='red')
            + scale_color_manual(values=['#666666', '#D62728'])
            + labs(
                x='Published TWAS Z-score',
                y='Your TWAS Z-score',
                title='Effect Size Concordance'
            )
            + theme_prism()
        )

        # Save plotnine plot to second axis (requires conversion)
        p.save(output_file.replace('.svg', '_scatter.svg'), dpi=300)

        # For combined figure, use matplotlib scatter
        ax2.scatter(
            merged['twas_z_published'],
            merged['twas_z_user'],
            c=['#D62728' if abs(z) > 3.0 else '#666666' for z in merged['twas_z_user']],
            alpha=0.6,
            s=50
        )
        ax2.plot([-10, 10], [-10, 10], 'r--', alpha=0.5)
        ax2.set_xlabel('Published TWAS Z-score')
        ax2.set_ylabel('Your TWAS Z-score')
        ax2.set_title('Effect Size Concordance')
        ax2.grid(True, alpha=0.3)

        # Add concordance rate
        if validation_results['effect_concordance'] is not None:
            ax2.text(
                0.05, 0.95,
                f"Concordance: {validation_results['effect_concordance']:.1%}",
                transform=ax2.transAxes,
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5)
            )

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Validation plot saved to {output_file}")


# Example usage
if __name__ == "__main__":
    # Example: List available traits
    print("Fetching available traits from TWAS Hub...")
    traits = list_available_traits()

    if not traits.empty:
        print("\nAvailable traits (showing first 10):")
        print(traits.head(10))

    # Example validation workflow
    print("\nExample validation workflow:")
    print("1. Download published TWAS results")
    print("   published = download_twas_hub_data('coronary_artery_disease', 'Artery_Coronary')")
    print("\n2. Compare to your results")
    print("   validation = compare_to_published_twas(your_results, 'coronary_artery_disease', 'Artery_Coronary')")
    print("\n3. Visualize comparison")
    print("   plot_replication_comparison(validation, your_results)")

