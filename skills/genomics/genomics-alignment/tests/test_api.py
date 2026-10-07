from pathlib import Path
import pandas as pd
from skills._sdk.notebook import load_skill

def test_public_analysis_matches_worked_fixture_and_leaves_input_unchanged():
    api = load_skill("genomics-alignment")
    source = next((Path(__file__).resolve().parents[1] / "data").glob("example.*"))
    data = api.read_records(source)
    before = data.copy(deep=True)
    result = api.analyze(data)
    assert api.run_info(result)["summary"]["mapping_rate_pct"] == 75
    pd.testing.assert_frame_equal(data, before)
    assert len(api.distribution_figure(result).axes) == 1


def test_secondary_alignments_are_not_counted_as_primary_mapped_reads():
    api = load_skill("genomics-alignment")
    data = pd.DataFrame({"flag": [0, 4, 256, 2048, 1024], "mapq": [40, 0, 60, 60, 20], "tlen": [0] * 5})
    info = api.run_info(api.analyze(data))["summary"]
    assert info["primary_alignments"] == 3
    assert info["mapped_reads"] == 2
    assert info["duplicates"] == 1
    assert info["mean_insert_size"] == 0
