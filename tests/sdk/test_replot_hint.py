"""``write_replot_hint`` after its move into single-cell ``_lib`` (plan 0062 Q2, case 21).

Moved unchanged from ``omicsclaw/common/report.py`` so the framework no
longer imports ``skills.*``. The command it writes still names the retired
``python omicsclaw.py replot`` (see ``OMICSCLAW.md``); fixing that is out of
scope here, the move only preserves behaviour.
"""

from __future__ import annotations

import json

from skills._sdk.result import write_result_json
from skills.singlecell._lib.viz.r.renderer_params import SKILL_RENDERERS
from skills.singlecell._lib.viz.r.replot_hint import write_replot_hint


def test_a_known_skill_gets_a_replot_block(tmp_path):
    skill = "sc-batch-integration"
    assert skill in SKILL_RENDERERS
    write_result_json(tmp_path, skill, "1", {}, {})
    write_replot_hint(tmp_path, skill)
    payload = json.loads((tmp_path / "result.json").read_text())
    assert payload["replot"]["available"] is True
    assert set(payload["replot"]["renderers"]) == set(SKILL_RENDERERS[skill])
    assert payload["replot"]["command"].endswith(f"{skill} --output {tmp_path}")


def test_an_unknown_skill_leaves_the_file_alone(tmp_path):
    before = write_result_json(tmp_path, "no-such-skill", "1", {}, {}).read_text()
    write_replot_hint(tmp_path, "no-such-skill")
    assert (tmp_path / "result.json").read_text() == before


def test_a_broken_result_json_does_not_raise(tmp_path):
    (tmp_path / "result.json").write_text("{broken")
    write_replot_hint(tmp_path, "sc-batch-integration")
    assert (tmp_path / "result.json").read_text() == "{broken"
    write_replot_hint(tmp_path / "missing", "sc-batch-integration")
