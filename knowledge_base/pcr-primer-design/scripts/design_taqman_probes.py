"""
Design TaqMan probes for qPCR assays.

This module provides functions for designing TaqMan (hydrolysis probe) assays,
including both primers and probe with appropriate melting temperatures.
"""

import primer3


def design_taqman_assay(
    sequence: str,
    target_region: tuple = None,
    probe_tm_offset: float = 8.0,
    primer_tm_range: tuple = (58, 62),
    amplicon_size_range: tuple = (70, 140),
    num_return: int = 5
) -> dict:
    """
    Design a complete TaqMan assay (primers + probe).

    The probe Tm should be 5-10°C higher than the primers for optimal performance.
    The probe is typically 18-30 nt long and positioned between the primers.

    Parameters
    ----------
    sequence : str
        Target DNA sequence
    target_region : tuple, optional
        (start, end) positions for assay design
    probe_tm_offset : float
        Target Tm difference between probe and primers (°C). Default: 8.0
    primer_tm_range : tuple
        (min, max) primer Tm in °C. Default: (58, 62)
    amplicon_size_range : tuple
        (min, max) amplicon size in bp. Default: (70, 140)
    num_return : int
        Number of assays to return. Default: 5

    Returns
    -------
    dict
        Dictionary containing complete TaqMan assay designs

    Example
    -------
    >>> assay = design_taqman_assay(
    ...     sequence="ATGCGTACG..." * 30
    ... )
    >>> print(f"Probe Tm: {assay['assays'][0]['probe_tm']}°C")
    >>> print(f"Primer Tm: {assay['assays'][0]['forward_tm']}°C")
    """

    # Validate input
    sequence = sequence.upper().strip()
    if not all(base in 'ATCGN' for base in sequence):
        raise ValueError("Sequence must contain only A, T, C, G, or N characters")

    if len(sequence) < amplicon_size_range[0]:
        raise ValueError(f"Sequence too short for amplicon size range")

    # Calculate target probe Tm
    optimal_primer_tm = (primer_tm_range[0] + primer_tm_range[1]) / 2
    optimal_probe_tm = optimal_primer_tm + probe_tm_offset

    # Primer3 parameters for TaqMan design
    primer3_params = {
        'PRIMER_OPT_SIZE': 20,
        'PRIMER_MIN_SIZE': 18,
        'PRIMER_MAX_SIZE': 25,
        'PRIMER_OPT_TM': optimal_primer_tm,
        'PRIMER_MIN_TM': primer_tm_range[0],
        'PRIMER_MAX_TM': primer_tm_range[1],
        'PRIMER_PAIR_MAX_DIFF_TM': 2.0,
        'PRIMER_MIN_GC': 40.0,
        'PRIMER_MAX_GC': 60.0,
        'PRIMER_PRODUCT_SIZE_RANGE': [amplicon_size_range],
        'PRIMER_NUM_RETURN': num_return,
        # Probe-specific parameters
        'PRIMER_PICK_INTERNAL_OLIGO': 1,  # Design internal oligo (probe)
        'PRIMER_INTERNAL_OPT_SIZE': 24,
        'PRIMER_INTERNAL_MIN_SIZE': 18,
        'PRIMER_INTERNAL_MAX_SIZE': 30,
        'PRIMER_INTERNAL_OPT_TM': optimal_probe_tm,
        'PRIMER_INTERNAL_MIN_TM': optimal_probe_tm - 3,
        'PRIMER_INTERNAL_MAX_TM': optimal_probe_tm + 3,
        'PRIMER_INTERNAL_MIN_GC': 40.0,
        'PRIMER_INTERNAL_MAX_GC': 60.0,
        'PRIMER_INTERNAL_MAX_POLY_X': 4,
        'PRIMER_INTERNAL_MAX_SELF_ANY': 8,
        'PRIMER_INTERNAL_MAX_SELF_END': 3,
        # Avoid G at 5' end of probe (quenching issue)
        'PRIMER_MAX_POLY_X': 4,
        'PRIMER_MAX_NS_ACCEPTED': 0,
    }

    # Sequence input
    seq_args = {
        'SEQUENCE_TEMPLATE': sequence,
    }

    if target_region is not None:
        start, end = target_region
        if start < 0 or end > len(sequence) or start >= end:
            raise ValueError(f"Invalid target region")
        seq_args['SEQUENCE_TARGET'] = [start, end - start]

    # Run Primer3
    primer3_result = primer3.designPrimers(seq_args, primer3_params)

    # Parse results
    assays_list = []
    num_returned = primer3_result.get('PRIMER_PAIR_NUM_RETURNED', 0)

    for i in range(num_returned):
        # Check if probe was designed for this pair
        probe_key = f'PRIMER_INTERNAL_{i}_SEQUENCE'
        if probe_key not in primer3_result:
            continue

        # Extract primer sequences
        forward_seq = primer3_result[f'PRIMER_LEFT_{i}_SEQUENCE']
        reverse_seq = primer3_result[f'PRIMER_RIGHT_{i}_SEQUENCE']
        probe_seq = primer3_result[probe_key]

        # Extract positions
        forward_pos, forward_len = primer3_result[f'PRIMER_LEFT_{i}']
        reverse_pos, reverse_len = primer3_result[f'PRIMER_RIGHT_{i}']
        probe_pos, probe_len = primer3_result[f'PRIMER_INTERNAL_{i}']

        # Extract properties
        forward_tm = primer3_result[f'PRIMER_LEFT_{i}_TM']
        reverse_tm = primer3_result[f'PRIMER_RIGHT_{i}_TM']
        probe_tm = primer3_result[f'PRIMER_INTERNAL_{i}_TM']

        forward_gc = primer3_result[f'PRIMER_LEFT_{i}_GC_PERCENT']
        reverse_gc = primer3_result[f'PRIMER_RIGHT_{i}_GC_PERCENT']
        probe_gc = primer3_result[f'PRIMER_INTERNAL_{i}_GC_PERCENT']

        # Amplicon size
        amplicon_size = primer3_result[f'PRIMER_PAIR_{i}_PRODUCT_SIZE']

        # Penalty score
        penalty = primer3_result[f'PRIMER_PAIR_{i}_PENALTY']

        # Calculate Tm differences
        primer_tm_diff = abs(forward_tm - reverse_tm)
        probe_primer_diff = probe_tm - ((forward_tm + reverse_tm) / 2)

        # Check if probe starts with G (not ideal for TaqMan)
        probe_starts_with_g = probe_seq[0] == 'G'

        assay = {
            'assay_id': i,
            'forward_seq': forward_seq,
            'reverse_seq': reverse_seq,
            'probe_seq': probe_seq,
            'forward_tm': round(forward_tm, 2),
            'reverse_tm': round(reverse_tm, 2),
            'probe_tm': round(probe_tm, 2),
            'primer_tm_diff': round(primer_tm_diff, 2),
            'probe_primer_tm_diff': round(probe_primer_diff, 2),
            'forward_gc': round(forward_gc, 2),
            'reverse_gc': round(reverse_gc, 2),
            'probe_gc': round(probe_gc, 2),
            'forward_length': forward_len,
            'reverse_length': reverse_len,
            'probe_length': probe_len,
            'forward_pos': forward_pos,
            'reverse_pos': reverse_pos,
            'probe_pos': probe_pos,
            'amplicon_size': amplicon_size,
            'penalty': round(penalty, 3),
            'probe_starts_with_g': probe_starts_with_g,
            'warning': 'Probe starts with G (may reduce quenching efficiency)' if probe_starts_with_g else None,
        }

        assays_list.append(assay)

    # Compile results
    results = {
        'assays': assays_list,
        'parameters': {
            'probe_tm_offset': probe_tm_offset,
            'primer_tm_range': primer_tm_range,
            'amplicon_size_range': amplicon_size_range,
        },
        'sequence_length': len(sequence),
        'num_assays_found': len(assays_list),
    }

    return results


def validate_taqman_assay(assay: dict) -> dict:
    """
    Validate if a TaqMan assay meets design criteria.

    Parameters
    ----------
    assay : dict
        TaqMan assay dictionary

    Returns
    -------
    dict
        Validation results
    """

    checks = {
        'amplicon_size_ok': 70 <= assay['amplicon_size'] <= 140,
        'primer_tm_match_ok': assay['primer_tm_diff'] <= 2.0,
        'probe_tm_offset_ok': 5 <= assay['probe_primer_tm_diff'] <= 10,
        'probe_length_ok': 18 <= assay['probe_length'] <= 30,
        'probe_gc_ok': 40 <= assay['probe_gc'] <= 60,
        'probe_5prime_ok': not assay['probe_starts_with_g'],
    }

    all_passed = all(checks.values())

    return {
        'assay_valid': all_passed,
        'checks': checks,
        'failed_checks': [k for k, v in checks.items() if not v],
        'warnings': [assay['warning']] if assay['warning'] else [],
    }

