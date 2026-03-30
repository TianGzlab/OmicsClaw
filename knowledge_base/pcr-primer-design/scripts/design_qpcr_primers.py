"""
Design qPCR primers following MIQE 2.0 guidelines.

This module provides functions for designing quantitative PCR primers with strict
validation criteria according to MIQE (Minimum Information for Publication of
Quantitative Real-Time PCR Experiments) guidelines.
"""

import primer3


def design_qpcr_primers(
    sequence: str,
    target_region: tuple = None,
    amplicon_size_range: tuple = (70, 140),
    tm_match_threshold: float = 2.0,
    primer_tm_range: tuple = (58, 62),
    avoid_3prime_mismatch: bool = True,
    num_return: int = 5
) -> dict:
    """
    Design qPCR primers with strict MIQE-compliant parameters.

    MIQE-compliant parameters:
    - Amplicon size: 70-140 bp (optimal for qPCR)
    - Tm difference: ≤ 2°C between forward and reverse primers
    - Primer Tm: 58-62°C (optimal for most qPCR protocols)
    - No 3' mismatches or secondary structures

    Parameters
    ----------
    sequence : str
        Target DNA sequence (must be uppercase ATCG)
    target_region : tuple, optional
        (start, end) positions for primer placement. If None, uses entire sequence.
    amplicon_size_range : tuple
        (min, max) amplicon size in bp. Default: (70, 140) per MIQE
    tm_match_threshold : float
        Maximum Tm difference between primers in °C. Default: 2.0
    primer_tm_range : tuple
        (min, max) primer Tm in °C. Default: (58, 62)
    avoid_3prime_mismatch : bool
        Strictly avoid 3' end mismatches. Default: True
    num_return : int
        Number of primer pairs to return. Default: 5

    Returns
    -------
    dict
        Dictionary containing:
        - 'primers': list of MIQE-compliant primer pairs
        - 'miqe_compliant': bool indicating if primers meet all MIQE criteria
        - 'parameters': design parameters used

    Example
    -------
    >>> primers = design_qpcr_primers(
    ...     sequence="ATGCGTACG..." * 30,
    ...     amplicon_size_range=(80, 120)
    ... )
    >>> for pair in primers['primers']:
    ...     print(f"Amplicon: {pair['amplicon_size']} bp, ΔTm: {pair['tm_diff']}°C")
    """

    # Validate input
    sequence = sequence.upper().strip()
    if not all(base in 'ATCGN' for base in sequence):
        raise ValueError("Sequence must contain only A, T, C, G, or N characters")

    if len(sequence) < amplicon_size_range[0]:
        raise ValueError(f"Sequence length ({len(sequence)}) is shorter than minimum amplicon size ({amplicon_size_range[0]})")

    # MIQE-compliant Primer3 parameters
    optimal_tm = (primer_tm_range[0] + primer_tm_range[1]) / 2

    primer3_params = {
        'PRIMER_OPT_SIZE': 20,
        'PRIMER_MIN_SIZE': 18,
        'PRIMER_MAX_SIZE': 25,
        'PRIMER_OPT_TM': optimal_tm,
        'PRIMER_MIN_TM': primer_tm_range[0],
        'PRIMER_MAX_TM': primer_tm_range[1],
        'PRIMER_PAIR_MAX_DIFF_TM': tm_match_threshold,  # Critical for qPCR
        'PRIMER_MIN_GC': 40.0,
        'PRIMER_MAX_GC': 60.0,
        'PRIMER_PRODUCT_SIZE_RANGE': [amplicon_size_range],
        'PRIMER_NUM_RETURN': num_return * 2,  # Request more to filter for MIQE compliance
        'PRIMER_MAX_POLY_X': 4,
        'PRIMER_GC_CLAMP': 1,
        'PRIMER_MAX_NS_ACCEPTED': 0,
        'PRIMER_MAX_SELF_ANY': 8,
        'PRIMER_MAX_SELF_END': 3 if avoid_3prime_mismatch else 5,
        'PRIMER_PAIR_MAX_COMPL_ANY': 8,
        'PRIMER_PAIR_MAX_COMPL_END': 3 if avoid_3prime_mismatch else 5,
        # Additional qPCR-specific parameters
        'PRIMER_MAX_HAIRPIN_TH': 47.0,  # Maximum hairpin Tm
    }

    # Set up sequence input
    seq_args = {
        'SEQUENCE_TEMPLATE': sequence,
    }

    # Add target region if specified
    if target_region is not None:
        start, end = target_region
        if start < 0 or end > len(sequence) or start >= end:
            raise ValueError(f"Invalid target region ({start}, {end}) for sequence length {len(sequence)}")
        seq_args['SEQUENCE_TARGET'] = [start, end - start]

    # Run Primer3
    primer3_result = primer3.designPrimers(seq_args, primer3_params)

    # Parse results
    primers_list = []
    num_returned = primer3_result.get('PRIMER_PAIR_NUM_RETURNED', 0)

    for i in range(num_returned):
        # Extract primer sequences
        forward_seq = primer3_result[f'PRIMER_LEFT_{i}_SEQUENCE']
        reverse_seq = primer3_result[f'PRIMER_RIGHT_{i}_SEQUENCE']

        # Extract positions
        forward_pos, forward_len = primer3_result[f'PRIMER_LEFT_{i}']
        reverse_pos, reverse_len = primer3_result[f'PRIMER_RIGHT_{i}']

        # Extract properties
        forward_tm = primer3_result[f'PRIMER_LEFT_{i}_TM']
        reverse_tm = primer3_result[f'PRIMER_RIGHT_{i}_TM']
        forward_gc = primer3_result[f'PRIMER_LEFT_{i}_GC_PERCENT']
        reverse_gc = primer3_result[f'PRIMER_RIGHT_{i}_GC_PERCENT']

        # Amplicon size
        amplicon_size = primer3_result[f'PRIMER_PAIR_{i}_PRODUCT_SIZE']

        # Penalty score
        penalty = primer3_result[f'PRIMER_PAIR_{i}_PENALTY']

        # Calculate Tm difference
        tm_diff = abs(forward_tm - reverse_tm)

        # Check MIQE compliance
        miqe_compliant = (
            amplicon_size_range[0] <= amplicon_size <= amplicon_size_range[1] and
            tm_diff <= tm_match_threshold and
            40 <= forward_gc <= 60 and
            40 <= reverse_gc <= 60 and
            18 <= forward_len <= 25 and
            18 <= reverse_len <= 25
        )

        primer_pair = {
            'pair_id': i,
            'forward_seq': forward_seq,
            'reverse_seq': reverse_seq,
            'forward_tm': round(forward_tm, 2),
            'reverse_tm': round(reverse_tm, 2),
            'tm_diff': round(tm_diff, 2),
            'forward_gc': round(forward_gc, 2),
            'reverse_gc': round(reverse_gc, 2),
            'forward_length': forward_len,
            'reverse_length': reverse_len,
            'forward_pos': forward_pos,
            'reverse_pos': reverse_pos,
            'amplicon_size': amplicon_size,
            'penalty': round(penalty, 3),
            'miqe_compliant': miqe_compliant,
        }

        primers_list.append(primer_pair)

        # Stop if we have enough MIQE-compliant primers
        miqe_count = sum(1 for p in primers_list if p['miqe_compliant'])
        if miqe_count >= num_return:
            break

    # Sort by penalty (best first) and filter for MIQE compliance
    primers_list.sort(key=lambda x: (not x['miqe_compliant'], x['penalty']))

    # Take top num_return primers
    primers_list = primers_list[:num_return]

    # Check if we have any MIQE-compliant primers
    any_miqe_compliant = any(p['miqe_compliant'] for p in primers_list)

    # Compile results
    results = {
        'primers': primers_list,
        'miqe_compliant': any_miqe_compliant,
        'parameters': {
            'amplicon_size_range': amplicon_size_range,
            'tm_match_threshold': tm_match_threshold,
            'primer_tm_range': primer_tm_range,
            'avoid_3prime_mismatch': avoid_3prime_mismatch,
        },
        'sequence_length': len(sequence),
        'num_primers_found': len(primers_list),
        'num_miqe_compliant': sum(1 for p in primers_list if p['miqe_compliant']),
    }

    return results


def validate_miqe_compliance(primer_pair: dict) -> dict:
    """
    Validate if a primer pair meets MIQE guidelines.

    Parameters
    ----------
    primer_pair : dict
        Primer pair dictionary from design_qpcr_primers

    Returns
    -------
    dict
        Validation results with pass/fail for each criterion
    """

    checks = {
        'amplicon_size_ok': 70 <= primer_pair['amplicon_size'] <= 140,
        'tm_difference_ok': primer_pair['tm_diff'] <= 2.0,
        'tm_range_ok': 58 <= primer_pair['forward_tm'] <= 62 and 58 <= primer_pair['reverse_tm'] <= 62,
        'gc_content_ok': 40 <= primer_pair['forward_gc'] <= 60 and 40 <= primer_pair['reverse_gc'] <= 60,
        'primer_length_ok': 18 <= primer_pair['forward_length'] <= 25 and 18 <= primer_pair['reverse_length'] <= 25,
    }

    all_passed = all(checks.values())

    return {
        'miqe_compliant': all_passed,
        'checks': checks,
        'failed_checks': [k for k, v in checks.items() if not v],
    }

