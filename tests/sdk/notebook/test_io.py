"""``read_input``, ``write_output`` and ``load_demo`` as a running step sees them."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from skills._sdk.notebook import _hashing, _io, _ledger, load_demo, read_input, write_output


@pytest.fixture
def step(tmp_path, monkeypatch):
    """The environment the runner gives step ``01_x.py`` of module ``02_mod``; returns the ledger path."""
    root = tmp_path / "proj"
    (root / "analysis" / "02_mod").mkdir(parents=True)
    (root / "results" / "02_mod").mkdir(parents=True)
    (root / "data").mkdir()
    step_file = root / "analysis" / "02_mod" / "01_x.py"
    step_file.write_text("")
    ledger = root / "results" / "02_mod" / "provenance" / "runs" / "01_x" / "r.jsonl"
    monkeypatch.setenv("OMICSCLAW_STEP_FILE", str(step_file))
    monkeypatch.setenv("OMICSCLAW_STEP_LEDGER", str(ledger))
    monkeypatch.chdir(tmp_path)
    return root, ledger


def _events(ledger, kind):
    return [e for e in _ledger.read_events(ledger) if e["event"] == kind]


def test_read_input_dispatches_by_suffix(step):
    root, _ = step
    (root / "data" / "a.json").write_text('{"x": 1}')
    (root / "data" / "b.txt").write_text("hello")
    (root / "data" / "c.csv").write_text("g,v\na,1\n")
    (root / "data" / "d.tsv").write_text("g\tv\na\t1\n")
    (root / "data" / "e.bin").write_bytes(b"\0")
    assert read_input("data/a.json") == {"x": 1}
    assert read_input("data/b.txt") == "hello"
    assert list(read_input("data/c.csv").columns) == ["g", "v"]
    assert list(read_input("data/d.tsv").columns) == ["g", "v"]
    assert read_input("data/e.bin") == root / "data" / "e.bin"


def test_read_input_is_relative_to_the_project_root_not_the_cwd(step):
    root, ledger = step
    (root / "data" / "a.json").write_text("[1]")
    assert Path.cwd() != root
    assert read_input("data/a.json") == [1]
    event = _events(ledger, "input")[0]
    assert event["path"] == "data/a.json"
    assert event["sha256"] == _hashing.sha256_file(root / "data" / "a.json")
    assert event["via"] == "read_input" and event["outside_contract"] is False


def test_read_input_uses_a_given_reader(step):
    root, _ = step
    (root / "data" / "a.json").write_text("[1]")
    assert read_input("data/a.json", reader=lambda p: p.name) == "a.json"


def test_a_directory_input_hashes_its_files(step):
    root, ledger = step
    folder = root / "data" / "mtx"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.txt").write_text("a")
    (folder / "sub" / "b.txt").write_text("b")
    assert read_input("data/mtx") == folder
    first = _events(ledger, "input")[-1]["sha256"]
    (folder / "sub" / "b.txt").write_text("B")
    assert _hashing.sha256_path(folder) != first


def test_reading_outside_the_contract_warns_and_is_recorded(step, capsys):
    root, ledger = step
    (root / "results" / "01_up" / "figures").mkdir(parents=True)
    (root / "results" / "01_up" / "figures" / "f.txt").write_text("x")
    (root / "results" / "01_up" / "tables").mkdir(parents=True)
    (root / "results" / "01_up" / "tables" / "t.txt").write_text("x")
    (root / "loose.txt").write_text("x")
    read_input("results/01_up/tables/t.txt")
    read_input("results/01_up/figures/f.txt")
    read_input("loose.txt")
    flags = [e["outside_contract"] for e in _events(ledger, "input")]
    assert flags == [False, True, True]
    assert capsys.readouterr().err.count("outside what a step reads") == 2


def test_write_output_writes_into_the_module_results_and_records_it(step):
    root, ledger = step
    target = write_output({"a": 1}, "tables/x.json")
    assert target == root / "results" / "02_mod" / "tables" / "x.json"
    assert json.loads(target.read_text()) == {"a": 1}
    event = _events(ledger, "output")[0]
    assert event["path"] == "tables/x.json" and event["kind"] == "tables"
    assert event["sha256"] == _hashing.sha256_file(target)
    assert [p.name for p in target.parent.iterdir()] == ["x.json"]


def test_write_output_dispatches_by_type_and_suffix(step):
    import pandas as pd

    root, _ = step
    frame = pd.DataFrame({"g": ["a", "b"], "v": [1, 2]})
    assert write_output(frame, "tables/t.csv").read_text().splitlines()[0] == "g,v"
    indexed = frame.set_index("g")
    assert write_output(indexed, "tables/i.tsv").read_text().splitlines()[0] == "g\tv"
    assert write_output("# Notes\n", "logs/n.md").read_text() == "# Notes\n"
    with pytest.raises(ValueError, match="writer="):
        write_output(object(), "tables/o.csv")


def test_write_output_saves_figures(step):
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.plot([1, 2])
    path = write_output(fig, "figures/line.png")
    assert path.read_bytes()[:4] == b"\x89PNG"


def test_write_output_takes_a_writer(step):
    path = write_output([1, 2], "intermediate/raw.bin", writer=lambda obj, p: p.write_bytes(bytes(obj)))
    assert path.read_bytes() == b"\x01\x02"


@pytest.mark.parametrize("bad", ["provenance/manifest.json", "notebooks/x.ipynb", "../01_up/tables/x.json",
                                 "/tmp/x.json", "x.json", "reviews/r.md"])
def test_write_output_refuses_paths_outside_the_output_folders(step, bad):
    with pytest.raises(ValueError):
        write_output({}, bad)


def test_a_failed_writer_leaves_no_partial_file(step):
    root, _ = step

    def broken(obj, path):
        path.write_text("half")
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError):
        write_output({}, "tables/x.json", writer=broken)
    assert list((root / "results" / "02_mod" / "tables").iterdir()) == []


def test_write_output_refuses_a_frozen_module(step):
    root, _ = step
    manifest = root / "results" / "02_mod" / "provenance" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"frozen": True}))
    with pytest.raises(RuntimeError, match="revise"):
        write_output({}, "tables/x.json")


def test_run_on_its_own_the_step_is_taken_from_argv_and_nothing_is_recorded(tmp_path, monkeypatch, capsys):
    root = tmp_path / "proj"
    step_file = root / "analysis" / "01_m" / "01_s.py"
    step_file.parent.mkdir(parents=True)
    step_file.write_text("")
    monkeypatch.delenv("OMICSCLAW_STEP_FILE", raising=False)
    monkeypatch.delenv("OMICSCLAW_STEP_LEDGER", raising=False)
    monkeypatch.setattr("sys.argv", ["analysis/01_m/01_s.py"])
    monkeypatch.chdir(root)
    monkeypatch.setattr(_ledger, "_NOTICE_SHOWN", False)
    path = write_output({"a": 1}, "tables/x.json")
    assert path == root / "results" / "01_m" / "tables" / "x.json"
    assert "not running under the step runner" in capsys.readouterr().err
    assert not (root / "results" / "01_m" / "provenance").exists()


def test_write_output_outside_a_step_explains_itself(tmp_path, monkeypatch):
    monkeypatch.delenv("OMICSCLAW_STEP_FILE", raising=False)
    monkeypatch.setattr("sys.argv", ["ipykernel_launcher.py"])
    with pytest.raises(RuntimeError, match="analysis/<NN_slug>"):
        write_output({}, "tables/x.json")


def test_load_demo_looks_in_the_demo_dir_first_and_records_the_input(step, tmp_path, monkeypatch):
    anndata = pytest.importorskip("anndata")
    import numpy as np

    root, ledger = step
    demo = tmp_path / "demo"
    demo.mkdir()
    anndata.AnnData(np.ones((3, 2), dtype="float32")).write_h5ad(demo / "pbmc3k_raw.h5ad")
    monkeypatch.setenv("OMICSCLAW_DEMO_DIR", str(demo))
    adata = load_demo("pbmc3k_raw")
    assert adata.shape == (3, 2)
    event = _events(ledger, "input")[0]
    assert event["path"] == str(demo / "pbmc3k_raw.h5ad")
    assert event["via"] == "load_demo" and event["outside_contract"] is False


def test_load_demo_lists_where_it_looked_when_it_cannot_download(step, tmp_path, monkeypatch):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path / "nowhere")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("OMICSCLAW_DEMO_DIR", str(tmp_path / "demo"))

    def offline(name):
        raise OSError("network is unreachable")

    monkeypatch.setattr(_io, "_download_demo", offline)
    with pytest.raises(RuntimeError) as caught:
        load_demo("pbmc3k_processed")
    message = str(caught.value)
    assert str(tmp_path / "demo" / "pbmc3k_processed.h5ad") in message
    assert str(tmp_path / "cache" / "omicsclaw" / "demo" / "pbmc3k_processed.h5ad") in message
    assert "OMICSCLAW_DEMO_DIR" in message


def test_load_demo_rejects_an_unknown_name():
    with pytest.raises(LookupError, match="pbmc3k_raw"):
        load_demo("pbmc4k")


def test_generated_demo_is_cached_and_recorded_as_a_file(step, tmp_path, monkeypatch):
    anndata = pytest.importorskip("anndata")
    import numpy as np

    from skills._sdk.notebook import _demos

    def generate():
        return anndata.AnnData(np.random.default_rng(0).poisson(2, (4, 3)).astype("float32"))

    monkeypatch.setitem(_io.DEMOS, "test_generated", {
        "files": [], "generator": "test_generated", "about": "A temporary test dataset",
    })
    monkeypatch.setattr(_demos, "test_generated", generate, raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv("OMICSCLAW_DEMO_DIR", raising=False)
    _, ledger = step
    first = load_demo("test_generated")
    path = tmp_path / "cache" / "omicsclaw" / "demo" / "test_generated.h5ad"
    event = _events(ledger, "input")[-1]
    assert event["path"] == str(path)
    assert event["sha256"] == _hashing.sha256_file(path)
    assert event["via"] == "load_demo" and not event["outside_contract"]
    np.testing.assert_array_equal(anndata.read_h5ad(path).X, first.X)
    np.testing.assert_array_equal(first.X, generate().X)

    def unavailable():
        raise AssertionError("a cached dataset must not be generated again")

    monkeypatch.setattr(_demos, "test_generated", unavailable)
    second = load_demo("test_generated")
    np.testing.assert_array_equal(first.X, second.X)
    assert _events(ledger, "input")[-1]["sha256"] == event["sha256"]


def test_read_input_of_a_missing_file(step):
    with pytest.raises(FileNotFoundError):
        read_input("data/missing.csv")
    assert os.environ["OMICSCLAW_STEP_LEDGER"]


def test_spatial_demo_has_seeded_counts_and_spatial_domains(step, tmp_path, monkeypatch):
    pytest.importorskip("anndata")
    import numpy as np

    monkeypatch.setenv("OMICSCLAW_DEMO_DIR", str(tmp_path / "demos"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    first = load_demo("spatial_synthetic")
    second = load_demo("spatial_synthetic")
    assert first.shape == (180, 300)
    assert first.obsm["spatial"].shape == (180, 2)
    np.testing.assert_array_equal(first.X, second.X)
    assert np.all(first.X >= 0) and np.all(first.X == np.floor(first.X))
    for group in range(3):
        chosen = first.obs["domain_ground_truth"] == f"domain_{group}"
        block = slice(group * 30, (group + 1) * 30)
        assert first.X[chosen, block].mean() > 3 * first.X[~chosen, block].mean()
    events = _events(step[1], "input")
    assert events[-1]["sha256"] == events[-2]["sha256"]
