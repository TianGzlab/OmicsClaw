# Drug-associated expression and optional models

The legacy simple_correlation name means an unweighted mean of X over available
genes and cells within a group. The column is mean_target_expression, rounded
to four decimals for CLI compatibility. It is not correlation, IC50, AUC or
predicted sensitivity. Built-in sets mix targets and response/resistance genes
without direction weights, so a larger mean cannot establish therapeutic benefit.

The API supports explicit gene sets, reports overlap counts, and leaves AnnData
unchanged. CLI drug_score_* obs columns and drug_sensitivity_umap.png retain
their historical names but show these same descriptive values.

CaDRReS requires explicitly supplied trusted local pretrained models,
omicverse's adapter and a CaDRReS-Sc checkout. The old release URLs are unavailable;
no verified replacement or automatic download is provided. The model directory
is read-only to this API; intermediate predictions use a temporary directory.
Score direction and units depend on the model. Model-backed execution has not
been validated in this migration because those models/backend are absent.

The CLI's cadrres demo uses synthetic values solely to exercise reporting.
The public cadrres API never fabricates output when models are missing.
