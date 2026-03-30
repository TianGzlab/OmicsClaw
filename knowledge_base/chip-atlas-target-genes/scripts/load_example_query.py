"""
Example query data for ChIP-Atlas Target Genes skill.

Provides pre-defined TF queries for testing and demonstration.
"""


def load_example_query(query="tp53"):
    """
    Load a pre-defined example query for target genes analysis.

    Args:
        query: Query name - "tp53" (default), "e2f1", or "myc"

    Returns:
        dict: Query parameters with keys: protein, genome, distance, description
    """
    queries = {
        "tp53": {
            "protein": "TP53",
            "genome": "hg38",
            "distance": 5,
            "description": (
                "TP53 (tumor protein p53) - Master tumor suppressor and transcription factor. "
                "Well-characterized targets include CDKN1A, BAX, MDM2. "
                "Large dataset (~395 experiments, ~16K target genes). "
                "Expected runtime: ~10-30 seconds (large download ~13MB)."
            ),
        },
        "e2f1": {
            "protein": "E2F1",
            "genome": "hg38",
            "distance": 5,
            "description": (
                "E2F1 (E2F transcription factor 1) - Key cell cycle regulator. "
                "Targets include genes involved in DNA replication and cell division. "
                "Moderate dataset size. "
                "Expected runtime: ~5-15 seconds."
            ),
        },
        "myc": {
            "protein": "MYC",
            "genome": "hg38",
            "distance": 5,
            "description": (
                "MYC (MYC proto-oncogene) - Key transcription factor in cell growth. "
                "Broad binding profile with many target genes. "
                "Expected runtime: ~5-15 seconds."
            ),
        },
    }

    key = query.lower().strip()
    if key not in queries:
        available = ", ".join(f'"{k}"' for k in queries)
        raise ValueError(f"Unknown example query '{query}'. Available: {available}")

    result = queries[key]
    print(f"  ✓ Query loaded: {result['protein']} target genes ({result['genome']}, ±{result['distance']}kb)")
    print(f"    {result['description']}")
    return result

