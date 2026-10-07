# Methodology

All wrappers require log-normalized expression and annotated populations.
They score ligand-receptor relationships without filtering by physical
distance. Spatial figures must not be described as evidence of contact.

| Method | Matrix | Species | Statistical interpretation |
|---|---|---|---|
| LIANA | raw when present, otherwise X | human, mouse | Consensus magnitude rank is converted to score = 1 - rank; pvalue is cellphone_pvals only. |
| CellPhoneDB | X | human | Mean-expression statistic and permutation p value. |
| FastCCC | X | human | Scores and p values from its statistical_analysis_method. |
| CellChat | X | human, mouse | computeCommunProb probability and pval, filtered by minimum group size. |

Missing p values remain NaN, never inferred from ranks. Significance counts
use measured p values below 0.05. Summed scores and sender/receiver roles
are descriptive; their scales are not comparable across methods.

LIANA uses bundled consensus resources (mouseconsensus for mouse).
CellPhoneDB and FastCCC require a local CellPhoneDB database; discovery checks
the configured environment and cache locations. Missing packages or databases
raise errors rather than fabricating interactions.

CellChat receives MatrixMarket expression plus feature names, barcodes and
metadata in a temporary directory. Its R script maps population labels to
safe internal names, restores them in outputs, and returns CSV tables.
Temporary inputs and the R object are removed after return. Required R
packages are Matrix and CellChat.

Seeds default to LIANA 1337, CellPhoneDB 0 and CellChat 1. The public
random_state keyword overrides these. FastCCC exposes no seed control.
Use more permutations for analysis than the example's 10, which only tests
execution and replay. The example's PBMC expression is real; its coordinates
are synthetic and cannot support spatial biological conclusions.
