import numpy as np
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def cohort():
    data = pd.DataFrame([range(8)], index=["G"], columns=[f"s{i}" for i in range(8)])
    clinical = pd.DataFrame({"sample": data.columns, "time": [1, 2, 3, 4, 2, 4, 6, 8], "event": [1] * 8})
    return data, clinical


def test_python_backend_records_the_incidence_rate_estimator():
    data, clinical = cohort()
    api = load_skill("bulkrna-survival")
    result = api.analyze(data, clinical=clinical, backend="python")
    assert result.gene.tolist() == ["G"]
    assert result.hazard_ratio.iloc[0] == 0.5
    assert api.run_info(result)["hazard_estimator"] == "events-per-person-time"
    curves = api.km_table(result)
    assert curves.groupby("group").survival.last().eq(0).all()


def test_missing_genes_raise_instead_of_silent_partial_results():
    data, clinical = cohort()
    with pytest.raises(ValueError, match="Missing genes"):
        load_skill("bulkrna-survival").analyze(data, clinical=clinical, genes=["absent"])


def test_censoring_tied_with_an_event_leaves_the_next_risk_set():
    data, clinical = cohort()
    clinical.loc[4:, "time"] = [1, 1, 2, 3]
    clinical.loc[4:, "event"] = [1, 0, 1, 1]
    api = load_skill("bulkrna-survival")
    result = api.analyze(data, clinical=clinical, backend="python")
    high = api.km_table(result).query("group == 'high'")
    assert high.survival.tolist() == [1, 0.75, 0.375, 0]


def test_real_r_reports_a_cox_estimator():
    data, clinical = cohort()
    api = load_skill("bulkrna-survival")
    try:
        result = api.analyze(data, clinical=clinical, backend="r")
    except ImportError as exc:
        pytest.skip(str(exc))
    assert api.run_info(result)["hazard_estimator"] == "cox-ph"
    assert 0 <= result.log_rank_pval.iloc[0] <= 1
    assert result.hazard_ratio.iloc[0] < 1
