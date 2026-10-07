from pathlib import Path
import pandas as pd
from skills._sdk.notebook import load_skill

def test_public_analysis_matches_worked_fixture_and_leaves_input_unchanged():
    api = load_skill("genomics-epigenomics")
    source = next((Path(__file__).resolve().parents[1] / "data").glob("example.*"))
    data = api.read_records(source)
    before = data.copy(deep=True)
    result = api.analyze(data)
    assert api.run_info(result)["summary"]["mean_peak_width"] == 200
    pd.testing.assert_frame_equal(data, before)
    figure = api.distribution_figure(result)
    assert len(figure.axes) == 1
    api.run_info(result, keep=False)
    assert "run_info" not in result.attrs
