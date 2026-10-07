"""Recorded metabolomics CLI cases and their public-library counterparts."""


def register(Case, Skill):
    scripts = {
        'normalization': 'metabolomics_normalization.py',
        'quantification': 'met_quantify.py',
        'de': 'met_diff.py',
        'statistics': 'metabolomics_statistics.py',
        'annotation': 'metabolomics_annotation.py',
        'peak-detection': 'peak_detect.py',
        'pathway-enrichment': 'met_pathway.py',
        'xcms-preprocessing': 'metabolomics_xcms_preprocessing.py',
    }

    cases = {
        'normalization': {m: ('--method', m) for m in ('median', 'quantile', 'total', 'pqn', 'log')},
        'quantification': {m: ('--impute', m) for m in ('min', 'median', 'knn')},
        'de': {'default': ()},
        'statistics': {m: ('--method', m) for m in ('ttest', 'wilcoxon', 'anova', 'kruskal')},
        'annotation': {'default': (), 'tight': ('--ppm', '5')},
        'peak-detection': {'default': (), 'sensitive': ('--prominence', '1000', '--distance', '3')},
        'pathway-enrichment': {'default': ()},
        'xcms-preprocessing': {'default': ()},
    }
    return {
        'metabolomics-' + name: Skill(
            f'skills/metabolomics/metabolomics-{name}/{script}',
            None if name == 'xcms-preprocessing' else 'tests.parity.metabolomics:api_' + name.replace('-', '_'),
            {case: Case(('--demo', *args), environment={'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})
             for case, args in cases[name].items()},
        ) for name, script in scripts.items()
    }


def api_normalization(case):
    from skills._sdk.notebook import load_skill
    from skills.metabolomics._lib.demo import normalization
    result = load_skill('metabolomics-normalization').normalize(normalization(), method=case)
    return {'tables': {'normalized.csv': result.reset_index().rename(columns={'index': 'Unnamed: 0'})}}


def api_quantification(case):
    from skills._sdk.notebook import load_skill
    from skills.metabolomics._lib.demo import quantification
    library = load_skill('metabolomics-quantification')
    result = library.quantify(quantification(), impute=case)
    return {'tables': {'quantified_features.csv': result}, 'summary': library.run_info(result)}


def api_de(case):
    from skills._sdk.notebook import load_skill
    from skills.metabolomics._lib.demo import de
    library = load_skill('metabolomics-de')
    result = library.differential_expression(de())
    return {'tables': {'differential_features.csv': result, 'significant_features.csv': result[result.fdr < .05]}, 'summary': library.run_info(result)}


def api_statistics(case):
    from skills._sdk.notebook import load_skill
    from skills.metabolomics._lib.demo import statistics
    data, first, second = statistics()
    library = load_skill('metabolomics-statistics')
    result = library.test_groups(data, method=case, group1_cols=first, group2_cols=second)
    info = library.run_info(result)
    return {'tables': {'statistics.csv': result, 'significant.csv': result[result.fdr < .05]},
            'summary': {k: info[k] for k in ('method', 'n_tested', 'n_significant', 'sig_rate')}}


def api_annotation(case):
    from skills._sdk.notebook import load_skill
    from skills.metabolomics._lib.demo import annotation
    library = load_skill('metabolomics-annotation')
    result = library.annotate(annotation(), ppm=5. if case == 'tight' else 10., reference=library.demo_reference())
    return {'tables': {'annotations.csv': result}}


def api_peak_detection(case):
    from skills._sdk.notebook import load_skill
    from skills.metabolomics._lib.demo import peak_detection
    library = load_skill('metabolomics-peak-detection')
    result = library.detect_peaks(peak_detection(), **({'prominence': 1000, 'distance': 3} if case == 'sensitive' else {}))
    return {'tables': {'detected_peaks.csv': result}, 'summary': library.run_info(result)}


def api_pathway_enrichment(case):
    from skills._sdk.notebook import load_skill
    from skills.metabolomics._lib.demo import pathway_enrichment
    library = load_skill('metabolomics-pathway-enrichment')
    result = library.enrich(pathway_enrichment()['metabolite'], pathways=library.demo_pathways())
    info = library.run_info(result)
    return {'tables': {'pathway_enrichment.csv': result},
            'summary': {k: info[k] for k in ('method', 'n_metabolites', 'n_pathways_tested', 'n_significant')}}
