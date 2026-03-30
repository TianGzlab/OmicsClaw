"""
Generate primer design summary reports.

This module creates comprehensive reports of primer design and validation results
in multiple formats (text, markdown, HTML).
"""

from typing import Dict, List
from datetime import datetime


def generate_primer_report(
    primers: Dict,
    validation_results: Dict = None,
    output_format: str = "markdown",
    include_miqe_checklist: bool = False
) -> str:
    """
    Generate a comprehensive primer design and validation report.

    Parameters
    ----------
    primers : dict
        Primer design results from design_*_primers functions
    validation_results : dict, optional
        Dictionary containing validation results:
        - 'specificity': from validate_specificity
        - 'dimers': from analyze_dimers
        - 'secondary_structures': from analyze_secondary_structures
    output_format : str
        Output format: "text", "markdown", or "html". Default: "markdown"
    include_miqe_checklist : bool
        Include MIQE compliance checklist. Default: False

    Returns
    -------
    str
        Formatted report

    Example
    -------
    >>> report = generate_primer_report(
    ...     primers=primer_results,
    ...     validation_results={'specificity': spec, 'dimers': dim},
    ...     output_format="markdown"
    ... )
    >>> print(report)
    """

    if output_format == "markdown":
        return _generate_markdown_report(primers, validation_results, include_miqe_checklist)
    elif output_format == "text":
        return _generate_text_report(primers, validation_results, include_miqe_checklist)
    elif output_format == "html":
        return _generate_html_report(primers, validation_results, include_miqe_checklist)
    else:
        raise ValueError(f"Unknown output format: {output_format}")


def _generate_markdown_report(
    primers: Dict,
    validation_results: Dict = None,
    include_miqe: bool = False
) -> str:
    """Generate markdown format report."""

    lines = []

    # Header
    lines.append("# PCR Primer Design Report")
    lines.append(f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"\n**Sequence Length:** {primers.get('sequence_length', 'N/A')} bp")
    lines.append(f"**Primers Found:** {primers.get('num_primers_found', 0)}")
    lines.append("\n---\n")

    # Design Parameters
    lines.append("## Design Parameters\n")
    params = primers.get('parameters', {})
    for key, value in params.items():
        if value is not None:
            lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
    lines.append("\n---\n")

    # Primer Pairs
    lines.append("## Primer Pairs\n")

    for i, primer_pair in enumerate(primers.get('primers', [])[:5], 1):  # Top 5
        lines.append(f"### Primer Pair {i}")

        if primer_pair.get('miqe_compliant') is not None:
            compliance = "✅ MIQE Compliant" if primer_pair['miqe_compliant'] else "⚠️ Not MIQE Compliant"
            lines.append(f"\n**{compliance}**\n")

        lines.append("#### Sequences")
        lines.append(f"- **Forward:** `{primer_pair['forward_seq']}`")
        lines.append(f"- **Reverse:** `{primer_pair['reverse_seq']}`")

        if 'probe_seq' in primer_pair:
            lines.append(f"- **Probe:** `{primer_pair['probe_seq']}`")

        lines.append("\n#### Properties")
        lines.append(f"- **Amplicon Size:** {primer_pair['amplicon_size']} bp")
        lines.append(f"- **Forward Tm:** {primer_pair['forward_tm']}°C (GC: {primer_pair['forward_gc']}%, Length: {primer_pair['forward_length']} bp)")
        lines.append(f"- **Reverse Tm:** {primer_pair['reverse_tm']}°C (GC: {primer_pair['reverse_gc']}%, Length: {primer_pair['reverse_length']} bp)")
        lines.append(f"- **Tm Difference:** {primer_pair['tm_diff']}°C")

        if 'probe_tm' in primer_pair:
            lines.append(f"- **Probe Tm:** {primer_pair['probe_tm']}°C (GC: {primer_pair['probe_gc']}%)")

        lines.append(f"- **Design Quality Score:** {primer_pair['penalty']:.3f} (lower is better)")

        lines.append("")

    # Validation Results
    if validation_results:
        lines.append("\n---\n")
        lines.append("## Validation Results\n")

        # Specificity
        if 'specificity' in validation_results:
            spec = validation_results['specificity']
            lines.append("### Specificity Check")

            if spec.get('is_specific'):
                lines.append("\n✅ **Primers are specific to target**\n")
            else:
                lines.append("\n⚠️ **Potential off-target amplification detected**\n")

            lines.append(f"- **On-target hits:** {spec.get('on_target_hits', 'N/A')}")
            lines.append(f"- **Off-target hits:** {spec.get('off_target_hits', 'N/A')}")

            if spec.get('off_targets'):
                lines.append("\n**Off-target Products:**")
                for ot in spec['off_targets'][:3]:
                    lines.append(f"- {ot.get('description', 'Unknown')}")

            lines.append("")

        # Dimers
        if 'dimers' in validation_results:
            dim = validation_results['dimers']
            lines.append("### Primer Dimer Analysis")

            if dim['has_issues']:
                lines.append(f"\n⚠️ **{dim['num_problematic']} problematic dimer(s) detected**\n")

                for interaction in dim['problematic_dimers']:
                    lines.append(f"- **{interaction['type'].title()}:** ΔG = {interaction['dg']} kcal/mol")
            else:
                lines.append("\n✅ **No problematic dimers detected**\n")

            lines.append("")

        # Secondary Structures
        if 'secondary_structures' in validation_results:
            sec = validation_results['secondary_structures']
            lines.append("### Secondary Structure Analysis")

            if sec['has_issues']:
                lines.append("\n⚠️ **Secondary structure issues detected**\n")

                if sec['hairpin']['problematic']:
                    lines.append(f"- **Hairpin:** ΔG = {sec['hairpin']['dg']} kcal/mol")

                if sec['self_dimer']['problematic']:
                    lines.append(f"- **Self-dimer:** ΔG = {sec['self_dimer']['dg']} kcal/mol")

                if sec['self_comp_3prime']['problematic']:
                    lines.append(f"- **3' Self-complementarity:** {sec['self_comp_3prime']['3prime_complementary_bases']} bp")
            else:
                lines.append("\n✅ **No secondary structure issues**\n")

            lines.append("")

    # MIQE Checklist
    if include_miqe:
        lines.append("\n---\n")
        lines.append("## MIQE Compliance Checklist\n")
        lines.append(_generate_miqe_checklist(primers))

    # Recommendations
    lines.append("\n---\n")
    lines.append("## Recommendations\n")
    lines.append(_generate_recommendations(primers, validation_results))

    return "\n".join(lines)


def _generate_text_report(
    primers: Dict,
    validation_results: Dict = None,
    include_miqe: bool = False
) -> str:
    """Generate plain text format report."""

    lines = []

    # Header
    lines.append("=" * 60)
    lines.append("PCR PRIMER DESIGN REPORT")
    lines.append("=" * 60)
    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Sequence Length: {primers.get('sequence_length', 'N/A')} bp")
    lines.append(f"Primers Found: {primers.get('num_primers_found', 0)}\n")

    # Primer Pairs
    lines.append("-" * 60)
    lines.append("PRIMER PAIRS")
    lines.append("-" * 60)

    for i, primer_pair in enumerate(primers.get('primers', [])[:3], 1):
        lines.append(f"\nPrimer Pair {i}:")
        lines.append(f"  Forward: {primer_pair['forward_seq']}")
        lines.append(f"  Reverse: {primer_pair['reverse_seq']}")
        lines.append(f"  Amplicon: {primer_pair['amplicon_size']} bp")
        lines.append(f"  Forward Tm: {primer_pair['forward_tm']}°C")
        lines.append(f"  Reverse Tm: {primer_pair['reverse_tm']}°C")
        lines.append(f"  Tm Difference: {primer_pair['tm_diff']}°C")

    return "\n".join(lines)


def _generate_html_report(
    primers: Dict,
    validation_results: Dict = None,
    include_miqe: bool = False
) -> str:
    """Generate HTML format report."""

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>PCR Primer Design Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #2c3e50; }}
        h2 {{ color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #3498db; color: white; }}
        .sequence {{ font-family: 'Courier New', monospace; background: #ecf0f1; padding: 2px 5px; }}
        .pass {{ color: #27ae60; font-weight: bold; }}
        .warn {{ color: #e67e22; font-weight: bold; }}
        .fail {{ color: #e74c3c; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>PCR Primer Design Report</h1>
    <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p><strong>Sequence Length:</strong> {primers.get('sequence_length', 'N/A')} bp</p>
    <p><strong>Primers Found:</strong> {primers.get('num_primers_found', 0)}</p>

    <h2>Primer Pairs</h2>
    <table>
        <tr>
            <th>Pair</th>
            <th>Forward</th>
            <th>Reverse</th>
            <th>Amplicon (bp)</th>
            <th>Forward Tm</th>
            <th>Reverse Tm</th>
            <th>ΔTm</th>
        </tr>
"""

    for i, primer_pair in enumerate(primers.get('primers', [])[:5], 1):
        html += f"""
        <tr>
            <td>{i}</td>
            <td class="sequence">{primer_pair['forward_seq']}</td>
            <td class="sequence">{primer_pair['reverse_seq']}</td>
            <td>{primer_pair['amplicon_size']}</td>
            <td>{primer_pair['forward_tm']}°C</td>
            <td>{primer_pair['reverse_tm']}°C</td>
            <td>{primer_pair['tm_diff']}°C</td>
        </tr>
"""

    html += """
    </table>
</body>
</html>
"""

    return html


def _generate_miqe_checklist(primers: Dict) -> str:
    """Generate MIQE compliance checklist."""

    lines = []
    lines.append("### Experimental Design")
    lines.append("- [ ] qPCR purpose and application specified")
    lines.append("- [ ] Experimental design documented")
    lines.append("- [ ] Biological replicates specified (minimum 3)")
    lines.append("- [ ] Technical replicates specified (minimum 2)")

    lines.append("\n### Sample Information")
    lines.append("- [ ] RNA/DNA quality verified (RIN/DIN score)")
    lines.append("- [ ] Sample storage conditions documented")
    lines.append("- [ ] Reverse transcription method documented (for RT-qPCR)")

    lines.append("\n### Assay Validation")
    lines.append("- [x] Primer sequences documented")
    lines.append("- [ ] Standard curve generated (R² > 0.98)")
    lines.append("- [ ] PCR efficiency calculated (90-110%)")
    lines.append("- [ ] Linear dynamic range determined (≥5 logs)")
    lines.append("- [ ] Melt curve analysis performed (single peak)")

    lines.append("\n### qPCR Protocol")
    lines.append("- [ ] Complete qPCR protocol provided")
    lines.append("- [ ] PCR conditions documented (cycling parameters)")
    lines.append("- [ ] Reaction volume specified")
    lines.append("- [ ] Mastermix composition documented")

    return "\n".join(lines)


def _generate_recommendations(primers: Dict, validation_results: Dict = None) -> str:
    """Generate actionable recommendations."""

    recs = []

    # Check primer quality
    best_primer = primers.get('primers', [{}])[0]

    if best_primer.get('tm_diff', 0) > 2.0:
        recs.append("⚠️ Consider primers with smaller Tm difference (≤2°C) for qPCR")

    if best_primer.get('amplicon_size', 0) > 200:
        recs.append("⚠️ For qPCR, consider shorter amplicon (70-140 bp) for better efficiency")

    # Check validation
    if validation_results:
        if validation_results.get('dimers', {}).get('has_issues'):
            recs.append("⚠️ Redesign primers to avoid dimer formation")

        if not validation_results.get('specificity', {}).get('is_specific'):
            recs.append("⚠️ Verify off-target products experimentally or redesign primers")

    if not recs:
        recs.append("✅ Primers meet quality criteria. Proceed with experimental validation.")

    return "\n".join(f"- {rec}" for rec in recs)


def generate_summary_table(primers_list: List[Dict]) -> str:
    """
    Generate a summary table comparing multiple primer sets.

    Parameters
    ----------
    primers_list : list of dict
        List of primer design results

    Returns
    -------
    str
        Markdown table comparing primers
    """

    lines = []
    lines.append("| Set | Forward | Reverse | Amplicon | Forward Tm | Reverse Tm | ΔTm |")
    lines.append("|-----|---------|---------|----------|------------|------------|-----|")

    for i, primers in enumerate(primers_list, 1):
        if primers.get('primers'):
            best = primers['primers'][0]
            lines.append(
                f"| {i} | `{best['forward_seq'][:15]}...` | "
                f"`{best['reverse_seq'][:15]}...` | "
                f"{best['amplicon_size']} bp | "
                f"{best['forward_tm']}°C | "
                f"{best['reverse_tm']}°C | "
                f"{best['tm_diff']}°C |"
            )

    return "\n".join(lines)

