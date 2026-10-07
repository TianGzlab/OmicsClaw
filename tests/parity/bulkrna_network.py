"""Recorded bulk identifier and PPI CLI comparisons."""


def register(Case, Skill):
    return {f'bulkrna-{name}': Skill(f'skills/bulkrna/bulkrna-{name}/bulkrna_{name.replace("-", "_")}.py',
            'tests.parity.bulkrna_network:api_' + name.replace('-', '_'),
            {'default': Case(('--demo',), environment={'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})})
            for name in ('geneid-mapping', 'ppi-network')}


def api_geneid_mapping(case):
    import pandas as pd
    from skills._sdk.notebook import load_skill
    from skills.bulkrna._lib.geneid import _generate_demo_data
    library = load_skill('bulkrna-geneid-mapping')
    result = library.map_ids(_generate_demo_data())
    mapping = library.mapping_table(result)
    return {'tables': {'mapped_counts.csv': result.reset_index().rename(columns={'index': 'Unnamed: 0'}),
                       'mapping_table.csv': mapping,
                       'unmapped_genes.csv': pd.DataFrame({'unmapped_gene': mapping.loc[~mapping.was_mapped, 'original_id'].tolist()})},
            'summary': library.run_info(result)['summary']}


def api_ppi_network(case):
    from pathlib import Path
    import pandas as pd
    from skills._sdk.notebook import load_skill
    from skills.bulkrna._lib.ppi import _generate_demo_de
    reference = Path(__file__).resolve().parents[2] / 'skills/bulkrna/bulkrna-ppi-network/data/demo_string_edges.csv'
    edges = pd.read_csv(reference)
    library = load_skill('bulkrna-ppi-network')
    result = library.analyze(edges, genes=_generate_demo_de().gene.tolist())
    return {'tables': {'interaction_edges.csv': edges, 'node_centrality.csv': result, 'hub_genes.csv': result.head(20)},
            'summary': library.run_info(result)}
