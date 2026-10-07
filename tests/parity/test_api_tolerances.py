"""Only DPT's API pseudotime columns allow the measured JIT rounding drift."""

import pandas as pd

from tests.parity import snapshot
from tests.parity.test_sc_parity import _api_column_rtol


def test_dpt_jit_tolerance_is_scoped_and_rejects_larger_drift():
    options = _api_column_rtol("sc-pseudotime", "default", "obs_numeric.csv")
    assert options == {"dpt_pseudotime": 3e-5, "pseudotime": 3e-5}
    expected = pd.DataFrame({"pseudotime": [0., 0.01], "n_counts": [1., 2.]})
    within = expected.copy()
    within.loc[1, "pseudotime"] *= 1 + 2.5e-5
    assert snapshot.compare_frames(expected, within, "api", column_rtol=options) == []
    assert snapshot.compare_frames(expected, within, "cli")
    beyond = expected.copy()
    beyond.loc[1, "pseudotime"] *= 1 + 4e-5
    assert snapshot.compare_frames(expected, beyond, "api", column_rtol=options)
    nonzero_root = expected.copy()
    nonzero_root.loc[0, "pseudotime"] = 1e-12
    assert snapshot.compare_frames(expected, nonzero_root, "api", column_rtol=options)
    unrelated = expected.copy()
    unrelated.loc[1, "n_counts"] *= 1 + 2e-6
    assert snapshot.compare_frames(expected, unrelated, "api", column_rtol=options)


def test_no_other_case_or_column_gets_the_dpt_exception():
    assert _api_column_rtol("sc-pseudotime", "default", "tables/pseudotime_cells.csv") == {"pseudotime": 3e-5}
    assert _api_column_rtol("sc-pseudotime", "default", "tables/trajectory_genes.csv") == {}
    assert _api_column_rtol("sc-pseudotime", "palantir", "obs_numeric.csv") == {}
    assert _api_column_rtol("sc-velocity", "default", "obs_numeric.csv") == {}
