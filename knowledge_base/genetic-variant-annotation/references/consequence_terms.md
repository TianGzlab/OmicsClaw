# Variant Consequence Terms

This document describes the Sequence Ontology consequence terms used by VEP and SNPEff to classify variant effects.

---

## Impact Categories

Variants are classified into four impact levels based on their predicted effect:

| Impact | Description | Expected Frequency |
|--------|-------------|-------------------|
| **HIGH** | Variant likely to disrupt protein function | Rare (0.1-1% of variants) |
| **MODERATE** | Non-disruptive variant that might affect protein function | 1-5% of variants |
| **LOW** | Unlikely to affect protein function significantly | 5-10% of variants |
| **MODIFIER** | Non-coding or intronic variants | Majority of variants |

---

## HIGH Impact Consequences

These variants are predicted to have severe effects on protein function:

### transcript_ablation (SO:0001893)
**Definition:** Deletion removes entire transcript

**Impact:** Causes complete loss of gene function

**Example:** Large deletion encompassing entire gene

### splice_acceptor_variant (SO:0001574)
**Definition:** Variant falls in the 2bp region at 3' end of intron

**Impact:** Likely disrupts normal splicing, may cause exon skipping or intron retention

**Typical positions:** Last 1-2bp of intron (AG dinucleotide)

**Example:** chr17:41234567:AG>AA in BRCA1

### splice_donor_variant (SO:0001575)
**Definition:** Variant falls in the 2bp region at 5' end of intron

**Impact:** Disrupts splice donor site, likely causes aberrant splicing

**Typical positions:** First 2bp of intron (GT dinucleotide)

**Example:** chr17:41234500:GT>GC in BRCA1

### stop_gained (SO:0001587)
**Definition:** Nonsense mutation that introduces premature stop codon

**Impact:** Truncated protein, often subject to nonsense-mediated decay (NMD)

**Example:** c.1234C>T (p.Gln412Ter) - Creates TAG stop codon

**Note:** Variants in last exon may escape NMD

### frameshift_variant (SO:0001589)
**Definition:** Insertion or deletion causes frameshift in coding sequence

**Impact:** Changes all downstream amino acids, usually introduces stop codon

**Example:**
- c.1234delA (p.Lys412fs) - Deletion not multiple of 3
- c.1234_1235insGG (p.Lys412fs) - Insertion not multiple of 3

### stop_lost (SO:0001578)
**Definition:** Variant removes stop codon, extends translation

**Impact:** Extended protein with additional amino acids until next stop

**Example:** c.*1A>T - Converts TAA to TTA (Leu)

### start_lost (SO:0002012)
**Definition:** Variant removes start codon (ATG)

**Impact:** Loss of normal translation initiation, may use downstream ATG

**Example:** c.1A>G - Converts ATG to GTG

### transcript_amplification (SO:0001889)
**Definition:** Copy number increase of transcript region

**Impact:** Gene dosage increase, may cause disease through overexpression

**Example:** MECP2 duplication in males causes severe neurodevelopmental disorder

---

## MODERATE Impact Consequences

These variants change protein sequence but don't necessarily disrupt protein function:

### inframe_insertion (SO:0001821)
**Definition:** Insertion maintains reading frame (multiple of 3bp)

**Impact:** Adds amino acids to protein sequence

**Example:** c.1234_1235insGGC (p.Lys412_Glu413insGly) - Adds 1 amino acid

**Pathogenicity:** Variable; depends on location and amino acids added

### inframe_deletion (SO:0001822)
**Definition:** Deletion maintains reading frame (multiple of 3bp)

**Impact:** Removes amino acids from protein sequence

**Example:** c.1234_1236del (p.Lys412del) - Removes 1 amino acid

**Pathogenicity:** Variable; critical for structural regions or functional domains

### missense_variant (SO:0001583)
**Definition:** Substitution changes amino acid

**Impact:** Alters protein sequence, effect depends on amino acid properties

**Example:** c.1234A>T (p.Lys412Met)

**Classification:**
- **Conservative:** Similar amino acids (e.g., Leu→Ile)
- **Non-conservative:** Different properties (e.g., Lys→Met, charged→nonpolar)

**Pathogenicity assessment:** Use SIFT, PolyPhen, CADD, REVEL

### protein_altering_variant (SO:0001818)
**Definition:** Variant alters protein but exact consequence unclear

**Impact:** Changes protein sequence, but mechanism uncertain

**Context:** Complex variants, stop codon readthrough

---

## LOW Impact Consequences

These variants affect transcripts but have minimal protein impact:

### splice_region_variant (SO:0001630)
**Definition:** Variant in 1-3bp at exon edge or 3-8bp into intron

**Impact:** May affect splicing efficiency, but less severe than splice site variants

**Regions:**
- Last 3bp of exon
- First 8bp of intron (after GT)
- Last 8bp of intron (before AG)

**Note:** Often co-occurs with other consequences (e.g., missense_variant&splice_region_variant)

### incomplete_terminal_codon_variant (SO:0001626)
**Definition:** Change within final codon when sequence length not multiple of 3

**Impact:** Affects last incomplete codon

**Context:** Sequencing or annotation artifacts

### start_retained_variant (SO:0002019)
**Definition:** Synonymous change at start codon

**Impact:** Maintains ATG but may affect translation efficiency

**Example:** c.3G>A - ATG to ATA (still codes for Met, but rare codon)

### stop_retained_variant (SO:0001567)
**Definition:** Synonymous change at stop codon

**Impact:** Stop codon maintained (e.g., TAA→TAG)

**Example:** c.*1T>G

### synonymous_variant (SO:0001819)
**Definition:** Substitution doesn't change amino acid

**Impact:** Usually benign, but may affect:
- mRNA stability
- Splicing (if in splice region)
- Translation efficiency
- microRNA binding

**Example:** c.1234C>T (p.Lys412=) - Both code for Lys

---

## MODIFIER Impact Consequences

These variants are in non-coding regions or far from genes:

### intron_variant (SO:0001627)
**Definition:** Variant in intron, not near splice sites

**Impact:** Usually benign; may affect:
- Branch point sequence
- Splicing enhancers/silencers
- Non-coding RNA

### intergenic_variant (SO:0001628)
**Definition:** Variant outside of annotated genes

**Impact:** Usually benign; may affect:
- Regulatory elements
- Long non-coding RNAs
- Unannotated genes

### upstream_gene_variant (SO:0001631)
**Definition:** Variant within 5kb upstream of transcription start site

**Impact:** May affect promoter or regulatory elements

**Note:** SNPEff default uses 5kb; VEP uses 5kb

### downstream_gene_variant (SO:0001632)
**Definition:** Variant within 5kb downstream of transcription end

**Impact:** May affect 3' regulatory elements or polyadenylation

### 5_prime_UTR_variant (SO:0001623)
**Definition:** Variant in 5' untranslated region

**Impact:** May affect:
- mRNA stability
- Translation efficiency
- Upstream ORFs (uORFs)

### 3_prime_UTR_variant (SO:0001624)
**Definition:** Variant in 3' untranslated region

**Impact:** May affect:
- mRNA stability
- Polyadenylation
- microRNA binding sites

### non_coding_transcript_exon_variant (SO:0001792)
**Definition:** Variant in exon of non-coding RNA

**Impact:** May affect:
- lncRNA function
- miRNA biogenesis
- Regulatory RNA function

### regulatory_region_variant (SO:0001566)
**Definition:** Variant in annotated regulatory region

**Impact:** May affect transcription factor binding or enhancer activity

**Examples:** Promoters, enhancers, silencers, insulators

### TF_binding_site_variant (SO:0001782)
**Definition:** Variant in transcription factor binding motif

**Impact:** May alter transcription factor binding affinity

---

## Special Cases

### Combined Consequences

Variants can have multiple consequences, separated by "&":

**Example:** `missense_variant&splice_region_variant`
- Changes amino acid AND is near splice site
- Consider both effects for pathogenicity assessment

**Priority:** Most severe consequence is reported first

### Transcript-Specific Consequences

Same variant may have different consequences in different transcripts:

**Example:** Variant may be:
- Missense in canonical transcript
- Synonymous in alternative transcript
- Intronic in another isoform

**Best practice:** Focus on canonical or MANE Select transcripts for clinical reporting

---

## Filtering Recommendations

### Clinical Diagnostics

**Include:**
- HIGH impact: All
- MODERATE impact: missense, inframe indels
- LOW impact: splice_region (if with other consequences)

**Exclude:**
- Most MODIFIER impact consequences
- Synonymous (unless in critical splice regions)

### Research Studies

**More permissive filtering:**
- Include all coding variants
- Consider regulatory variants for expression QTL studies
- Include upstream/downstream for promoter analysis

---

## Pathogenicity Prediction

### High Confidence Pathogenic

Variants likely to be pathogenic:
- stop_gained (nonsense)
- frameshift_variant
- splice_acceptor/donor_variant
- start_lost

**Exception:** Last exon stop_gained may escape NMD, consider carefully

### Moderate Confidence

Require additional evidence:
- missense_variant → Use SIFT, PolyPhen, CADD, REVEL
- inframe_insertion/deletion → Consider location and amino acids
- splice_region_variant → Use SpliceAI or MaxEntScan

### Low Confidence

Usually benign:
- synonymous_variant
- intron_variant
- intergenic_variant

**Exception:** May be pathogenic if:
- Creates cryptic splice site
- Disrupts regulatory element
- In highly conserved region

---

## References

- Sequence Ontology: http://www.sequenceontology.org/
- MacArthur DG, et al. (2014) A systematic survey of loss-of-function variants in human protein-coding genes. Science 335:823-828
- McLaren W, et al. (2016) The Ensembl Variant Effect Predictor. Genome Biology 17:122
