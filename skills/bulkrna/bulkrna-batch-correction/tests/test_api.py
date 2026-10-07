import numpy as np
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_explicit_python_backend_aligns_samples_and_records_actual_method():
    rng = np.random.default_rng(7)
    data = pd.DataFrame(rng.normal(20, 1, (30, 8)), columns=list("abcdefgh"))
    data.loc[:, list("efgh")] += 10
    batches = pd.DataFrame({"sample": list("hgfedcba"), "batch": ["b"] * 4 + ["a"] * 4})
    original = data.copy(deep=True)
    api = load_skill("bulkrna-batch-correction")
    result = api.correct(data, batches=batches, backend="python")
    assert result.index.equals(data.index) and result.columns.equals(data.columns)
    assert np.isfinite(result.to_numpy()).all()
    info = api.run_info(result)
    assert info["executed_method"] == "python-parametric"
    assert info["summary"]["n_batches"] == 2
    pd.testing.assert_frame_equal(data, original)


def test_python_cannot_claim_nonparametric_correction():
    api = load_skill("bulkrna-batch-correction")
    data = pd.DataFrame(np.arange(32).reshape(4, 8) + 1, columns=list("abcdefgh"))
    batches = pd.DataFrame({"sample": list("abcdefgh"), "batch": ["a"] * 4 + ["b"] * 4})
    with pytest.raises(ValueError, match="non-parametric"):
        api.correct(data, batches=batches, backend="python", mode="non-parametric")


def test_real_r_bridge_preserves_non_syntactic_identifiers():
    rng = np.random.default_rng(11)
    data = pd.DataFrame(rng.normal(20, 1, (30, 8)),
                        index=["001"] + [f"gene-{i}" for i in range(29)],
                        columns=[f"sample {i}" for i in range(8)])
    batches = pd.DataFrame({"sample": data.columns, "batch": ["a"] * 4 + ["b"] * 4})
    api = load_skill("bulkrna-batch-correction")
    try:
        result = api.correct(data, batches=batches, backend="r")
    except ImportError as exc:
        pytest.skip(str(exc))
    assert result.index.tolist() == data.index.tolist()
    assert result.columns.tolist() == data.columns.tolist()
    assert api.run_info(result)["executed_method"] == "r-parametric"


def test_pca_accepts_negative_corrected_expression():
    api = load_skill("bulkrna-batch-correction")
    data = pd.DataFrame([[-4, 1, 2, 3], [3, 2, -2, 1]], columns=list("abcd"))
    batches = pd.DataFrame({"sample": list("abcd"), "batch": ["a", "a", "b", "b"]})
    assert len(api.pca_figure(data, batches=batches).axes) == 1


def test_failed_r_process_warns_and_records_the_real_fallback(monkeypatch):
    import subprocess
    real_run = subprocess.run
    def fail_script(command, *args, **kwargs):
        if len(command) > 1 and str(command[1]).endswith(".R"):
            return subprocess.CompletedProcess(command, 1, "", "R backend failed")
        return real_run(command, *args, **kwargs)
    monkeypatch.setattr(subprocess, "run", fail_script)
    data = pd.DataFrame(np.random.default_rng(11).normal(20, 1, (30, 8)), columns=list("abcdefgh"))
    batches = pd.DataFrame({"sample": data.columns, "batch": ["a"] * 4 + ["b"] * 4})
    api = load_skill("bulkrna-batch-correction")
    with pytest.warns(RuntimeWarning, match="Python"):
        result = api.correct(data, batches=batches)
    info = api.run_info(result)
    assert info["requested_method"] == "auto-parametric"
    assert info["executed_method"] == "python-parametric"
    assert info["fallback_reason"]
