# Methodology

maxquant is the default; fragpipe, diann and generic normalize their own column names. read_table detects CSV/TSV separation.

standardize filters MaxQuant Reverse, Potential contaminant and Only identified by site flags. Generic import does not infer those flags.
