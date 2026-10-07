"""Seeded legacy CLI recordings for the eight protein-table skills."""
from pathlib import Path

SCRIPTS = {
    'data-import': 'proteomics_data_import.py', 'ms-qc': 'proteomics_ms_qc.py',
    'identification': 'proteomics_identification.py',
    'quantification': 'proteomics_quantification.py', 'de': 'proteomics_de.py',
    'ptm': 'proteomics_ptm.py', 'enrichment': 'prot_enrichment.py',
    'structural': 'struct_proteomics.py',
}


def register(Case, Skill):
    result = {}
    for short, script in SCRIPTS.items():
        cases = {'default': Case(('--demo',))}
        if short in ('quantification', 'de'):
            for method in (('ibaq', 'spectral_count') if short == 'quantification' else ('welch', 'mann_whitney')):
                cases[method] = Case(('--demo', '--method', method))
        if short == 'structural':
            cases['edc'] = Case(('--demo', '--crosslinker', 'EDC'))
        if short == 'ptm':
            cases['strict'] = Case(('--demo', '--loc-threshold', '0.95'))
        result[f'proteomics-{short}'] = Skill(
            f'skills/proteomics/proteomics-{short}/{script}',
            f'tests.parity.proteomics:api_{short.replace("-", "_")}', cases)
    return result


def api_quantification(case, *, input_path=None):
    from skills._sdk.notebook import load_skill
    lib = load_skill('proteomics-quantification')
    result = lib.quantify(lib.demo_data(), method='lfq' if case == 'default' else case)
    return {'tables': {'protein_abundance.csv':result}, 'summary':lib.run_info(result)['summary']}


def api_de(case, *, input_path=None):
    from skills._sdk.notebook import load_skill
    lib = load_skill('proteomics-de')
    method = 'ttest' if case == 'default' else case
    result = lib.differential_abundance(lib.demo_data(), method=method)
    sig = lib.significant(result)
    return {'tables':{'differential_abundance.csv':result, 'significant.csv':sig},
            'summary':{'method':method,'n_tested':len(result),'n_significant':len(sig),
                       'n_up':int((sig['log2fc'] > 0).sum()),'n_down':int((sig['log2fc'] < 0).sum())}}


def api_data_import(case, *, input_path=None):
    from skills._sdk.notebook import load_skill
    lib = load_skill('proteomics-data-import')
    result = lib.standardize(lib.demo_data())
    return {'tables':{'proteins.csv':result},'summary':lib.run_info(result)['summary']}


def api_ms_qc(case, *, input_path=None):
    from skills._sdk.notebook import load_skill
    lib = load_skill('proteomics-ms-qc')
    result = lib.quality_control(lib.demo_data())
    summary = lib.run_info(result)['summary']
    summary.pop('sample_columns')
    return {'tables':{'qc_metrics.csv':result},'summary':summary}


def api_identification(case, *, input_path=None):
    from skills._sdk.notebook import load_skill
    lib = load_skill('proteomics-identification')
    result = lib.filter_identifications(lib.demo_data(), n_spectra=1000)
    return {'tables':{'peptides.csv':result},'summary':lib.run_info(result)['summary']}


def api_ptm(case, *, input_path=None):
    from skills._sdk.notebook import load_skill
    lib = load_skill('proteomics-ptm')
    result = lib.classify_sites(lib.demo_data(), loc_threshold=.95 if case == 'strict' else .75)
    return {'tables':{'ptm_sites.csv':result,'ptm_class_I_sites.csv':result[result['site_class']=='Class I']},
            'summary':lib.run_info(result)['summary']}


def api_enrichment(case, *, input_path=None):
    from skills._sdk.notebook import load_skill
    lib = load_skill('proteomics-enrichment')
    result = lib.enrich(lib.demo_data()['protein_id'].tolist(), pathway_db=lib.demo_pathways())
    return {'tables':{'enrichment_results.csv':result},'summary':lib.run_info(result)['summary']}


def api_structural(case, *, input_path=None):
    from skills._sdk.notebook import load_skill
    lib = load_skill('proteomics-structural')
    result = lib.analyse_crosslinks(lib.demo_data(), crosslinker='EDC' if case == 'edc' else 'DSS')
    return {'tables':{'crosslinks.csv':result,'inter_protein_crosslinks.csv':result[result['link_type']=='inter-protein']},
            'summary':lib.run_info(result)['summary']}
