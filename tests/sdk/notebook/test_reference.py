"""The step runner's ``reference``."""

from __future__ import annotations

from skills._sdk.notebook import _reference, checks, run
from skills._sdk.notebook import __all__ as STEP_FUNCTIONS
from skills._sdk.notebook._io import DEMOS
from skills._sdk.notebook.contract import LAYOUT

LIMIT = 12000
"""Most characters the whole reference may take: inside what one bash call shows (16,000)."""


def test_the_reference_covers_every_step_function_and_check():
    text = _reference.render()
    for name in [*STEP_FUNCTIONS, *checks.__all__]:
        assert f"\n{name}(" in text, name
    for demo in DEMOS:
        assert demo in text
    for folder in LAYOUT["output_dirs"]:
        assert f"{folder}/" in text


def test_the_reference_fits_in_one_bash_output():
    assert len(_reference.render()) <= LIMIT


def test_one_function_prints_only_its_entry(capsys):
    assert run.main(["reference", "write_output"]) == 0
    text = capsys.readouterr().out
    assert text.startswith("write_output(obj")
    assert "RangeIndex" in text
    assert "read_input(" not in text


def test_load_demo_lists_the_registered_datasets(capsys):
    assert run.main(["reference", "load_demo"]) == 0
    text = capsys.readouterr().out
    for demo, info in DEMOS.items():
        assert f"{demo}: {info['about']}" in text


def test_demo_reference_distinguishes_downloads_and_generators(monkeypatch):
    monkeypatch.setitem(DEMOS, "test_generated", {
        "files": [], "generator": "test_generated", "about": "Temporary test data",
    })
    text = _reference.render("load_demo")
    assert "pbmc3k_raw: " in text and "[download: scanpy.datasets.pbmc3k]" in text
    assert "test_generated: Temporary test data [generator: test_generated]" in text


def test_an_unknown_name_lists_the_known_ones(capsys):
    assert run.main(["reference", "write_outputs"]) == 2
    text = capsys.readouterr().out
    assert "no step function or check named 'write_outputs'" in text
    assert "check_counts" in text


def test_the_whole_reference_prints(capsys):
    assert run.main(["reference"]) == 0
    assert capsys.readouterr().out.strip() == _reference.render()


def test_reference_includes_r_io_from_the_shipped_comments():
    from pathlib import Path

    text = _reference.render()
    assert "R steps" in text and "Rscript analysis/<NN_slug>/<step>.R" in text
    comments = Path(_reference.__file__).with_name("step.R").read_text()
    for line in comments.splitlines():
        if line.startswith("#' "):
            assert line[3:] in text
