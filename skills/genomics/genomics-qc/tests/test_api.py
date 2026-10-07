from pathlib import Path
import pandas as pd
from skills._sdk.notebook import load_skill
import pytest

def test_public_analysis_matches_worked_fixture_and_leaves_input_unchanged():
    api = load_skill("genomics-qc")
    source = next((Path(__file__).resolve().parents[1] / "data").glob("example.*"))
    data = api.read_records(source)
    before = data.copy(deep=True)
    result = api.analyze(data)
    assert api.run_info(result)["summary"]["total_reads"] == 3
    pd.testing.assert_frame_equal(data, before)
    assert len(api.distribution_figure(result).axes) == 1


def test_malformed_fastq_is_not_reported_as_successful_partial_qc(tmp_path):
    path = tmp_path / "bad.fastq"
    path.write_text("@read\nACGT\n+\nIII\n")
    with pytest.raises(ValueError, match="FASTQ"):
        load_skill("genomics-qc").read_records(path)


def test_phred_base_rates_and_read_limit_are_known():
    api = load_skill("genomics-qc")
    data = pd.DataFrame({"sequence": ["ACGT", "GGNN"], "quality": ["IIII", "5555"]})
    result = api.analyze(data)
    info = api.run_info(result)["summary"]
    assert info["mean_quality"] == 30
    assert info["q30_rate"] == 50
    assert info["q20_rate"] == 100
    assert info["gc_content"] == 50
    assert info["n_content"] == 25
    assert api.run_info(api.analyze(data, max_reads=1))["summary"]["mean_quality"] == 40
