from pathlib import Path
import pandas as pd
from skills._sdk.notebook import load_skill

def test_public_analysis_matches_worked_fixture_and_leaves_input_unchanged():
    api = load_skill("genomics-assembly")
    source = next((Path(__file__).resolve().parents[1] / "data").glob("example.*"))
    data = api.read_records(source)
    before = data.copy(deep=True)
    result = api.analyze(data)
    assert api.run_info(result)["summary"]["n50"] == 12
    pd.testing.assert_frame_equal(data, before)
    figure = api.distribution_figure(result)
    assert len(figure.axes) == 1
    api.run_info(result, keep=False)
    assert "run_info" not in result.attrs


def test_nx_length_and_gc_metrics_have_hand_worked_values():
    api = load_skill("genomics-assembly")
    data = pd.DataFrame({"contig": ["a", "b", "c"], "sequence": ["ACGTACGTACGT", "GGGGCC", "AT"]})
    info = api.run_info(api.analyze(data, genome_size=40))["summary"]
    assert info["total_length"] == 20
    assert info["gc_content"] == 60
    assert info["n90"] == 6
    assert info["l50"] == 1
    assert info["completeness_pct"] == 50
