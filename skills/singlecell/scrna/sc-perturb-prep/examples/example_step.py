# %% [markdown]
# Attach supplied guide calls to raw counts. WNT3 is a target, not an NT control.
# Calls sc-perturb-prep: standardize_mapping, collapse_assignments, attach_assignments,
# assignment_summary, perturbation_counts, perturbation_counts_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

prep = load_skill('sc-perturb-prep')
adata = load_demo('perturbseq_synthetic')
mapping = adata.uns['guide_mapping'].copy()

# %%
mapping = prep.standardize_mapping(mapping)
assigned, dropped = prep.collapse_assignments(mapping)
result = prep.attach_assignments(adata, assigned)
write_output(result, 'intermediate/processed.h5ad')
write_output(prep.assignment_summary(result), 'tables/assignment_status_counts.csv')
write_output(prep.perturbation_counts(result), 'tables/perturbation_counts.csv')
write_output(prep.perturbation_counts_figure(result), 'figures/perturbation_counts.png')

# %%
assert dropped.empty
assert result.n_obs == adata.n_obs
assert set(result.obs['perturbation']) == {'NT', 'KO_A', 'WNT3'}
assert (result.obs['perturbation'] == 'WNT3').sum() == 60
assert (result.obs['perturbation'] == 'NT').sum() == 60
controls = adata.obs['perturbation'].astype(str) == 'NT'
for target, genes in adata.uns['synthetic_downregulated_gene_sets'].items():
    cells = adata.obs['perturbation'].astype(str) == target
    assert adata[cells, genes].X.mean() < .2 * adata[controls, genes].X.mean()
