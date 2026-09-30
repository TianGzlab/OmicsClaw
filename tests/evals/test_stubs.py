"""Skill stubs: which commands count as a skill run, replay, pass-through, the seam."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from omicsclaw.evals import Failure, StubResult, stubbed_skill_runs
from omicsclaw.evals.runner import skill_index
from omicsclaw.evals.stubs import REPO_ROOT, find_skill_run, normalize
from omicsclaw.tools import ApprovalDecision
from omicsclaw.tools._workspace import Workspace
from omicsclaw.tools.builtin import bash as bash_module
from omicsclaw.tools.builtin.bash import BashTool
from omicsclaw.tools.context import use_tool_context

SKILLS = REPO_ROOT / "skills"


@pytest.mark.parametrize(
    ("script", "skill", "domain"),
    [
        ("spatial/spatial-preprocess/spatial_preprocess.py", "spatial-preprocess", "spatial"),
        ("singlecell/scrna/sc-clustering/sc_cluster.py", "sc-clustering", "singlecell"),
        ("literature/literature_parse.py", "literature", "literature"),
    ],
)
def test_all_three_directory_depths_are_recognised(tmp_path, script, skill, domain):
    for spelling in (str(SKILLS / script), f"skills/{script}"):
        run = find_skill_run(f"cd {tmp_path} && python3 -u {spelling} --output out/x", tmp_path, skill_index())
        assert run is not None and run.skill.name == skill and run.skill.domain == domain
        assert run.output == "out/x"


def test_reading_or_listing_a_skill_is_not_a_run(tmp_path):
    index = skill_index()
    directory = SKILLS / "spatial" / "spatial-preprocess"
    assert find_skill_run(f"cat {directory}/SKILL.md", tmp_path, index) is None
    assert find_skill_run(f"ls {directory}", tmp_path, index) is None
    assert find_skill_run("python -c 'print(1)'", tmp_path, index) is None


def test_output_flag_spellings(tmp_path):
    index = skill_index()
    script = SKILLS / "bulkrna" / "bulkrna-de" / "bulkrna_de.py"
    assert find_skill_run(f"python {script} -o a", tmp_path, index).output == "a"
    assert find_skill_run(f"python {script} --output=b", tmp_path, index).output == "b"
    assert find_skill_run(f"python {script} --demo", tmp_path, index).output is None
    assert find_skill_run(f"python {script} --help", tmp_path, index).wants_help


def _bash(tmp_path: Path, command: str) -> str:
    tool = BashTool(Workspace(tmp_path))
    with use_tool_context(approval=lambda request: ApprovalDecision(approved=True)):
        return asyncio.run(tool.execute(json.dumps({"command": command})))


def test_a_stubbed_run_writes_the_files_and_returns_the_output(tmp_path):
    stub = StubResult(stdout="QC done in {output}", files={"result.json": '{"n_spots": 3}'}, binary_files=("fig.png",))
    runs, failures = [], []
    script = SKILLS / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    with stubbed_skill_runs({"spatial-preprocess": stub}, skill_index(), runs, failures):
        output = _bash(tmp_path, f"python {script} --input missing.h5ad --output out/pp")
    assert output == f"QC done in {tmp_path / 'out' / 'pp'}"
    assert json.loads((tmp_path / "out" / "pp" / "result.json").read_text()) == {"n_spots": 3}
    assert (tmp_path / "out" / "pp" / "fig.png").read_bytes() == b""
    assert [(r.skill, r.stubbed) for r in runs] == [("spatial-preprocess", True)]
    assert failures == []


def test_other_commands_and_help_run_for_real(tmp_path):
    runs, failures = [], []
    script = SKILLS / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    stub = StubResult(stdout="STUB")
    with stubbed_skill_runs({"spatial-preprocess": stub}, skill_index(), runs, failures):
        assert _bash(tmp_path, "echo real").strip() == "real"
        helped = _bash(tmp_path, f"{sys.executable} {script} --help")
    assert "STUB" not in helped
    assert runs == []


def test_an_unstubbed_skill_run_is_recorded_as_such(tmp_path):
    runs = []
    script = SKILLS / "bulkrna" / "bulkrna-de" / "bulkrna_de.py"
    with stubbed_skill_runs({}, skill_index(), runs):
        _bash(tmp_path, f"python {script} --input missing.csv --output out || true")
    assert [(r.skill, r.stubbed) for r in runs] == [("bulkrna-de", False)]


def test_a_missing_script_or_output_is_a_hard_failure(tmp_path):
    failures: list[Failure] = []
    stub = StubResult(stdout="STUB")
    directory = SKILLS / "spatial" / "spatial-preprocess"
    with stubbed_skill_runs({"spatial-preprocess": stub}, skill_index(), [], failures):
        gone = _bash(tmp_path, f"python {directory}/renamed.py --output out")
        bare = _bash(tmp_path, f"python {directory}/spatial_preprocess.py --demo")
    assert "does not exist" in gone and "no --output" in bare
    assert [f.assertion for f in failures] == ["stub_target_missing", "stub_target_missing"]
    assert all(not f.is_soft for f in failures)


def test_a_stub_for_an_unknown_skill_is_refused():
    with pytest.raises(KeyError):
        with stubbed_skill_runs({"no-such-skill": StubResult(stdout="")}, skill_index(), []):
            pass


def test_bash_resolves_its_local_runner_when_it_runs(tmp_path, monkeypatch):
    """The stub replaces ``bash._locally`` as a module attribute.

    That only works while ``BashTool.execute`` looks the name up at call
    time. If a refactor binds it earlier (a default argument, a method),
    this test fails first instead of every stub going quietly unused.
    """
    seen = []

    async def fake(command, cwd, timeout):
        seen.append(command)
        return bash_module.CommandOutcome(output="from the fake", exit_code=0), False

    monkeypatch.setattr(bash_module, "_locally", fake)
    assert _bash(tmp_path, "echo never") == "from the fake"
    assert seen == ["echo never"]


def test_normalize_replaces_paths_and_timestamps(tmp_path):
    out = tmp_path / "output"
    text = f"wrote {out}/report.md at 2026-09-30T04:12:10.5+00:00 into {REPO_ROOT}/x run_20260930_041210"
    assert normalize(text, output=out, home=Path("/nonexistent-home")) == (
        "wrote {output}/report.md at 2000-01-01T00:00:00 into {repo}/x run_20000101_000000"
    )


def test_a_stub_round_trips_through_its_fixture(tmp_path):
    stub = StubResult(stdout="x", exit_code=1, files={"b": "2", "a": "1"}, provenance={"skill": "s"})
    stub.dump(tmp_path / "s.json")
    assert StubResult.load(tmp_path / "s.json") == stub


def test_the_fallback_answers_a_skill_without_a_stub_and_nothing_runs(tmp_path):
    """With a fallback, no skill script runs for real; what follows it on the line does not run either."""
    runs, failures = [], []
    fallback = StubResult(stdout="[eval] {skill} ran into {output}", files={"result.json": "{}"})
    script = SKILLS / "bulkrna" / "bulkrna-de" / "bulkrna_de.py"
    with stubbed_skill_runs({}, skill_index(), runs, failures, fallback=fallback):
        output = _bash(tmp_path, f"python {script} --input c.csv --output o; touch ran.txt")
    assert output == f"[eval] bulkrna-de ran into {tmp_path / 'o;'}"
    assert (tmp_path / "o;" / "result.json").is_file()
    assert not (tmp_path / "ran.txt").exists()
    assert [(r.skill, r.stubbed) for r in runs] == [("bulkrna-de", True)]
    assert failures == []


def test_the_fallback_refuses_a_run_without_output_with_exit_2(tmp_path):
    runs, failures = [], []
    directory = SKILLS / "bulkrna" / "bulkrna-de"
    with stubbed_skill_runs({}, skill_index(), runs, failures, fallback=StubResult(stdout="X")):
        bare = _bash(tmp_path, f"python {directory}/bulkrna_de.py --demo; touch ran.txt")
        gone = _bash(tmp_path, f"python {directory}/renamed.py --output out")
    assert "--output is required" in bare and "[exit status 2]" in bare
    assert "No such file" in gone
    assert not (tmp_path / "ran.txt").exists()
    assert runs == [] and failures == []


def test_a_recorded_stub_still_wins_over_the_fallback(tmp_path):
    runs = []
    script = SKILLS / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    with stubbed_skill_runs(
        {"spatial-preprocess": StubResult(stdout="RECORDED")}, skill_index(), runs, fallback=StubResult(stdout="FALLBACK")
    ):
        assert _bash(tmp_path, f"python {script} --output o") == "RECORDED"
