# PCR Primer Design Code Examples

Complete code examples for all workflow steps. Reference these when executing the workflow.

**← Back to [SKILL.md](../SKILL.md) | See also:** [Parameter Ranges](parameter_ranges.md) | [Best Practices](primer_design_best_practices.md) | [Troubleshooting](troubleshooting_guide.md)

## How to Use This Guide

This reference provides **complete, working code examples** for understanding and adapting primer design workflows. Use these examples when you need to:
- Understand the full API of each function
- Customize parameters beyond the Standard Workflow in SKILL.md
- Implement advanced features (multiplex, TaqMan, custom validation)

**For standard workflows:** See [SKILL.md Standard Workflow](../SKILL.md#standard-workflow) for low-freedom "execute exactly" commands.

---

## Table of Contents

1. [Loading Target Sequences](#loading-target-sequences)
2. [Primer Design Examples](#primer-design-examples)
3. [Validation Examples](#validation-examples)
4. [Report Generation](#report-generation)
5. [Visualization](#visualization)
6. [Export Examples](#export-examples)

---

## Loading Target Sequences

### From FASTA File

```python
from Bio import SeqIO

# Load sequence from FASTA file
record = SeqIO.read("target_sequence.fasta", "fasta")
sequence = str(record.seq)
print(f"Loaded sequence: {record.id}, length: {len(sequence)} bp")
```

### From GenBank/RefSeq Accession

```python
from Bio import Entrez, SeqIO

# Set your email for NCBI
Entrez.email = "your.email@example.com"

# Fetch sequence by accession
handle = Entrez.efetch(db="nucleotide", id="NM_001256799", rettype="fasta", retmode="text")
record = SeqIO.read(handle, "fasta")
sequence = str(record.seq)
handle.close()

print(f"Retrieved: {record.id}")
print(f"Length: {len(sequence)} bp")
```

### From Gene Name Search

```python
from Bio import Entrez, SeqIO

# Search for gene
Entrez.email = "your.email@example.com"

# Search gene database
search_term = "GAPDH[Gene] AND Homo sapiens[Organism]"
handle = Entrez.esearch(db="gene", term=search_term)
record = Entrez.read(handle)
handle.close()

if record["IdList"]:
    gene_id = record["IdList"][0]
    print(f"Found gene ID: {gene_id}")

    # Get gene details
    handle = Entrez.efetch(db="gene", id=gene_id, rettype="gb", retmode="xml")
    gene_record = Entrez.read(handle)
    handle.close()

    # Extract RefSeq accession and fetch sequence
    # (parsing logic depends on gene record structure)
else:
    print("Gene not found")
```

---

## Primer Design Examples

### Standard PCR Primers

```python
from scripts.design_standard_primers import design_pcr_primers

# Design standard PCR primers
primers = design_pcr_primers(
    sequence=sequence,
    target_region=None,  # None = entire sequence, or (start, end) tuple
    primer_size_range=(18, 25),
    tm_range=(55, 65),
    gc_range=(40, 60),
    amplicon_size_range=(100, 1000),
    num_return=5
)

# Display results
print(f"Found {len(primers['primers'])} primer pairs")

for i, pair in enumerate(primers['primers'][:3], 1):
    print(f"\nPrimer pair {i}:")
    print(f"  Forward: {pair['forward_seq']} (Tm: {pair['forward_tm']:.1f}°C)")
    print(f"  Reverse: {pair['reverse_seq']} (Tm: {pair['reverse_tm']:.1f}°C)")
    print(f"  Amplicon: {pair['amplicon_size']} bp")
    print(f"  Quality score: {pair['penalty']:.3f}")
```

### qPCR Primers (MIQE-Compliant)

```python
from scripts.design_qpcr_primers import design_qpcr_primers, validate_miqe_compliance

# Design qPCR primers with strict MIQE guidelines
primers = design_qpcr_primers(
    sequence=sequence,
    target_region=None,
    amplicon_size_range=(70, 140),  # MIQE: 70-140 bp
    tm_match_threshold=2.0,  # Max Tm difference
    primer_tm_range=(58, 62),
    avoid_3prime_mismatch=True,
    num_return=5
)

print(f"MIQE-compliant pairs: {primers['num_miqe_compliant']}/{primers['num_primers_found']}")

# Validate MIQE compliance
for pair in primers['primers']:
    validation = validate_miqe_compliance(pair)

    print(f"\nPrimer pair {pair['pair_id'] + 1}:")
    print(f"  MIQE compliant: {validation['miqe_compliant']}")

    if not validation['miqe_compliant']:
        print(f"  Failed checks: {', '.join(validation['failed_checks'])}")
```

### TaqMan Assay Design

```python
from scripts.design_taqman_probes import design_taqman_assay, validate_taqman_assay

# Design complete TaqMan assay (primers + probe)
assay = design_taqman_assay(
    sequence=sequence,
    target_region=None,
    probe_tm_offset=8.0,  # Probe Tm = primer Tm + 8°C
    primer_tm_range=(58, 62),
    amplicon_size_range=(70, 140)
)

# Display first assay
if assay['assays']:
    a = assay['assays'][0]
    print("TaqMan Assay Design:")
    print(f"  Forward: {a['forward_seq']} (Tm: {a['forward_tm']:.1f}°C)")
    print(f"  Reverse: {a['reverse_seq']} (Tm: {a['reverse_tm']:.1f}°C)")
    print(f"  Probe:   {a['probe_seq']} (Tm: {a['probe_tm']:.1f}°C)")
    print(f"  Amplicon: {a['amplicon_size']} bp")

    # Validate assay
    validation = validate_taqman_assay(a)
    print(f"  Valid: {validation['assay_valid']}")

    if validation['warnings']:
        for warning in validation['warnings']:
            print(f"  ⚠ {warning}")
```

---

## Validation Examples

### Melting Temperature Calculation

```python
from scripts.calculate_tm import calculate_tm_comprehensive, calculate_tm_range

# Calculate Tm using all methods
tm_result = calculate_tm_comprehensive(
    primer_sequence="ATGCGTACGATCGATCG",
    method="all",
    salt_conc=50.0,
    dna_conc=200.0
)

print(f"Nearest-Neighbor Tm: {tm_result['tm_nn']:.1f}°C (recommended)")
print(f"Salt-Adjusted Tm: {tm_result['tm_salt_adjusted']:.1f}°C")
print(f"GC-Content Tm: {tm_result['tm_gc']:.1f}°C")

# Calculate Tm range for multiple primers
primers_list = [
    "ATGCGTACGATCGATCG",
    "CGTAGCTAGCTAGCTAG",
    "GCTATCGATCGTAGCTA"
]

tm_range = calculate_tm_range(primers_list, method="nearest_neighbor")

print(f"\nTm Range Analysis:")
print(f"  Minimum Tm: {tm_range['tm_min']:.1f}°C")
print(f"  Maximum Tm: {tm_range['tm_max']:.1f}°C")
print(f"  Range: {tm_range['tm_range']:.1f}°C")
print(f"  Compatible for multiplex: {tm_range['tm_compatible']}")
```

### Specificity Validation

```python
from scripts.validate_specificity import check_primer_specificity, in_silico_pcr

# Check specificity using in-silico PCR (local)
products = in_silico_pcr(
    forward_primer=primers['primers'][0]['forward_seq'],
    reverse_primer=primers['primers'][0]['reverse_seq'],
    sequence=sequence,
    max_product_size=5000
)

print(f"In-silico PCR: {len(products)} product(s)")
for p in products:
    print(f"  {p['product_size']} bp at position {p['forward_start']}-{p['reverse_start']}")

# Note: For actual specificity checking via NCBI Primer-BLAST,
# implement the full API workflow (requires multiple requests)
```

### Dimer Analysis

```python
from scripts.check_dimers import analyze_dimers, check_3prime_complementarity

# Check for dimers
primer_sequences = [
    primers['primers'][0]['forward_seq'],
    primers['primers'][0]['reverse_seq']
]

dimer_analysis = analyze_dimers(
    primer_list=primer_sequences,
    temperature=60.0,
    dg_threshold=-5.0
)

print(f"Dimer Analysis:")
print(f"  Interactions checked: {dimer_analysis['num_interactions']}")
print(f"  Problematic dimers: {dimer_analysis['num_problematic']}")

for interaction in dimer_analysis['interactions']:
    status = "⚠ WARNING" if interaction['problematic'] else "✓ OK"
    print(f"  {interaction['type']}: ΔG = {interaction['dg']:.2f} kcal/mol {status}")

# Check 3' complementarity specifically
three_prime = check_3prime_complementarity(
    primer1=primer_sequences[0],
    primer2=primer_sequences[1],
    window_size=5
)

print(f"\n3' Complementarity: {three_prime['complementary_bases']} bp")
if three_prime['is_problematic']:
    print(f"  ⚠ {three_prime['warning']}")
```

### Secondary Structure Analysis

```python
from scripts.check_secondary_structures import (
    analyze_secondary_structures,
    comprehensive_qc_check,
    check_gc_clamp,
    check_poly_runs
)

# Analyze secondary structures
structures = analyze_secondary_structures(
    primer_sequence=primers['primers'][0]['forward_seq'],
    temperature=60.0
)

print("Secondary Structure Analysis:")
print(f"  Hairpin ΔG: {structures['hairpin']['dg']:.2f} kcal/mol")
print(f"    Problematic: {structures['hairpin']['problematic']}")

print(f"  Self-dimer ΔG: {structures['self_dimer']['dg']:.2f} kcal/mol")
print(f"    Problematic: {structures['self_dimer']['problematic']}")

print(f"  3' Self-complementarity: {structures['self_comp_3prime']['3prime_complementary_bases']} bp")
print(f"    Problematic: {structures['self_comp_3prime']['problematic']}")

# Comprehensive QC check
qc = comprehensive_qc_check(
    primer_sequence=primers['primers'][0]['forward_seq'],
    temperature=60.0
)

print(f"\nComprehensive QC: {'✓ PASS' if qc['passes_qc'] else '✗ FAIL'}")
if qc['issues']:
    for issue in qc['issues']:
        print(f"  - {issue}")

# Check GC clamp
gc_clamp = check_gc_clamp(primers['primers'][0]['forward_seq'])
print(f"\nGC Clamp: {gc_clamp['recommendation']}")

# Check poly runs
poly_runs = check_poly_runs(primers['primers'][0]['forward_seq'])
if poly_runs['has_long_runs']:
    print(f"⚠ {poly_runs['warning']}")
else:
    print("✓ No problematic poly runs")
```

### Multiplex Compatibility

```python
from scripts.check_dimers import analyze_multiplex_compatibility

# Check multiple primer pairs for multiplex PCR
primer_pairs = [
    {
        'forward_seq': "ATGCGTACGATCGATCG",
        'reverse_seq': "CGTAGCTAGCTAGCTAG",
        'forward_tm': 58.5,
        'reverse_tm': 59.2
    },
    {
        'forward_seq': "GCTATCGATCGTAGCTA",
        'reverse_seq': "TAGCTAGCTAGCGATCG",
        'forward_tm': 59.0,
        'reverse_tm': 58.8
    }
]

compatibility = analyze_multiplex_compatibility(
    primer_pairs=primer_pairs,
    temperature=60.0,
    dg_threshold=-5.0
)

print(f"Multiplex Compatibility: {compatibility['is_compatible']}")
print(f"  Tm range: {compatibility['tm_range']:.1f}°C")
print(f"  Tm compatible: {compatibility['tm_compatible']}")

if compatibility['recommendations']:
    print("\nRecommendations:")
    for rec in compatibility['recommendations']:
        print(f"  - {rec}")
```

---

## Report Generation

### Generate Comprehensive Report

```python
from scripts.generate_reports import generate_primer_report

# Compile validation results
validation_results = {
    'specificity': {
        'is_specific': True,
        'num_products': 1,
        'on_target_hits': 1,
        'off_target_hits': 0,
    },
    'dimers': dimer_analysis,
    'secondary_structures': structures,
}

# Generate markdown report
report = generate_primer_report(
    primers=primers,
    validation_results=validation_results,
    output_format="markdown",
    include_miqe_checklist=True
)

# Save to file
with open("primer_design_report.md", "w") as f:
    f.write(report)

print("Report generated: primer_design_report.md")

# Also generate HTML version
html_report = generate_primer_report(
    primers=primers,
    validation_results=validation_results,
    output_format="html",
    include_miqe_checklist=False
)

with open("primer_design_report.html", "w") as f:
    f.write(html_report)
```

### Generate Summary Table

```python
from scripts.generate_reports import generate_summary_table

# Compare multiple primer designs
primers_list = [primers1, primers2, primers3]

summary_table = generate_summary_table(primers_list)
print(summary_table)
```

---

## Visualization

### Plot Primer Alignment

```python
from scripts.visualize_primers import plot_primer_alignment

# Visualize primer binding sites on sequence
plot_primer_alignment(
    sequence=sequence,
    primers=primers['primers'][0],
    output_file="primer_alignment.svg",
    show_sequence=False
)

print("Visualization saved: primer_alignment.svg")
```

### Plot Tm Distribution

```python
from scripts.visualize_primers import plot_tm_distribution

# Plot Tm for all primer pairs
plot_tm_distribution(
    primer_set=primers['primers'],
    output_file="tm_distribution.svg"
)
```

### Plot Primer Properties

```python
from scripts.visualize_primers import (
    plot_primer_properties,
    plot_amplicon_sizes,
    plot_qc_summary
)

# Plot all primer properties
plot_primer_properties(
    primer_set=primers['primers'][:5],
    output_file="primer_properties.svg"
)

# Plot amplicon sizes with target range
plot_amplicon_sizes(
    primer_set=primers['primers'],
    output_file="amplicon_sizes.svg",
    target_range=(70, 140)
)

# Plot QC summary (requires validation results for each pair)
plot_qc_summary(
    primer_set=primers['primers'][:3],
    validation_results=[val1, val2, val3],
    output_file="qc_summary.svg"
)
```

---

## Export Examples

### Export to CSV

```python
from scripts.export_results import export_primers

# Export to CSV
export_primers(
    primers=primers,
    format="csv",
    output_file="primers.csv",
    include_validation=True,
    validation_results=validation_results
)
```

### Export to Excel

```python
# Export to Excel with multiple sheets
export_primers(
    primers=primers,
    format="excel",
    output_file="primers.xlsx",
    include_validation=True,
    validation_results=validation_results
)
```

### Export to JSON

```python
# Export to JSON
export_primers(
    primers=primers,
    format="json",
    output_file="primers.json",
    include_validation=True,
    validation_results=validation_results
)
```

### Export IDT Order Format

```python
# Export in IDT order format
export_primers(
    primers=primers,
    format="idt_order",
    output_file="idt_order.txt"
)

# Ready to paste into IDT ordering system
```

### Export MIQE Checklist

```python
# Export MIQE compliance checklist (Excel)
export_primers(
    primers=primers,
    format="miqe_checklist",
    output_file="miqe_checklist.xlsx"
)
```

### Export for Benchling

```python
from scripts.export_results import export_for_benchling

# Export in Benchling-compatible format
export_for_benchling(
    primers=primers,
    output_file="benchling_primers.csv"
)
```

---

## Complete Workflow Example

See [eval/complete_example_analysis.py](../eval/complete_example_analysis.py) for a full end-to-end example including:
- Sequence loading
- qPCR primer design
- Complete validation workflow
- Report generation
- Export in multiple formats

Run with:
```bash
cd eval
python complete_example_analysis.py
```

---

**Last Updated:** 2026-01-28
