"""``replay``: every step in a fresh kernel, validate last, outputs compared."""

from __future__ import annotations

import json
import sys

from skills._sdk.notebook import _ledger

WRITE = '''
# %%
from skills._sdk.notebook import write_output
write_output({"value": VALUE}, "tables/a.json")
'''

VALIDATE = '''
# %%
from skills._sdk.notebook import read_input
assert read_input("results/01_m/tables/a.json")["value"] > 0
'''


def _module(project, value=1):
    module = project.new("m")
    project.step(module, "01_write.py", WRITE.replace("VALUE", str(value)))
    project.step(module, "02_validate.py", VALIDATE)
    return module


def test_replay_runs_every_step_validate_last_and_marks_the_module_replayed(project):
    module = _module(project)
    project.run(f"analysis/{module}")
    project.step(module, "01b_more.py", "# %%\nfrom skills._sdk.notebook import write_output\nwrite_output({'b': 1}, 'tables/b.json')\n")
    assert project.replay(f"analysis/{module}") == 0, project.text
    order = [line.split()[1] for line in project.lines if line.startswith("[01_m] 0")]
    assert order == ["01_write.py", "01b_more.py", "02_validate.py"]
    manifest = project.manifest(module)
    assert manifest["status"] == "replayed"
    assert manifest["replay"]["status"] == "ok"
    assert set(manifest["replay"]["step_sha256"]) == {"01_write.py", "01b_more.py", "02_validate.py"}
    runs = _ledger.runs_of(project.root / "results/01_m/provenance/runs", "01_write")
    assert runs[-1].mode == "replay"
    assert "status: REPLAYED" in project.text


def test_replay_runs_up_to_date_steps_too(project):
    module = _module(project)
    project.run(f"analysis/{module}")
    project.replay(f"analysis/{module}")
    assert len(_ledger.runs_of(project.root / "results/01_m/provenance/runs", "01_write")) == 2


def test_replay_needs_exactly_one_validate_step(project):
    module = project.new("m")
    project.step(module, "01_write.py", WRITE.replace("VALUE", "1"))
    assert project.replay(f"analysis/{module}") == 2
    assert "exactly one validate step" in project.text
    project.step(module, "02_validate.py", VALIDATE)
    project.step(module, "03_validate.py", VALIDATE)
    assert project.replay(f"analysis/{module}") == 2


def test_replay_refuses_another_interpreter_unless_told_why(project):
    module = _module(project)
    project.run(f"analysis/{module}")
    path = project.root / "results/01_m/provenance/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["interpreter"] = {"path": "/other/bin/python", "prefix": "/other", "version": "3.0", "overlay": None}
    path.write_text(json.dumps(manifest))
    assert project.replay(f"analysis/{module}") == 2
    assert "--new-interpreter" in project.text
    assert project.replay(f"analysis/{module}", new_interpreter="moved to the overlay with scvi") == 0
    replay = project.manifest(module)["replay"]
    assert replay["new_interpreter_reason"] == "moved to the overlay with scvi"
    assert replay["interpreter"] == sys.executable


def test_replay_stops_at_the_first_failure(project):
    module = project.new("m")
    project.step(module, "01_boom.py", "# %%\nraise RuntimeError('broken')\n")
    project.step(module, "02_later.py", "# %%\nx = 1\n")
    project.step(module, "03_validate.py", "# %%\nx = 2\n")
    assert project.replay(f"analysis/{module}") == 1
    assert "replay stopped; not run: 02_later.py, 03_validate.py" in project.text
    manifest = project.manifest(module)
    assert manifest["replay"]["status"] == "failed" and manifest["status"] == "draft"


def test_changed_and_orphan_outputs_are_reported_not_deleted(project):
    module = _module(project)
    project.run(f"analysis/{module}")
    stray = project.root / "results/01_m/figures/old.png"
    stray.write_bytes(b"old")
    project.step(module, "01_write.py", WRITE.replace("VALUE", "2"))
    assert project.replay(f"analysis/{module}") == 0
    replay = project.manifest(module)["replay"]
    assert replay["changed_outputs"] == ["tables/a.json"]
    assert replay["orphan_outputs"] == ["figures/old.png"]
    assert stray.exists()
    assert "orphan outputs" in project.text


def test_run_cli_outputs_are_not_orphans(project, skills_tree):
    module = project.new("m")
    project.step(module, "01_cli.py", "# %%\nfrom skills._sdk.notebook import run_cli\nrun_cli('sc-clustering')\n")
    project.step(module, "02_validate.py", "# %%\nx = 1\n")
    assert project.replay(f"analysis/{module}") == 0, project.text
    replay = project.manifest(module)["replay"]
    assert replay["orphan_outputs"] == []
    outputs = {o["path"] for o in project.manifest(module)["steps"][0]["outputs"]}
    assert outputs == {"intermediate/sc-clustering/result.json", "intermediate/sc-clustering/tables/clusters.csv"}


def test_editing_a_step_after_replay_returns_the_module_to_draft(project):
    module = _module(project)
    project.replay(f"analysis/{module}")
    assert project.manifest(module)["status"] == "replayed"
    project.step(module, "01_write.py", WRITE.replace("VALUE", "3"))
    assert "01_m  DRAFT" in project.status()
    project.run(f"analysis/{module}")
    assert project.manifest(module)["status"] == "draft"


def test_replay_takes_a_module_not_a_step(project):
    module = _module(project)
    assert project.replay(f"analysis/{module}/01_write.py") == 2
