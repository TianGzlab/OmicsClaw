# MACS2 Binding Scores

## Score Formula

Binding scores in ChIP-Atlas Target Genes data are computed as:

```
Score = −10 × log10(MACS2 Q-value)
```

This transforms MACS2 Q-values (Benjamini-Hochberg adjusted p-values) into positive scores where higher values indicate stronger binding evidence.

## Score Interpretation

| Score | MACS2 Q-value | Interpretation |
|-------|--------------|----------------|
| 0 | No peak | No binding detected in this experiment |
| 50 | 1e-5 | Default MACS2 threshold (weak but detectable) |
| 100 | 1e-10 | Moderate binding evidence |
| 200 | 1e-20 | Strong binding evidence |
| 500 | 1e-50 | Very strong binding evidence |
| 1000 | 1e-100 | Extremely strong binding evidence |

## Color Mapping (ChIP-Atlas Web Interface)

The web interface uses a three-color gradient:
- **0** → Blue (no binding)
- **500** → Green (strong binding)
- **1000** → Red (very strong binding)

## Multiple Peaks

When multiple peaks from a single experiment overlap one gene's TSS window, only the **highest** score is retained. This ensures each experiment contributes a single score per gene.

## Average Score

The `{Protein}|Average` column contains the **arithmetic mean** of MACS2 scores across all experiments for that antigen. This provides a consensus binding strength:

- **High average (>500):** Consistently strong binding across many experiments — high-confidence direct target
- **Moderate average (100-500):** Binding detected in multiple experiments — likely target
- **Low average (10-100):** Binding in few experiments or weak peaks — possible target, may be cell-type-specific
- **Very low average (<10):** Marginal evidence — binding in very few experiments

### Averaging Includes Zeros

**Important:** The average is computed across ALL experiments, including those with no binding (score 0). This means genes bound in fewer experiments get diluted averages even if they have very strong binding in a few cell types. For example, a gene with score 1000 in 5 experiments but 0 in 395 experiments would have an average of ~12.5.

### Q-value Interpretation of Averaged Scores

**Important:** The score-to-Q-value mapping in the table above (e.g., 500 → Q = 1e-50) applies to **individual experiment** scores. The averaged scores reported in gene rankings do NOT have a direct per-experiment Q-value interpretation because the average includes zeros from experiments with no binding. An average score of 500 means the *consensus across all experiments* reaches that level — it does NOT mean every experiment shows Q ≤ 1e-50. Use `max_score` to see the strongest individual experiment evidence, and `binding_rate` to see how consistently the gene is bound.

**Complementary metrics to consider:**
- **`max_score`** — Highest score in any single experiment. Captures strong cell-type-specific binding that the average may obscure.
- **`binding_rate`** — Fraction of experiments with any binding. High binding rate + moderate average suggests consistent but moderate binding; low binding rate + moderate average suggests strong but cell-type-specific binding.
- **Median non-zero score** — Not pre-computed, but can be derived from the per-experiment data to avoid zero dilution.

## Peak Calling Parameters

ChIP-Atlas uses `MACS2 callpeak` with:
- Q-value threshold: 1e-5 (default)
- Genome size: `-g hs` (human), `-g mm` (mouse), etc.
- Only peaks passing this threshold appear in target gene data
