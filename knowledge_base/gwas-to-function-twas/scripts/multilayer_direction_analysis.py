"""
Multi-layer directionality analysis for TWAS results.

This module validates therapeutic directionality by checking consistency across:
1. eQTL layer: Risk allele → Gene expression change
2. TWAS layer: Predicted expression → Trait change
3. Combined: Risk allele → Expression → Trait causal pathway

Consistent directionality across layers increases confidence in therapeutic strategy.

Author: Claude Code (Anthropic)
Date: 2026-01-28
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional


def analyze_directionality_layers(
    gene: str,
    gwas_sumstats: pd.DataFrame,
    eqtl_data: pd.DataFrame,
    twas_results: pd.DataFrame,
    coloc_results: Optional[pd.DataFrame] = None,
    lead_snp: Optional[str] = None
) -> Dict:
    """
    Analyze directional consistency across eQTL and TWAS layers.

    Parameters
    ----------
    gene : str
        Gene symbol to analyze
    gwas_sumstats : pd.DataFrame
        GWAS summary statistics with columns: SNP, CHR, BP, A1, A2, BETA, SE, P
        BETA is the effect size of A1 (effect allele) on trait
    eqtl_data : pd.DataFrame
        eQTL summary statistics for the gene with columns: SNP, BETA, P
        BETA is the effect size of effect allele on gene expression
    twas_results : pd.DataFrame
        TWAS results with columns: GENE, TWAS.Z, TWAS.P
    coloc_results : pd.DataFrame, optional
        Colocalization results with columns: GENE, PP.H4, lead_SNP
    lead_snp : str, optional
        Manually specify lead SNP if not provided in coloc_results

    Returns
    -------
    dict
        Dictionary with multi-layer directionality analysis:
        - gene: Gene symbol
        - lead_eqtl_snp: Lead eQTL variant
        - gwas_lead_snp: Lead GWAS variant in region
        - eqtl_layer: Direction at eQTL layer
        - twas_layer: Direction at TWAS layer
        - combined_pathway: Full causal pathway description
        - directional_consistency: Whether directions are consistent
        - therapeutic_action: Recommended therapeutic strategy
        - confidence: Confidence level based on consistency and colocalization

    Examples
    --------
    >>> # IL6R example: Risk allele increases expression, expression increases CAD
    >>> layers = analyze_directionality_layers(
    ...     gene="IL6R",
    ...     gwas_sumstats=gwas_df,
    ...     eqtl_data=eqtl_df,
    ...     twas_results=twas_df,
    ...     coloc_results=coloc_df
    ... )
    >>> print(layers['combined_pathway'])
    'Risk allele (rs2228145-C) → ↑ IL6R Expression → ↑ CAD Risk'
    >>> print(layers['therapeutic_action'])
    'INHIBIT gene expression'
    """

    result = {
        "gene": gene,
        "layers": {}
    }

    # Extract TWAS results for this gene
    gene_twas = twas_results[twas_results['GENE'] == gene]
    if len(gene_twas) == 0:
        result["error"] = f"Gene {gene} not found in TWAS results"
        return result

    twas_z = gene_twas.iloc[0]['TWAS.Z']
    twas_p = gene_twas.iloc[0]['TWAS.P']

    # Determine lead SNP
    if lead_snp is None:
        if coloc_results is not None:
            gene_coloc = coloc_results[coloc_results['GENE'] == gene]
            if len(gene_coloc) > 0 and 'lead_SNP' in gene_coloc.columns:
                lead_snp = gene_coloc.iloc[0]['lead_SNP']

        # If still None, use lead eQTL SNP
        if lead_snp is None:
            lead_snp = eqtl_data.loc[eqtl_data['P'].idxmin(), 'SNP']

    result['lead_eqtl_snp'] = lead_snp

    # Extract effect sizes for lead SNP
    eqtl_lead = eqtl_data[eqtl_data['SNP'] == lead_snp]
    if len(eqtl_lead) == 0:
        result["error"] = f"Lead SNP {lead_snp} not found in eQTL data"
        return result

    eqtl_beta = eqtl_lead.iloc[0]['BETA']  # Effect on expression
    eqtl_p = eqtl_lead.iloc[0]['P']

    # Get GWAS effect for the same SNP
    gwas_lead = gwas_sumstats[gwas_sumstats['SNP'] == lead_snp]
    if len(gwas_lead) == 0:
        result["warning"] = f"Lead SNP {lead_snp} not found in GWAS data"
        gwas_beta = np.nan
    else:
        gwas_beta = gwas_lead.iloc[0]['BETA']  # Effect on trait

    result['gwas_lead_snp'] = lead_snp

    # Layer 1: eQTL direction (Risk allele → Expression)
    # Positive eQTL beta = risk allele increases expression
    # Negative eQTL beta = risk allele decreases expression
    if gwas_beta > 0:  # Risk allele increases trait (risk)
        if eqtl_beta > 0:
            eqtl_interpretation = "Risk allele increases expression"
            eqtl_arrow = "↑"
        else:
            eqtl_interpretation = "Risk allele decreases expression"
            eqtl_arrow = "↓"
    else:  # Protective allele (decreases trait risk)
        if eqtl_beta > 0:
            eqtl_interpretation = "Protective allele increases expression"
            eqtl_arrow = "↑"
        else:
            eqtl_interpretation = "Protective allele decreases expression"
            eqtl_arrow = "↓"

    result['layers']['eqtl'] = {
        "lead_snp": lead_snp,
        "eqtl_beta": eqtl_beta,
        "eqtl_pvalue": eqtl_p,
        "interpretation": eqtl_interpretation,
        "direction_arrow": eqtl_arrow
    }

    # Layer 2: TWAS direction (Predicted expression → Trait)
    # Positive TWAS Z = higher expression increases trait
    # Negative TWAS Z = higher expression decreases trait
    if twas_z > 0:
        twas_interpretation = "Higher expression increases trait"
        twas_arrow = "↑"
    else:
        twas_interpretation = "Higher expression decreases trait"
        twas_arrow = "↓"

    result['layers']['twas'] = {
        "twas_z": twas_z,
        "twas_pvalue": twas_p,
        "interpretation": twas_interpretation,
        "direction_arrow": twas_arrow
    }

    # Layer 3: Combined pathway interpretation
    # Check for directional consistency
    # If both eQTL and TWAS point in same direction relative to risk allele,
    # we have consistent causal pathway

    # Combined effect: eQTL direction * TWAS direction
    # If risk allele increases expression AND expression increases risk → Inhibit
    # If risk allele decreases expression AND expression increases risk → Activate
    # If risk allele increases expression AND expression decreases risk → Activate
    # If risk allele decreases expression AND expression decreases risk → Inhibit

    combined_effect = np.sign(eqtl_beta) * np.sign(twas_z)

    if combined_effect > 0:
        # Same direction: risk allele acts through expression in same direction
        if twas_z > 0:  # Expression increases risk
            pathway = f"Risk allele → {eqtl_arrow} {gene} Expression → {twas_arrow} Trait Risk"
            therapeutic_action = "INHIBIT gene expression"
            consistency = "Consistent"
        else:  # Expression decreases risk
            pathway = f"Risk allele → {eqtl_arrow} {gene} Expression → {twas_arrow} Trait Risk"
            therapeutic_action = "ACTIVATE gene expression"
            consistency = "Consistent"
    else:
        # Opposite directions: more complex interpretation
        pathway = f"Risk allele → {eqtl_arrow} {gene} Expression → {twas_arrow} Trait Risk"

        if eqtl_beta > 0 and twas_z < 0:
            # Risk allele increases expression, but expression decreases risk
            therapeutic_action = "ACTIVATE gene expression (complex: risk allele paradoxically increases protective expression)"
            consistency = "Paradoxical (may indicate feedback loops or multi-pathway effects)"
        elif eqtl_beta < 0 and twas_z > 0:
            # Risk allele decreases expression, and expression would increase risk
            therapeutic_action = "Unclear - risk allele already decreases expression which should be protective"
            consistency = "Inconsistent (recheck allele harmonization)"
        else:
            therapeutic_action = "Requires further investigation"
            consistency = "Unclear"

    result['combined_pathway'] = pathway
    result['directional_consistency'] = consistency
    result['therapeutic_action'] = therapeutic_action

    # Confidence assessment
    confidence_factors = []

    # Factor 1: Statistical significance
    if eqtl_p < 5e-8 and twas_p < 0.05 / 20000:
        confidence_factors.append("Strong statistical evidence")
    elif eqtl_p < 1e-5 and twas_p < 0.001:
        confidence_factors.append("Moderate statistical evidence")
    else:
        confidence_factors.append("Weak statistical evidence")

    # Factor 2: Colocalization
    if coloc_results is not None:
        gene_coloc = coloc_results[coloc_results['GENE'] == gene]
        if len(gene_coloc) > 0 and 'PP.H4' in gene_coloc.columns:
            pp4 = gene_coloc.iloc[0]['PP.H4']
            result['coloc_pp4'] = pp4

            if pp4 > 0.8:
                confidence_factors.append("Strong colocalization (PP.H4 > 0.8)")
            elif pp4 > 0.5:
                confidence_factors.append("Moderate colocalization (PP.H4 = 0.5-0.8)")
            else:
                confidence_factors.append("Weak colocalization (PP.H4 < 0.5) - likely LD artifact")

    # Factor 3: Directional consistency
    if consistency == "Consistent":
        confidence_factors.append("Consistent directionality across layers")
    elif consistency == "Paradoxical":
        confidence_factors.append("Paradoxical directionality - complex regulation")
    else:
        confidence_factors.append("Inconsistent directionality - requires investigation")

    # Overall confidence
    if ("Strong statistical" in confidence_factors[0] and
        "Strong colocalization" in str(confidence_factors) and
        consistency == "Consistent"):
        overall_confidence = "High"
    elif ("Weak colocalization" in str(confidence_factors) or
          consistency == "Inconsistent"):
        overall_confidence = "Low"
    else:
        overall_confidence = "Medium"

    result['confidence'] = overall_confidence
    result['confidence_factors'] = confidence_factors

    return result


def batch_multilayer_analysis(
    genes: List[str],
    gwas_sumstats: pd.DataFrame,
    eqtl_data_dict: Dict[str, pd.DataFrame],
    twas_results: pd.DataFrame,
    coloc_results: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Batch process multiple genes for multi-layer directionality analysis.

    Parameters
    ----------
    genes : list
        List of gene symbols to analyze
    gwas_sumstats : pd.DataFrame
        GWAS summary statistics
    eqtl_data_dict : dict
        Dictionary mapping gene symbols to eQTL DataFrames
    twas_results : pd.DataFrame
        TWAS results for all genes
    coloc_results : pd.DataFrame, optional
        Colocalization results

    Returns
    -------
    pd.DataFrame
        DataFrame with multi-layer analysis results for all genes

    Examples
    --------
    >>> eqtl_dict = {
    ...     'IL6R': il6r_eqtl_df,
    ...     'PCSK9': pcsk9_eqtl_df,
    ...     'SORT1': sort1_eqtl_df
    ... }
    >>> multilayer_df = batch_multilayer_analysis(
    ...     genes=['IL6R', 'PCSK9', 'SORT1'],
    ...     gwas_sumstats=gwas_df,
    ...     eqtl_data_dict=eqtl_dict,
    ...     twas_results=twas_df,
    ...     coloc_results=coloc_df
    ... )
    """

    results = []

    for gene in genes:
        if gene not in eqtl_data_dict:
            print(f"Warning: eQTL data not available for {gene}, skipping...")
            continue

        eqtl_data = eqtl_data_dict[gene]

        layer_result = analyze_directionality_layers(
            gene=gene,
            gwas_sumstats=gwas_sumstats,
            eqtl_data=eqtl_data,
            twas_results=twas_results,
            coloc_results=coloc_results
        )

        # Flatten result for DataFrame
        flat_result = {
            'gene': layer_result['gene'],
            'lead_eqtl_snp': layer_result.get('lead_eqtl_snp'),
            'eqtl_beta': layer_result['layers']['eqtl']['eqtl_beta'],
            'eqtl_direction': layer_result['layers']['eqtl']['interpretation'],
            'twas_z': layer_result['layers']['twas']['twas_z'],
            'twas_direction': layer_result['layers']['twas']['interpretation'],
            'combined_pathway': layer_result['combined_pathway'],
            'directional_consistency': layer_result['directional_consistency'],
            'therapeutic_action': layer_result['therapeutic_action'],
            'confidence': layer_result['confidence']
        }

        if 'coloc_pp4' in layer_result:
            flat_result['coloc_pp4'] = layer_result['coloc_pp4']

        results.append(flat_result)

    return pd.DataFrame(results)


def visualize_pathway(
    gene: str,
    multilayer_result: Dict,
    output_file: Optional[str] = None
):
    """
    Create ASCII art visualization of the causal pathway.

    Parameters
    ----------
    gene : str
        Gene symbol
    multilayer_result : dict
        Result from analyze_directionality_layers
    output_file : str, optional
        File to save visualization (if None, prints to console)

    Examples
    --------
    >>> layers = analyze_directionality_layers(...)
    >>> visualize_pathway("IL6R", layers)

    Output:
    ┌─────────────────────────────────────────────────────────────┐
    │  IL6R Causal Pathway                                        │
    ├─────────────────────────────────────────────────────────────┤
    │                                                              │
    │  Risk Variant    →    Gene Expression    →    Disease Risk  │
    │  rs2228145-C     →    ↑ IL6R Expression  →    ↑ CAD Risk   │
    │                                                              │
    │  Therapeutic Strategy: INHIBIT IL6R expression               │
    │  Confidence: High                                           │
    └─────────────────────────────────────────────────────────────┘
    """

    pathway_viz = f"""
┌─────────────────────────────────────────────────────────────────────┐
│  {gene} Causal Pathway - Multi-Layer Directionality Analysis        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Layer 1: eQTL (Risk Variant → Gene Expression)                    │
│    {multilayer_result['layers']['eqtl']['interpretation']:50s}      │
│    Lead SNP: {multilayer_result['lead_eqtl_snp']:20s}               │
│    eQTL Beta: {multilayer_result['layers']['eqtl']['eqtl_beta']:+.3f} │
│                                                                     │
│  Layer 2: TWAS (Gene Expression → Trait)                           │
│    {multilayer_result['layers']['twas']['interpretation']:50s}      │
│    TWAS Z-score: {multilayer_result['layers']['twas']['twas_z']:+.3f} │
│                                                                     │
│  Combined Pathway:                                                  │
│    {multilayer_result['combined_pathway']:60s}                      │
│                                                                     │
│  Directional Consistency: {multilayer_result['directional_consistency']:30s} │
│  Therapeutic Strategy: {multilayer_result['therapeutic_action']:35s}    │
│  Confidence Level: {multilayer_result['confidence']:40s}                │
│                                                                     │
│  Evidence:                                                          │
"""

    for factor in multilayer_result.get('confidence_factors', []):
        pathway_viz += f"│    • {factor:60s}  │\n"

    pathway_viz += "└─────────────────────────────────────────────────────────────────────┘"

    if output_file:
        with open(output_file, 'w') as f:
            f.write(pathway_viz)
        print(f"Pathway visualization saved to {output_file}")
    else:
        print(pathway_viz)

    return pathway_viz


if __name__ == "__main__":
    print("Multi-Layer Directionality Analysis Module")
    print("=" * 70)

    # Example data
    print("\nExample: IL6R multi-layer analysis")

    # Simulated data
    gwas_sim = pd.DataFrame({
        'SNP': ['rs2228145', 'rs4129267', 'rs7529229'],
        'CHR': [1, 1, 1],
        'BP': [154426970, 154426980, 154427000],
        'A1': ['C', 'T', 'A'],
        'A2': ['A', 'C', 'G'],
        'BETA': [0.05, 0.03, 0.02],  # Risk allele increases CAD
        'SE': [0.01, 0.01, 0.01],
        'P': [1e-7, 1e-5, 1e-4]
    })

    eqtl_sim = pd.DataFrame({
        'SNP': ['rs2228145', 'rs4129267', 'rs7529229'],
        'BETA': [0.3, 0.2, 0.15],  # Risk allele increases IL6R expression
        'SE': [0.05, 0.05, 0.05],
        'P': [1e-9, 1e-7, 1e-6]
    })

    twas_sim = pd.DataFrame({
        'GENE': ['IL6R', 'PCSK9', 'SORT1'],
        'TWAS.Z': [4.52, 3.87, -3.21],  # Positive = higher expression → higher trait
        'TWAS.P': [1.2e-6, 2.3e-5, 5.1e-4]
    })

    coloc_sim = pd.DataFrame({
        'GENE': ['IL6R', 'PCSK9', 'SORT1'],
        'PP.H4': [0.92, 0.88, 0.65],
        'lead_SNP': ['rs2228145', 'rs11591147', 'rs646776']
    })

    # Run analysis
    il6r_layers = analyze_directionality_layers(
        gene="IL6R",
        gwas_sumstats=gwas_sim,
        eqtl_data=eqtl_sim,
        twas_results=twas_sim,
        coloc_results=coloc_sim
    )

    # Visualize
    visualize_pathway("IL6R", il6r_layers)

    print("\n" + "=" * 70)
    print("Key insights:")
    print(f"  Combined pathway: {il6r_layers['combined_pathway']}")
    print(f"  Therapeutic action: {il6r_layers['therapeutic_action']}")
    print(f"  Confidence: {il6r_layers['confidence']}")

