# Decision Guide: When to Use What

## LASSO vs Elastic Net vs Ridge

| Situation | Recommendation | Alpha |
|-----------|---------------|-------|
| Biomarker panel for clinical assay | **Pure LASSO** | 1.0 |
| Features highly correlated (same pathway) | **Elastic net** | 0.5 |
| Many weak signals, no dominant features | **Elastic net** | 0.5 |
| Gene expression (some correlation) | **Start with LASSO**, try elastic net if <3 stable features | 1.0 → 0.5 |
| Proteomics (SOMAscan/Olink) | **LASSO** — typically lower correlation | 1.0 |
| Multi-omics features | **Elastic net** — captures cross-omics correlations | 0.5 |

## This Skill vs Other Skills

| Goal | Use This Skill? | Alternative |
|------|----------------|-------------|
| Select minimal biomarker panel | ✅ Yes | — |
| Predict binary outcome from omics | ✅ Yes | — |
| Unsupervised patient clustering | ❌ No | `bulk-omics-clustering` |
| Find differentially expressed genes | ❌ No | `bulk-rnaseq-counts-to-de-deseq2` |
| Multi-omics factor analysis | ❌ No | `multiomics-patient-stratification` |
| Pathway enrichment of results | After this skill | `functional-enrichment-from-degs` |
| Co-expression context | Before or after | `coexpression-network` |

## Pre-filtering Strategy

### When to Pre-filter Features
- **>10,000 features**: Pre-filter to top 5,000 by variance (done by `prepare_features.R`)
- **>20,000 features**: Consider DE pre-filtering (`filter_by_de()`) first
- **<5,000 features**: No pre-filtering needed

### Pre-filtering Methods (Best to Worst)
1. **DE-based** (`filter_by_de()`) — statistically principled, but introduces circularity if outcome used
2. **Variance-based** (default) — no circularity, captures informative features
3. **WGCNA hub genes** — biologically informed, reduces to pathway-representative features
4. **Random subset** — never recommended

## Troubleshooting Decision Tree

```
Problem: No stable features (all <80% frequency)
├── Try alpha = 0.5 (elastic net)
│   ├── Still no stable features?
│   │   ├── Lower stability threshold to 0.6
│   │   └── If still none: signal may be too weak for this sample size
│   └── Features found → proceed with elastic net panel
│
Problem: Too many stable features (>20)
├── Increase stability threshold to 0.9
├── Use top_n_features = 10 per iteration
└── Switch to alpha = 1.0 if using elastic net
│
Problem: Low AUC (<0.6)
├── Check class balance (need ≥30% minority)
├── Try DE pre-filtering (more informative features)
├── Increase n_repeats to 100 (more stable estimates)
└── Consider: effect size may be too small for this cohort size
```
