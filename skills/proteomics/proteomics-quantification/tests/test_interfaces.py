"""Exercise each protein-table library through the notebook loader."""
import numpy as np
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


@pytest.mark.parametrize(('name','compute','plot'), [
    ('data-import','standardize','intensity_figure'),
    ('ms-qc','quality_control','completeness_figure'),
    ('identification','filter_identifications','score_figure'),
    ('quantification','quantify','abundance_figure'),
    ('de','differential_abundance','volcano_figure'),
    ('ptm','classify_sites','class_figure'),
    ('enrichment','enrich','enrichment_figure'),
    ('structural','analyse_crosslinks','distance_figure'),
])
def test_library_returns_figures_and_removable_diagnostics_without_writes(name, compute, plot, tmp_path, monkeypatch):
    from matplotlib.figure import Figure
    monkeypatch.chdir(tmp_path)
    before = np.random.get_state()
    lib = load_skill('proteomics-' + name)
    data = lib.demo_data(random_state=42)
    pd.testing.assert_frame_equal(data, lib.demo_data(random_state=42))
    if name == 'enrichment':
        result = lib.enrich(data['protein_id'].tolist(), pathway_db=lib.demo_pathways())
    else:
        result = getattr(lib, compute)(data)
    assert isinstance(result, pd.DataFrame) and not result.empty
    assert isinstance(getattr(lib, plot)(result), Figure)
    assert lib.run_info(result, keep=False)
    assert lib.run_info(result) == {}
    assert list(tmp_path.iterdir()) == []
    after = np.random.get_state()
    assert before[0] == after[0] and np.array_equal(before[1], after[1]) and before[2:] == after[2:]
