from pathlib import Path
import pandas as pd
from skills._sdk.notebook import load_skill
import pytest

def test_public_analysis_matches_worked_fixture_and_leaves_input_unchanged():
    api = load_skill("genomics-vcf-operations")
    source = next((Path(__file__).resolve().parents[1] / "data").glob("example.*"))
    data = api.read_records(source)
    before = data.copy(deep=True)
    result = api.analyze(data)
    assert api.run_info(result)["summary"]["n_snps"] == 4
    pd.testing.assert_frame_equal(data, before)
    assert len(api.distribution_figure(result).axes) == 1


def test_thresholds_filter_per_alt_and_preserve_header_metadata():
    api = load_skill("genomics-vcf-operations")
    source = Path(__file__).resolve().parents[1] / "data/example.vcf"
    data = api.read_records(source)
    result = api.analyze(data, min_qual=30, min_dp=10)
    assert len(result) == 5
    assert api.run_info(result)["summary"]["n_indels"] == 1
    assert result.attrs["vcf_headers"] == data.attrs["vcf_headers"]
    assert len(data) == 6
    with pytest.raises(ValueError, match="No variants"):
        api.analyze(data, min_qual=1000)
