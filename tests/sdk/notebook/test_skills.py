"""``load_skill`` and ``run_cli``: finding skills, recording calls, stubs, CLI runs."""

from __future__ import annotations

import json
import textwrap

import pytest

from skills._sdk.notebook import _ledger, _skills, load_skill, run_cli


@pytest.fixture
def step(tmp_path, monkeypatch, skills_tree):
    root = tmp_path / "proj"
    (root / "analysis" / "01_de").mkdir(parents=True)
    (root / "results" / "01_de").mkdir(parents=True)
    (root / "data").mkdir()
    step_file = root / "analysis" / "01_de" / "01_s.py"
    step_file.write_text("")
    ledger = root / "results" / "01_de" / "provenance" / "runs" / "01_s" / "r.jsonl"
    monkeypatch.setenv("OMICSCLAW_STEP_FILE", str(step_file))
    monkeypatch.setenv("OMICSCLAW_STEP_LEDGER", str(ledger))
    monkeypatch.delenv("OMICSCLAW_SKILL_STUBS", raising=False)
    return root, ledger


def _events(ledger, kind):
    return [e for e in _ledger.read_events(ledger) if e["event"] == kind]


def test_a_hyphenated_skill_loads_and_exposes_only_its_all(step):
    clustering = load_skill("sc-clustering")
    assert clustering.__all__ == ["cluster", "cluster_summary"]
    assert clustering.cluster_summary({"leiden": ["0", "1", "0"]}) == {"0": 2, "1": 1}
    with pytest.raises(AttributeError, match="available: cluster, cluster_summary"):
        clustering._helper
    with pytest.raises(AttributeError):
        clustering.missing


def test_calls_are_recorded_with_a_summary_of_their_arguments(step):
    _, ledger = step
    clustering = load_skill("sc-clustering")
    clustering.cluster({"cells": [1, 2]}, resolution=0.5)
    load = _events(ledger, "skill_load")
    assert len(load) == 1 and load[0]["skill"] == "sc-clustering" and load[0]["stub"] is False
    assert load[0]["candidate"] is None
    assert set(load[0]["dependencies"]) == {"json5", "pytest"}
    call = _events(ledger, "skill_call")[0]
    assert call["function"] == "cluster"
    assert call["args"] == {"data": "dict", "resolution": 0.5}
    assert call["seconds"] >= 0 and call["stub"] is False


def test_a_failing_call_is_recorded_with_its_error(step):
    _, ledger = step
    with pytest.raises(KeyError):
        load_skill("sc-clustering").cluster({})
    assert _events(ledger, "skill_call")[0]["error"].startswith("KeyError")


def test_a_shape_is_kept_in_the_argument_summary():
    np = pytest.importorskip("numpy")
    assert _ledger.summarize_value(np.zeros((3, 4))) == "ndarray(3, 4)"
    assert _ledger.summarize_value([1, "a"]) == [1, "a"]


def test_outside_a_step_run_nothing_is_recorded_and_stubs_are_ignored(tmp_path, monkeypatch, skills_tree):
    monkeypatch.delenv("OMICSCLAW_STEP_LEDGER", raising=False)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "sc-clustering.py").write_text("def cluster(data, **_):\n    return 'stub'\n")
    monkeypatch.setenv("OMICSCLAW_SKILL_STUBS", str(stubs))
    clustering = load_skill("sc-clustering")
    assert clustering.cluster({"cells": [1]})["leiden"] == ["0"]


def test_skill_lookup_skips_private_and_hidden_dirs_and_disabled_skills(skills_tree):
    for folder in ("_lib/sc-hidden", ".quarantine/sc-hidden2", "singlecell/scrna/sc-off"):
        (skills_tree / folder).mkdir(parents=True)
    (skills_tree / "_lib/sc-hidden/SKILL.md").write_text("x")
    (skills_tree / ".quarantine/sc-hidden2/SKILL.md").write_text("x")
    (skills_tree / "singlecell/scrna/sc-off/SKILL.md.disabled").write_text("x")
    _skills._INDEX.clear()
    for name in ("sc-hidden", "sc-hidden2", "sc-off"):
        with pytest.raises(LookupError):
            _skills.skill_dir(name)


def test_an_unknown_name_suggests_close_ones(skills_tree):
    with pytest.raises(LookupError, match="closest: sc-clustering"):
        load_skill("sc-clusterin")


def test_two_skills_with_one_name_is_an_error(skills_tree):
    copy = skills_tree / "spatial" / "sc-clustering"
    copy.mkdir(parents=True)
    (copy / "SKILL.md").write_text("x")
    _skills._INDEX.clear()
    with pytest.raises(LookupError, match="more than one"):
        load_skill("sc-clustering")


def test_a_skill_without_a_library_points_at_run_cli(skills_tree):
    with pytest.raises(LookupError, match="run_cli"):
        load_skill("bulkrna-de")


def test_another_root_is_recorded_as_a_candidate(step, tmp_path, skills_tree):
    import shutil

    _, ledger = step
    candidate = tmp_path / "cand-007" / "skills"
    shutil.copytree(skills_tree, candidate)
    load_skill("sc-clustering", root=candidate).cluster_summary({"leiden": []})
    load = _events(ledger, "skill_load")[0]
    assert load["candidate"] == "cand-007"
    assert load["root"] == str(candidate)


def test_a_matching_stub_replaces_the_library(step, tmp_path, monkeypatch):
    _, ledger = step
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "sc-clustering.py").write_text(textwrap.dedent('''
        def cluster(data, *, resolution=1.0, **_):
            return {"stub": resolution}
    '''))
    monkeypatch.setenv("OMICSCLAW_SKILL_STUBS", str(stubs))
    assert load_skill("sc-clustering").cluster({}, resolution=0.3) == {"stub": 0.3}
    assert _events(ledger, "skill_load")[0]["stub"] is True
    assert _events(ledger, "skill_call")[0]["stub"] is True


def test_a_stub_naming_a_function_the_library_lacks_is_stub_target_missing(step, tmp_path, monkeypatch):
    _, ledger = step
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "sc-clustering.py").write_text("def cluster(d):\n    return d\n\ndef cluster_report(d):\n    return d\n")
    monkeypatch.setenv("OMICSCLAW_SKILL_STUBS", str(stubs))
    with pytest.raises(LookupError, match="cluster_report"):
        load_skill("sc-clustering")
    missing = _events(ledger, "stub_target_missing")[0]
    assert missing["skill"] == "sc-clustering" and missing["names"] == ["cluster_report"]


def test_a_stub_for_a_skill_without_a_library_is_stub_target_missing(step, tmp_path, monkeypatch):
    _, ledger = step
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "bulkrna-de.py").write_text("def de(d):\n    return d\n")
    monkeypatch.setenv("OMICSCLAW_SKILL_STUBS", str(stubs))
    with pytest.raises(LookupError):
        load_skill("bulkrna-de")
    assert _events(ledger, "stub_target_missing")[0]["reason"] == "bulkrna-de has no _api.py"


def test_run_cli_defaults_its_output_and_records_outputs(step):
    root, ledger = step
    (root / "data" / "counts.csv").write_text("g,a\nx,1\n")
    output = run_cli("sc-clustering", "--input", "data/counts.csv", inputs=["data/counts.csv"])
    assert output == root / "results" / "01_de" / "intermediate" / "sc-clustering"
    assert json.loads((output / "result.json").read_text()) == {"input": "data/counts.csv"}
    assert "clustered data/counts.csv" in (root / "results/01_de/logs/01_s__sc-clustering.log").read_text()
    assert _events(ledger, "input")[0]["via"] == "run_cli"
    cli = _events(ledger, "skill_cli")[0]
    assert cli["exit_code"] == 0 and cli["output_dir"] == "intermediate/sc-clustering" and cli["stub"] is False
    assert {e["path"] for e in _events(ledger, "output")} == {
        "intermediate/sc-clustering/result.json", "intermediate/sc-clustering/tables/clusters.csv",
    }


def test_run_cli_strips_the_step_variables_from_the_child(step, skills_tree):
    root, _ = step
    script = skills_tree / "singlecell" / "scrna" / "sc-clustering" / "sc_cluster.py"
    script.write_text(
        "import os, sys, pathlib\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('--output') + 1]); out.mkdir(parents=True, exist_ok=True)\n"
        "print(sorted(k for k in os.environ if k.startswith('OMICSCLAW_STEP') or k == 'OMICSCLAW_SKILL_STUBS'))\n"
    )
    run_cli("sc-clustering")
    assert "[]" in (root / "results/01_de/logs/01_s__sc-clustering.log").read_text()


def test_run_cli_takes_an_output_inside_the_module_and_refuses_one_outside(step):
    root, _ = step
    assert run_cli("sc-clustering", "--output", "results/01_de/intermediate/custom") == (
        root / "results/01_de/intermediate/custom"
    )
    with pytest.raises(ValueError, match="outside results/01_de"):
        run_cli("sc-clustering", "--output", "results/02_x/intermediate/custom")


def test_run_cli_raises_on_a_failing_script(step):
    _, ledger = step
    with pytest.raises(RuntimeError, match="status 3"):
        run_cli("sc-clustering", "--fail")
    assert _events(ledger, "skill_cli")[0]["exit_code"] == 3
    assert _events(ledger, "output") == []


def test_run_cli_answers_from_a_stub_result(step, tmp_path, monkeypatch, capsys):
    root, ledger = step
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "bulkrna-de.json").write_text(json.dumps({
        "stdout": "DE done: {output}\n", "exit_code": 0,
        "files": {"result.json": "{\"out\": \"{output}\"}"}, "binary_files": ["figures/volcano.png"],
    }))
    monkeypatch.setenv("OMICSCLAW_SKILL_STUBS", str(stubs))
    output = run_cli("bulkrna-de", "--input", "data/c.csv")
    assert json.loads((output / "result.json").read_text()) == {"out": str(output)}
    assert (output / "figures" / "volcano.png").read_bytes() == b""
    assert f"DE done: {output}" in capsys.readouterr().out
    assert _events(ledger, "skill_cli")[0]["stub"] is True
    assert len(_events(ledger, "output")) == 2


def test_a_cli_stub_for_a_skill_without_a_script_is_stub_target_missing(step, tmp_path, monkeypatch, skills_tree):
    _, ledger = step
    (skills_tree / "bulkrna" / "bulkrna-de" / "bulkrna_de.py").unlink()
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "bulkrna-de.json").write_text(json.dumps({"stdout": "x"}))
    monkeypatch.setenv("OMICSCLAW_SKILL_STUBS", str(stubs))
    with pytest.raises(LookupError):
        run_cli("bulkrna-de")
    assert _events(ledger, "stub_target_missing")[0]["skill"] == "bulkrna-de"
