# %% [markdown]
# Synthetic marker sets test enrichment; these are not biological pathways.

# %%
import matplotlib.pyplot as plt
import scanpy as sc
from skills._sdk.notebook import load_demo, load_skill, write_output

library = load_skill('spatial-enrichment')
adata = load_demo('spatial_synthetic')
sc.pp.normalize_total(adata)
sc.pp.log1p(adata)
gene_sets = {f'domain_{i}_markers': [f'Gene_{j:03d}' for j in range(i * 30, (i + 1) * 30)]
             for i in range(3)}

# %%
library.enrich(adata, groupby='domain_ground_truth', gene_sets=gene_sets)
table = library.results(adata)
# GSEApy reports overlap members from a set; order them for stable CSV replay.
table['genes'] = table['genes'].map(lambda genes: ';'.join(sorted(str(genes).split(';'))))
hits = table[(table['group'] == 'domain_0') & (table['term'] == 'domain_0_markers')]
assert len(hits) == 1 and hits['pvalue_adj'].iloc[0] < 0.001
write_output(table, 'tables/enrichment_results.csv')
write_output(adata, 'intermediate/processed.h5ad')
figure = library.terms_figure(adata)
write_output(figure, 'figures/enrichment.png')
plt.close(figure)
