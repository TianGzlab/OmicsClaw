"""
Tool Selection Module for Variant Annotation

This module provides logic for automatically selecting between Ensembl VEP
and SNPEff based on organism, use case, resources, and annotation priorities.
"""


def select_annotation_tool(organism, use_case, resources, annotation_priorities):
    """
    Automatically select VEP or SNPEff based on use case and requirements.

    Parameters
    ----------
    organism : str
        Target organism ('human', 'mouse', 'rat', 'zebrafish', 'drosophila',
        'celegans', or other)
    use_case : str
        Primary analysis purpose ('clinical', 'population', 'cancer', 'research')
    resources : str
        Available computational resources ('high-performance', 'standard', 'limited')
    annotation_priorities : list
        List of required annotation types (e.g., ['clinical_significance',
        'pathogenicity_predictions', 'regulatory_impacts'])

    Returns
    -------
    str
        'vep' or 'snpeff' with reasoning

    Examples
    --------
    >>> select_annotation_tool('human', 'clinical', 'high-performance',
    ...                        ['clinical_significance', 'pathogenicity_predictions'])
    'vep'

    >>> select_annotation_tool('zebrafish', 'research', 'limited', ['basic'])
    'snpeff'
    """
    model_organisms = ['human', 'mouse', 'rat', 'zebrafish', 'drosophila', 'celegans']

    # Non-model organism → SNPEff (38,000+ genomes)
    if organism.lower() not in model_organisms:
        return 'snpeff'

    # Limited resources → SNPEff (faster, smaller cache)
    if resources == 'limited':
        return 'snpeff'

    # Clinical use case with comprehensive annotations → VEP
    if use_case == 'clinical' and 'clinical_significance' in annotation_priorities:
        return 'vep'

    # Regulatory annotations important → VEP (ENCODE integration)
    if 'regulatory_impacts' in annotation_priorities:
        return 'vep'

    # Multiple pathogenicity predictors needed → VEP (more plugins)
    pathogenicity_tools = ['pathogenicity_predictions', 'protein_domains', 'conservation_scores']
    if len([p for p in pathogenicity_tools if p in annotation_priorities]) >= 2:
        return 'vep'

    # Default: VEP for human (most comprehensive), SNPEff otherwise
    return 'vep' if organism.lower() == 'human' else 'snpeff'


def get_vep_recommended_config(use_case, annotation_priorities):
    """
    Get recommended VEP configuration based on use case.

    Parameters
    ----------
    use_case : str
        Primary analysis purpose
    annotation_priorities : list
        Required annotation types

    Returns
    -------
    dict
        Recommended VEP parameters
    """
    config = {
        'everything': True,
        'vcf': True,
        'force_overwrite': True,
        'fork': 4,
        'buffer_size': 5000
    }

    # Clinical use case
    if use_case == 'clinical':
        config['plugins'] = ['CADD', 'dbNSFP,ALL', 'REVEL']
        config['clinical_annotations'] = True
        config['check_existing'] = True

    # Add specific plugins based on priorities
    if 'conservation_scores' in annotation_priorities:
        if 'plugins' not in config:
            config['plugins'] = []
        config['plugins'].extend(['Conservation', 'Blosum62'])

    if 'regulatory_impacts' in annotation_priorities:
        config['regulatory'] = True

    # Population frequencies
    if 'population_frequencies' in annotation_priorities:
        config['max_af'] = 'gnomAD'

    return config


def get_snpeff_recommended_config(use_case):
    """
    Get recommended SNPEff configuration based on use case.

    Parameters
    ----------
    use_case : str
        Primary analysis purpose

    Returns
    -------
    dict
        Recommended SNPEff parameters
    """
    config = {
        'stats': 'snpeff_summary.html',
        'csv_stats': 'snpeff_stats.csv',
        'format_eff': False,  # Use ANN format
        'canon': True,
        'hgvs': True,
        'threads': 4
    }

    # Clinical/research: focus on coding regions
    if use_case in ['clinical', 'research']:
        config['lof'] = True
        config['no_downstream'] = True
        config['no_upstream'] = True
        config['no_intergenic'] = True

    return config


def compare_tools(organism='human', use_case='clinical'):
    """
    Generate comparison summary between VEP and SNPEff for given context.

    Parameters
    ----------
    organism : str
        Target organism
    use_case : str
        Primary analysis purpose

    Returns
    -------
    dict
        Comparison summary with pros/cons for each tool
    """
    comparison = {
        'vep': {
            'pros': [
                'Comprehensive clinical annotations (ClinVar, COSMIC, HGMD)',
                'Multiple pathogenicity predictions (SIFT, PolyPhen, CADD, REVEL)',
                'Extensive regulatory annotations (ENCODE)',
                'Quarterly updates',
                'VCF output compatible with most tools'
            ],
            'cons': [
                'Large cache files (~15-20 GB for human)',
                'Slower than SNPEff',
                'More complex setup'
            ]
        },
        'snpeff': {
            'pros': [
                'Fast annotation speed',
                'Lightweight setup (~2-3 GB for human)',
                'Simple installation',
                '38,000+ genome databases',
                'Excellent GATK integration'
            ],
            'cons': [
                'Fewer pathogenicity predictors',
                'Less comprehensive clinical databases',
                'Limited regulatory annotations'
            ]
        }
    }

    # Context-specific notes
    if organism.lower() not in ['human', 'mouse', 'rat']:
        comparison['snpeff']['pros'].insert(0, f'Excellent support for {organism}')
        comparison['vep']['cons'].append(f'Limited support for {organism}')

    if use_case == 'clinical':
        comparison['vep']['recommended'] = True
    elif use_case == 'research':
        comparison['snpeff']['recommended'] = True

    return comparison

