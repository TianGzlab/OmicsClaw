from pathlib import Path
import pandas as pd
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
