from __future__ import annotations

import json
from pathlib import Path

from omicsclaw.execution.autonomous_analysis import run_autonomous_analysis


class _SuccessfulNotebookSession:
    def __init__(self, notebook_path: str):
        self.notebook_path = Path(notebook_path)
        self.notebook_path.parent.mkdir(parents=True, exist_ok=True)
        self.notebook_path.write_text(
            json.dumps(
                {
                    "cells": [],
                    "metadata": {},
                    "nbformat": 4,
                    "nbformat_minor": 5,
                }
            ),
            encoding="utf-8",
        )
        self.calls = 0

    def insert_cell(self, *_args, **_kwargs):
        return None

    def insert_execute_code_cell(self, *_args, **_kwargs):
        self.calls += 1
        return {"ok": True, "output_preview": "done", "error": ""}

    def shutdown(self):
        return None


class _FailingNotebookSession(_SuccessfulNotebookSession):
    def insert_execute_code_cell(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return {"ok": True, "output_preview": "ready", "error": ""}
        return {"ok": False, "output_preview": "partial", "error": "boom"}


def test_run_autonomous_analysis_writes_manifest_and_completion_report(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "omicsclaw.execution.autonomous_analysis.NotebookSession",
        _SuccessfulNotebookSession,
    )

    result = run_autonomous_analysis(
        output_root=str(tmp_path),
        goal="summarize markers",
        analysis_plan="1. run analysis",
        python_code="print('ok')",
    )

    assert result["ok"] is True
    output_dir = Path(str(result["output_dir"]))
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "completion_report.json").exists()
    assert result["completion"]["completed"] is True
    assert result["completion"]["status"] == "complete"


def test_run_autonomous_analysis_failure_still_emits_completion_report(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "omicsclaw.execution.autonomous_analysis.NotebookSession",
        _FailingNotebookSession,
    )

    result = run_autonomous_analysis(
        output_root=str(tmp_path),
        goal="fail gracefully",
        analysis_plan="1. run analysis",
        python_code="print('ok')",
    )

    assert result["ok"] is False
    output_dir = Path(str(result["output_dir"]))
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "completion_report.json").exists()
    assert result["completion"]["completed"] is False
    assert result["completion"]["status"] == "failed"
