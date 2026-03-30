"""
Load example gene lists for testing ChIP-Atlas peak enrichment.

Provides three example gene sets:
1. tp53_targets - 5 TP53 target genes (~2-3 min runtime)
2. immune_response - 20 cytokine/immune genes (~5-7 min runtime)
3. user_72genes - 72-gene list for comprehensive testing (~15-20 min runtime)
"""


def load_example_data(gene_set="tp53_targets"):
    """
    Load example gene list for testing.

    Parameters:
    -----------
    gene_set : str
        'tp53_targets' (5 genes, ~2 min), 'immune_response' (20 genes, ~5 min),
        or 'user_72genes' (72 genes, ~15 min)

    Returns:
    --------
    dict: {'genes': List[str], 'description': str}

    Examples:
    ---------
    >>> data = load_example_data("tp53_targets")
    >>> print(f"Loaded {len(data['genes'])} genes")
    ✓ Data loaded successfully: 5 genes
    """

    gene_sets = {
        'tp53_targets': {
            'genes': [
                "CDKN1A",  # p21, cell cycle arrest
                "BAX",     # Pro-apoptotic
                "BBC3",    # PUMA, apoptosis
                "GADD45A", # DNA damage response
                "MDM2"     # p53 negative regulator
            ],
            'description': 'TP53 target genes (cell cycle, apoptosis)',
        },

        'immune_response': {
            'genes': [
                "IL1A", "IL1B", "IL6", "IL8", "TNF", "IFNG", "IL10",
                "CCL2", "CCL5", "CXCL10", "CD40", "CD80", "CD86",
                "STAT1", "STAT3", "NFKB1", "RELA", "JUN", "FOS", "MYD88"
            ],
            'description': 'Immune response genes (cytokines, TFs)',
        },

        'user_72genes': {
            'genes': [
                'TLR10', 'MDGA2', 'TENM4', 'AIG1', 'NBEA', 'SVIL', 'AC090425.1', 'OCRL',
                'FXN', 'MOB3B', 'FOCAD', 'MREG', 'BOLA3', 'C1QTNF3', 'ST6GALNAC3',
                'DHRS3', 'MIPOL1', 'MED28P3', 'ARHGAP42', 'ME3', 'FERMT1', 'APP',
                'BCKDHB', 'RSAD1', 'SPIDR', 'FER', 'RBM45', 'GOT2', 'PLAGL1',
                'HNRNPA1P29', 'SLC38A5', 'ABCC4', 'ELOVL6', 'AAAS', 'TTC5', 'ADAM22',
                'SNORA7B', 'AARS2', 'QDPR', 'GCSHP5', 'LINC00342', 'AADAT', 'HIST2H2BA',
                'MYC', 'PCCA', 'STAC', 'SUMF1', 'DCHS2', 'ARHGAP15', 'SPATA5',
                'PRKCQ-AS1', 'SMYD3', 'TTC27', 'RPL36AP26', 'SETP6', 'PDF', 'COG5',
                'C11orf87', 'PLOD2', 'ACO1', 'GUSBP2', 'TERT', 'GMDS', 'FBN2',
                'RN7SL674P', 'EXPH5', 'IPO11', 'GSAP', 'PPARGC1B', 'TMEM38B', 'HSPB7',
                'ZNF462', 'TEX261', 'FARS2', 'MZT2A', 'DHRS13'
            ],
            'description': 'User-provided gene list (72 genes, diverse functions)',
        }
    }

    if gene_set not in gene_sets:
        available = ', '.join(gene_sets.keys())
        raise ValueError(f"Unknown gene set: '{gene_set}'. Available: {available}")

    data = gene_sets[gene_set]

    print(f"✓ Data loaded successfully: {len(data['genes'])} genes")
    print(f"   Description: {data['description']}")

    return data


if __name__ == "__main__":
    # Test all gene sets
    print("Testing tp53_targets:")
    data1 = load_example_data("tp53_targets")
    print(f"   Genes: {data1['genes']}\n")

    print("Testing immune_response:")
    data2 = load_example_data("immune_response")
    print(f"   First 5 genes: {data2['genes'][:5]}\n")

    print("Testing user_72genes:")
    data3 = load_example_data("user_72genes")
    print(f"   Total genes: {len(data3['genes'])}")
    print(f"   First 10: {data3['genes'][:10]}")

