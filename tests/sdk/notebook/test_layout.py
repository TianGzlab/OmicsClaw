"""Project layout: names, step order, the skeleton ``new`` fills in."""

from __future__ import annotations

import pytest

from skills._sdk.notebook import _executor, _layout
from skills._sdk.notebook._layout import LayoutError, Module, resolve_target


@pytest.mark.parametrize("name", ["01_qc", "03_clustering", "12_de_by_sample"])
def test_valid_module_names(name):
    assert _layout.parse_module_name(name)[1] == name[3:]


@pytest.mark.parametrize("name", ["1_qc", "01-qc", "01_QC", "01_", "qc"])
def test_invalid_module_names(name):
    with pytest.raises(LayoutError):
        _layout.parse_module_name(name)


def test_steps_run_by_name_with_variants_and_validate_last(tmp_path):
    module = Module(root=tmp_path, number=3, slug="clustering")
    module.analysis_dir.mkdir(parents=True)
    for name in ("02b_louvain.py", "01_load.py", "03_validate.py", "02a_leiden.py", "notes.py", "README.md", "04_plot.py"):
        (module.analysis_dir / name).write_text("")
    assert [p.name for p in module.steps()] == [
        "01_load.py", "02a_leiden.py", "02b_louvain.py", "04_plot.py", "03_validate.py",
    ]
    assert [p.name for p in module.validate_steps()] == ["03_validate.py"]
    assert [p.name for p in module.ignored_files()] == ["notes.py"]


def test_resolve_target_accepts_module_dirs_step_files_and_bare_names(tmp_path):
    (tmp_path / "analysis" / "03_clustering").mkdir(parents=True)
    assert resolve_target(tmp_path, "analysis/03_clustering")[0].name == "03_clustering"
    assert resolve_target(tmp_path, "analysis/03_clustering/")[1] is None
    module, step = resolve_target(tmp_path, "analysis/03_clustering/02_cluster.py")
    assert step.name == "02_cluster.py"
    assert resolve_target(tmp_path, "03_clustering")[0].number == 3
    with pytest.raises(LayoutError, match="not a step name"):
        resolve_target(tmp_path, "analysis/03_clustering/cluster.py")
    with pytest.raises(LayoutError):
        resolve_target(tmp_path, "data/x.h5ad")


def _snapshot(root):
    return {
        p.relative_to(root).as_posix(): (p.read_bytes() if p.is_file() else None)
        for p in sorted(root.rglob("*"))
    }


def test_the_first_new_only_adds_what_is_missing(tmp_path):
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    (root / "data" / "cells.h5ad").write_bytes(b"cells")
    (root / "scripts").mkdir()
    (root / "scripts" / "mine.sh").write_text("echo mine\n")
    (root / "notes.txt").write_text("my notes\n")
    (root / "docs" / "analysis_strategy").mkdir(parents=True)
    (root / "docs" / "analysis_strategy" / "STRATEGY.md").write_text("# Mine\n")
    before = _snapshot(root)
    lines = []
    assert _executor.new_module(root, "qc", out=lines.append) == 0
    after = _snapshot(root)
    for path, content in before.items():
        assert after[path] == content, path
    assert (root / "analysis/01_qc/README.md").is_file()
    for folder in ("figures", "tables", "intermediate", "logs", "notebooks", "provenance", "reviews", "baseline"):
        assert (root / "results/01_qc" / folder).is_dir()
    for folder in ("results/_archive", "manifests", "work"):
        assert (root / folder).is_dir()
    assert not (root / "PROJECT.md").exists() and not (root / "METHODS_LEDGER.md").exists()


def test_new_writes_the_strategy_template_when_missing(tmp_path):
    lines = []
    _executor.new_module(tmp_path, "qc", out=lines.append)
    text = (tmp_path / "docs/analysis_strategy/STRATEGY.md").read_text()
    for heading in ("## Question", "## Data", "## Plan", "## Decisions"):
        assert heading in text
    readme = (tmp_path / "analysis/01_qc/README.md").read_text()
    assert readme.startswith("# 01_qc")
    assert str(_layout.CHECKOUT) in readme


def test_new_in_a_checkout_warns_and_leaves_its_files_alone(tmp_path):
    (tmp_path / "skills" / "_sdk").mkdir(parents=True)
    (tmp_path / "skills" / "_sdk" / "__init__.py").write_text("")
    (tmp_path / "omicsclaw").mkdir()
    (tmp_path / ".gitignore").write_text("data/*\n")
    lines = []
    assert _executor.new_module(tmp_path, "qc", out=lines.append) == 0
    assert any("inside an OmicsClaw checkout" in line for line in lines)
    assert (tmp_path / ".gitignore").read_text() == "data/*\n"


def test_the_repository_ignores_a_project_opened_in_the_checkout():
    ignored = set((_layout.CHECKOUT / ".gitignore").read_text().splitlines())
    assert {"/analysis/", "/results/", "/manifests/", "/work/", "/docs/analysis_strategy/"} <= ignored


def test_numbers_continue_after_the_highest_existing_module(tmp_path):
    (tmp_path / "results" / "04_old").mkdir(parents=True)
    lines = []
    _executor.new_module(tmp_path, "next", out=lines.append)
    assert (tmp_path / "analysis" / "05_next").is_dir()
