"""The ledger and ``selection.json``, the interface consensus reads.

The ledger is append-only and flushed per event so an interrupted run can be
audited up to its last decision. ``selection.json`` is checked on write and on
read: consensus builds on it, and a selection naming a label table that is
not there must fail where it is read, not three steps later.
"""

from __future__ import annotations

import json

import pytest

from omicsclaw.ensemble.tuning.ledger import (
    Ledger,
    Selection,
    SelectionError,
    load_selection,
)


def test_events_are_numbered_and_typed(tmp_path):
    ledger = Ledger(tmp_path / "tuning")
    first = ledger.append("start", arm="det")
    second = ledger.append("k_decision", chosen_k=7)
    assert (first["seq"], second["seq"]) == (1, 2)
    assert [e["kind"] for e in ledger.events()] == ["start", "k_decision"]
    with pytest.raises(ValueError):
        ledger.append("whatever")
    again = Ledger(tmp_path / "tuning")
    assert again.append("end")["seq"] == 3


def test_model_calls_are_kept_in_full_and_numbered(tmp_path):
    ledger = Ledger(tmp_path / "tuning")
    assert ledger.record_llm({"prompt": "p"}) == "llm/0001.json"
    assert ledger.record_llm({"prompt": "q"}) == "llm/0002.json"
    assert json.loads((tmp_path / "tuning" / "llm" / "0002.json").read_text())["prompt"] == "q"


def _selection(tmp_path, **overrides):
    labels = tmp_path / "labels.csv.gz"
    labels.write_bytes(b"x")
    values = dict(
        status="ok", arm="det", skill="spatial-domains", input="in.h5ad", input_sha256="0" * 64,
        panel_version="spatial_domains/3",
        k={"chosen": 7, "grid": [3, 16], "stable_peaks": [4, 6], "source": "llm"},
        methods={
            "spagcn": {"status": "ok", "run_id": "r", "trial": "t0002", "params": {"n_domains": 7},
                       "fixed_k_score": 0.4, "se": 0.02, "n_labels": 7, "labels": str(labels), "h5ad": None},
            "graphst": {"status": "failed"},
        },
        final={"method": "spagcn", "run_id": "r", "trial": "t0002"},
    )
    values.update(overrides)
    return Selection(**values)


def test_a_selection_round_trips(tmp_path):
    path = _selection(tmp_path).write(tmp_path / "selection.json")
    loaded = load_selection(path)
    assert loaded.k["chosen"] == 7 and loaded.final["method"] == "spagcn"
    assert loaded.member_labels("spagcn").is_file()
    assert json.loads(path.read_text())["schema"] == "omicsclaw.ensemble.selection/1"


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"status": "great"}, "status"),
        ({"arm": "x"}, "arm"),
        ({"k": {"chosen": 7, "source": "oracle"}}, "k.source"),
        ({"final": {"method": "leiden", "run_id": "r", "trial": "t1"}}, "final names"),
        ({"final": None}, "must have a final"),
    ],
)
def test_a_bad_selection_is_refused_on_write(tmp_path, overrides, fragment):
    with pytest.raises(SelectionError, match=fragment):
        _selection(tmp_path, **overrides).write(tmp_path / "selection.json")


def test_a_selection_naming_missing_labels_is_refused_on_read(tmp_path):
    path = _selection(tmp_path).write(tmp_path / "selection.json")
    (tmp_path / "labels.csv.gz").unlink()
    with pytest.raises(SelectionError, match="does not exist"):
        load_selection(path)
