"""Tests for omicsclaw.autoagent.failure_memory."""

from __future__ import annotations

import json

import pytest

from omicsclaw.autoagent.failure_memory import FailureBank, FailureRecord


class TestFailureRecord:
    def test_construction(self):
        rec = FailureRecord(
            iteration=1,
            reasoning="Tried MAD filtering",
            diff_summary="1 file(s), 2 hunk(s)",
            gate_failures=["cell_retention"],
            error_summary="Retention dropped to 1%",
        )
        assert rec.iteration == 1
        assert rec.timestamp  # auto-populated

    def test_roundtrip(self):
        rec = FailureRecord(
            iteration=3,
            reasoning="test",
            target_files=["a.py"],
        )
        d = rec.to_dict()
        loaded = FailureRecord.from_dict(d)
        assert loaded.iteration == 3
        assert loaded.reasoning == "test"
        assert loaded.target_files == ["a.py"]


class TestFailureBank:
    def test_append_and_read(self, tmp_path):
        bank = FailureBank(tmp_path / "failures.jsonl")
        assert len(bank) == 0

        bank.append(FailureRecord(iteration=0, reasoning="first"))
        bank.append(FailureRecord(iteration=1, reasoning="second"))
        assert len(bank) == 2

        all_f = bank.all_failures()
        assert len(all_f) == 2
        assert all_f[0].reasoning == "first"
        assert all_f[1].reasoning == "second"

    def test_persistence(self, tmp_path):
        path = tmp_path / "failures.jsonl"
        bank1 = FailureBank(path)
        bank1.append(FailureRecord(iteration=0, reasoning="persisted"))

        # New instance loads from disk
        bank2 = FailureBank(path)
        assert len(bank2) == 1
        assert bank2.all_failures()[0].reasoning == "persisted"

    def test_recent(self, tmp_path):
        bank = FailureBank(tmp_path / "f.jsonl")
        for i in range(10):
            bank.append(FailureRecord(iteration=i, reasoning=f"fail-{i}"))

        recent = bank.recent(3)
        assert len(recent) == 3
        assert recent[0].reasoning == "fail-7"
        assert recent[2].reasoning == "fail-9"

    def test_to_directive_context(self, tmp_path):
        bank = FailureBank(tmp_path / "f.jsonl")
        bank.append(FailureRecord(
            iteration=0,
            reasoning="Tried X",
            diff_summary="1 file(s)",
            gate_failures=["no_crash"],
            error_summary="ValueError",
        ))

        ctx = bank.to_directive_context()
        assert len(ctx) == 1
        assert ctx[0]["reasoning"] == "Tried X"
        assert ctx[0]["gate_failures"] == ["no_crash"]
        assert ctx[0]["error_summary"] == "ValueError"
        assert ctx[0]["diff_summary"] == "1 file(s)"

    def test_corrupted_line_skipped(self, tmp_path):
        path = tmp_path / "f.jsonl"
        path.write_text(
            json.dumps({"iteration": 0, "reasoning": "good"}) + "\n"
            "this is not json\n"
            + json.dumps({"iteration": 1, "reasoning": "also good"}) + "\n"
        )
        bank = FailureBank(path)
        assert len(bank) == 2

    def test_empty_file(self, tmp_path):
        path = tmp_path / "f.jsonl"
        path.write_text("")
        bank = FailureBank(path)
        assert len(bank) == 0
