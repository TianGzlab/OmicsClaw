"""
Druggability Assessment for TWAS Targets

This module provides functions for evaluating therapeutic feasibility of TWAS genes
based on protein class, known drugs, and structural features.
"""

import pandas as pd


# Druggable protein classes
TIER1_CLASSES = ['kinase', 'gpcr', 'ion channel', 'nuclear receptor', 'protease']
TIER2_CLASSES = ['enzyme', 'transporter', 'peptidase', 'phosphatase', 'transferase']
TIER3_CLASSES = ['transcription factor', 'adaptor', 'scaffold', 'structural']


def assess_druggability(genes, include_known_drugs=True, include_protein_class=True,
                        include_ppi_inhibitors=False):
    """
    Assess druggability of gene targets.

    Parameters
    ----------
    genes : list
        List of gene symbols
    include_known_drugs : bool
        Include known drug information from DrugBank/ChEMBL (default: True)
    include_protein_class : bool
        Include protein class annotations (default: True)
    include_ppi_inhibitors : bool
        Consider protein-protein interaction inhibitors (default: False)

    Returns
    -------
    pandas.DataFrame
        Druggability scores and annotations
    """
    print(f"Assessing druggability for {len(genes)} genes...")

    results = []

    for gene in genes:
        # Get protein class (placeholder - would query UniProt/InterPro)
        protein_class = get_protein_class(gene)

        # Determine druggability tier
        druggability_tier = classify_druggability(protein_class, include_ppi_inhibitors)

        # Get known drugs (placeholder - would query DrugBank/ChEMBL)
        known_drugs = get_known_drugs(gene) if include_known_drugs else []

        # Calculate druggability score (0-1)
        druggability_score = calculate_druggability_score(
            druggability_tier,
            len(known_drugs),
            protein_class
        )

        # Check for clinical precedent
        clinical_precedent = len(known_drugs) > 0

        results.append({
            'gene': gene,
            'protein_class': protein_class,
            'druggability_tier': druggability_tier,
            'druggability_score': druggability_score,
            'known_drugs': '; '.join(known_drugs) if known_drugs else 'None',
            'n_known_drugs': len(known_drugs),
            'clinical_precedent': clinical_precedent
        })

    druggability_df = pd.DataFrame(results)

    print(f"\nDruggability summary:")
    print(f"  Tier 1 (High): {(druggability_df['druggability_tier'] == 'Tier 1').sum()}")
    print(f"  Tier 2 (Medium): {(druggability_df['druggability_tier'] == 'Tier 2').sum()}")
    print(f"  Tier 3 (Low): {(druggability_df['druggability_tier'] == 'Tier 3').sum()}")
    print(f"  Tier 4 (Very Low): {(druggability_df['druggability_tier'] == 'Tier 4').sum()}")
    print(f"  Genes with known drugs: {druggability_df['clinical_precedent'].sum()}")

    return druggability_df


def get_protein_class(gene):
    """
    Get protein class annotation for gene.

    Parameters
    ----------
    gene : str
        Gene symbol

    Returns
    -------
    str
        Protein class
    """
    # Placeholder - would query UniProt API
    # For demonstration, return example values
    protein_classes = {
        'IL6R': 'gpcr',
        'PCSK9': 'protease',
        'SORT1': 'transporter',
        'HMGCR': 'enzyme'
    }

    return protein_classes.get(gene, 'unknown')


def classify_druggability(protein_class, include_ppi=False):
    """
    Classify druggability tier based on protein class.

    Parameters
    ----------
    protein_class : str
        Protein class annotation
    include_ppi : bool
        Whether to consider PPI inhibitors druggable

    Returns
    -------
    str
        Druggability tier (Tier 1-4)
    """
    protein_class_lower = protein_class.lower()

    if any(cls in protein_class_lower for cls in TIER1_CLASSES):
        return 'Tier 1'
    elif any(cls in protein_class_lower for cls in TIER2_CLASSES):
        return 'Tier 2'
    elif any(cls in protein_class_lower for cls in TIER3_CLASSES):
        if include_ppi:
            return 'Tier 2'  # Upgrade if PPI inhibitors considered
        else:
            return 'Tier 3'
    else:
        return 'Tier 4'


def get_known_drugs(gene):
    """
    Get known drugs targeting gene.

    Parameters
    ----------
    gene : str
        Gene symbol

    Returns
    -------
    list
        List of drug names
    """
    # Placeholder - would query DrugBank/ChEMBL APIs
    known_drugs_db = {
        'IL6R': ['Tocilizumab', 'Sarilumab'],
        'PCSK9': ['Evolocumab', 'Alirocumab'],
        'HMGCR': ['Atorvastatin', 'Simvastatin', 'Rosuvastatin']
    }

    return known_drugs_db.get(gene, [])


def calculate_druggability_score(tier, n_drugs, protein_class):
    """
    Calculate composite druggability score (0-1).

    Parameters
    ----------
    tier : str
        Druggability tier
    n_drugs : int
        Number of known drugs
    protein_class : str
        Protein class

    Returns
    -------
    float
        Druggability score (0-1)
    """
    # Base score from tier
    tier_scores = {
        'Tier 1': 0.9,
        'Tier 2': 0.6,
        'Tier 3': 0.3,
        'Tier 4': 0.1
    }

    base_score = tier_scores.get(tier, 0.1)

    # Boost for known drugs
    drug_boost = min(n_drugs * 0.05, 0.1)

    # Final score (capped at 1.0)
    final_score = min(base_score + drug_boost, 1.0)

    return final_score

