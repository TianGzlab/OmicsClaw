"""Parity recording and comparison on small local outputs."""

from __future__ import annotations

import json

from tests.parity import snapshot
import pytest
import signal


def test_exclusions_remove_only_named_columns_and_files(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    for folder, score in ((left, 1), (right, 2)):
        (folder / "tables").mkdir(parents=True)
        (folder / "tables" / "scores.csv").write_text(f"gene,score,count\nA,{score},5\n")
    (left / "tables" / "old.csv").write_text("old\n1\n")
    exclude = {
        "tables/scores.csv:score": "The method now returns corrected scores.",
        "tables/old.csv": "The obsolete placeholder output was removed.",
    }
    assert snapshot.compare(left, right)
    assert snapshot.compare(left, right, exclude=exclude) == []
    (right / "tables" / "scores.csv").write_text("gene,score,count\nA,2,6\n")
    assert snapshot.compare(left, right, exclude=exclude)


def test_structural_comparison_keeps_rows_columns_and_label_sets(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    for folder, score, labels in ((left, 1, ["A", "B"]), (right, 2, ["B", "A"])):
        (folder / "tables").mkdir(parents=True)
        (folder / "tables" / "scores.csv").write_text(f"gene,score\nA,{score}\nB,3\n")
        (folder / "obs_labels").mkdir()
        (folder / "obs_labels" / "cluster.csv").write_text(
            f"obs_name,label\nc1,{labels[0]}\nc2,{labels[1]}\n"
        )
    assert snapshot.compare(left, right)
    assert snapshot.compare(left, right, structure_only=True) == []
    (right / "obs_labels" / "cluster.csv").write_text("obs_name,label\nc1,A\nc2,C\n")
    assert snapshot.compare(left, right, structure_only=True)
    (right / "tables" / "scores.csv").write_text("gene,score\nA,2\n")
    assert any("shape" in message for message in snapshot.compare(left, right, structure_only=True))


def test_exclusions_require_reasons(tmp_path):
    with pytest.raises(ValueError, match="reason"):
        snapshot.compare(tmp_path, tmp_path, exclude={"tables/x.csv": ""})


def test_exclusions_cover_one_summary_field_and_one_figure(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "summary.json").write_text('{"method": "old", "cells": 2}')
    (right / "summary.json").write_text('{"method": "new", "cells": 2}')
    (left / "figures.json").write_text('["obsolete.png", "kept.png"]')
    (right / "figures.json").write_text('["kept.png"]')
    exclude = {"summary.json:method": "The default method changed.",
               "figures/obsolete.png": "The misleading plot was removed."}
    assert snapshot.compare(left, right, exclude=exclude) == []
    (right / "summary.json").write_text('{"method": "new", "cells": 3}')
    assert snapshot.compare(left, right, exclude=exclude)


def test_summary_integers_are_exact():
    assert snapshot.compare_values({"count": 10_000_000}, {"count": 10_000_001}, "summary")


def test_api_parity_cannot_pass_without_comparable_outputs(tmp_path, monkeypatch):
    from tests.parity.test_sc_parity import compare_api

    monkeypatch.setattr(snapshot, "GOLDEN", tmp_path / "golden")
    output = tmp_path / "empty"
    output.mkdir()
    assert compare_api("sc-filter", "default", output)


def test_api_parity_rejects_unrecorded_label_files(tmp_path, monkeypatch):
    from tests.parity.test_sc_parity import compare_api

    monkeypatch.setattr(snapshot, "GOLDEN", tmp_path / "golden")
    output = tmp_path / "api"
    (output / "obs_labels").mkdir(parents=True)
    (output / "obs_labels/unrecorded.csv").write_text("obs_name,label\nc1,A\n")
    assert any("unrecorded.csv" in problem for problem in compare_api("sc-filter", "default", output))


def test_registered_input_is_shared_by_both_recordings(tmp_path, monkeypatch):
    def generate(path):
        path.write_text("fixed input")

    script = tmp_path / "cli.py"
    script.write_text(
        "import argparse,json,os\nfrom pathlib import Path\n"
        "p=argparse.ArgumentParser();p.add_argument('--input');p.add_argument('--output');a=p.parse_args()\n"
        "out=Path(a.output);out.mkdir(parents=True);(out/'tables').mkdir()\n"
        "(out/'tables'/'x.csv').write_text('value\\n'+str(os.getpid())+'\\n')\n"
        "(out/'result.json').write_text(json.dumps({'summary': {'input':Path(a.input).read_text()}}))\n"
    )
    monkeypatch.setitem(snapshot.REGISTRY, "test-skill", snapshot.Skill(
        script=str(script), api_runner=None, cases={"default": snapshot.Case(args=(), input=generate)},
    ))
    monkeypatch.setattr(snapshot, "GOLDEN", tmp_path / "golden")
    target = snapshot.record("test-skill", "default")
    meta = json.loads((target / "meta.json").read_text())
    assert meta["deterministic"] is False
    assert meta["repeat_differences"] and meta["uncertainty_reason"]
    assert (target / "input.h5ad").read_text() == "fixed input"
    assert len(meta["input_sha256"]) == 64
    assert meta["runs"] == 2
    output = tmp_path / "later"
    assert snapshot.run_cli("test-skill", "default", output).returncode == 0
    assert snapshot.compare_output("test-skill", "default", output) == []


@pytest.mark.parametrize("skill,allowed", [("sc-velocity", True), ("test-skill", False)])
def test_sigkill_is_accepted_only_for_registered_velocity_recordings(tmp_path, monkeypatch, skill, allowed):
    import anndata
    import numpy as np

    script = tmp_path / "killed.py"
    script.write_text("import os,signal\nos.killpg(os.getpgid(0), signal.SIGKILL)\n")
    monkeypatch.setitem(snapshot.REGISTRY, skill, snapshot.Skill(
        script=str(script), api_runner=None, cases={"default": snapshot.Case(())}, legacy_sigkill=True,
    ))
    output = tmp_path / "out"
    output.mkdir()
    result = {
        "skill": skill, "version": "1", "completed_at": "2026-10-07T00:00:00Z",
        "input_checksum": "", "summary": {"n_cells": 2, "n_genes": 2},
        "data": {"output_h5ad": "processed.h5ad", "output_files": {
            "processed_h5ad": str(output / "processed.h5ad"),
            "compatibility_aliases": [str(output / "adata_with_velocity.h5ad")],
        }},
    }
    (output / "result.json").write_text(json.dumps(result))
    anndata.AnnData(np.ones((2, 2))).write_h5ad(output / "processed.h5ad")
    proc = snapshot.run_cli(skill, "default", output)
    assert proc.returncode == -signal.SIGKILL
    assert snapshot.recording_succeeded(skill, proc, output) is False
    (output / "tables").mkdir()
    (output / "tables" / "velocity_cells.csv").write_text("cell,confidence\na,0.9\nb,0.8\n")
    (output / "tables" / "top_velocity_genes.csv").write_text("gene,score\ng1,0.8\n")
    (output / "tables" / "velocity_summary.csv").write_text("metric,value\nn_cells,2\n")
    (output / "report.md").write_text("Velocity report\n")
    (output / "figures").mkdir()
    (output / "figures" / "manifest.json").write_text('{"plots": []}')
    (output / "adata_with_velocity.h5ad").write_bytes((output / "processed.h5ad").read_bytes())
    assert snapshot.recording_succeeded(skill, proc, output) is allowed
    if allowed:
        (output / "tables" / "velocity_cells.csv").write_text("cell,confidence\na,0.9\n")
        assert snapshot.recording_succeeded(skill, proc, output) is False
        (output / "tables" / "velocity_cells.csv").write_text("cell,confidence\na,0.9\nb,0.8\n")
    result["status"] = "failed"
    (output / "result.json").write_text(json.dumps(result))
    assert snapshot.recording_succeeded(skill, proc, output) is False
