# %% [markdown]
# Real CPU Mixscape on a synthetic screen with known strong expression shifts.
# The extended CI environment supplies pertpy; an all-NP result fails this example.
# Calls sc-perturb: mixscape, class_counts, global_class_counts, global_class_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

perturb = load_skill('sc-perturb')
adata = load_demo('perturbseq_synthetic')
mapping = adata.uns['guide_mapping']
assert mapping['target_gene'].eq('WNT3').sum() == 60
controls = adata.obs['perturbation'].astype(str) == 'NT'
for target, genes in adata.uns['synthetic_downregulated_gene_sets'].items():
    cells = adata.obs['perturbation'].astype(str) == target
    assert adata[cells, genes].X.mean() < .2 * adata[controls, genes].X.mean()
    assert adata[cells, [target]].X.mean() < .2 * adata[controls, [target]].X.mean()

# %%
result = perturb.mixscape(adata, split_by='replicate', random_state=0)
write_output(result, 'intermediate/processed.h5ad')
write_output(perturb.class_counts(result), 'tables/mixscape_class_counts.csv')
write_output(perturb.global_class_counts(result), 'tables/mixscape_global_class_counts.csv')
write_output(perturb.global_class_figure(result), 'figures/mixscape_global_classes.png')

# %%
controls = result.obs['perturbation'].astype(str) == 'NT'
assert result.obs.loc[controls, 'mixscape_class_global'].astype(str).eq('NT').all()
for target in ['KO_A', 'WNT3']:
    cells = result.obs['perturbation'].astype(str) == target
    assert cells.sum() == 60
    assert result.obs.loc[cells, 'mixscape_class_global'].astype(str).eq('KO').sum() >= 45
assert result.obs['mixscape_class_p_ko'].between(0, 1).all()
