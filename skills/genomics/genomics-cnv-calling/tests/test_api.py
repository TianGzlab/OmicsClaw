from pathlib import Path
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill

DATA = Path(__file__).resolve().parents[1] / "data/example.csv"


def test_unsegmented_bins_keep_their_copy_number_state_without_mutating_input():
    api = load_skill("genomics-cnv-calling")
    data = pd.read_csv(DATA)
    before = data.copy(deep=True)
    result = api.analyze(data, method="none")
    assert result.cn_state.tolist() == ["neutral"] * 10 + ["amplification"] * 10 + ["loss"] * 3
    pd.testing.assert_frame_equal(data, before)
    assert api.run_info(result)["summary"]["n_gains"] == 10


def test_unknown_method_is_rejected_instead_of_silent_fallback():
    with pytest.raises(ValueError, match="method"):
        load_skill("genomics-cnv-calling").analyze(pd.read_csv(DATA), method="typo")


def test_cbs_recovers_the_three_constant_regions():
    api = load_skill("genomics-cnv-calling")
    result = api.analyze(pd.read_csv(DATA))
    assert result.cn_state.tolist() == ["neutral", "amplification", "loss"]
    assert result.n_bins.tolist() == [10, 10, 3]
    assert result.start.tolist() == [0, 1000, 0]
