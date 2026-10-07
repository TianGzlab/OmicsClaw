from pathlib import Path
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill

def test_public_analysis_matches_worked_fixture_and_leaves_input_unchanged():
    api = load_skill("genomics-phasing")
    source = next((Path(__file__).resolve().parents[1] / "data").glob("example.*"))
    data = api.read_records(source)
    before = data.copy(deep=True)
    result = api.analyze(data)
    assert api.run_info(result)["summary"]["phased_fraction"] == 0.8
    pd.testing.assert_frame_equal(data, before)
    figure = api.distribution_figure(result)
    assert len(figure.axes) == 1
    api.run_info(result, keep=False)
    assert "run_info" not in result.attrs


def test_phase_sets_are_scoped_by_chromosome():
    api = load_skill("genomics-phasing")
    source = Path(__file__).resolve().parents[1] / "data/example.vcf"
    summary = api.run_info(api.analyze(api.read_records(source)))["summary"]
    assert summary["n_phase_blocks"] == 2
    assert summary["phase_block_n50_bp"] == 200
    assert summary["n_het_variants"] == 5


def test_header_only_vcf_returns_empty_table_and_zero_summary(tmp_path):
    api = load_skill("genomics-phasing")
    source = tmp_path / "empty.vcf"
    source.write_text(
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n",
        encoding="utf-8",
    )
    data = api.read_records(source)
    before = data.copy(deep=True)

    result = api.analyze(data)

    assert result.empty
    assert list(result.columns) == [
        "chrom", "pos", "ref", "alt", "gt", "is_phased", "is_het", "phase_set",
    ]
    assert api.run_info(result)["summary"] == {
        "n_total_variants": 0,
        "n_het_variants": 0,
        "n_phased_het": 0,
        "phased_fraction": 0.0,
        "n_phase_blocks": 0,
        "phase_block_n50_bp": 0,
        "phase_block_n50_variants": 0,
        "longest_block_bp": 0,
        "longest_block_variants": 0,
        "mean_block_length_bp": 0,
        "median_block_length_bp": 0,
    }
    pd.testing.assert_frame_equal(data, before)
    assert "run_info" not in data.attrs
    with pytest.raises(ValueError, match="no records"):
        api.distribution_figure(result)


def test_empty_table_without_required_columns_is_rejected():
    api = load_skill("genomics-phasing")
    with pytest.raises(ValueError, match="Missing columns"):
        api.analyze(pd.DataFrame())
