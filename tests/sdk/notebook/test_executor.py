"""The step runner's ``new``, ``run`` and ``status``, driven with an in-process runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from skills._sdk.notebook import _executor, _ledger, _manifest
from skills._sdk.notebook._layout import module_from_name
from skills._sdk.notebook._lock import hold

REPO = Path(__file__).resolve().parents[3]
RUN = REPO / "skills" / "_sdk" / "notebook" / "run.py"

WRITE_A = '''
# %% [markdown]
# Writes a table.

# %%
from skills._sdk.notebook import write_output
write_output({"value": VALUE}, "intermediate/a.json")
'''

READ_A = '''
# %%
from skills._sdk.notebook import read_input, write_output
a = read_input("results/01_first/intermediate/a.json")
write_output({"double": a["value"] * 2}, "tables/b.json")
'''


def _two_steps(project, value=1):
    module = project.new("first")
    project.step(module, "01_write.py", WRITE_A.replace("VALUE", str(value)))
    project.step(module, "02_read.py", READ_A)
    return module


def _runs(project, module, stem):
    """Ledger files of one step, oldest run first."""
    return [r.path for r in _ledger.runs_of(project.root / "results" / module / "provenance" / "runs", stem)]


def test_run_executes_never_run_steps_in_order(project):
    module = _two_steps(project)
    assert project.run(f"analysis/{module}") == 0
    assert "[01_first] 01_write.py  ok" in project.text
    assert "why:      never run" in project.text
    assert json.loads((project.root / "results/01_first/tables/b.json").read_text()) == {"double": 2}
    manifest = json.loads((project.root / "results/01_first/provenance/manifest.json").read_text())
    assert [s["state"] for s in manifest["steps"]] == ["ok", "ok"]
    assert manifest["steps"][1]["inputs"][0]["path"] == "results/01_first/intermediate/a.json"


def test_an_up_to_date_step_is_skipped(project):
    module = _two_steps(project)
    project.run(f"analysis/{module}")
    assert project.run(f"analysis/{module}") == 0
    assert "01_write.py  up to date" in project.text
    assert len(_runs(project, module, "01_write")) == 1


def test_force_runs_an_up_to_date_step(project):
    module = _two_steps(project)
    project.run(f"analysis/{module}")
    assert project.run(f"analysis/{module}/01_write.py", force=True) == 0
    assert "why:      forced" in project.text
    assert len(_runs(project, module, "01_write")) == 2


def test_a_step_file_target_runs_only_that_step(project):
    module = _two_steps(project)
    assert project.run(f"analysis/{module}/01_write.py") == 0
    assert "02_read.py" not in project.text
    assert _runs(project, module, "02_read") == []


def test_a_changed_step_is_stale_with_reason(project):
    module = _two_steps(project)
    project.run(f"analysis/{module}")
    project.step(module, "02_read.py", READ_A + "\nprint('changed')\n")
    assert "02_read.py  stale: step changed" in project.status()
    project.run(f"analysis/{module}")
    assert "why:      step changed" in project.text


def test_a_changed_input_makes_the_reader_rerun_in_the_same_run(project):
    module = _two_steps(project)
    project.run(f"analysis/{module}")
    project.step(module, "01_write.py", WRITE_A.replace("VALUE", "5"))
    project.run(f"analysis/{module}")
    assert "02_read.py  ok" in project.text
    assert "why:      input changed: results/01_first/intermediate/a.json" in project.text
    assert json.loads((project.root / "results/01_first/tables/b.json").read_text()) == {"double": 10}


def test_a_missing_input_is_a_reason(project):
    module = _two_steps(project)
    project.run(f"analysis/{module}")
    (project.root / "results/01_first/intermediate/a.json").unlink()
    assert "02_read.py  stale: input missing: results/01_first/intermediate/a.json" in project.status()


def test_a_failed_step_stops_the_run_and_stays_failed(project):
    module = project.new("first")
    project.step(module, "01_boom.py", "# %%\nraise ValueError('nope')\n")
    project.step(module, "02_after.py", "# %%\nx = 1\n")
    assert project.run(f"analysis/{module}") == 1
    assert "error:    cell 1: ValueError: nope" in project.text
    assert "stopped; not run: 02_after.py" in project.text
    assert "01_boom.py  failed: last run failed" in project.status()


def test_upstream_change_marks_the_downstream_module_stale(project):
    first = _two_steps(project)
    project.run(f"analysis/{first}")
    second = project.new("second")
    project.step(second, "01_use.py", READ_A)
    project.run(f"analysis/{second}")
    project.step(first, "01_write.py", WRITE_A.replace("VALUE", "7"))
    project.run(f"analysis/{first}")
    status = project.status()
    assert "02_second  DRAFT" in status
    assert "01_use.py  stale: input changed: results/01_first/intermediate/a.json" in status


def test_the_manifest_is_written_atomically_and_lists_skills(project, skills_tree):
    module = project.new("first")
    project.step(module, "01_cluster.py", '''
        # %%
        from skills._sdk.notebook import load_skill, write_output
        clustering = load_skill("sc-clustering")
        data = clustering.cluster({"cells": [1, 2, 3]}, resolution=0.5)
        write_output(clustering.cluster_summary(data), "tables/counts.json")
    ''')
    assert project.run(f"analysis/{module}") == 0, project.text
    assert "skills:   sc-clustering.cluster(data=dict, resolution=0.5)" in project.text
    provenance = project.root / "results/01_first/provenance"
    assert [p.name for p in provenance.iterdir() if p.name.endswith(".tmp")] == []
    manifest = json.loads((provenance / "manifest.json").read_text())
    entry = manifest["steps"][0]["skills"][0]
    assert entry["skill"] == "sc-clustering"
    assert entry["functions"] == ["cluster", "cluster_summary"]
    assert "sc-clustering.cluster, sc-clustering.cluster_summary" in project.status()


def test_an_interpreter_change_warns_and_is_recorded(project):
    module = _two_steps(project)
    project.run(f"analysis/{module}")
    manifest_path = project.root / "results/01_first/provenance/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["interpreter"] = {"path": "/elsewhere/bin/python", "prefix": "/elsewhere", "version": "3.0", "overlay": None}
    manifest_path.write_text(json.dumps(manifest))
    project.run(f"analysis/{module}/01_write.py", force=True)
    assert "warning: module 01_first was run with /elsewhere/bin/python" in project.text
    latest = _runs(project, module, "01_write")[-1]
    start = json.loads(latest.read_text().splitlines()[0])
    assert start["interpreter_changed_from"] == "/elsewhere/bin/python"
    assert json.loads(manifest_path.read_text())["interpreter"]["path"] == sys.executable


def test_a_lowercase_r_file_in_the_module_is_refused(project):
    module = _two_steps(project)
    (project.root / "analysis" / module / "03_plot.r").write_text("x <- 1\n")
    assert project.run(f"analysis/{module}") == 2
    assert "uppercase .R" in project.text


def test_missing_rscript_is_an_actionable_usage_error_for_run_and_replay(project, monkeypatch, tmp_path):
    module = _two_steps(project)
    project.step(module, "03_r.R", "x <- 1\n")
    project.step(module, "04_validate.py", "assert True\n")
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("CONDA_PREFIX", str(tmp_path))
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    for command in (project.run, project.replay):
        assert command(module) == 2
        assert "Rscript not found" in project.text
        assert "CONDA_PREFIX/bin/Rscript" in project.text and "PATH" in project.text


def test_invalid_r_layout_is_reported_before_any_step_runs(project):
    module = _two_steps(project)
    project.step(module, "03_same.py", "raise AssertionError('must not run')\n")
    project.step(module, "03_same.R", "stop('must not run')\n")
    project.step(module, "04_validate.R", "TRUE\n")
    for command in (project.run, project.replay):
        assert command(module) == 2
        assert "same stem" in project.text and "validate step must be Python" in project.text
    assert "same stem" in project.status(module)


def test_a_mixed_module_dispatches_to_the_two_injected_runners(project):
    from skills._sdk.notebook._runners import StepOutcome

    seen = []

    class RecordingRunner:
        def __init__(self, kind):
            self.kind = kind

        def run(self, notebook, *, env, cwd):
            step = Path(env["OMICSCLAW_STEP_FILE"]).name
            seen.append((self.kind, step))
            return StepOutcome(status="ok", notebook=notebook, seconds=0)

    module = project.new("mixed")
    for name in ("01_first.py", "02_model.R", "03_validate.py", "04_plot.R"):
        project.step(module, name, "# %%\n# recorded without execution\n")
    runners = {kind: RecordingRunner(kind) for kind in ("python", "r")}
    assert _executor.run_targets(project.root, [module], runners=runners, out=project.out) == 0
    assert seen == [("python", "01_first.py"), ("r", "02_model.R"), ("r", "04_plot.R"), ("python", "03_validate.py")]
    manifest = project.manifest(module)
    assert [step["kind"] for step in manifest["steps"]] == ["python", "r", "r", "python"]


def test_a_busy_module_lock_exits_3(project):
    module = _two_steps(project)
    lock = project.root / "results" / module / "provenance" / ".lock"
    code = (
        "import sys, time\n"
        f"sys.path.insert(0, {str(REPO)!r})\n"
        "from skills._sdk.notebook._lock import hold\n"
        f"with hold({str(lock)!r}, command='run'):\n"
        "    print('held', flush=True)\n"
        "    time.sleep(30)\n"
    )
    holder = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        assert project.run(f"analysis/{module}") == 3
        assert "is busy" in project.text and "command run" in project.text
    finally:
        holder.kill()
        holder.wait()


def test_new_numbers_modules_and_the_project_lock_keeps_numbers_unique(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    procs = [
        subprocess.Popen([sys.executable, str(RUN), "new", f"m{i}"], cwd=root, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for i in range(4)
    ]
    outputs = [p.communicate(timeout=120)[0] for p in procs]
    assert all(p.returncode == 0 for p in procs), outputs
    numbers = sorted(p.name[:2] for p in (root / "analysis").iterdir())
    assert numbers == ["01", "02", "03", "04"]


def test_new_rejects_a_bad_slug(project):
    assert _executor.new_module(project.root, "Bad-Name", out=project.out) == 2


def test_new_rejects_a_slug_that_already_has_a_number(project):
    assert _executor.new_module(project.root, "01_qc", out=project.out) == 2
    assert "`new qc`" in project.text
    assert not (project.root / "analysis").exists()


def test_status_without_modules(project):
    assert "No modules yet" in project.status()


def test_run_writes_step_and_module_notebooks(project):
    import nbformat

    module = _two_steps(project)
    project.run(f"analysis/{module}")
    notebooks = project.root / "results/01_first/notebooks"
    step_nb = nbformat.read(str(notebooks / "01_write.ipynb"), as_version=4)
    assert step_nb.metadata["omicsclaw"]["step"]["file"] == "01_write.py"
    combined = nbformat.read(str(notebooks / "M01_first.ipynb"), as_version=4)
    headers = [c.source for c in combined.cells if c.source.startswith("## Step")]
    assert [h.splitlines()[0] for h in headers] == ["## Step 01_write.py", "## Step 02_read.py"]


def test_overwriting_an_input_does_not_leave_the_step_stale_forever(project):
    module = project.new("first")
    project.step(module, "01_write.py", WRITE_A.replace("VALUE", "1"))
    project.step(module, "02_rewrite.py", '''
        # %%
        from skills._sdk.notebook import read_input, write_output
        a = read_input("results/01_first/intermediate/a.json")
        write_output({"value": a["value"] + 1}, "intermediate/a.json")
    ''')
    project.run(f"analysis/{module}")
    assert "overwrote a file it read" in project.text
    project.run(f"analysis/{module}")
    assert "02_rewrite.py  up to date" in project.text


REWRITE_A = '''
# %%
from skills._sdk.notebook import read_input, write_output
a = read_input("results/01_first/intermediate/a.json")
write_output({"value": a["value"] + 1}, "intermediate/a.json")
'''


def test_a_step_that_overwrote_its_input_reruns_when_an_earlier_step_rewrites_it(project):
    module = project.new("first")
    first = project.step(module, "01_write.py", WRITE_A.replace("VALUE", "1"))
    project.step(module, "02_rewrite.py", REWRITE_A)
    project.run(f"analysis/{module}")
    a_json = project.root / "results/01_first/intermediate/a.json"
    assert json.loads(a_json.read_text()) == {"value": 2}
    first.write_text(first.read_text().replace('{"value": 1}', '{"value": 5}'))
    assert project.run(f"analysis/{module}") == 0
    assert "02_rewrite.py  up to date" not in project.text
    assert "why:      input changed: results/01_first/intermediate/a.json" in project.text
    assert json.loads(a_json.read_text()) == {"value": 6}
    project.run(f"analysis/{module}")
    assert "01_write.py  up to date" in project.text and "02_rewrite.py  up to date" in project.text


def test_a_step_that_overwrote_its_input_is_stale_when_the_file_is_changed_by_hand(project):
    module = project.new("first")
    project.step(module, "01_write.py", WRITE_A.replace("VALUE", "1"))
    project.step(module, "02_rewrite.py", REWRITE_A)
    project.run(f"analysis/{module}")
    (project.root / "results/01_first/intermediate/a.json").write_text('{"value": 40}')
    states = {s["file"]: s for s in project.manifest(module)["steps"]}
    assert states["02_rewrite.py"]["state"] == "ok"
    assert "02_rewrite.py  stale: input changed: results/01_first/intermediate/a.json" in project.status()


def test_frozen_module_refuses_run(project):
    module = _two_steps(project)
    project.run(f"analysis/{module}")
    mod = module_from_name(project.root, module)
    manifest = _manifest.load(mod)
    manifest["frozen"] = True
    _manifest.save(mod, manifest)
    assert project.run(f"analysis/{module}") == 2
    assert "accepted and frozen" in project.text


def _freeze_while_holding_the_lock(project, module, command="accept"):
    """Hold the module lock in a thread, freeze the module, then let go."""
    mod = module_from_name(project.root, module)
    held = threading.Event()

    def holder():
        with hold(mod.lock_path, command=command):
            held.set()
            manifest = _manifest.load(mod)
            manifest["frozen"] = True
            _manifest.save(mod, manifest)
            time.sleep(0.5)

    thread = threading.Thread(target=holder)
    thread.start()
    held.wait(5)
    return thread


def test_a_run_that_waited_for_the_lock_refuses_a_module_frozen_meanwhile(project):
    module = _two_steps(project)
    project.run(f"analysis/{module}")
    project.step(module, "02_read.py", READ_A + "\nprint('changed')\n")
    before = len(_runs(project, module, "02_read"))
    thread = _freeze_while_holding_the_lock(project, module)
    project.lines.clear()
    code = _executor.run_targets(project.root, [f"analysis/{module}"], runner=project.runner, wait=10,
                                 out=project.out)
    thread.join()
    assert code == 2 and "accepted and frozen" in project.text
    assert len(_runs(project, module, "02_read")) == before


def test_a_replay_that_waited_for_the_lock_refuses_a_module_frozen_meanwhile(project):
    module = _two_steps(project)
    project.step(module, "03_validate.py", "# %%\nx = 1\n")
    project.run(f"analysis/{module}")
    before = len(_runs(project, module, "01_write"))
    thread = _freeze_while_holding_the_lock(project, module)
    project.lines.clear()
    code = _executor.replay(project.root, f"analysis/{module}", runner=project.runner, wait=10, out=project.out)
    thread.join()
    assert code == 2 and "accepted and frozen" in project.text
    assert len(_runs(project, module, "01_write")) == before


def test_a_step_that_cannot_be_parsed_leaves_no_old_notebook_behind(project):
    import nbformat

    module = _two_steps(project)
    project.run(f"analysis/{module}")
    notebook = project.root / "results/01_first/notebooks/02_read.ipynb"
    assert notebook.is_file()
    project.step(module, "02_read.py", READ_A + "\n%time print(a)\n")
    assert project.run(f"analysis/{module}") == 1
    assert "PercentError" in project.text
    assert "notebook: none (no cell ran)" in project.text and "(partial)" not in project.text
    assert not notebook.exists()
    combined = nbformat.read(str(project.root / "results/01_first/notebooks/M01_first.ipynb"), as_version=4)
    sources = "\n".join(cell.source for cell in combined.cells)
    assert "stopped before any cell ran" in sources
    assert 'read_input("results/01_first/intermediate/a.json")' not in sources


def test_a_step_that_is_not_utf8_fails_with_a_clear_error_and_a_finished_ledger(project):
    module = project.new("first")
    (project.root / "analysis" / module / "01_latin.py").write_bytes(b"# %%\nname = 'Andr\xe9'\n")
    assert project.run(f"analysis/{module}") == 1
    assert "UnicodeDecodeError: 01_latin.py is not UTF-8 text" in project.text
    run = _ledger.runs_of(project.root / "results/01_first/provenance/runs", "01_latin")[-1]
    assert run.status == "failed" and run.end["error"]["ename"] == "UnicodeDecodeError"
    assert project.manifest(module)["steps"][0]["state"] == "failed"


def test_an_interpreter_change_is_repeated_at_the_end_of_the_output(project):
    module = _two_steps(project)
    project.run(f"analysis/{module}")
    mod = module_from_name(project.root, module)
    manifest = _manifest.load(mod)
    manifest["interpreter"] = {"path": "/other/bin/python", "prefix": "/other", "version": "3.0", "overlay": None}
    _manifest.save(mod, manifest)
    assert project.run(f"analysis/{module}", force=True) == 0
    warning = f"warning: module {module} was run with /other/bin/python; this run uses {sys.executable}"
    assert project.lines[0] == warning and project.lines[-1] == warning


def test_the_lock_records_its_holder(tmp_path):
    lock = tmp_path / "x.lock"
    with hold(lock, command="replay"):
        holder = json.loads(lock.read_text())
        assert holder["command"] == "replay" and holder["pid"] == os.getpid()
