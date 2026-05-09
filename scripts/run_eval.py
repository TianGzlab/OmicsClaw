#!/usr/bin/env python3
"""Convenience wrapper: run the behavioral-parity eval suite + emit REPORT.md.

Usage:
    python scripts/run_eval.py                       # full 18-case run
    python scripts/run_eval.py --query "do sc-de"    # single case (substring match against EvalCase.query)
    python scripts/run_eval.py --list-cases          # list IDs without running

Requires ``LLM_API_KEY`` (or ``ANTHROPIC_API_KEY``) in the env. Without
credentials, the underlying pytest invocation will skip every eval
case and exit 0; this script reports that as a clean "skipped" run.

Exit codes:
    0  – every must-priority case passed (should-failures recorded as warnings)
    1  – at least one must-priority case failed
    2  – pytest-level error (config / import problem)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "tests" / "eval" / "results"

# Allow ``from tests.eval.invariants import ...`` when this script is
# invoked as ``python scripts/run_eval.py`` from the repo root.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _run_pytest(query_filter: str, run_timestamp: str) -> int:
    """Invoke pytest -m eval; return its exit code."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "eval",
        "tests/eval/",
        "-W",
        "default::UserWarning",  # keep should-warnings visible in stdout
    ]
    if query_filter:
        cmd.extend(["-k", query_filter])

    env = dict(os.environ)
    env["EVAL_RUN_TIMESTAMP"] = run_timestamp

    return subprocess.call(cmd, cwd=str(REPO_ROOT), env=env)


def _aggregate_results(run_dir: Path) -> tuple[list[dict], dict[str, int]]:
    """Load every per-case JSON and compute summary counts."""
    cases: list[dict] = []
    counts = {"total": 0, "passed": 0, "failed_must": 0, "failed_should": 0, "skipped": 0}
    if not run_dir.is_dir():
        return cases, counts

    for path in sorted(run_dir.glob("*.json")):
        if path.name == "REPORT.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            cases.append({"case": {"id": path.stem}, "load_error": str(exc)})
            continue
        cases.append(payload)
        counts["total"] += 1
        if payload.get("passed_overall"):
            counts["passed"] += 1
        else:
            priority = payload.get("case", {}).get("priority", "must")
            if priority == "must":
                counts["failed_must"] += 1
            else:
                counts["failed_should"] += 1
    return cases, counts


def _write_report(run_dir: Path, cases: list[dict], counts: dict[str, int], model: str) -> Path:
    lines = [
        "# Behavioral Parity Eval Report",
        "",
        f"- Run: `{run_dir.name}`",
        f"- Model: `{model}`",
        f"- Cases: total={counts['total']}, passed={counts['passed']}, "
        f"failed_must={counts['failed_must']}, failed_should={counts['failed_should']}",
        "",
        "## Per-case status",
        "",
        "| Status | Priority | Category | ID | Failures |",
        "|---|---|---|---|---|",
    ]
    for payload in cases:
        case = payload.get("case", {})
        case_id = case.get("id", "?")
        if "load_error" in payload:
            lines.append(f"| ERROR | ? | ? | `{case_id}` | load_error: {payload['load_error']} |")
            continue
        priority = case.get("priority", "?")
        category = case.get("category", "?")
        passed = payload.get("passed_overall", False)
        if passed:
            status = "✅ pass"
            failures = ""
        else:
            status = "❌ fail" if priority == "must" else "⚠️ warn"
            failure_lines = [
                f"`{o['name']}`: {'; '.join(o['reasons'])[:120]}"
                for o in payload.get("invariant_outcomes", [])
                if not o.get("passed")
            ]
            failures = "<br>".join(failure_lines)
        lines.append(f"| {status} | {priority} | {category} | `{case_id}` | {failures} |")

    lines.extend(["", "## Per-category summary", ""])
    by_category: dict[str, dict[str, int]] = {}
    for payload in cases:
        category = payload.get("case", {}).get("category", "?")
        bucket = by_category.setdefault(category, {"total": 0, "passed": 0})
        bucket["total"] += 1
        if payload.get("passed_overall"):
            bucket["passed"] += 1

    if by_category:
        lines.extend(["| Category | Passed / Total |", "|---|---|"])
        for cat in sorted(by_category):
            b = by_category[cat]
            lines.append(f"| {cat} | {b['passed']} / {b['total']} |")

    report_path = run_dir / "REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="", help="Substring to match against case.id (uses pytest -k).")
    parser.add_argument("--list-cases", action="store_true", help="List the corpus IDs without running pytest.")
    args = parser.parse_args()

    if args.list_cases:
        from tests.eval.invariants import EVAL_CASES

        for case in EVAL_CASES:
            print(f"  [{case.priority:6s}] {case.category:12s}  {case.id}")
        return 0

    run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    rc = _run_pytest(args.query, run_timestamp)
    if rc not in (0, 1):
        # 0 = all passed, 1 = some failed; anything else is an actual pytest error
        print(f"pytest exited with code {rc}; eval setup may be broken", file=sys.stderr)
        return 2

    run_dir = RESULTS_DIR / run_timestamp
    cases, counts = _aggregate_results(run_dir)

    if not cases:
        print(f"No artifacts written to {run_dir} — did the eval skip due to missing API key?")
        return rc

    model = (cases[0].get("model") if cases else "") or os.getenv("EVAL_MODEL", "claude-sonnet-4-6")
    report_path = _write_report(run_dir, cases, counts, model)

    print()
    print(f"=== Eval summary ({run_timestamp}) ===")
    print(
        f"  total={counts['total']} passed={counts['passed']} "
        f"failed_must={counts['failed_must']} failed_should={counts['failed_should']}"
    )
    print(f"  artifacts: {run_dir}")
    print(f"  report:    {report_path}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
