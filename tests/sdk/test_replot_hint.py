"""Skills no longer write a ``replot`` hint into ``result.json``.

The hint named ``python omicsclaw.py replot``, a command removed with the
old CLI. There is no replacement re-render command, so the hint and its
22 call sites were deleted rather than repointed; changing a plot means
re-running the skill, which is what ``OMICSCLAW.md`` tells the agent.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_no_skill_script_writes_the_replot_hint():
    offenders = [
        path.relative_to(REPO).as_posix()
        for path in (REPO / "skills").rglob("*.py")
        if "write_replot_hint" in (text := path.read_text(encoding="utf-8", errors="replace"))
        or "omicsclaw.py replot" in text
    ]
    assert offenders == []
    assert not (REPO / "skills/singlecell/_lib/viz/r/replot_hint.py").exists()


def test_the_runtime_contract_does_not_name_the_removed_command():
    contract = (REPO / "OMICSCLAW.md").read_text(encoding="utf-8")
    assert "omicsclaw.py replot" not in contract
    assert "re-run the skill" in contract
