"""
Analyze primer secondary structures (hairpins, self-complementarity).

This module checks for problematic secondary structures that can reduce
primer binding efficiency and PCR performance.
"""

import primer3
from typing import Dict
from Bio.Seq import Seq


def analyze_secondary_structures(
    primer_sequence: str,
    temperature: float = 60.0,
    mv_conc: float = 50.0,
    dv_conc: float = 0.0,
    dntp_conc: float = 0.8,
    dna_conc: float = 50.0
) -> Dict:
    """
    Analyze primer for hairpins and self-complementarity.

    Parameters
    ----------
    primer_sequence : str
        Primer sequence to analyze
    temperature : float
        PCR annealing temperature in °C. Default: 60.0
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
        - 'hairpin': hairpin structure analysis
        - 'self_comp': self-complementarity analysis
        - 'has_issues': bool indicating problematic structures

    Example
    -------
    >>> structures = analyze_secondary_structures("ATGCGTACGATCGATCG")
    >>> if structures['hairpin']['dg'] < -2.0:
    ...     print("⚠ Hairpin detected!")
    """

    # Validate input
    primer_sequence = primer_sequence.upper().strip()

    if not all(base in 'ATCGN' for base in primer_sequence):
        raise ValueError("Primer must contain only A, T, C, G, or N")

    # Calculate hairpin
    hairpin = primer3.calcHairpin(
        primer_sequence,
        mv_conc=mv_conc,
        dv_conc=dv_conc,
        dntp_conc=dntp_conc,
        dna_conc=dna_conc,
        temp_c=temperature,
        output_structure=True
    )

    hairpin_dg = hairpin.dg / 1000.0  # Convert to kcal/mol
    hairpin_tm = hairpin.tm if hairpin.tm is not None else None
    hairpin_structure = hairpin.ascii_structure if hasattr(hairpin, 'ascii_structure') else "N/A"

    # Calculate self-complementarity (homodimer)
    self_dimer = primer3.calcHomodimer(
        primer_sequence,
        mv_conc=mv_conc,
        dv_conc=dv_conc,
        dntp_conc=dntp_conc,
        dna_conc=dna_conc,
        temp_c=temperature,
        output_structure=True
    )

    self_dimer_dg = self_dimer.dg / 1000.0  # Convert to kcal/mol
    self_dimer_tm = self_dimer.tm if self_dimer.tm is not None else None

    # Check 3' self-complementarity (critical for PCR)
    three_prime_comp = check_3prime_self_complementarity(primer_sequence)

    # Determine if there are issues
    hairpin_issue = hairpin_dg < -2.0  # Stable hairpins
    self_comp_issue = self_dimer_dg < -5.0  # Stable self-dimers
    three_prime_issue = three_prime_comp['complementary_bases'] > 8

    has_issues = hairpin_issue or self_comp_issue or three_prime_issue

    results = {
        'primer_sequence': primer_sequence,
        'primer_length': len(primer_sequence),
        'hairpin': {
            'dg': round(hairpin_dg, 2),
            'tm': round(hairpin_tm, 2) if hairpin_tm is not None else None,
            'structure': hairpin_structure,
            'problematic': hairpin_issue,
            'threshold': -2.0,
        },
        'self_dimer': {
            'dg': round(self_dimer_dg, 2),
            'tm': round(self_dimer_tm, 2) if self_dimer_tm is not None else None,
            'problematic': self_comp_issue,
            'threshold': -5.0,
        },
        'self_comp_3prime': three_prime_comp,
        'has_issues': has_issues,
        'parameters': {
            'temperature': temperature,
            'mv_conc': mv_conc,
            'dv_conc': dv_conc,
            'dntp_conc': dntp_conc,
            'dna_conc': dna_conc,
        }
    }

    return results


def check_3prime_self_complementarity(primer_sequence: str, window_size: int = 5) -> Dict:
    """
    Check for self-complementarity at the 3' end of a primer.

    3' self-complementarity can lead to primer extension and reduced efficiency.

    Parameters
    ----------
    primer_sequence : str
        Primer sequence
    window_size : int
        Number of bases at 3' end to check. Default: 5

    Returns
    -------
    dict
        3' self-complementarity analysis
    """

    primer_sequence = primer_sequence.upper()

    # Get 3' end
    three_prime = primer_sequence[-window_size:]

    # Get reverse complement
    three_prime_rc = str(Seq(three_prime).reverse_complement())

    # Count complementary bases
    complementary_bases = 0
    for i in range(min(len(three_prime), len(three_prime_rc))):
        if three_prime[-(i+1)] == three_prime_rc[i]:
            complementary_bases += 1
        else:
            break

    # Total self-complementarity
    total_comp = sum(1 for i, base in enumerate(primer_sequence)
                     for j, base2 in enumerate(primer_sequence)
                     if i < j and base == str(Seq(base2).complement()))

    is_problematic = complementary_bases > 8 or total_comp > 12

    return {
        '3prime_complementary_bases': complementary_bases,
        'total_complementarity': total_comp,
        'problematic': is_problematic,
        'threshold_3prime': 8,
        'threshold_total': 12,
    }


def check_gc_clamp(primer_sequence: str) -> Dict:
    """
    Check for appropriate GC clamp at 3' end.

    A GC clamp (1-2 G or C bases in the last 5 positions) helps primer binding,
    but too many (>3) can cause non-specific binding.

    Parameters
    ----------
    primer_sequence : str
        Primer sequence

    Returns
    -------
    dict
        GC clamp analysis
    """

    primer_sequence = primer_sequence.upper()

    # Check last 5 bases
    three_prime_5 = primer_sequence[-5:]

    # Count G and C in last 5 bases
    gc_count = sum(1 for base in three_prime_5 if base in 'GC')

    # Check last 3 bases for consecutive GC
    three_prime_3 = primer_sequence[-3:]
    all_gc_3prime = all(base in 'GC' for base in three_prime_3)

    # Optimal: 1-2 GC in last 5 bases, not all GC in last 3
    is_optimal = 1 <= gc_count <= 2 and not all_gc_3prime
    is_problematic = gc_count == 0 or all_gc_3prime

    recommendation = None
    if gc_count == 0:
        recommendation = "Consider adding 1-2 G/C bases at 3' end for better binding"
    elif all_gc_3prime:
        recommendation = "Too many G/C at 3' end may cause non-specific binding"
    elif is_optimal:
        recommendation = "GC clamp is optimal"

    return {
        'gc_count_last5': gc_count,
        'all_gc_last3': all_gc_3prime,
        'is_optimal': is_optimal,
        'is_problematic': is_problematic,
        'recommendation': recommendation,
    }


def check_poly_runs(primer_sequence: str, max_length: int = 4) -> Dict:
    """
    Check for runs of identical nucleotides.

    Long runs of the same nucleotide (e.g., AAAA, GGGG) can cause
    non-specific binding and PCR artifacts.

    Parameters
    ----------
    primer_sequence : str
        Primer sequence
    max_length : int
        Maximum acceptable run length. Default: 4

    Returns
    -------
    dict
        Poly-run analysis
    """

    primer_sequence = primer_sequence.upper()

    # Find runs of each nucleotide
    runs = {'A': 0, 'T': 0, 'C': 0, 'G': 0}

    for base in 'ATCG':
        current_run = 0
        max_run = 0

        for seq_base in primer_sequence:
            if seq_base == base:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 0

        runs[base] = max_run

    # Find longest run
    longest_run_base = max(runs, key=runs.get)
    longest_run_length = runs[longest_run_base]

    has_long_runs = longest_run_length > max_length

    return {
        'runs': runs,
        'longest_run_base': longest_run_base,
        'longest_run_length': longest_run_length,
        'has_long_runs': has_long_runs,
        'max_acceptable': max_length,
        'warning': f"Run of {longest_run_length} {longest_run_base}s exceeds maximum ({max_length})" if has_long_runs else None,
    }


def comprehensive_qc_check(primer_sequence: str, temperature: float = 60.0) -> Dict:
    """
    Perform comprehensive QC check on a primer.

    Combines all secondary structure and sequence quality checks.

    Parameters
    ----------
    primer_sequence : str
        Primer sequence
    temperature : float
        PCR annealing temperature

    Returns
    -------
    dict
        Comprehensive QC results

    Example
    -------
    >>> qc = comprehensive_qc_check("ATGCGTACGATCGATCG", temperature=60)
    >>> if qc['passes_qc']:
    ...     print("✓ Primer passes all QC checks")
    """

    # Run all checks
    secondary = analyze_secondary_structures(primer_sequence, temperature)
    gc_clamp = check_gc_clamp(primer_sequence)
    poly_runs = check_poly_runs(primer_sequence)

    # Compile all issues
    all_issues = []

    if secondary['hairpin']['problematic']:
        all_issues.append(f"Hairpin formation (ΔG = {secondary['hairpin']['dg']} kcal/mol)")

    if secondary['self_dimer']['problematic']:
        all_issues.append(f"Self-dimer formation (ΔG = {secondary['self_dimer']['dg']} kcal/mol)")

    if secondary['self_comp_3prime']['problematic']:
        all_issues.append(f"High 3' self-complementarity ({secondary['self_comp_3prime']['3prime_complementary_bases']} bp)")

    if gc_clamp['is_problematic']:
        all_issues.append(gc_clamp['recommendation'])

    if poly_runs['has_long_runs']:
        all_issues.append(poly_runs['warning'])

    passes_qc = len(all_issues) == 0

    return {
        'primer_sequence': primer_sequence,
        'passes_qc': passes_qc,
        'secondary_structures': secondary,
        'gc_clamp': gc_clamp,
        'poly_runs': poly_runs,
        'issues': all_issues,
        'num_issues': len(all_issues),
    }

