# Methodology

The CLI defaults are DSS and fdr_threshold=0.05. DSS/BS3/DSSO/DSBU use 30 angstrom; EDC uses 20 angstrom.

analyse_crosslinks requires protein_a and protein_b. Distance constraints apply only to finite observed distances after FDR filtering. Missing rows have a nullable constraint result and do not enter the satisfaction-rate denominator. run_info records checked and unchecked counts; with no observed distances, satisfaction counts and rate are null. Negative or infinite distances are rejected. FDR filtering requires an fdr column.
