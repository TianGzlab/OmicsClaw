# LASSO Parameter Reference Guide

## Key Parameters

### Alpha (Mixing Parameter)
- `alpha = 1.0` — **Pure LASSO** (L1 penalty). Produces sparsest panels. Use when you want the fewest possible features (clinical assay development).
- `alpha = 0.5` — **Elastic net** (mixed L1+L2). Retains correlated features. Use when features are highly correlated (e.g., co-expressed genes in the same pathway).
- `alpha = 0.0` — **Ridge regression** (L2 only). No feature selection. Not recommended for biomarker panels.

**Recommendation:** Start with `alpha = 1.0` (default). If no features pass stability selection, try `alpha = 0.5`.

### Lambda (Regularization Strength)
Selected automatically by `cv.glmnet` via inner 10-fold CV.
- `lambda.min` — Lambda that minimizes CV error. Default choice.
- `lambda.1se` — Largest lambda within 1 SE of minimum. More conservative (fewer features).

**Recommendation:** Use `lambda.min` (default in `run_lasso_panel`).

### Stability Threshold
- `0.8` (default) — Feature must be selected in ≥80% of CV iterations. Standard choice.
- `0.9` — Stringent. Very robust features only.
- `0.6` — Relaxed. Use if few features pass 0.8 threshold.

### Number of Repeats
- `50` (default) — 50 random 70/30 train/test splits. Provides stable frequency estimates.
- `100` — More stable, but 2x slower. Use for final publication results.
- `20` — Fast exploration. Adequate for initial screen.

## Interpreting Results

### Selection Frequency
The fraction of CV iterations where a feature had a non-zero LASSO coefficient.
- ≥0.8: **Highly stable** — include in panel
- 0.5-0.8: **Moderately stable** — consider including
- <0.5: **Unstable** — likely spurious or redundant

### LASSO Coefficients
- **Positive**: Higher feature value → higher probability of outcome = 1
- **Negative**: Higher feature value → lower probability of outcome = 1
- **Magnitude**: Relative importance (larger = more influential in prediction)
- **CI crossing zero**: Feature's direction is uncertain (less reliable)

### AUC Interpretation
| AUC Range | Clinical Interpretation |
|-----------|----------------------|
| 0.9-1.0 | Excellent discrimination |
| 0.8-0.9 | Good — clinically useful |
| 0.7-0.8 | Moderate — useful with other factors |
| 0.6-0.7 | Weak — limited added value |
| 0.5-0.6 | Near random — not useful |

## Clinical Interpretation Quick Reference

- **AUC > 0.8**: Strong discriminative ability (clinically useful)
- **AUC 0.7-0.8**: Moderate — useful with other clinical factors
- **AUC 0.6-0.7**: Weak but above chance — typical for baseline transcriptomic prediction of treatment response
- **Stability >= 80%**: Feature is robustly selected (high confidence in panel)
- **Positive coefficient**: Higher expression → higher probability of positive outcome
- **Negative coefficient**: Higher expression → lower probability of positive outcome
- **Calibration**: Points near the diagonal indicate a well-calibrated model

## Advanced: Nested CV vs Simple CV

**Why nested CV is essential for biomarker panels:**
- Simple CV (single `cv.glmnet`) optimizes lambda AND evaluates AUC on the same data split → **optimistic bias**
- Nested CV separates lambda optimization (inner) from AUC estimation (outer) → **unbiased AUC**
- The Ali et al. (Nat Med 2025) approach: 50 repetitions of 70/30 splits, each with inner 10-fold cv.glmnet

## Advanced: WGCNA → LASSO Cascade

Following Shen et al. (Cell 2024), you can pre-filter features using WGCNA co-expression networks:
1. Run `coexpression-network` skill to identify modules and hub genes
2. Use hub genes (top connectivity per module) as LASSO input features
3. This reduces thousands of genes to hundreds of biologically coherent candidates
4. LASSO then selects the minimal panel from these candidates

```r
# After running coexpression-network skill:
hub_genes <- readRDS("coexpression_results/hub_genes.rds")
# Use as feature filter in prepare_features.R
expr_filtered <- expression[rownames(expression) %in% hub_genes, ]
features <- prepare_feature_matrix(expr_filtered, metadata, outcome_col)
```
