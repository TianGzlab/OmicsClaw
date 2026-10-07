# Differential-expression methods

The CLI and notebook library use the same bulk count calculation. The default `deseq2` method calls the existing R DESeq2 bridge; it does not use PyDESeq2. Missing R packages raise an installation hint. A failed fit emits a warning and records a Welch fallback in `run_info` and `result.json.data.diagnostics`.

Control and treatment columns are selected by their prefixes. Total counts below `min_count=10` are filtered. The R script has its own additional count filter. Welch tests operate on raw counts and use the effect `log2(mean_treat + 1) - log2(mean_ctrl + 1)`, a delta-method standard error and Benjamini–Hochberg adjustment. A Welch result is not equivalent to a negative-binomial fit.

Use raw integer counts, not VST/rlog values. The legacy Welch implementation treats constant groups as p=1; its output should not be interpreted as evidence of equivalence. Independent biological replicates are required for inferential use. See the generated API section in `../SKILL.md` for argument defaults and validation.
