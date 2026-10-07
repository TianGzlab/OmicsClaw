# %% [markdown]
# Extract six NMF programs from the log-normalized PBMC68k snapshot.
# Reads pbmc68k_reduced.
# Calls sc-gene-programs: find_programs, top_program_genes, usage_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

programs = load_skill('sc-gene-programs')
adata = load_demo('pbmc68k_reduced').raw.to_adata()

# %%
result = programs.find_programs(adata, method='nmf')
top = programs.top_program_genes(result, n=10)
write_output(result, 'intermediate/programs.h5ad')
write_output(top, 'tables/top_program_genes.csv')
write_output(programs.usage_figure(result), 'figures/program_usage.png')

# %%
assert result.obsm['X_gene_programs'].shape == (adata.n_obs, 6)
assert (result.obsm['X_gene_programs'] >= 0).all()
assert top['program'].nunique() == 6
assert set(top.gene).issubset(adata.var_names)
