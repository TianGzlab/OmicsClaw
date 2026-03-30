"""
Load example experiment ID sets for testing ChIP-Atlas Diff Analysis.

Provides pre-built experiment ID pairs for quick testing:
1. tp53_k562_dmso_vs_daunorubicin - TP53 ChIP-seq: K-562 DMSO vs Daunorubicin (n=8 vs n=8, ~5-10 min)
2. tp53_molm13_vs_k562 - TP53 ChIP-seq: MOLM-13 vs K-562 (n=4 vs n=4, ~3-5 min)

All IDs from GSE131484 (Bhatt et al., K-562/MOLM-13 TP53 mutant panel), verified against ChIP-Atlas (hg38).
"""


def load_example_data(dataset="tp53_k562_dmso_vs_daunorubicin"):
    """
    Load example experiment IDs for testing.

    Parameters
    ----------
    dataset : str
        'tp53_k562_dmso_vs_daunorubicin' (recommended, n=8 vs n=8) or
        'tp53_molm13_vs_k562' (n=4 vs n=4, demonstrates sex-chr QC)

    Returns
    -------
    dict
        {
            'experiments_a': list of str,
            'experiments_b': list of str,
            'genome': str,
            'analysis_type': str,
            'description_a': str,
            'description_b': str,
            'description': str,
        }

    Examples
    --------
    >>> data = load_example_data("tp53_k562_dmso_vs_daunorubicin")
    >>> print(f"Group A: {len(data['experiments_a'])} experiments")
    """

    datasets = {
        # PRIMARY EXAMPLE: Same cell line, treatment comparison
        # Clean design: no sex confound, no CNV differences, n=8 per group
        "tp53_k562_dmso_vs_daunorubicin": {
            "experiments_a": [
                "SRX5865959",   # K562, R175H, DMSO
                "SRX5865960",   # K562, Y220C, DMSO
                "SRX5865961",   # K562, M237I, DMSO
                "SRX5865962",   # K562, R248Q, DMSO
                "SRX5865963",   # K562, R273H, DMSO
                "SRX5865964",   # K562, R282W, DMSO
                "SRX5865965",   # K562, KO, DMSO
                "SRX5865966",   # K562, WT, DMSO
            ],
            "experiments_b": [
                "SRX5865967",   # K562, R175H, Daunorubicin
                "SRX5865968",   # K562, Y220C, Daunorubicin
                "SRX5865969",   # K562, M237I, Daunorubicin
                "SRX5865970",   # K562, R248Q, Daunorubicin
                "SRX5865971",   # K562, R273H, Daunorubicin
                "SRX5865972",   # K562, R282W, Daunorubicin
                "SRX5865973",   # K562, KO, Daunorubicin
                "SRX5865974",   # K562, WT, Daunorubicin
            ],
            "genome": "hg38",
            "analysis_type": "diffbind",
            "description_a": "K562_DMSO",
            "description_b": "K562_Daunorubicin",
            "description": (
                "TP53 ChIP-seq in K-562 cells: DMSO (vehicle) vs Daunorubicin "
                "(chemotherapy). 8 TP53 genotype backgrounds per condition (WT + 6 "
                "hotspot mutants + KO) from GSE131484. Identifies genomic regions "
                "where Daunorubicin-induced DNA damage alters TP53 binding."
            ),
            "design_caveats": [
                "Each group contains 8 different TP53 genotypes (WT, R175H, Y220C, "
                "M237I, R248Q, R273H, R282W, KO), not 8 biological replicates of "
                "the same genotype. edgeR treats all experiments within a group as "
                "replicates, so the differential analysis captures the average "
                "DMSO-vs-Daunorubicin effect across genotypes. Genotype-specific "
                "effects are averaged out and cannot be distinguished from noise.",
            ],
        },
        # SECONDARY EXAMPLE: Cross-cell-line comparison
        # Demonstrates sex-chromosome QC (MOLM-13=male, K-562=female)
        "tp53_molm13_vs_k562": {
            "experiments_a": [
                "SRX5865975",   # MOLM-13, R175H, DMSO
                "SRX5865976",   # MOLM-13, Y220C, DMSO
                "SRX5865977",   # MOLM-13, M237I, DMSO
                "SRX5865982",   # MOLM-13, WT, DMSO
            ],
            "experiments_b": [
                "SRX5865959",   # K-562, R175H, DMSO
                "SRX5865960",   # K-562, Y220C, DMSO
                "SRX5865961",   # K-562, M237I, DMSO
                "SRX5865966",   # K-562, WT, DMSO
            ],
            "genome": "hg38",
            "analysis_type": "diffbind",
            "description_a": "MOLM-13",
            "description_b": "K-562",
            "description": (
                "TP53 ChIP-seq: MOLM-13 (AML, male) vs K-562 (CML, female) under "
                "DMSO. Matched TP53 genotypes (R175H, Y220C, M237I, WT) from "
                "GSE131484. Note: expected chrY sex-chromosome confound (demonstrates "
                "automated QC detection)."
            ),
            "design_caveats": [
                "Each group contains 4 different TP53 genotypes (R175H, Y220C, "
                "M237I, WT), not 4 biological replicates. edgeR treats within-group "
                "experiments as replicates, so the analysis captures the average "
                "cell-line difference across genotypes.",
            ],
        },
    }

    if dataset not in datasets:
        available = ", ".join(datasets.keys())
        raise ValueError(f"Unknown dataset: '{dataset}'. Available: {available}")

    data = datasets[dataset]

    n_a = len(data["experiments_a"])
    n_b = len(data["experiments_b"])
    print(f"✓ Data loaded successfully: {n_a} vs {n_b} experiments")
    print(f"   Dataset: {dataset}")
    print(f"   Group A ({data['description_a']}): {data['experiments_a']}")
    print(f"   Group B ({data['description_b']}): {data['experiments_b']}")
    print(f"   Genome: {data['genome']}")
    print(f"   Analysis type: {data['analysis_type']}")
    print(f"   Description: {data['description']}")

    return data


if __name__ == "__main__":
    print("Testing example datasets:\n")

    print("=" * 60)
    print("Dataset: tp53_k562_dmso_vs_daunorubicin (primary)")
    print("=" * 60)
    data1 = load_example_data("tp53_k562_dmso_vs_daunorubicin")
    print()

    print("=" * 60)
    print("Dataset: tp53_molm13_vs_k562 (secondary, QC demo)")
    print("=" * 60)
    data2 = load_example_data("tp53_molm13_vs_k562")

