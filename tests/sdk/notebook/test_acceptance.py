"""``accept`` and ``revise``: the four conditions, freezing, and baseline snapshots."""

from __future__ import annotations

import os
import time

import pytest

from skills._sdk.notebook import _acceptance, _layout
from skills._sdk.report import DISCLAIMER

WRITE = '''
# %%
from skills._sdk.notebook import write_output
write_output({"value": 1}, "tables/a.json")
'''
VALIDATE = "# %%\nx = 1\n"


def _replayed(project):
    module = project.new("m")
    project.step(module, "01_write.py", WRITE)
    project.step(module, "02_validate.py", VALIDATE)
    assert project.replay(f"analysis/{module}") == 0, project.text
    return module


def _report(project, module, text=None):
    path = project.root / "results" / module / "M01_m_REPORT.md"
    path.write_text(text if text is not None else f"# Module 01\n\nValue 1 (tables/a.json).\n\n{DISCLAIMER}\n")
    return path


def _review(project, module, verdict="APPROVE", name="2026-10-01_review.md"):
    path = project.root / "results" / module / "reviews" / name
    time.sleep(0.01)
    path.write_text(f"VERDICT: {verdict}\n\nNo findings.\n")
    later = time.time() + 1
    os.utime(path, (later, later))
    return f"results/{module}/reviews/{name}"


def test_accept_with_an_approving_review_freezes_the_module(project):
    module = _replayed(project)
    _report(project, module)
    review = _review(project, module)
    assert project.manifest(module)["status"] == "replayed"
    assert "01_m  REVIEWED" in project.status()
    assert project.accept(f"analysis/{module}", review=review) == 0, project.text
    manifest = project.manifest(module)
    assert manifest["status"] == "accepted" and manifest["frozen"] is True
    assert manifest["accepted"]["review"] == "reviews/2026-10-01_review.md"
    assert manifest["review"] == {"file": "reviews/2026-10-01_review.md", "verdict": "APPROVE"}
    assert "01_m  ACCEPTED" in project.status()


def test_skip_review_records_the_users_words(project):
    module = _replayed(project)
    _report(project, module)
    assert project.accept(f"analysis/{module}", skip_review="Skip the review, I checked it myself.") == 0
    assert project.manifest(module)["accepted"]["skip_review"] == "Skip the review, I checked it myself."


def test_missing_readme_is_refused(project):
    module = _replayed(project)
    _report(project, module)
    (project.root / "analysis" / module / "README.md").unlink()
    assert project.accept(f"analysis/{module}", skip_review="ok") == 4
    assert "README.md is missing" in project.text


def test_a_module_that_was_never_replayed_is_refused(project):
    module = project.new("m")
    project.step(module, "01_write.py", WRITE)
    project.step(module, "02_validate.py", VALIDATE)
    project.run(f"analysis/{module}")
    _report(project, module)
    assert project.accept(f"analysis/{module}", skip_review="ok") == 4
    assert "has not been replayed" in project.text


def test_a_step_changed_after_the_replay_is_refused(project):
    module = _replayed(project)
    _report(project, module)
    project.step(module, "01_write.py", WRITE + "\nprint(1)\n")
    assert project.accept(f"analysis/{module}", skip_review="ok") == 4
    assert "changed since the latest replay" in project.text


def test_a_report_without_the_disclaimer_is_refused(project):
    module = _replayed(project)
    _report(project, module, "# Module 01\n\nNo disclaimer.\n")
    assert project.accept(f"analysis/{module}", skip_review="ok") == 4
    assert "disclaimer" in project.text


def test_a_missing_report_is_refused(project):
    module = _replayed(project)
    assert project.accept(f"analysis/{module}", skip_review="ok") == 4
    assert "M01_m_REPORT.md is missing" in project.text


def test_a_disclaimer_wrapped_over_lines_counts(project):
    module = _replayed(project)
    wrapped = DISCLAIMER.replace(" It is", "\nIt is")
    _report(project, module, f"# R\n\n{wrapped}\n")
    assert project.accept(f"analysis/{module}", skip_review="ok") == 0


@pytest.mark.parametrize("verdict", ["REVISE", "MAYBE"])
def test_a_review_that_does_not_approve_is_refused(project, verdict):
    module = _replayed(project)
    _report(project, module)
    review = _review(project, module, verdict=verdict)
    assert project.accept(f"analysis/{module}", review=review) == 4
    assert "VERDICT: APPROVE" in project.text


def test_a_review_older_than_the_replay_is_refused(project):
    module = _replayed(project)
    _report(project, module)
    review = _review(project, module)
    old = time.time() - 3600
    os.utime(project.root / review, (old, old))
    assert project.accept(f"analysis/{module}", review=review) == 4
    assert "older than the latest replay" in project.text


def test_an_archived_review_is_refused(project):
    module = _replayed(project)
    _report(project, module)
    _review(project, module)
    assert project.replay(f"analysis/{module}") == 0, project.text
    [archived] = project.manifest(module)["review_history"]
    assert project.accept(f"analysis/{module}", review=f"results/{module}/{archived['file']}") == 4
    assert "archived by a later replay" in project.text


def test_a_review_outside_reviews_is_refused(project):
    module = _replayed(project)
    _report(project, module)
    (project.root / "work").mkdir(exist_ok=True)
    (project.root / "work" / "r.md").write_text("VERDICT: APPROVE\n")
    assert project.accept(f"analysis/{module}", review="work/r.md") == 4
    assert "reviews/" in project.text


def test_all_missing_conditions_are_listed_together(project):
    module = project.new("m")
    (project.root / "analysis" / module / "README.md").unlink()
    assert project.accept(f"analysis/{module}", skip_review="ok") == 4
    assert sum(line.startswith("  - ") for line in project.lines) == 3


def test_a_frozen_module_refuses_write_run_and_replay(project, monkeypatch):
    from skills._sdk.notebook import write_output

    module = _replayed(project)
    _report(project, module)
    project.accept(f"analysis/{module}", skip_review="ok")
    assert project.run(f"analysis/{module}", force=True) == 2
    assert "frozen" in project.text
    assert project.replay(f"analysis/{module}") == 2
    step = project.root / "analysis" / module / "01_write.py"
    monkeypatch.setenv("OMICSCLAW_STEP_FILE", str(step))
    monkeypatch.delenv("OMICSCLAW_STEP_LEDGER", raising=False)
    with pytest.raises(RuntimeError, match="revise"):
        write_output({}, "tables/x.json")


def test_revise_snapshots_and_unfreezes(project, monkeypatch):
    module = _replayed(project)
    _report(project, module)
    project.accept(f"analysis/{module}", skip_review="ok")
    big = project.root / "results" / module / "intermediate" / "big.bin"
    big.write_bytes(b"x" * 4096)
    monkeypatch.setattr(_acceptance, "LARGE_FILE_BYTES", 2048)
    assert project.revise(f"analysis/{module}") == 0, project.text
    baseline = project.root / "results" / module / "baseline" / f"{_layout.today()}_pre_revision"
    assert (baseline / "results" / "tables" / "a.json").is_file()
    assert (baseline / "results" / "M01_m_REPORT.md").is_file()
    assert (baseline / "analysis" / "01_write.py").read_text() == (project.root / "analysis" / module / "01_write.py").read_text()
    assert not (baseline / "results" / "intermediate" / "big.bin").exists()
    assert "intermediate/big.bin  4096" in (baseline / "LARGE_FILES.sha256").read_text()
    manifest = project.manifest(module)
    assert manifest["frozen"] is False and manifest["status"] == "draft"
    assert manifest["revisions"][0]["baseline"] == f"baseline/{_layout.today()}_pre_revision"
    assert "01_m  DRAFT (revising)" in project.status()


def test_a_revision_follows_its_accepted_review_into_the_archive(project):
    module = _replayed(project)
    _report(project, module)
    review = _review(project, module)
    assert project.accept(f"analysis/{module}", review=review) == 0, project.text
    project.revise(f"analysis/{module}")
    assert project.manifest(module)["revisions"][0]["accepted"]["review"] == "reviews/2026-10-01_review.md"
    assert project.replay(f"analysis/{module}") == 0, project.text
    manifest = project.manifest(module)
    moved = manifest["revisions"][0]["accepted"]["review"]
    assert moved.startswith("reviews/archive/") and moved.endswith("/2026-10-01_review.md")
    assert (project.root / "results" / module / moved).is_file()
    assert manifest["review_history"][0]["original"] == "reviews/2026-10-01_review.md"


def test_a_second_revise_on_the_same_day_gets_its_own_baseline(project):
    module = _replayed(project)
    _report(project, module)
    project.accept(f"analysis/{module}", skip_review="ok")
    project.revise(f"analysis/{module}")
    assert project.replay(f"analysis/{module}") == 0
    project.accept(f"analysis/{module}", skip_review="ok again")
    project.revise(f"analysis/{module}")
    names = sorted(p.name for p in (project.root / "results" / module / "baseline").iterdir())
    assert names == [f"{_layout.today()}_pre_revision", f"{_layout.today()}_pre_revision-2"]
    second = project.root / "results" / module / "baseline" / names[1]
    assert not (second / "results" / "baseline").exists()


def test_revise_needs_an_accepted_module(project):
    module = _replayed(project)
    assert project.revise(f"analysis/{module}") == 2
