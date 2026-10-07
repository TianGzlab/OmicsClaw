# Parameters

`map_trajectory` takes sample/cell rows and gene columns. NNLS estimates cell-type
fractions. Joint reference-plus-bulk log1p expression is standardized, projected
with PCA, and mapped with 15 nearest reference cells. Use comparable expression
scales; at least 50 shared genes are required. PCA receives `random_state=42`.
The CLI's `--n-epochs` remains unused; no VAE or GNN is fitted.

The generated API section in `../SKILL.md` lists arguments and defaults.
The CLI `--help` lists file and report options.
