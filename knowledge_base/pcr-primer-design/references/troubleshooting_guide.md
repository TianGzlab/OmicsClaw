# PCR Primer Design Troubleshooting Guide

**← Back to [SKILL.md](../SKILL.md) | See also:** [Parameter Ranges](parameter_ranges.md) | [Best Practices](primer_design_best_practices.md) | [Code Examples](code_examples.md)

Common problems and solutions for PCR and qPCR primer design and optimization. Referenced from SKILL.md Common Issues table for detailed troubleshooting.

---

## Table of Contents

1. [No Amplification](#no-amplification)
2. [Weak or Variable Amplification](#weak-or-variable-amplification)
3. [Non-Specific Amplification](#non-specific-amplification)
4. [Primer Dimers](#primer-dimers)
5. [qPCR-Specific Issues](#qpcr-specific-issues)
6. [Template-Specific Issues](#template-specific-issues)

---

## No Amplification

### Symptom
- No band on gel
- No amplification curve in qPCR
- Cq values > 35 or undetected

### Possible Causes & Solutions

| Cause | Check | Solution |
|-------|-------|----------|
| **Poor primer design** | BLAST primers, check for mismatches | Redesign primers in different region |
| **Primer degradation** | Check primer stock age/storage | Order fresh primers |
| **Wrong primer concentration** | Verify stock and working dilutions | Remake dilutions, typically use 0.2-0.5 µM final |
| **Template quality** | Run template on gel, check 260/280 | Extract fresh template, check for inhibitors |
| **No template** | Verify template is present | Check concentration, use positive control |
| **Annealing temp too high** | Run gradient PCR | Lower by 2-5°C, try Tm-5°C as starting point |
| **Mg²⁺ too low** | Test 1.5, 2.0, 2.5, 3.0 mM | Increase Mg²⁺ to 2.5-3.0 mM |
| **PCR inhibitors** | Dilute template 1:10 | Dilute template, re-extract, use BSA |
| **Extension time too short** | Check amplicon size | Use 1 min per kb (high-fidelity: 30 sec per kb) |
| **Polymerase inactive** | Run positive control | Use fresh enzyme, check storage |

### Troubleshooting Steps

1. **Verify primers:**
   - Re-BLAST primers against target
   - Check for off-target binding
   - Verify no SNPs at primer sites

2. **Test with positive control:**
   - Use known working template
   - If control works: template issue
   - If control fails: reaction issue

3. **Run gradient PCR:**
   - Test Tm ± 5°C in 1-2°C increments
   - Find optimal annealing temperature

4. **Check template quality:**
   - Run on gel (gDNA should be high MW)
   - Check 260/280 ratio (1.8-2.0)
   - Try fresh extraction

5. **Optimize Mg²⁺:**
   - Try 1.5, 2.0, 2.5, 3.0 mM
   - Too low: no amplification
   - Too high: non-specific products

---

## Weak or Variable Amplification

### Symptom
- Faint band on gel
- High Cq values (> 30 for abundant targets)
- Inconsistent results between replicates

### Possible Causes & Solutions

| Cause | Check | Solution |
|-------|-------|----------|
| **Low template** | Quantify template accurately | Increase template input |
| **Poor primer efficiency** | Check primer Tm, GC%, structure | Redesign primers |
| **Primer concentration too low** | Verify dilutions | Increase to 0.3-0.5 µM |
| **Suboptimal annealing temp** | Run gradient PCR | Optimize temperature |
| **Secondary structures in template** | Predict structures at target site | Add DMSO (2-10%) or betaine (1-2 M) |
| **GC-rich or AT-rich target** | Check target GC content | See Template-Specific Issues section |
| **Pipetting errors** | Check technique, use replicate | Use electronic pipettes, increase volume |
| **Primer degradation** | Check storage conditions | Store at -20°C, avoid freeze-thaw |

### Troubleshooting Steps

1. **Optimize annealing temperature:**
   - Run gradient PCR
   - Select temperature giving strongest signal

2. **Increase template:**
   - Try 2× - 10× more template
   - But watch for inhibition at high amounts

3. **Check primer efficiency (qPCR):**
   - Run standard curve
   - Efficiency should be 90-110%
   - If outside range: redesign primers

4. **Add PCR enhancers:**
   - DMSO: 2-10% (GC-rich)
   - Betaine: 1-2 M (GC-rich)
   - BSA: 0.1-0.4 mg/mL (inhibitors)

---

## Non-Specific Amplification

### Symptom
- Multiple bands on gel
- Multiple peaks in melt curve
- Amplification in NTCs

### Possible Causes & Solutions

| Cause | Check | Solution |
|-------|-------|----------|
| **Annealing temp too low** | Compare to primer Tm | Increase by 2-5°C |
| **Primer concentration too high** | Check final concentration | Decrease to 0.2-0.3 µM |
| **Primer dimers** | Check dimer formation energy | Redesign primers (see Primer Dimers section) |
| **Too many cycles** | Check cycle number | Reduce to 25-35 for standard PCR |
| **Mg²⁺ too high** | Check Mg²⁺ concentration | Decrease to 1.5-2.0 mM |
| **Primers not specific** | Re-BLAST primers | Redesign in unique region |
| **Template contamination** | Check NTCs, clean workspace | Use filter tips, UV-treat workspace, aliquot reagents |
| **gDNA in RT-qPCR** | Check -RT control | Use primers spanning exon junction, DNase treat RNA |

### Troubleshooting Steps

1. **Increase stringency:**
   - Raise annealing temp by 2-5°C
   - Use hot-start polymerase
   - Decrease primer concentration

2. **Check primer specificity:**
   - BLAST both primers
   - Check for off-target sites with < 3 mismatches
   - Redesign if non-specific

3. **Use touchdown PCR:**
   ```
   Start at Tm + 5°C
   Decrease 0.5-1°C per cycle for 10 cycles
   Then continue at Tm - 5°C for remaining cycles
   ```

4. **Check for contamination:**
   - Run NTCs with every reaction
   - Use separate areas for setup and post-PCR
   - Use filter tips
   - UV-treat bench and pipettes

5. **For qPCR, check melt curve:**
   - Single sharp peak: specific
   - Multiple peaks: non-specific
   - Broad peak: primer dimers or mixed products

---

## Primer Dimers

### Symptom
- Small band on gel (< 100 bp)
- Early amplification in qPCR NTCs
- Low temperature peak in melt curve (< 80°C)

### Possible Causes & Solutions

| Cause | Check | Solution |
|-------|-------|----------|
| **Complementary 3' ends** | Check primer sequences | Redesign primers |
| **Low Tm primers** | Check primer Tm | Increase Tm to 58-62°C |
| **High primer concentration** | Check concentration | Decrease to 0.2-0.3 µM |
| **Too many cycles** | Check cycle number | Reduce cycles |
| **Low annealing temp** | Check temperature | Increase by 2-5°C |

### Analysis

**Check primer dimer formation energy:**
```python
from scripts.check_dimers import analyze_dimers

dimer_result = analyze_dimers(
    primer_list=[forward_primer, reverse_primer],
    temperature=60.0
)

# ΔG < -5 kcal/mol: problematic dimers
# ΔG > -5 kcal/mol: acceptable
```

### Solutions

1. **Redesign primers:**
   - Avoid complementarity at 3' ends
   - Check for self-complementarity
   - Increase Tm

2. **Optimize reaction conditions:**
   - Increase annealing temperature
   - Decrease primer concentration
   - Use hot-start polymerase

3. **For qPCR:**
   - Use higher annealing temp (62°C)
   - Reduce primer concentration to 0.2 µM
   - Check that NTC Cq > 35

---

## qPCR-Specific Issues

### Issue 1: Poor Efficiency (< 90% or > 110%)

**Symptom:** Standard curve slope outside -3.1 to -3.6

**Causes & Solutions:**

| Efficiency | Slope | Likely Cause | Solution |
|------------|-------|--------------|----------|
| < 90% | > -3.6 | Inhibitors, poor primers, secondary structures | Dilute template, redesign primers, add enhancers |
| 90-110% | -3.1 to -3.6 | Good | No action needed |
| > 110% | < -3.1 | Primer dimers, contamination, pipetting errors | Check for dimers, check NTCs, improve pipetting |

**Troubleshooting:**
1. Run fresh standard curve with clean reagents
2. Check for primer dimers (melt curve, gel)
3. Redesign primers if efficiency consistently poor
4. Try different template dilution series

### Issue 2: High Cq Variation (CV > 5%)

**Symptom:** Technical replicates differ by > 1 Cq

**Causes & Solutions:**

| Cause | Check | Solution |
|-------|-------|----------|
| **Pipetting errors** | Check technique | Use electronic pipettes, increase volume |
| **Template at limit of detection** | Check Cq values | Use more template or more replicates |
| **Bubbles in wells** | Visual inspection | Centrifuge plate, avoid bubbles when pipetting |
| **Evaporation** | Check seals | Use proper seals, avoid edge wells |
| **Thermal cycling variability** | Run controls across plate | Use same position for replicates |

**Troubleshooting:**
1. Use good pipetting technique
2. Ensure template is well-mixed before pipetting
3. Avoid bubbles (spin plate briefly)
4. Use technical triplicates for important samples
5. If Cq > 30, increase replicates to 4-6

### Issue 3: Amplification in NTC

**Symptom:** No-template control shows amplification (Cq < 35)

**Causes & Solutions:**

| Cause | Check | Solution |
|-------|-------|----------|
| **Contamination** | Clean workspace, pipettes | UV-treat workspace, use filter tips, separate reagent aliquots |
| **Primer dimers** | Check melt temperature | Should be < 80°C if dimers; redesign if needed |
| **Aerosol contamination** | Check setup procedure | Never open tubes near amplified products |
| **Reagent contamination** | Test reagents individually | Use fresh aliquots or new reagents |

**Prevention:**
- Use separate areas for pre- and post-PCR
- Use filter tips always
- Aliquot reagents (never pipette from stock bottles)
- UV-treat bench and pipettes regularly
- Include NTC in every run

### Issue 4: Multiple Peaks in Melt Curve

**Symptom:** Melt curve shows > 1 peak

**Interpretation:**

| Peak Pattern | Likely Cause | Solution |
|--------------|--------------|----------|
| Main peak + low temp peak (< 80°C) | Primer dimers | Optimize conditions or redesign |
| Two similar height peaks | Two products (off-target) | Redesign primers for specificity |
| Broad single peak | Mixed products or SNPs | Check product by gel/sequencing |

**Troubleshooting:**
1. Run products on gel to visualize size
2. Sequence products to identify amplicons
3. Redesign primers if non-specific
4. Increase annealing temp for specificity

---

## Template-Specific Issues

### GC-Rich Sequences (> 65% GC)

**Problems:**
- Strong secondary structures
- Poor denaturation
- Low amplification efficiency

**Solutions:**
1. **Add PCR enhancers:**
   - DMSO: 5-10%
   - Betaine: 1-2 M
   - 7-deaza-dGTP: Replace 20-100% of dGTP

2. **Optimize cycling:**
   - Increase denaturation temp to 98°C
   - Extend denaturation time (60 sec)
   - Slow down extension (2 min per kb)

3. **Use specialized polymerase:**
   - GC-rich optimized polymerases available
   - Higher processivity in GC-rich regions

4. **Primer design:**
   - Choose AT-rich primer binding sites if possible
   - Accept slightly lower primer Tm

### AT-Rich Sequences (< 35% GC)

**Problems:**
- Low primer Tm
- Weak primer binding
- Non-specific amplification

**Solutions:**
1. **Primer design:**
   - Increase primer length (22-25 nt)
   - Accept lower Tm (50-55°C)
   - Use multiple A/T primers if needed

2. **PCR conditions:**
   - Lower annealing temperature
   - Increase primer concentration slightly
   - Use hot-start polymerase

3. **Use touchdown PCR:**
   - Start stringent, decrease gradually
   - Helps specificity despite low Tm

### Repetitive Sequences

**Problems:**
- Primers bind to multiple sites
- Non-specific amplification
- Multiple products

**Solutions:**
1. **Design strategy:**
   - Use RepeatMasker to identify repeats
   - Design primers in unique flanking regions
   - Avoid Alu, LINE, SINE elements

2. **Increase specificity:**
   - Use nested PCR (two primer sets)
   - Increase primer length (24-27 nt)
   - Use higher annealing temperature

3. **Alternative approaches:**
   - Long-range PCR to span repeats
   - Design primers with anchors in unique sequence

### RNA Templates (RT-qPCR)

**Specific Issues:**

| Problem | Cause | Solution |
|---------|-------|----------|
| **gDNA contamination** | No DNase treatment | DNase treat RNA, use primers spanning exon junction |
| **Poor RT efficiency** | Low RNA quality, secondary structures | Check RIN > 7, use random primers + oligo(dT) |
| **Amplification in -RT** | gDNA present | Treat with DNase, check -RT controls (should be > target +5 Cq) |
| **Variable results** | RNA degradation | Minimize freeze-thaw, work quickly, store at -80°C |

---

## Diagnostic Flowchart

### For No Amplification:

```
No amplification
    ├─> Positive control works?
    │       ├─> No: Check reagents, enzyme, protocol
    │       └─> Yes: Template or primer issue
    │               ├─> BLAST primers → mismatches? Redesign
    │               ├─> Template quality → poor? Re-extract
    │               └─> Run gradient PCR → optimize Tm
    │
    └─> Check primers
            ├─> Dimers (ΔG < -5)? → Redesign
            ├─> Hairpins (ΔG < -2)? → Redesign
            └─> Tm too high/low? → Adjust or redesign
```

### For Non-Specific Products:

```
Multiple products
    ├─> Run gel → Multiple bands?
    │       └─> Yes: Size tells you:
    │               ├─> < 100 bp: Primer dimers
    │               ├─> Expected + others: Off-target
    │               └─> Smear: Degradation or over-amplification
    │
    ├─> BLAST primers → Off-targets?
    │       └─> Yes: Redesign primers
    │
    ├─> Increase stringency:
    │       ├─> Raise annealing temp +5°C
    │       ├─> Decrease primer concentration
    │       └─> Use hot-start polymerase
    │
    └─> If still problematic: Redesign primers
```

---

## Quick Reference: First Things to Try

### Problem: No amplification
1. Run gradient PCR (Tm ± 5°C)
2. Check template quality and concentration
3. Verify primer sequences (BLAST)

### Problem: Weak signal
1. Increase template 2-10×
2. Lower annealing temp by 3°C
3. Increase Mg²⁺ to 2.5-3.0 mM

### Problem: Non-specific products
1. Increase annealing temp by 3-5°C
2. Decrease primer concentration
3. Use hot-start polymerase

### Problem: Primer dimers
1. Increase annealing temp
2. Decrease primer concentration to 0.2 µM
3. Redesign primers

### Problem: Poor qPCR efficiency
1. Redesign primers (check for dimers, secondary structures)
2. Optimize primer concentration (try 0.2, 0.3, 0.5 µM)
3. Check for template inhibitors (dilute 1:10)

---

**Last Updated:** 2026-01-28


---
