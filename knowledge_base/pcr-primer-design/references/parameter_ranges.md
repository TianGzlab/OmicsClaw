# Primer Design Parameter Ranges

Quick reference guide for primer design parameters across different applications.

**← Back to [SKILL.md](../SKILL.md) | See also:** [Code Examples](code_examples.md) | [Best Practices](primer_design_best_practices.md) | [MIQE Guidelines](miqe_guidelines.md)

**Use this guide** when customizing design parameters beyond standard workflows. Referenced from SKILL.md Clarification Question #3 for parameter customization.

---

## Standard Parameter Ranges

### Primer Length

| Application | Optimal Range | Acceptable Range | Notes |
|-------------|---------------|------------------|-------|
| Standard PCR | 20-22 nt | 18-25 nt | Balance specificity and efficiency |
| qPCR | 18-22 nt | 18-24 nt | Shorter is better for kinetics |
| Sequencing | 20-24 nt | 18-26 nt | Longer for specificity |
| Multiplex PCR | 20-22 nt | 18-24 nt | Keep all primers similar length |
| SNP Genotyping | 18-25 nt | 18-28 nt | Allele-specific primer can be longer |

### Melting Temperature (Tm)

| Application | Optimal Tm | Tm Match (ΔTm) | Notes |
|-------------|------------|----------------|-------|
| Standard PCR | 55-65°C | ≤ 5°C | More relaxed tolerance |
| qPCR | 58-62°C | ≤ 2°C | Strict matching required |
| qPCR (MIQE strict) | 59-61°C | ≤ 1°C | Best practice for publication |
| Sequencing | 55-60°C | N/A | Single primer |
| Multiplex PCR | 58-62°C | ≤ 3°C | All primers in range |
| TaqMan Probe | 65-70°C | +5 to +10°C vs primers | Higher than primers |

### GC Content

| Range | Category | Suitability | Notes |
|-------|----------|-------------|-------|
| < 30% | Very AT-rich | Poor | Weak binding, low Tm, redesign if possible |
| 30-40% | AT-rich | Acceptable | May need optimization |
| 40-60% | Optimal | Excellent | Standard range for most applications |
| 60-65% | GC-rich | Acceptable | May form secondary structures |
| > 65% | Very GC-rich | Poor | Strong secondary structures, redesign if possible |

### Amplicon Size

| Application | Optimal Range | Maximum | Notes |
|-------------|---------------|---------|-------|
| qPCR (SYBR) | 70-140 bp | 200 bp | Shorter = higher efficiency |
| qPCR (TaqMan) | 70-140 bp | 150 bp | MIQE recommendation |
| Standard PCR | 200-600 bp | 3-5 kb | Depends on polymerase |
| Multiplex PCR | 100-600 bp | 1000 bp | Space by 50+ bp for gel resolution |
| Sequencing | 400-800 bp | 1000 bp | Depends on sequencing platform |

---

## Thermodynamic Parameters

### Primer Dimers and Secondary Structures

| Structure Type | Threshold | Interpretation |
|----------------|-----------|----------------|
| **Primer Dimer (ΔG)** | > -5 kcal/mol | Acceptable (unlikely to form) |
| | -5 to -9 kcal/mol | Marginal (may form, monitor) |
| | < -9 kcal/mol | Problematic (will form, redesign) |
| **Hairpin (ΔG)** | > -2 kcal/mol | Acceptable |
| | -2 to -4 kcal/mol | Marginal |
| | < -4 kcal/mol | Problematic |
| **Self-Complementarity (3')** | < 8 bp | Acceptable |
| | 8-10 bp | Marginal |
| | > 10 bp | Problematic |
| **Self-Complementarity (Total)** | < 12 bp | Acceptable |
| | 12-16 bp | Marginal |
| | > 16 bp | Problematic |

### Salt Concentrations (for Tm Calculation)

| Component | Standard PCR | qPCR | High-Fidelity |
|-----------|--------------|------|---------------|
| Monovalent (Na⁺, K⁺) | 50 mM | 50 mM | 50 mM |
| Divalent (Mg²⁺) | 1.5-2.5 mM | 3.0-5.0 mM | 2.0-4.0 mM |
| dNTPs | 0.2-0.8 mM | 0.8 mM | 0.2 mM |
| Primer concentration | 0.2-1.0 µM | 0.2-0.5 µM | 0.2-0.5 µM |

---

## Application-Specific Guidelines

### Standard PCR

**Parameters:**
```
Primer Length:     18-25 nt (optimal: 20-22)
Tm:                55-65°C
ΔTm:               ≤ 5°C
GC%:               40-60%
Amplicon:          100-1000 bp (optimal: 200-600)
GC Clamp:          1-2 G/C in last 5 bases
Max Poly-X:        ≤ 4 nucleotides
```

**Typical Cycling:**
```
Initial denaturation: 95°C, 3-5 min
Denaturation:        95°C, 30 sec
Annealing:           55-65°C, 30 sec
Extension:           72°C, 1 min/kb
Cycles:              25-35
Final extension:     72°C, 5-10 min
```

### Quantitative PCR (qPCR)

**MIQE-Compliant Parameters:**
```
Primer Length:     18-22 nt (optimal: 20)
Tm:                58-62°C (optimal: 59-61°C)
ΔTm:               ≤ 2°C (optimal: ≤ 1°C)
GC%:               40-60%
Amplicon:          70-140 bp
GC Clamp:          1-2 G/C in last 5 bases
Max Poly-X:        ≤ 4 nucleotides
3' Stability:      No mismatches at 3' end
Exon-spanning:     Yes (or intron > 1 kb)
```

**Typical Cycling:**
```
Initial denaturation: 95°C, 10 min
Denaturation:        95°C, 15 sec
Annealing/Extension: 60°C, 60 sec
Cycles:              40-45
Melt curve:          60-95°C, 0.5°C increments (SYBR)
```

**Validation Criteria:**
```
Efficiency:        90-110% (optimal: 95-105%)
R²:                > 0.98
Linear range:      ≥ 5 logs
Specificity:       Single melt peak (SYBR)
NTC Cq:            > 35 or undetected
-RT Cq:            > target +5 or undetected
Technical CV:      < 5%
```

### TaqMan Assays

**Primer Parameters:**
```
Same as qPCR above
```

**Probe Parameters:**
```
Probe Length:      18-30 nt (optimal: 20-25)
Probe Tm:          65-70°C (5-10°C higher than primers)
GC%:               40-60%
No G at 5' end:    Avoid (quenching issue)
Location:          Between primers, closer to forward
```

### Multiplex PCR

**Parameters:**
```
Primer Length:     18-24 nt (all similar)
Tm:                58-62°C
ΔTm:               All primers within 3-5°C
GC%:               40-60%
Amplicon spacing:  ≥ 50 bp difference (for gel)
Check all pairs:   For cross-dimers
```

**Design Priority:**
1. Design each primer pair individually
2. Check all pairwise interactions for dimers
3. Verify no off-target amplification between targets
4. Test individually before multiplexing
5. Optimize primer ratios if needed

---

## PCR Reaction Optimization

### Annealing Temperature

| Strategy | Temperature | Use Case |
|----------|-------------|----------|
| Standard | Tm - 5°C | Starting point |
| Stringent | Tm | High specificity needed |
| Relaxed | Tm - 7°C | Weak amplification |
| Gradient PCR | Tm ± 5°C | Optimization |
| Touchdown | Start Tm + 5°C, decrease 0.5-1°C per cycle | Non-specific products |

### Mg²⁺ Concentration

| [Mg²⁺] | Effect | Use Case |
|--------|--------|----------|
| 1.0-1.5 mM | Low | High specificity, reduce non-specific |
| 1.5-2.5 mM | Standard | Most applications |
| 2.5-4.0 mM | High | Weak amplification, increase yield |
| > 4.0 mM | Very high | Last resort, may reduce fidelity |

### Primer Concentration

| [Primer] | Effect | Use Case |
|----------|--------|----------|
| 0.1-0.2 µM | Low | Reduce dimers, high specificity |
| 0.2-0.5 µM | Standard | qPCR, most applications |
| 0.5-1.0 µM | High | Standard PCR, weak targets |
| > 1.0 µM | Very high | Not recommended (excess dimers) |

### Cycle Number

| Application | Typical Cycles | Notes |
|-------------|----------------|-------|
| qPCR | 40-45 | Stop when Cq reached |
| Standard PCR | 25-35 | More cycles = more non-specific |
| Colony PCR | 30-35 | More cycles for crude template |
| Nested PCR | 20-25 (outer), 20-30 (inner) | Two rounds |

---

## Tm Calculation Methods

### Nearest-Neighbor (Recommended)

**Most accurate method**
- Considers sequence context
- Accounts for nearest-neighbor interactions
- Requires salt concentration inputs

**Use:** All applications, especially qPCR

### Salt-Adjusted

**Formula:**
```
Tm = 2(A+T) + 4(G+C) - 16.6×log₁₀[Na⁺] + 0.41(%GC)
```

**Use:** Quick estimates, standard PCR

### Basic Wallace Rule

**Formula:**
```
Tm = 2(A+T) + 4(G+C)
```

**Use:** Very rough estimate only (<13 nt)

### %GC Method (for primers >13 nt)

**Formula:**
```
Tm = 64.9 + 41×(G+C-16.4)/(A+T+G+C)
```

**Use:** Quick estimate for longer primers

---

## Primer Design Software Settings

### Primer3 Key Parameters

```python
PRIMER_OPT_SIZE = 20              # Optimal length
PRIMER_MIN_SIZE = 18              # Minimum length
PRIMER_MAX_SIZE = 25              # Maximum length
PRIMER_OPT_TM = 60.0              # Optimal Tm
PRIMER_MIN_TM = 58.0              # Minimum Tm
PRIMER_MAX_TM = 62.0              # Maximum Tm
PRIMER_PAIR_MAX_DIFF_TM = 2.0     # Max Tm difference
PRIMER_MIN_GC = 40.0              # Minimum GC%
PRIMER_MAX_GC = 60.0              # Maximum GC%
PRIMER_PRODUCT_SIZE_RANGE = [(70, 140)]  # For qPCR
PRIMER_MAX_POLY_X = 4             # Max nucleotide run
PRIMER_GC_CLAMP = 1               # GC at 3' end
PRIMER_MAX_SELF_ANY = 8           # Max self-complementarity
PRIMER_MAX_SELF_END = 3           # Max 3' self-complementarity
PRIMER_PAIR_MAX_COMPL_ANY = 8     # Max primer-primer complementarity
PRIMER_PAIR_MAX_COMPL_END = 3     # Max 3' primer-primer complementarity
```

### For Standard PCR (Relaxed)

```python
PRIMER_PRODUCT_SIZE_RANGE = [(100, 1000)]
PRIMER_PAIR_MAX_DIFF_TM = 5.0
PRIMER_MAX_SELF_END = 5
```

### For Highly Stringent qPCR

```python
PRIMER_PRODUCT_SIZE_RANGE = [(80, 120)]
PRIMER_PAIR_MAX_DIFF_TM = 1.0
PRIMER_MIN_TM = 59.0
PRIMER_MAX_TM = 61.0
PRIMER_MAX_SELF_END = 2
```

---

## Quick Reference: Decision Trees

### When to Increase Tm?

- Current primers giving non-specific products
- Multiple bands on gel
- Broad or multiple melt peaks
- High background in qPCR

**Action:** Increase annealing temp by 2-5°C or redesign

### When to Decrease Tm?

- No amplification with current primers
- Very weak signal
- High Cq values (> 35) in qPCR

**Action:** Decrease annealing temp by 2-5°C or redesign

### When to Redesign Primers?

- ΔTm > 2°C (or >1°C for qPCR)
- Primer dimers ΔG < -5 kcal/mol
- Hairpins ΔG < -2 kcal/mol
- Multiple off-target hits in BLAST
- qPCR efficiency < 90% or > 110%
- Multiple products (melt curve or gel)
- Amplicon > 150 bp for qPCR

---

**Last Updated:** 2026-01-28
