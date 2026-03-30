"""
User query input handling for ChIP-Atlas Target Genes skill.

Validates and prepares user-specified query parameters.
"""

VALID_GENOMES = ["hg38", "hg19", "mm10", "mm9", "rn6", "dm6", "dm3", "ce11", "ce10", "sacCer3"]
VALID_DISTANCES = [1, 5, 10]


def load_user_query(protein, genome="hg38", distance=5):
    """
    Prepare and validate a user-specified target genes query.

    Args:
        protein: Protein/TF name (case-sensitive, e.g., "TP53")
        genome: Genome assembly (default: "hg38")
        distance: Distance from TSS in kb (1, 5, or 10; default: 5)

    Returns:
        dict: Query parameters with keys: protein, genome, distance, description
    """
    # Validate protein name
    if not protein or not isinstance(protein, str):
        raise ValueError("Protein name must be a non-empty string (e.g., 'TP53', 'CTCF', 'MYC')")

    protein = protein.strip()
    if not protein:
        raise ValueError("Protein name must be a non-empty string")

    # Validate genome
    if genome not in VALID_GENOMES:
        raise ValueError(f"Invalid genome '{genome}'. Valid options: {', '.join(VALID_GENOMES)}")

    # Validate distance
    if distance not in VALID_DISTANCES:
        raise ValueError(f"Invalid distance {distance}. Valid options: {VALID_DISTANCES}")

    result = {
        "protein": protein,
        "genome": genome,
        "distance": distance,
        "description": f"User query: {protein} target genes in {genome} (±{distance}kb from TSS)",
    }

    print(f"  ✓ Query prepared: {result['protein']} target genes ({result['genome']}, ±{result['distance']}kb)")
    return result

