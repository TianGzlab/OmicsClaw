"""Fixed inputs and public-function comparisons for spatial expression analyses."""
from pathlib import Path


def input_data(path: Path) -> None:
    import scanpy as sc
    from scripts.generate_demo_data import generate_demo_visium

    adata = generate_demo_visium()
    adata.layers['counts'] = adata.X.copy()
    sc.pp.normalize_total(adata, target_sum=10000)
    sc.pp.log1p(adata)
    adata.obs['leiden'] = adata.obs['domain_ground_truth'].astype(str)
    sc.pp.pca(adata, n_comps=15, random_state=0)
    sc.pp.neighbors(adata, random_state=0)
    sc.tl.umap(adata, random_state=0)
    adata.write_h5ad(path)


def register(Case, Skill):
    environment = {key: '1' for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS')}
    environment['PYTHONHASHSEED'] = '0'
    return {
        'spatial-de': Skill('skills/spatial/spatial-de/spatial_de.py', 'tests.parity.spatial_s2:api_de', {
            name: Case(args, input=input_data, environment=environment)
            for name, args in {'default': (), 't-test': ('--method', 't-test')}.items()
        }),
        'spatial-enrichment': Skill('skills/spatial/spatial-enrichment/spatial_enrichment.py', 'tests.parity.spatial_s2:api_enrichment', {
            name: Case(args, input=input_data, environment=environment, exclude={
                f'summary.json:{key}': 'Record the requested and executed fallback method explicitly.'
                for key in ('requested_method', 'executed_method', 'fallback_reason')
            } if name != 'default' else {})
            for name, args in {'default': (), 'gsea': ('--method', 'gsea'), 'ssgsea': ('--method', 'ssgsea')}.items()
        }),
        'spatial-genes': Skill('skills/spatial/spatial-genes/spatial_genes.py', 'tests.parity.spatial_s2:api_genes', {
            name: Case(args, input=input_data, environment=environment)
            for name, args in {'default': (), 'flashs': ('--method', 'flashs')}.items()
        }),
    }


def api_de(case, *, input_path):
    import scanpy as sc
    from skills._sdk.notebook import load_skill
    data = sc.read_h5ad(input_path)
    library = load_skill('spatial-de')
    library.differential_expression(data, method='t-test' if case == 't-test' else 'wilcoxon')
    return {'adata': data, 'tables': {'de_full.csv': library.results(data)}}


def api_enrichment(case, *, input_path):
    import scanpy as sc
    from skills._sdk.notebook import load_skill
    data = sc.read_h5ad(input_path)
    library = load_skill('spatial-enrichment')
    library.enrich(data, method='enrichr' if case == 'default' else case)
    info = library.run_info(data)
    # The CLI owns sorting for presentation; ranked input markers retain their order.
    tables = {'ranked_markers.csv': info['marker_df']} if len(info['marker_df'].columns) else {}
    return {'adata': data, 'tables': tables,
            'summary': {key: info[key] for key in ('method', 'n_terms_tested', 'n_significant')}}


def api_genes(case, *, input_path):
    import scanpy as sc
    from skills._sdk.notebook import load_skill
    data = sc.read_h5ad(input_path)
    library = load_skill('spatial-genes')
    library.spatial_genes(data, method='flashs' if case == 'flashs' else 'morans')
    info = library.run_info(data)
    table = library.results(data)
    columns = ['gene', info['score_column'], info['significance_column']]
    columns += [column for column in ('pval', 'pval_norm', 'qval', 'var_norm', 'l', 'pval_z_sim')
                if column in table and column not in columns]
    columns += [column for column in table if column not in columns]
    return {'adata': data, 'tables': {'svg_results.csv': table[columns]}}
