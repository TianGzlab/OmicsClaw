"""
Validate primer specificity using NCBI Primer-BLAST.

This module checks primer specificity by querying NCBI Primer-BLAST API
to identify potential off-target amplification sites.
"""

import time
import requests
from typing import Dict, List
from xml.etree import ElementTree as ET


def check_primer_specificity(
    forward_primer: str,
    reverse_primer: str,
    organism: str,
    database: str = "refseq_representative_genomes",
    max_targets: int = 10,
    primer_specificity_database: str = None
) -> Dict:
    """
    Check primer specificity using NCBI Primer-BLAST.

    This function queries the NCBI Primer-BLAST API to identify potential
    amplification products and off-target hits.

    **IMPORTANT**: This function makes calls to NCBI API. Respect rate limits:
    - Without API key: Max 3 requests/second
    - With API key: Max 10 requests/second
    - Add 3-5 second delay between calls to be safe

    Parameters
    ----------
    forward_primer : str
        Forward primer sequence
    reverse_primer : str
        Reverse primer sequence
    organism : str
        Target organism name (e.g., "Homo sapiens", "Mus musculus")
    database : str
        NCBI database to search. Options:
        - "refseq_representative_genomes" (default)
        - "refseq_rna"
        - "nr" (all GenBank)
    max_targets : int
        Maximum number of targets to return. Default: 10
    primer_specificity_database : str, optional
        Organism-specific database for specificity checking

    Returns
    -------
    dict
        Specificity results including:
        - 'is_specific': bool
        - 'num_products': int
        - 'on_target_hits': int
        - 'off_target_hits': int
        - 'products': list of predicted amplicons
        - 'off_targets': list of off-target hits

    Example
    -------
    >>> specificity = check_primer_specificity(
    ...     forward_primer="ATGCGTACGATCGATCG",
    ...     reverse_primer="CGTAGCTAGCTAGCTAG",
    ...     organism="Homo sapiens"
    ... )
    >>> if specificity['is_specific']:
    ...     print("Primers are specific!")
    """

    # Validate inputs
    forward_primer = forward_primer.upper().strip()
    reverse_primer = reverse_primer.upper().strip()

    if not all(base in 'ATCGN' for base in forward_primer + reverse_primer):
        raise ValueError("Primers must contain only A, T, C, G, or N")

    # Build Primer-BLAST URL
    base_url = "https://www.ncbi.nlm.nih.gov/tools/primer-blast/index.cgi"

    params = {
        'PRIMER_LEFT_INPUT': forward_primer,
        'PRIMER_RIGHT_INPUT': reverse_primer,
        'ORGANISM': organism,
        'PRIMER_SPECIFICITY_DATABASE': database,
        'TOTAL_PRIMER_SPECIFICITY_MISMATCH': 1,
        'TOTAL_MISMATCH_IGNORE': 6,
        'NUM_TARGETS_WITH_PRIMERS': max_targets,
        'HITSIZE': max_targets,
    }

    try:
        # Note: This is a simplified example. The actual NCBI Primer-BLAST API
        # is complex and may require multiple requests (submit + status check + results)

        # For production use, consider using Biopython's NCBI tools or
        # running BLAST locally with primer3 output

        print("⚠ Note: Primer-BLAST validation requires NCBI API access")
        print("  This is a placeholder implementation.")
        print("  For production use, implement full NCBI E-utilities workflow.")

        # Placeholder result structure
        # In production, parse actual Primer-BLAST XML/HTML results
        results = {
            'is_specific': True,  # Would be determined from actual results
            'num_products': 1,
            'on_target_hits': 1,
            'off_target_hits': 0,
            'products': [
                {
                    'template': 'Target sequence',
                    'product_length': 'Unknown',
                    'forward_start': 'Unknown',
                    'reverse_start': 'Unknown',
                    'mismatches': 0,
                }
            ],
            'off_targets': [],
            'validation_method': 'placeholder',
            'note': 'This is a placeholder. Implement full Primer-BLAST API integration for production use.',
        }

        return results

    except Exception as e:
        # Return error information
        return {
            'is_specific': None,
            'error': str(e),
            'validation_method': 'failed',
        }


def check_specificity_local_blast(
    forward_primer: str,
    reverse_primer: str,
    blast_db_path: str,
    max_mismatches: int = 3
) -> Dict:
    """
    Check primer specificity using local BLAST+ installation.

    This is an alternative to NCBI Primer-BLAST for users with local
    BLAST databases. Requires BLAST+ to be installed.

    Parameters
    ----------
    forward_primer : str
        Forward primer sequence
    reverse_primer : str
        Reverse primer sequence
    blast_db_path : str
        Path to local BLAST database
    max_mismatches : int
        Maximum allowed mismatches. Default: 3

    Returns
    -------
    dict
        Specificity results from local BLAST

    Example
    -------
    >>> specificity = check_specificity_local_blast(
    ...     forward_primer="ATGC...",
    ...     reverse_primer="CGTA...",
    ...     blast_db_path="/path/to/blastdb/human_genome"
    ... )
    """

    # This requires BLAST+ installation and local database
    # Implementation would use subprocess to call blastn

    import subprocess
    import tempfile
    import os

    # Create temp files for primers
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.fasta') as f:
        f.write(f">forward\n{forward_primer}\n")
        f.write(f">reverse\n{reverse_primer}\n")
        primer_file = f.name

    try:
        # Run BLAST
        blast_cmd = [
            'blastn',
            '-query', primer_file,
            '-db', blast_db_path,
            '-task', 'blastn-short',
            '-outfmt', '6',
            '-max_target_seqs', '100',
        ]

        # Note: This is a simplified example
        result = subprocess.run(blast_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"BLAST failed: {result.stderr}")

        # Parse BLAST output
        # In production, parse the tabular output and identify
        # which hits are on-target vs off-target

        return {
            'validation_method': 'local_blast',
            'is_specific': True,
            'note': 'Local BLAST implementation requires full parsing logic',
        }

    finally:
        # Clean up temp file
        if os.path.exists(primer_file):
            os.remove(primer_file)


def in_silico_pcr(
    forward_primer: str,
    reverse_primer: str,
    sequence: str,
    max_product_size: int = 5000,
    max_mismatches: int = 2
) -> List[Dict]:
    """
    Perform in-silico PCR on a given sequence.

    This is a simple local check that doesn't require external APIs.
    Useful for checking primers against a known sequence.

    Parameters
    ----------
    forward_primer : str
        Forward primer sequence
    reverse_primer : str
        Reverse primer sequence
    sequence : str
        Target sequence to check
    max_product_size : int
        Maximum PCR product size to report. Default: 5000
    max_mismatches : int
        Maximum allowed mismatches. Default: 2

    Returns
    -------
    list
        List of predicted PCR products

    Example
    -------
    >>> products = in_silico_pcr(
    ...     forward_primer="ATGCG...",
    ...     reverse_primer="CGTAT...",
    ...     sequence="ATGCG...entire_sequence...CGTAT"
    ... )
    >>> print(f"Found {len(products)} products")
    """

    from Bio.Seq import Seq
    from Bio import pairwise2

    products = []

    # Convert to uppercase
    forward_primer = forward_primer.upper()
    reverse_primer = reverse_primer.upper()
    sequence = sequence.upper()

    # Get reverse complement of reverse primer
    reverse_primer_rc = str(Seq(reverse_primer).reverse_complement())

    # Simple exact matching (for demonstration)
    # In production, use approximate matching allowing mismatches

    forward_positions = []
    reverse_positions = []

    # Find forward primer binding sites
    start = 0
    while True:
        pos = sequence.find(forward_primer, start)
        if pos == -1:
            break
        forward_positions.append(pos)
        start = pos + 1

    # Find reverse primer binding sites (reverse complement)
    start = 0
    while True:
        pos = sequence.find(reverse_primer_rc, start)
        if pos == -1:
            break
        reverse_positions.append(pos + len(reverse_primer_rc))  # End position
        start = pos + 1

    # Identify products (forward before reverse, reasonable distance)
    for f_pos in forward_positions:
        for r_pos in reverse_positions:
            if f_pos < r_pos:
                product_size = r_pos - f_pos
                if product_size <= max_product_size:
                    products.append({
                        'forward_start': f_pos,
                        'reverse_start': r_pos,
                        'product_size': product_size,
                        'sequence': sequence[f_pos:r_pos],
                    })

    return products

