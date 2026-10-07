# %% [markdown]
# A synthetic chain checks topology independently of network services.

# %%
import pandas as pd
from skills._sdk.notebook import load_skill, write_output

library = load_skill('bulkrna-ppi-network')
edges = pd.DataFrame({'gene_a': ['A', 'B'], 'gene_b': ['B', 'C'], 'score': [.9, .8]})
genes = ['A', 'B', 'C', 'D']
nodes = library.analyze(edges, genes=genes)
assert nodes.set_index('gene').loc['B', 'degree'] == 2
assert library.run_info(nodes)['n_isolated'] == 1
write_output(nodes, 'tables/node_centrality.csv')
write_output(edges, 'tables/interaction_edges.csv')
write_output(library.network_figure(edges, genes=genes), 'figures/network.png')
