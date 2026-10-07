import pandas as pd
from skills._sdk.notebook import load_skill


def test_site_classes_respect_threshold_and_preserve_input():
    data = pd.DataFrame({'protein':['A']*3, 'ptm_type':['Phosphorylation']*3, 'localization_probability':[.9,.6,.2]})
    lib = load_skill('proteomics-ptm')
    result = lib.classify_sites(data)
    assert result['site_class'].tolist() == ['Class I','Class II','Class III']
    assert lib.run_info(result)['summary']['n_class_I'] == 1
    assert 'site_class' not in data


def test_missing_localization_remains_unknown():
    result = load_skill('proteomics-ptm').classify_sites(pd.DataFrame({'protein':['A'],'ptm_type':['Acetylation']}))
    assert result['site_class'].tolist() == ['Unknown']
