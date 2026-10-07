# Survival methods

Each gene is tested separately. Samples are split at the median or at a
cutoff maximizing the log-rank statistic. The optimal-cutoff scan does not
adjust its p-value for searching thresholds or testing several genes.

Both backends compute Kaplan-Meier curves and a two-group log-rank test.
R `survival` fits a univariate Cox model for the high-expression indicator,
including its hazard ratio confidence interval. The Python backend returns
a descriptive events/person-time ratio, not a Cox estimate.
`run_info()["hazard_estimator"]` names the estimator used.

A median survival is missing when its KM curve never reaches 0.5. The
Python risk set includes patients still at risk immediately before each
event; subjects censored at an earlier event time leave later risk sets.

There is no multivariate Cox model, gene-signature model or C-index in this
skill. The plots do not draw confidence bands. Clinical inputs remain local;
outputs are research summaries, not clinical prognoses.
