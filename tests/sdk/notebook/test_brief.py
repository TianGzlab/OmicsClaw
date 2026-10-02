"""The review brief a successful ``replay`` writes for the module reviewer."""

from __future__ import annotations

import os
from pathlib import Path

from skills._sdk.notebook import _brief, checks

STEP = '''
# %% [markdown]
# Cluster the cells.
# Calls sc-clustering: FIRST_CELL_NAMES.

# %%
from skills._sdk.notebook import load_skill, read_input, write_output
clustering = load_skill("sc-clustering")
data = clustering.cluster(read_input("data/cells.json"), resolution=0.5)
counts = clustering.cluster_summary(data)
write_output("cluster,n_cells\\n" + "".join(f"{k},{v}\\n" for k, v in counts.items()), "tables/summary.csv",
             writer=lambda text, path: path.write_text(text))
write_output("g,score\\n" + "".join(f"g{i},{i / 10}\\n" for i in range(30)), "tables/big.csv",
             writer=lambda text, path: path.write_text(text))
write_output({"method": "leiden", "n": len(counts)}, "tables/info.json")
write_output(b"\\x89PNG", "figures/plot.png", writer=lambda data, path: path.write_bytes(data))
write_output(b"\\x89HDF", "intermediate/cells.h5ad", writer=lambda data, path: path.write_bytes(data))
print("clustered", len(data["cells"]), "cells")
'''

VALIDATE = '''
# %%
from skills._sdk.notebook import read_input
assert len(read_input("results/01_clu/tables/summary.csv")) == 2
'''


def _module(project, skills_tree, names="cluster, cluster_summary"):
    (project.root / "data").mkdir(exist_ok=True)
    (project.root / "data" / "cells.json").write_text('{"cells": ["a", "b", "c"]}')
    module = project.new("clu")
    project.step(module, "01_cluster.py", STEP.replace("FIRST_CELL_NAMES", names))
    project.step(module, "02_validate.py", VALIDATE)
    return module


def _brief_text(project, module):
    return (project.root / "results" / module / "provenance" / "review_brief.md").read_text()


def test_a_successful_replay_writes_the_brief(project, skills_tree):
    module = _module(project, skills_tree)
    assert project.replay(f"analysis/{module}") == 0, project.text
    assert "  review brief: results/01_clu/provenance/review_brief.md" in project.lines
    text = _brief_text(project, module)
    assert text.startswith("# Review brief: 01_clu\n")
    assert "status ok · 2 steps, validate last (02_validate.py)" in text
    assert "> Calls sc-clustering: cluster, cluster_summary." in text
    assert "Recorded calls: sc-clustering.cluster(data=dict, resolution=0.5); sc-clustering.cluster_summary(data=dict)" in text
    assert "recorded but not named: none; named but not recorded: none" in text
    assert "Read: data/cells.json (" in text and "via read_input" in text
    assert "Wrote: tables/summary.csv (" in text
    assert "    clustered 3 cells" in text


def test_tables_come_whole_when_small_and_as_a_head_when_not(project, skills_tree):
    module = _module(project, skills_tree)
    project.replay(f"analysis/{module}")
    text = _brief_text(project, module)
    assert "### tables/summary.csv  2 rows x 2 columns" in text and ", whole table\ncluster,n_cells\n0,2\n1,1\n" in text
    assert "### tables/big.csv  30 rows x 2 columns" in text and "first 5 rows\ng,score\ng0,0.0\n" in text
    assert "g5,0.5" not in text
    assert "### tables/info.json  JSON" in text and '"method": "leiden"' in text
    tables = text[text.index("## Tables"):text.index("## Output files")]
    assert "cells.h5ad" not in tables and "plot.png" not in tables
    inventory = text[text.index("## Output files"):]
    assert "| figures/plot.png | 4 |" in inventory and "| intermediate/cells.h5ad | 4 |" in inventory


def test_the_word_match_flags_both_directions(project, skills_tree):
    module = _module(project, skills_tree, names="cluster_summary, auto_resolution")
    project.replay(f"analysis/{module}")
    text = _brief_text(project, module)
    assert "recorded but not named: sc-clustering.cluster; named but not recorded: none" in text


def test_a_named_library_function_that_was_not_called_is_flagged(project, skills_tree):
    module = _module(project, skills_tree)
    step = project.root / "analysis" / module / "01_cluster.py"
    step.write_text(step.read_text().replace("counts = clustering.cluster_summary(data)",
                                             "counts = {'0': 2, '1': 1}"))
    project.replay(f"analysis/{module}")
    text = _brief_text(project, module)
    assert "named but not recorded: sc-clustering.cluster_summary" in text


def test_a_failed_replay_leaves_no_brief(project, skills_tree):
    module = _module(project, skills_tree)
    assert project.replay(f"analysis/{module}") == 0
    project.step(module, "02_validate.py", "# %%\nassert False, 'broken'\n")
    assert project.replay(f"analysis/{module}") == 1
    assert not (project.root / "results" / module / "provenance" / "review_brief.md").exists()


def test_orphan_outputs_are_marked(project, skills_tree):
    module = _module(project, skills_tree)
    project.replay(f"analysis/{module}")
    (project.root / "results" / module / "tables" / "stale.csv").write_text("a\n1\n")
    assert project.replay(f"analysis/{module}") == 0
    text = _brief_text(project, module)
    assert "orphan outputs: tables/stale.csv" in text
    assert "| tables/stale.csv | 4 | orphan |" in text


def test_a_big_module_is_shortened_to_fit(project, skills_tree):
    module = _module(project, skills_tree)
    many = "# %%\nfrom skills._sdk.notebook import write_output\n" + "".join(
        f"write_output('x,y\\n' + ''.join(f'{{i}},{{i}}\\n' for i in range(30)), 'tables/t{n:02d}.csv', "
        "writer=lambda text, path: path.write_text(text))\n"
        for n in range(60)
    )
    project.step(module, "01b_many.py", many)
    assert project.replay(f"analysis/{module}") == 0, project.text
    text = _brief_text(project, module)
    assert len(text.splitlines()) <= _brief.MAX_LINES
    assert "Shortened to fit" in text
    assert "### tables/t59.csv  30 rows x 2 columns" in text


def test_the_brief_is_written_through_a_temporary_file_and_renamed(project, skills_tree, monkeypatch):
    module = _module(project, skills_tree)
    brief = project.root / "results" / module / "provenance" / "review_brief.md"
    renames = []
    real_replace = os.replace

    def spy(source, target, *args, **kwargs):
        if Path(target) == brief:
            renames.append((Path(source), Path(source).read_text()))
        return real_replace(source, target, *args, **kwargs)

    monkeypatch.setattr(_brief.os, "replace", spy)
    assert project.replay(f"analysis/{module}") == 0
    assert len(renames) == 1
    source, text = renames[0]
    assert source.parent == brief.parent and source.name.startswith(".review_brief.md.")
    assert text == brief.read_text()
    assert list(brief.parent.glob(".review_brief.md.*")) == []


def test_running_a_step_after_the_replay_drops_the_brief(project, skills_tree):
    module = _module(project, skills_tree)
    assert project.replay(f"analysis/{module}") == 0
    brief = project.root / "results" / module / "provenance" / "review_brief.md"
    assert brief.exists()
    step = project.root / "analysis" / module / "01_cluster.py"
    step.write_text(step.read_text().replace("resolution=0.5", "resolution=0.6"))
    assert project.run(f"analysis/{module}") == 0
    assert not brief.exists()
    assert project.manifest(module)["status"] == "draft"


def test_a_run_with_nothing_to_do_keeps_the_brief(project, skills_tree):
    module = _module(project, skills_tree)
    project.replay(f"analysis/{module}")
    assert project.run(f"analysis/{module}") == 0
    assert (project.root / "results" / module / "provenance" / "review_brief.md").exists()


CHECKED_VALIDATE = '''
# %%
from skills._sdk.notebook import read_input
from skills._sdk.notebook import checks as c
from skills._sdk.notebook.checks import check_files, check_rows as rows, as_labels

summary = read_input("results/01_clu/tables/summary.csv")
rows(summary, exactly=2)
c.check_columns(summary, ["cluster", "n_cells"])
check_files("figures/plot.png")
rows(summary, at_least=1)
'''


def test_the_validate_step_lists_the_checks_it_calls_and_what_each_asserts(project, skills_tree):
    module = _module(project, skills_tree)
    project.step(module, "02_validate.py", CHECKED_VALIDATE)
    assert project.replay(f"analysis/{module}") == 0, project.text
    text = _brief_text(project, module)
    section = text[text.index("### 02_validate.py"):text.index("## Tables")]
    listed = [line.split(":")[0].strip() for line in section.splitlines() if line.startswith("  check_")]
    assert listed == ["check_rows", "check_columns", "check_files"]  # as_labels is imported, never called
    first_line = checks.check_rows.__doc__.strip().splitlines()[0]
    assert f"  check_rows: {first_line}" in section
    cluster = text[text.index("### 01_cluster.py"):text.index("### 02_validate.py")]
    assert "Checks called" not in cluster


def test_a_validate_step_without_checks_says_so(project, skills_tree):
    module = _module(project, skills_tree)
    project.replay(f"analysis/{module}")
    assert "Checks called: none from skills._sdk.notebook.checks" in _brief_text(project, module)


def test_a_table_nested_too_deeply_does_not_stop_the_brief(project, skills_tree):
    module = _module(project, skills_tree)
    project.step(module, "01b_deep.py", (
        "# %%\nfrom skills._sdk.notebook import write_output\n"
        "write_output('[' * 200000 + ']' * 200000, 'tables/deep.json', "
        "writer=lambda text, path: path.write_text(text))\n"
    ))
    assert project.replay(f"analysis/{module}") == 0, project.text
    text = _brief_text(project, module)
    assert "### tables/deep.json  JSON" in text and "nested too deeply to parse" in text
    assert "### tables/summary.csv" in text


def test_a_brief_that_cannot_be_written_does_not_fail_the_replay(project, skills_tree, monkeypatch):
    module = _module(project, skills_tree)

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(_brief, "write", broken)
    assert project.replay(f"analysis/{module}") == 0
    assert "  warning: could not write the review brief: OSError: disk full" in project.lines
    assert project.manifest(module)["status"] == "replayed"


def test_any_error_while_writing_the_brief_leaves_the_replay_standing(project, skills_tree, monkeypatch):
    module = _module(project, skills_tree)

    def deep(*args, **kwargs):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(_brief, "write", deep)
    assert project.replay(f"analysis/{module}") == 0
    assert any(line.startswith("  warning: could not write the review brief: RecursionError")
               for line in project.lines)
    assert "status: REPLAYED" in project.text
    assert project.manifest(module)["status"] == "replayed"
