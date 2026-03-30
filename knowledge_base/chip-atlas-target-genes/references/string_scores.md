# STRING Interaction Scores

## Overview

The `STRING` column in ChIP-Atlas Target Genes data contains protein-gene interaction scores from the [STRING database](https://string-db.org/). These scores provide orthogonal evidence that a TF regulates a target gene, complementing the ChIP-seq binding evidence.

## Score Extraction

STRING scores are included when all of these conditions are met:
- `item_id_a` matches the query antigen (the TF/protein)
- `item_id_b` matches the target gene
- Interaction mode = `"expression"` (regulatory relationship)
- `a_is_acting` = `1` (the antigen is the regulator)

## Score Interpretation

| Score | Interpretation |
|-------|----------------|
| 0 | No STRING interaction evidence |
| 1-399 | Low confidence interaction |
| 400-699 | Medium confidence interaction |
| 700-899 | High confidence interaction |
| 900-1000 | Highest confidence interaction |

## Combining with Binding Scores

The most confident target gene predictions have both:
1. **High average binding score** — Direct ChIP-seq evidence of TF binding near gene TSS
2. **High STRING score** — Independent evidence of regulatory relationship

| Binding Score | STRING Score | Confidence |
|--------------|-------------|------------|
| High (>200) | High (>400) | Very high — binding + regulatory evidence |
| High (>200) | 0 | High — binding evidence only (novel target?) |
| Low (<50) | High (>400) | Moderate — known interaction but weak/indirect binding |
| Low (<50) | 0 | Low — minimal evidence |

## Limitations

- STRING covers well-studied interactions; novel or tissue-specific regulatory relationships may not be represented
- STRING "expression" mode captures co-expression and regulatory evidence, not exclusively direct regulation
- **Score of 0 does NOT mean "not a target"** — it means STRING lacks evidence for this specific pair. Even well-characterized, canonical targets can have STRING score 0. For example, BBC3 (PUMA) is one of the best-characterized TP53 apoptosis targets, yet it has STRING score 0 in ChIP-Atlas data. This reflects gaps in STRING's coverage, not biological reality.
- When reporting results, always note that absence of STRING evidence is not evidence of absence. Genes with high binding scores but STRING score 0 may still be bona fide targets — they simply lack this particular line of orthogonal evidence.
