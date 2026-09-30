"""Suite reports: stable JSON and Markdown, per-category totals, the summary command."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from omicsclaw.evals import Failure, build_report, step_summary, write_json, write_markdown
from omicsclaw.evals.report import NO_REPORT, load_report, main

from ._support import make_case, make_result

_AT = datetime(2026, 9, 30, tzinfo=timezone.utc)


def _results():
    return [
        make_result(case=make_case("safety/b"), passed=True),
        make_result(
            case=make_case("memory/a"),
            passed=False,
            failures=(Failure("NoError", "exchange failed"),),
            warnings=(Failure("MaxTurns(1)", "2 model calls", is_soft=True),),
        ),
        make_result(case=make_case("safety/a"), passed=True, tool_calls_executed=("bash",)),
    ]


def test_totals_and_categories():
    report = build_report(_results(), run_at=_AT)
    assert (report.total, report.passed, report.failed) == (3, 2, 1)
    assert list(report.categories) == ["memory", "safety"]
    assert report.categories["memory"].pass_rate == 0.0
    assert report.categories["memory"].warnings == 1
    assert report.categories["safety"].pass_rate == 1.0
    assert [r.id for r in report.results] == ["memory/a", "safety/a", "safety/b"]


def test_json_and_markdown_are_byte_stable(tmp_path):
    first, second = tmp_path / "1", tmp_path / "2"
    for directory, order in ((first, _results()), (second, list(reversed(_results())))):
        report = build_report(order, run_at=_AT)
        write_json(report, directory / "report.json")
        write_markdown(report, directory / "report.md")
    assert (first / "report.json").read_bytes() == (second / "report.json").read_bytes()
    assert (first / "report.md").read_bytes() == (second / "report.md").read_bytes()
    markdown = (first / "report.md").read_text()
    assert "FAIL `memory/a`" in markdown and "PASS `safety/a`" in markdown
    assert json.loads((first / "report.json").read_text())["failed"] == 1


def test_a_written_report_reads_back(tmp_path):
    report = build_report(_results(), run_at=_AT)
    write_json(report, tmp_path / "report.json")
    assert load_report(tmp_path / "report.json") == report


def test_the_step_summary_has_the_table_and_each_failure_and_warning():
    summary = step_summary(build_report(_results(), run_at=_AT))
    assert "| memory | 1 | 0 | 0.0% | 1 |" in summary
    assert "| safety | 2 | 2 | 100.0% | 0 |" in summary
    assert "- `memory/a`: NoError: exchange failed" in summary
    assert "- `memory/a`: MaxTurns(1): 2 model calls" in summary
    assert summary.startswith("## Scripted agent evals")


def test_the_summary_command_prints_the_summary(tmp_path, capsys):
    report = build_report(_results(), run_at=_AT)
    write_json(report, tmp_path / "report.json")
    assert main(["summary", str(tmp_path / "report.json")]) == 0
    assert capsys.readouterr().out == step_summary(report)


def test_the_summary_command_exits_zero_without_a_report(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-m", "omicsclaw.evals.report", "summary", str(tmp_path / "missing.json")],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == NO_REPORT
