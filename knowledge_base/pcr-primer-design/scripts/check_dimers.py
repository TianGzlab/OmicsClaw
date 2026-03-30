"""
Check for primer dimers and cross-dimers.

This module analyzes primer-primer interactions to identify potential
dimer formation that can reduce PCR efficiency.
"""

import primer3
from typing import List, Dict


def analyze_dimers(
    primer_list: List[str],
    temperature: float = 60.0,
    dg_threshold: float = -5.0,
    mv_conc: float = 50.0,
    dv_conc: float = 0.0,
    dntp_conc: float = 0.8,
    dna_conc: float = 50.0
) -> Dict:
    """
    Analyze primer dimers and cross-dimers for a set of primers.

    Parameters
    ----------
    primer_list : list of str
        List of primer sequences to analyze
    temperature : float
        PCR annealing temperature in °C. Default: 60.0
    dg_threshold : float
        ΔG threshold in kcal/mol for flagging dimers. Default: -5.0
        Dimers with ΔG < threshold are likely to form
    mv_conc : float
        Monovalent cation concentration in mM. Default: 50.0
    dv_conc : float
        Divalent cation concentration in mM. Default: 0.0
    dntp_conc : float
        dNTP concentration in mM. Default: 0.8
    dna_conc : float
        DNA concentration in nM. Default: 50.0

    Returns
    -------
    dict
        Dictionary containing:
        - 'interactions': list of all primer-primer interactions
        - 'problematic_dimers': list of dimers below threshold
        - 'has_issues': bool indicating if any dimers exceed threshold

    Example
    -------
    >>> primers = ["ATGCGTACGATCGATCG", "CGTAGCTAGCTAGCTAG"]
    >>> analysis = analyze_dimers(primers, temperature=60.0)
    >>> if analysis['has_issues']:
    ...     print("⚠ Primer dimers detected!")
    """

    # Validate inputs
    primer_list = [p.upper().strip() for p in primer_list]

    if len(primer_list) < 2:
        raise ValueError("Need at least 2 primers to check for dimers")

    for primer in primer_list:
        if not all(base in 'ATCGN' for base in primer):
            raise ValueError(f"Invalid primer sequence: {primer}")

    interactions = []
    problematic_dimers = []

    # Check all pairwise interactions
    for i, primer1 in enumerate(primer_list):
        for j, primer2 in enumerate(primer_list):
            if i <= j:  # Check each pair once, including self-dimers
                # Determine interaction type
                if i == j:
                    interaction_type = "self-dimer"
                    primer1_name = f"Primer_{i+1}"
                    primer2_name = f"Primer_{i+1}"
                else:
                    interaction_type = "cross-dimer"
                    primer1_name = f"Primer_{i+1}"
                    primer2_name = f"Primer_{j+1}"

                # Calculate homodimer (self-dimer) or heterodimer (cross-dimer)
                if i == j:
                    result = primer3.calcHomodimer(
                        primer1,
                        mv_conc=mv_conc,
                        dv_conc=dv_conc,
                        dntp_conc=dntp_conc,
                        dna_conc=dna_conc,
                        temp_c=temperature,
                        output_structure=True
                    )
                else:
                    result = primer3.calcHeterodimer(
                        primer1,
                        primer2,
                        mv_conc=mv_conc,
                        dv_conc=dv_conc,
                        dntp_conc=dntp_conc,
                        dna_conc=dna_conc,
                        temp_c=temperature,
                        output_structure=True
                    )

                # Extract results
                dg = result.dg / 1000.0  # Convert cal/mol to kcal/mol
                tm = result.tm
                structure = result.ascii_structure if hasattr(result, 'ascii_structure') else "N/A"

                interaction = {
                    'type': interaction_type,
                    'primer1': primer1_name,
                    'primer2': primer2_name,
                    'primer1_seq': primer1,
                    'primer2_seq': primer2,
                    'dg': round(dg, 2),
                    'tm': round(tm, 2) if tm is not None else None,
                    'structure': structure,
                    'problematic': dg < dg_threshold,
                }

                interactions.append(interaction)

                if dg < dg_threshold:
                    problematic_dimers.append(interaction)

    # Compile results
    results = {
        'interactions': interactions,
        'problematic_dimers': problematic_dimers,
        'has_issues': len(problematic_dimers) > 0,
        'num_primers': len(primer_list),
        'num_interactions': len(interactions),
        'num_problematic': len(problematic_dimers),
        'parameters': {
            'temperature': temperature,
            'dg_threshold': dg_threshold,
            'mv_conc': mv_conc,
            'dv_conc': dv_conc,
            'dntp_conc': dntp_conc,
            'dna_conc': dna_conc,
        }
    }

    return results


def check_3prime_complementarity(
    primer1: str,
    primer2: str,
    window_size: int = 5
) -> Dict:
    """
    Check for 3' end complementarity between two primers.

    3' complementarity is critical as it can lead to primer extension
    and dimer formation during PCR.

    Parameters
    ----------
    primer1 : str
        First primer sequence
    primer2 : str
        Second primer sequence
    window_size : int
        Number of bases at 3' end to check. Default: 5

    Returns
    -------
    dict
        Dictionary with 3' complementarity analysis

    Example
    -------
    >>> result = check_3prime_complementarity("ATGCGTACGATCG", "CGATCGTACGCAT")
    >>> print(f"3' complementarity: {result['complementary_bases']} bp")
    """

    from Bio.Seq import Seq

    primer1 = primer1.upper()
    primer2 = primer2.upper()

    # Get 3' ends
    primer1_3prime = primer1[-window_size:]
    primer2_3prime = primer2[-window_size:]

    # Get reverse complement of primer2's 3' end
    primer2_3prime_rc = str(Seq(primer2_3prime).reverse_complement())

    # Count complementary bases at 3' end
    complementary_bases = 0
    for i in range(min(len(primer1_3prime), len(primer2_3prime_rc))):
        if primer1_3prime[-(i+1)] == primer2_3prime_rc[i]:
            complementary_bases += 1
        else:
            break

    is_problematic = complementary_bases >= 3

    return {
        'primer1_3prime': primer1_3prime,
        'primer2_3prime': primer2_3prime,
        'complementary_bases': complementary_bases,
        'is_problematic': is_problematic,
        'warning': f"High 3' complementarity ({complementary_bases} bp)" if is_problematic else None,
    }


def analyze_multiplex_compatibility(
    primer_pairs: List[Dict],
    temperature: float = 60.0,
    dg_threshold: float = -5.0
) -> Dict:
    """
    Analyze compatibility of multiple primer pairs for multiplex PCR.

    Parameters
    ----------
    primer_pairs : list of dict
        List of primer pair dictionaries, each with 'forward_seq' and 'reverse_seq'
    temperature : float
        PCR annealing temperature
    dg_threshold : float
        ΔG threshold for dimer flagging

    Returns
    -------
    dict
        Multiplex compatibility analysis

    Example
    -------
    >>> pairs = [
    ...     {'forward_seq': 'ATGC...', 'reverse_seq': 'CGTA...'},
    ...     {'forward_seq': 'GCTA...', 'reverse_seq': 'TAGC...'}
    ... ]
    >>> compat = analyze_multiplex_compatibility(pairs)
    >>> print(f"Multiplex compatible: {compat['is_compatible']}")
    """

    # Collect all primers
    all_primers = []
    primer_labels = []

    for i, pair in enumerate(primer_pairs):
        all_primers.append(pair['forward_seq'])
        all_primers.append(pair['reverse_seq'])
        primer_labels.append(f"Pair{i+1}_F")
        primer_labels.append(f"Pair{i+1}_R")

    # Analyze all interactions
    dimer_analysis = analyze_dimers(
        primer_list=all_primers,
        temperature=temperature,
        dg_threshold=dg_threshold
    )

    # Check Tm compatibility
    tm_values = []
    for pair in primer_pairs:
        if 'forward_tm' in pair and 'reverse_tm' in pair:
            tm_values.extend([pair['forward_tm'], pair['reverse_tm']])

    tm_range = max(tm_values) - min(tm_values) if tm_values else 0
    tm_compatible = tm_range <= 5.0  # All primers should have Tm within 5°C

    # Compile multiplex results
    is_compatible = not dimer_analysis['has_issues'] and tm_compatible

    results = {
        'is_compatible': is_compatible,
        'num_pairs': len(primer_pairs),
        'total_primers': len(all_primers),
        'dimer_analysis': dimer_analysis,
        'tm_range': round(tm_range, 2) if tm_values else None,
        'tm_compatible': tm_compatible,
        'recommendations': [],
    }

    # Add recommendations
    if dimer_analysis['has_issues']:
        results['recommendations'].append(
            f"Remove or redesign primers with problematic dimers (ΔG < {dg_threshold} kcal/mol)"
        )

    if not tm_compatible:
        results['recommendations'].append(
            f"Adjust primer Tm values to be within 5°C (current range: {tm_range:.1f}°C)"
        )

    if is_compatible:
        results['recommendations'].append("Primer set is compatible for multiplex PCR")

    return results

