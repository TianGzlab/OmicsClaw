# Methodology

`map_trajectory` takes sample/cell rows and gene columns. NNLS estimates cell-type
fractions. Joint reference-plus-bulk log1p expression is standardized, projected
with PCA, and mapped with 15 nearest reference cells. Use comparable expression
scales; at least 50 shared genes are required. PCA receives `random_state=42`.
The CLI's `--n-epochs` remains unused; no VAE or GNN is fitted.

- `read_reference` requires cell_type and pseudotime annotations; it does not fabricate Unknown labels or zero pseudotime.
- `map_trajectory` aligns both annotation Series by reference cell index.
- `pseudotime_std` is neighbor spread, not a calibrated confidence interval.
- `run_info` retains fractions and PCA coordinates in DataFrame attrs; CSV serialization does not preserve them.
