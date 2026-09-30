"""Suite reports: JSON for machines, Markdown for people, a CI step summary.

``python -m omicsclaw.evals.report summary <report.json>`` prints the
step summary of a saved report. When the file does not exist it prints
one line saying so and exits 0, leaving the failure to be reported by
the step that should have produced it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .case import Result

__all__ = [
    "CategoryStats",
    "NO_REPORT",
    "ResultSnapshot",
    "SuiteReport",
    "build_report",
    "load_report",
    "main",
    "render_markdown",
    "step_summary",
    "write_json",
    "write_markdown",
]

NO_REPORT = "no eval report was produced; see the pytest step"


@dataclass
class CategoryStats:
    """Totals for one category."""

    total: int = 0
    passed: int = 0
    pass_rate: float = 0.0
    warnings: int = 0


@dataclass
class ResultSnapshot:
    """One case's result, reduced to what a report shows."""

    id: str
    category: str
    passed: bool
    turn_count: int
    tool_calls: list[str]
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class SuiteReport:
    """A whole run: overall totals, per-category totals, every case."""

    run_at: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    categories: dict[str, CategoryStats]
    results: list[ResultSnapshot]

    def to_dict(self) -> dict[str, Any]:
        """The report as JSON-ready data, categories and results sorted."""
        data = asdict(self)
        data["categories"] = {name: data["categories"][name] for name in sorted(data["categories"])}
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SuiteReport:
        """Rebuild a report from :meth:`to_dict` output.

        :raises KeyError: a required field is missing.
        """
        return cls(
            run_at=data["run_at"],
            total=data["total"],
            passed=data["passed"],
            failed=data["failed"],
            pass_rate=data["pass_rate"],
            categories={
                name: CategoryStats(**stats) for name, stats in data["categories"].items()
            },
            results=[ResultSnapshot(**item) for item in data["results"]],
        )


def build_report(results: Iterable[Result], *, run_at: datetime | None = None) -> SuiteReport:
    """Aggregate *results* into a :class:`SuiteReport`.

    Results are sorted by case id, so the same run always produces the
    same report apart from *run_at*.

    :param results: One result per case.
    :param run_at: The timestamp to record. ``None`` is now, in UTC.
    """
    ordered = sorted(results, key=lambda result: result.case.id)
    categories: dict[str, CategoryStats] = {}
    snapshots: list[ResultSnapshot] = []
    for result in ordered:
        stats = categories.setdefault(result.case.category, CategoryStats())
        stats.total += 1
        stats.passed += int(result.passed)
        stats.warnings += len(result.warnings)
        snapshots.append(
            ResultSnapshot(
                id=result.case.id,
                category=result.case.category,
                passed=result.passed,
                turn_count=result.turn_count,
                tool_calls=list(result.tool_calls_executed),
                failures=[str(failure) for failure in result.failures],
                warnings=[str(warning) for warning in result.warnings],
                duration_ms=int(result.duration_s * 1000),
            )
        )
    for stats in categories.values():
        stats.pass_rate = stats.passed / stats.total if stats.total else 0.0
    passed = sum(1 for snapshot in snapshots if snapshot.passed)
    stamp = (run_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    return SuiteReport(
        run_at=stamp,
        total=len(snapshots),
        passed=passed,
        failed=len(snapshots) - passed,
        pass_rate=passed / len(snapshots) if snapshots else 0.0,
        categories={name: categories[name] for name in sorted(categories)},
        results=snapshots,
    )


def write_json(report: SuiteReport, path: Path) -> None:
    """Write *report* as indented JSON to *path*, creating parent directories."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_report(path: Path) -> SuiteReport:
    """Read a report written by :func:`write_json`.

    :raises OSError: the file cannot be read.
    :raises ValueError: the file is not valid JSON.
    :raises KeyError: a required field is missing.
    """
    return SuiteReport.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _percent(rate: float) -> str:
    return f"{rate * 100:.1f}%"


def _category_table(report: SuiteReport) -> list[str]:
    lines = [
        "| Category | Total | Passed | Pass rate | Warnings |",
        "|---|---|---|---|---|",
    ]
    for name in sorted(report.categories):
        stats = report.categories[name]
        lines.append(
            f"| {name} | {stats.total} | {stats.passed} | {_percent(stats.pass_rate)} | {stats.warnings} |"
        )
    return lines


def render_markdown(report: SuiteReport) -> str:
    """The full Markdown report: totals, the category table, every case."""
    lines = [
        f"# Eval report ({report.run_at})",
        "",
        f"{report.total} cases, {report.passed} passed, {report.failed} failed, "
        f"pass rate {_percent(report.pass_rate)}.",
        "",
        "## Categories",
        "",
        *_category_table(report),
        "",
        "## Cases",
        "",
    ]
    for snapshot in report.results:
        status = "PASS" if snapshot.passed else "FAIL"
        lines.append(f"### {status} `{snapshot.id}`")
        lines.append("")
        tools = ", ".join(snapshot.tool_calls) or "none"
        lines.append(
            f"- model calls: {snapshot.turn_count}; tool calls: {tools}; "
            f"duration: {snapshot.duration_ms} ms"
        )
        lines.extend(f"- FAIL {failure}" for failure in snapshot.failures)
        lines.extend(f"- WARN {warning}" for warning in snapshot.warnings)
        lines.append("")
    return "\n".join(lines)


def write_markdown(report: SuiteReport, path: Path) -> None:
    """Write :func:`render_markdown` to *path*, creating parent directories."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")


def step_summary(report: SuiteReport) -> str:
    """A short Markdown summary for ``$GITHUB_STEP_SUMMARY``.

    The category table, then one line per failure and per warning.
    """
    verdict = "PASS" if report.failed == 0 else "FAIL"
    lines = [
        "## Scripted agent evals",
        "",
        f"{verdict}: {report.passed}/{report.total} cases passed ({_percent(report.pass_rate)}).",
        "",
        *_category_table(report),
    ]
    failing = [(s.id, f) for s in report.results for f in s.failures]
    warned = [(s.id, w) for s in report.results for w in s.warnings]
    if failing:
        lines += ["", "### Failures", ""]
        lines += [f"- `{case}`: {text}" for case, text in failing]
    if warned:
        lines += ["", "### Warnings", ""]
        lines += [f"- `{case}`: {text}" for case, text in warned]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """The ``python -m omicsclaw.evals.report`` command line.

    ``summary <report.json>`` prints :func:`step_summary` of the report,
    or :data:`NO_REPORT` when the file does not exist. Returns 0 either
    way.
    """
    parser = argparse.ArgumentParser(prog="python -m omicsclaw.evals.report")
    commands = parser.add_subparsers(dest="command", required=True)
    summary = commands.add_parser("summary", help="print the step summary of a report")
    summary.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    if not args.report.is_file():
        print(NO_REPORT)
        return 0
    sys.stdout.write(step_summary(load_report(args.report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
